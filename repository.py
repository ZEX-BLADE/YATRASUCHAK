"""
Data-access helpers sitting between the API routes / simulator and the SQL
tables. Centralising these here is what makes "find a train" consistent
throughout the backend: every code path that touches a train number
(searching, starting, polling telemetry, the websocket tick loop) goes
through `upsert_train`, so the same Train row and telemetry history back
every endpoint.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import or_

try:
    from backend.database.connection import get_session
    from backend.database.models_db import Train, TelemetryLog
except ImportError:
    from database.connection import get_session
    from database.models_db import Train, TelemetryLog


def upsert_train(
    train_no: str,
    name: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    has_live_route: Optional[bool] = None,
) -> dict:
    with get_session() as db:
        train = db.get(Train, train_no)
        if train is None:
            train = Train(train_no=train_no)
            db.add(train)
        if name is not None:
            train.name = name
        if origin is not None:
            train.origin = origin
        if destination is not None:
            train.destination = destination
        if has_live_route is not None:
            train.has_live_route = has_live_route
        db.flush()
        return train.as_dict()


def search_trains(query: str = "", limit: int = 20) -> list[dict]:
    with get_session() as db:
        q = db.query(Train)
        if query:
            like = f"%{query.strip()}%"
            q = q.filter(or_(Train.train_no.ilike(like), Train.name.ilike(like)))
        rows = q.order_by(Train.last_seen_at.desc()).limit(limit).all()
        return [t.as_dict() for t in rows]


def list_trains(limit: int = 100) -> list[dict]:
    return search_trains("", limit=limit)


def get_train(train_no: str) -> Optional[dict]:
    with get_session() as db:
        train = db.get(Train, train_no)
        return train.as_dict() if train else None


def log_telemetry(train_no: str, data: dict) -> None:
    with get_session() as db:
        row = TelemetryLog(
            train_no=train_no,
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            speed_kmph=data.get("speed_kmph"),
            current_delay_min=data.get("current_delay_min"),
            distance_to_station_km=data.get("distance_to_station_km"),
            historical_travel_time_min=data.get("historical_travel_time_min"),
            previous_delay_min=data.get("previous_delay_min"),
            congestion_index=data.get("congestion_index"),
            expected_dwell_min=data.get("expected_dwell_min"),
            signal_delay_min=data.get("signal_delay_min"),
            maintenance_block=data.get("maintenance_block"),
            level_crossing_delay_min=data.get("level_crossing_delay_min"),
            next_station=data.get("next_station"),
            last_station=data.get("last_station"),
            progress_pct=data.get("progress_pct"),
        )
        db.add(row)
        train = db.get(Train, train_no)
        if train is not None:
            from datetime import datetime, timezone

            train.last_seen_at = datetime.now(timezone.utc)


def get_telemetry_history(train_no: str, limit: int = 200) -> list[dict]:
    with get_session() as db:
        rows = (
            db.query(TelemetryLog)
            .filter(TelemetryLog.train_no == train_no)
            .order_by(TelemetryLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [r.as_dict() for r in reversed(rows)]


def count_telemetry_rows(train_no: Optional[str] = None) -> int:
    with get_session() as db:
        q = db.query(TelemetryLog)
        if train_no:
            q = q.filter(TelemetryLog.train_no == train_no)
        return q.count()
