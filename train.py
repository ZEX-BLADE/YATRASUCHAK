from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import json

try:
    from backend.models.train import TrainStartRequest
    from backend.database.connection import ACTIVE_TRAINS
    from backend.database.repository import upsert_train, log_telemetry
    from backend.services.eta_predictor import predict_remaining_minutes, arrival_iso
    from backend.services.delay_classifier import classify_delay
    from backend.services.train_simulator import get_or_create_simulator, reset_simulator
    from backend.utils.config import ROUTE_PATH, SCHEDULE_PATH
except ImportError:
    from models.train import TrainStartRequest
    from database.connection import ACTIVE_TRAINS
    from database.repository import upsert_train, log_telemetry
    from services.eta_predictor import predict_remaining_minutes, arrival_iso
    from services.delay_classifier import classify_delay
    from services.train_simulator import get_or_create_simulator, reset_simulator
    from utils.config import ROUTE_PATH, SCHEDULE_PATH

router = APIRouter(prefix="/api/train", tags=["train"])

# Fallback telemetry for train numbers that have no route/schedule data on
# disk (only demo train 12301 ships with both). These trains keep the
# original static-ish behaviour rather than erroring out.
DEFAULT_TELEMETRY = {
    "latitude": 22.5726,
    "longitude": 88.3639,
    "speed_kmph": 92,
    "current_delay_min": 8,
    "distance_to_station_km": 38,
    "historical_travel_time_min": 31,
    "previous_delay_min": 6,
    "congestion_index": 0.4,
    "expected_dwell_min": 3,
    "signal_delay_min": 2,
    "maintenance_block": 0,
    "level_crossing_delay_min": 1,
}


def _live_or_static_telemetry(train_no: str) -> tuple[dict, str]:
    """Returns (telemetry, next_station). Uses the dynamic simulator when
    route+schedule data exists for this train, else the static fallback.
    Either way, the train is registered in SQL and this reading is logged
    to TelemetryLog, so *every* train_no anyone looks up - not just the
    ones with real route data - accumulates real, queryable history and
    shows up in /api/trains/search."""
    sim = get_or_create_simulator(train_no)
    if sim is not None:
        data = sim.telemetry()
        ACTIVE_TRAINS[train_no] = data
        return data, data.get("next_station") or "Terminated"

    is_new = train_no not in ACTIVE_TRAINS
    if is_new:
        ACTIVE_TRAINS[train_no] = {
            **DEFAULT_TELEMETRY,
            "train_no": train_no,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            upsert_train(train_no, has_live_route=False)
        except Exception:
            pass
    data = ACTIVE_TRAINS[train_no]
    try:
        log_telemetry(train_no, {**data, "next_station": "Howrah Jn"})
    except Exception:
        pass
    return data, "Howrah Jn"


@router.post("/start")
def start_train(payload: TrainStartRequest):
    sim = reset_simulator(payload.train_no)  # also upserts a Train row when it has live route data
    if sim is None:
        ACTIVE_TRAINS[payload.train_no] = {
            **DEFAULT_TELEMETRY,
            "train_no": payload.train_no,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            upsert_train(payload.train_no, has_live_route=False)
        except Exception:
            pass
    return {
        "train_no": payload.train_no,
        "status": "started",
        "message": "Telemetry simulation initialized"
        + (" (live route simulation)" if sim is not None else " (static fallback - no route data for this train)"),
    }


@router.get("/{train_no}/telemetry")
def telemetry(train_no: str):
    data, _ = _live_or_static_telemetry(train_no)
    return data


@router.get("/{train_no}/eta")
def eta(train_no: str):
    data, next_station = _live_or_static_telemetry(train_no)
    minutes, source = predict_remaining_minutes(data)
    delay_info = classify_delay(
        data["current_delay_min"],
        data["signal_delay_min"],
        data["congestion_index"],
        data["maintenance_block"],
    )
    return {
        "train_no": train_no,
        "next_station": next_station,
        "predicted_remaining_time_min": minutes,
        "predicted_arrival_iso": arrival_iso(minutes),
        "current_delay_min": data["current_delay_min"],
        "model_source": source,
        "delay": delay_info,
    }


@router.get("/{train_no}/eta/stations")
def eta_all_stations(train_no: str):
    """Live predicted arrival/delay for every stop on the route - the
    dynamic counterpart to the static /schedule endpoint below."""
    sim = get_or_create_simulator(train_no)
    if sim is None:
        raise HTTPException(
            status_code=404,
            detail="No route/schedule data for this train; live per-station ETA is unavailable",
        )

    current_delay = sim.current_delay_min()
    out = []
    for i, stop in enumerate(sim.route.stops):
        predicted_offset = stop.scheduled_offset_min + current_delay
        out.append(
            {
                "station": stop.name,
                "scheduled_offset_min": round(stop.scheduled_offset_min, 1),
                "predicted_offset_min": round(predicted_offset, 1),
                "delay_min": round(current_delay, 1),
                "status": "passed" if i < sim.stop_index else ("next" if i == sim.stop_index else "upcoming"),
            }
        )
    return {"train_no": train_no, "stations": out}


@router.post("/{train_no}/event")
def trigger_event(train_no: str, event: str, minutes: float = 8.0):
    """Demo control: inject a delay-causing event so judges can see the
    prediction react live. event in: signal_delay, maintenance_block,
    level_crossing, congestion."""
    sim = get_or_create_simulator(train_no)
    if sim is None:
        raise HTTPException(status_code=404, detail="No live simulation for this train; nothing to inject an event into")
    valid_events = {"signal_delay", "maintenance_block", "level_crossing", "congestion"}
    if event not in valid_events:
        raise HTTPException(status_code=400, detail=f"event must be one of {sorted(valid_events)}")
    sim.inject_event(event, minutes=minutes)
    return {"ok": True, "train_no": train_no, "event": event, "minutes": minutes}


@router.get("/{train_no}/schedule")
def schedule(train_no: str):
    if not SCHEDULE_PATH.exists():
        raise HTTPException(status_code=404, detail="Schedule file not found")
    payload = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    payload["train_no"] = train_no
    return payload


@router.get("/{train_no}/route")
def route(train_no: str):
    if not ROUTE_PATH.exists():
        raise HTTPException(status_code=404, detail="Route file not found")
    return json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
