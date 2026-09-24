"""Registers every train that ships route+schedule data on disk as a
searchable Train row at startup, so a fresh database (e.g. a brand new
Render Postgres instance) already has demo train 12301 - and any others
you drop data files in for - findable without waiting for someone to hit
an endpoint first."""

import json

try:
    from backend.database.repository import upsert_train
    from backend.services.train_simulator import ROUTES_DIR, SCHEDULES_DIR
except ImportError:
    from database.repository import upsert_train
    from services.train_simulator import ROUTES_DIR, SCHEDULES_DIR


def seed_known_trains():
    if not ROUTES_DIR.exists():
        return
    for route_file in ROUTES_DIR.glob("*_route.geojson"):
        train_no = route_file.stem.replace("_route", "")
        schedule_file = SCHEDULES_DIR / f"{train_no}_schedule.json"
        if not schedule_file.exists():
            continue
        try:
            schedule = json.loads(schedule_file.read_text(encoding="utf-8"))
            stations = schedule.get("stations", [])
            origin = stations[0]["station"] if stations else None
            destination = stations[-1]["station"] if stations else None
        except (json.JSONDecodeError, KeyError, IndexError):
            origin = destination = None
        upsert_train(
            train_no,
            name=f"{origin} - {destination} Express" if origin and destination else train_no,
            origin=origin,
            destination=destination,
            has_live_route=True,
        )
