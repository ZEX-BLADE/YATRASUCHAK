from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
import asyncio, random

try:
    from backend.database.connection import ACTIVE_TRAINS
    from backend.api.routes.train import DEFAULT_TELEMETRY
    from backend.services.eta_predictor import predict_remaining_minutes
    from backend.services.train_simulator import get_or_create_simulator, REAL_TICK_SECONDS
except ImportError:
    from database.connection import ACTIVE_TRAINS
    from api.routes.train import DEFAULT_TELEMETRY
    from services.eta_predictor import predict_remaining_minutes
    from services.train_simulator import get_or_create_simulator, REAL_TICK_SECONDS

router = APIRouter()


@router.websocket("/ws/telemetry/{train_no}")
async def telemetry_ws(websocket: WebSocket, train_no: str):
    await websocket.accept()

    sim = get_or_create_simulator(train_no)

    try:
        if sim is not None:
            # Live multi-station simulation. The train_simulator's own
            # background loop (started in main.py) advances the sim on a
            # fixed cadence regardless of websocket connections; this loop
            # just streams whatever the current state is.
            while True:
                state = sim.telemetry()
                ACTIVE_TRAINS[train_no] = state
                eta_min, source = predict_remaining_minutes(state)
                await websocket.send_json({**state, "predicted_remaining_time_min": eta_min, "model_source": source})
                if sim.journey_complete:
                    break
                await asyncio.sleep(REAL_TICK_SECONDS)
        else:
            # No route/schedule data for this train number - keep the
            # original lightweight random-walk demo so arbitrary train
            # numbers still stream something.
            state = ACTIVE_TRAINS.setdefault(
                train_no,
                {
                    **DEFAULT_TELEMETRY,
                    "train_no": train_no,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            while True:
                state["speed_kmph"] = round(max(0, state["speed_kmph"] + random.uniform(-4, 4)), 1)
                state["distance_to_station_km"] = round(
                    max(0, state["distance_to_station_km"] - state["speed_kmph"] / 3600 * 2.5), 2
                )
                state["latitude"] = round(state["latitude"] + random.uniform(-0.0012, 0.0012), 6)
                state["longitude"] = round(state["longitude"] + random.uniform(-0.0012, 0.0012), 6)
                state["congestion_index"] = round(min(1, max(0, state["congestion_index"] + random.uniform(-0.03, 0.03))), 2)
                state["timestamp"] = datetime.now(timezone.utc).isoformat()

                eta_min, source = predict_remaining_minutes(state)
                await websocket.send_json({**state, "predicted_remaining_time_min": eta_min, "model_source": source})
                await asyncio.sleep(2.5)
    except WebSocketDisconnect:
        return
