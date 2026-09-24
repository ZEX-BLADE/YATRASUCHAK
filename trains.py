from fastapi import APIRouter, Query

try:
    from backend.database.repository import search_trains, list_trains, get_train, get_telemetry_history, upsert_train
    from backend.services.train_simulator import get_or_create_simulator
except ImportError:
    from database.repository import search_trains, list_trains, get_train, get_telemetry_history, upsert_train
    from services.train_simulator import get_or_create_simulator

router = APIRouter(prefix="/api/trains", tags=["trains"])


def _live_status(train_no: str) -> dict | None:
    sim = get_or_create_simulator(train_no)
    if sim is None:
        return None
    return {
        "progress_pct": round(sim.progress_km / sim.route.total_distance_km * 100, 1),
        "current_delay_min": sim.current_delay_min(),
        "next_station": sim._next_stop().name if sim._next_stop() else None,
        "journey_complete": sim.journey_complete,
    }


@router.get("/search")
def search(q: str = Query("", description="Train number or name, partial match"), limit: int = 20):
    """Find a train by number or name. This is the single source of truth
    other parts of the backend key off of - the train_no returned here can
    be used directly with every /api/train/{train_no}/... endpoint."""
    results = search_trains(q, limit=limit)
    for r in results:
        r["live"] = _live_status(r["train_no"])
    return {"query": q, "count": len(results), "results": results}


@router.get("")
def list_all(limit: int = 100):
    results = list_trains(limit=limit)
    for r in results:
        r["live"] = _live_status(r["train_no"])
    return {"count": len(results), "results": results}


@router.get("/{train_no}")
def get_one(train_no: str):
    """Looking up any train_no here registers it, live-route or not, so it
    shows up in subsequent searches and every /api/train/{train_no}/...
    endpoint is talking about the same persisted record from this point
    on - "finding" a train is what makes it known throughout the backend."""
    train = get_train(train_no)
    if train is None:
        sim = get_or_create_simulator(train_no)  # registers it in SQL if it has route data
        train = get_train(train_no)
        if train is None:  # no route data either - still register it as a known (static-fallback) train
            train = upsert_train(train_no, has_live_route=False)
    train["live"] = _live_status(train_no)
    return train


@router.get("/{train_no}/history")
def history(train_no: str, limit: int = 200):
    """Recent real-time telemetry for this train, read back from SQL."""
    return {"train_no": train_no, "count": limit, "rows": get_telemetry_history(train_no, limit=limit)}
