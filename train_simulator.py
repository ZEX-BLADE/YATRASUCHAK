"""
Dynamic, multi-station train simulation.

This is the piece the starter project was missing: `data_fusion.py` and
`validator.py` already existed but nothing ever called them, and
`ACTIVE_TRAINS` telemetry never actually evolved toward a destination -
`current_delay_min` stayed frozen at whatever `/start` set it to forever,
`next_station` was hardcoded to "Howrah Jn" everywhere, and the simulated
lat/lon just jittered randomly instead of moving along the real route.

For any train that has a route (`data/routes/<no>_route.geojson`) and a
schedule (`data/schedules/<no>_schedule.json`) on disk - currently just
demo train 12301 - this builds a proper multi-station journey and
simulates it every tick:

  GNSS-style fields (position, speed, distance-to-go)         -> gnss
  Signalling-style fields (signal delay, maintenance blocks,
  level-crossing delay - these already existed in the schema
  but nothing ever set them dynamically)                      -> signalling
      |
      v
  fuse_sources(gnss, signalling)   <-- backend/services/data_fusion.py
      |
      v
  validate_telemetry(fused)        <-- backend/services/validator.py
      |
      v
  live, schema-valid telemetry dict, with current_delay_min /
  next_station / distance_to_station_km all genuinely dynamic.

Trains with no route/schedule file fall back to the original static
DEFAULT_TELEMETRY + light random walk, so arbitrary train numbers keep
working exactly as before.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    from backend.utils.config import BASE_DIR
    from backend.services.data_fusion import fuse_sources
    from backend.services.validator import validate_telemetry
    from backend.database.repository import upsert_train, log_telemetry
except ImportError:  # running as `uvicorn main:app` from inside backend/
    from utils.config import BASE_DIR
    from services.data_fusion import fuse_sources
    from services.validator import validate_telemetry
    from database.repository import upsert_train, log_telemetry

ROUTES_DIR = BASE_DIR / "data" / "routes"
SCHEDULES_DIR = BASE_DIR / "data" / "schedules"

REAL_TICK_SECONDS = 2.0     # cadence the websocket/pollers advance the sim at
SIM_MINUTES_PER_TICK = 1.5  # simulated minutes advanced per tick (~45x real time)
EMA_ALPHA = 0.3
ARRIVAL_THRESHOLD_KM = 0.05


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _parse_hhmm_to_min(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


@dataclass
class _Stop:
    name: str
    vertex_index: int
    cum_distance_km: float
    scheduled_offset_min: float


@dataclass
class _RouteData:
    coordinates: list[tuple[float, float]]  # (lon, lat)
    cum_dist_at_vertex: list[float]
    stops: list[_Stop]
    total_distance_km: float
    total_scheduled_min: float


def load_route_data(train_no: str) -> Optional[_RouteData]:
    route_path = ROUTES_DIR / f"{train_no}_route.geojson"
    schedule_path = SCHEDULES_DIR / f"{train_no}_schedule.json"
    if not route_path.exists() or not schedule_path.exists():
        return None

    route_json = json.loads(route_path.read_text(encoding="utf-8"))
    schedule_json = json.loads(schedule_path.read_text(encoding="utf-8"))

    line = next(
        (f for f in route_json.get("features", []) if f.get("geometry", {}).get("type") == "LineString"),
        None,
    )
    if not line:
        return None
    coords = [tuple(c) for c in line["geometry"]["coordinates"]]  # (lon, lat)

    cum = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum.append(cum[-1] + _haversine_km(a, b))

    named_points = {
        f["properties"]["station"].strip().lower(): tuple(f["geometry"]["coordinates"])
        for f in route_json.get("features", [])
        if f.get("geometry", {}).get("type") == "Point" and f.get("properties", {}).get("station")
    }

    stations = schedule_json.get("stations", [])
    if not stations:
        return None

    base_offset = _parse_hhmm_to_min(stations[0]["scheduled"])
    unmatched_positions: list[int] = []
    stops: list[_Stop] = []

    for i, st in enumerate(stations):
        key = st["station"].strip().lower()
        vertex_idx = None
        if key in named_points:
            target = named_points[key]
            vertex_idx = min(range(len(coords)), key=lambda vi: _haversine_km(coords[vi], target))
        stops.append(
            _Stop(
                name=st["station"],
                vertex_index=vertex_idx if vertex_idx is not None else -1,
                cum_distance_km=0.0,  # filled below
                scheduled_offset_min=_parse_hhmm_to_min(st["scheduled"]) - base_offset,
            )
        )
        if vertex_idx is None:
            unmatched_positions.append(i)

    # First unmatched stop anchors to the route start, last to the route end;
    # anything else spreads evenly across the remaining vertices in order.
    if unmatched_positions:
        if unmatched_positions[0] == 0:
            stops[0].vertex_index = 0
            unmatched_positions.pop(0)
    if unmatched_positions and unmatched_positions[-1] == len(stops) - 1:
        stops[-1].vertex_index = len(coords) - 1
        unmatched_positions.pop()
    remaining_vertices = [i for i in range(len(coords)) if i not in {s.vertex_index for s in stops if s.vertex_index >= 0}]
    for pos in unmatched_positions:
        stops[pos].vertex_index = remaining_vertices.pop(0) if remaining_vertices else stops[pos - 1].vertex_index

    for s in stops:
        s.cum_distance_km = cum[s.vertex_index] if s.vertex_index >= 0 else 0.0

    return _RouteData(
        coordinates=coords,
        cum_dist_at_vertex=cum,
        stops=stops,
        total_distance_km=cum[-1],
        total_scheduled_min=stops[-1].scheduled_offset_min,
    )


@dataclass
class TrainSimulator:
    train_no: str
    route: _RouteData
    progress_km: float = 0.0
    sim_clock_min: float = 0.0
    effective_speed_kmph: float = 60.0
    stop_index: int = 0          # index of the next stop not yet reached
    dwell_remaining_min: float = 0.0
    journey_complete: bool = False
    previous_delay_min: float = 0.0
    signal_delay_min: float = field(default_factory=lambda: round(random.uniform(0, 3), 1))
    maintenance_block: int = 0
    level_crossing_delay_min: float = field(default_factory=lambda: round(random.uniform(0, 2), 1))
    congestion_index: float = field(default_factory=lambda: round(random.uniform(0.1, 0.4), 2))
    _maintenance_ticks_left: int = 0

    def _scheduled_offset_for_distance(self, distance_km: float) -> float:
        stops = self.route.stops
        if distance_km <= stops[0].cum_distance_km:
            return stops[0].scheduled_offset_min
        if distance_km >= stops[-1].cum_distance_km:
            return stops[-1].scheduled_offset_min
        for a, b in zip(stops, stops[1:]):
            if a.cum_distance_km <= distance_km <= b.cum_distance_km:
                span_km = b.cum_distance_km - a.cum_distance_km
                span_min = b.scheduled_offset_min - a.scheduled_offset_min
                frac = (distance_km - a.cum_distance_km) / span_km if span_km else 0
                return a.scheduled_offset_min + frac * span_min
        return stops[-1].scheduled_offset_min

    def _segment_scheduled_speed(self, distance_km: float) -> float:
        stops = self.route.stops
        for a, b in zip(stops, stops[1:]):
            if a.cum_distance_km <= distance_km <= b.cum_distance_km:
                span_km = b.cum_distance_km - a.cum_distance_km
                span_min = b.scheduled_offset_min - a.scheduled_offset_min
                return span_km / (span_min / 60) if span_min else 60.0
        return 60.0

    def _current_position_lonlat(self) -> tuple[float, float]:
        cum = self.route.cum_dist_at_vertex
        coords = self.route.coordinates
        d = min(self.progress_km, cum[-1])
        for i in range(len(cum) - 1):
            if cum[i] <= d <= cum[i + 1]:
                span = cum[i + 1] - cum[i]
                frac = (d - cum[i]) / span if span else 0
                lon = coords[i][0] + frac * (coords[i + 1][0] - coords[i][0])
                lat = coords[i][1] + frac * (coords[i + 1][1] - coords[i][1])
                return lon, lat
        return coords[-1]

    def _next_stop(self) -> Optional[_Stop]:
        if self.stop_index >= len(self.route.stops):
            return None
        return self.route.stops[self.stop_index]

    def _last_stop_name(self) -> Optional[str]:
        return self.route.stops[self.stop_index - 1].name if self.stop_index > 0 else None

    def _maybe_update_signalling(self):
        # Small random walk plus occasional spikes - stands in for a live
        # signalling feed until a real one is connected.
        self.signal_delay_min = max(0.0, round(self.signal_delay_min + random.uniform(-0.4, 0.5), 2))
        self.level_crossing_delay_min = max(0.0, round(self.level_crossing_delay_min + random.uniform(-0.3, 0.3), 2))
        self.congestion_index = min(1.0, max(0.0, round(self.congestion_index + random.uniform(-0.05, 0.05), 3)))

        if self._maintenance_ticks_left > 0:
            self._maintenance_ticks_left -= 1
            self.maintenance_block = 1
        else:
            self.maintenance_block = 0
            if random.random() < 0.01:
                self._maintenance_ticks_left = random.randint(4, 10)

    def tick(self):
        if self.journey_complete:
            return

        self._maybe_update_signalling()

        if self.dwell_remaining_min > 0:
            self.dwell_remaining_min = max(0.0, self.dwell_remaining_min - SIM_MINUTES_PER_TICK)
            self.sim_clock_min += SIM_MINUTES_PER_TICK
            return

        base_speed = self._segment_scheduled_speed(self.progress_km)
        slowdown = min(
            0.9,
            0.05 * self.signal_delay_min
            + 0.35 * self.maintenance_block
            + 0.05 * self.level_crossing_delay_min
            + 0.3 * self.congestion_index,
        )
        instantaneous_speed = max(0.0, base_speed * (1 - slowdown) + random.gauss(0, base_speed * 0.04))
        self.effective_speed_kmph = EMA_ALPHA * instantaneous_speed + (1 - EMA_ALPHA) * self.effective_speed_kmph

        self.progress_km = min(
            self.route.total_distance_km,
            self.progress_km + self.effective_speed_kmph * (SIM_MINUTES_PER_TICK / 60),
        )
        self.sim_clock_min += SIM_MINUTES_PER_TICK

        next_stop = self._next_stop()
        if next_stop and (next_stop.cum_distance_km - self.progress_km) <= ARRIVAL_THRESHOLD_KM:
            self.progress_km = next_stop.cum_distance_km
            self.previous_delay_min = round(self.sim_clock_min - next_stop.scheduled_offset_min, 1)
            self.stop_index += 1
            if self.stop_index >= len(self.route.stops):
                self.journey_complete = True
            else:
                self.dwell_remaining_min = 3.0  # simulated dwell at each stop

    def current_delay_min(self) -> float:
        return round(self.sim_clock_min - self._scheduled_offset_for_distance(self.progress_km), 1)

    def telemetry(self) -> dict:
        next_stop = self._next_stop()
        lon, lat = self._current_position_lonlat()
        distance_to_station_km = (
            round(max(0.0, next_stop.cum_distance_km - self.progress_km), 2) if next_stop else 0.0
        )

        prev_stop = self.route.stops[self.stop_index - 1] if self.stop_index > 0 else self.route.stops[0]
        historical_travel_time_min = (
            round(next_stop.scheduled_offset_min - prev_stop.scheduled_offset_min, 1) if next_stop else 0.0
        )

        gnss = {
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed_kmph": round(self.effective_speed_kmph, 1),
            "current_delay_min": self.current_delay_min(),
            "distance_to_station_km": distance_to_station_km,
            "historical_travel_time_min": historical_travel_time_min,
            "previous_delay_min": self.previous_delay_min,
            "expected_dwell_min": 3,
        }
        signalling = {
            "signal_delay_min": self.signal_delay_min,
            "maintenance_block": self.maintenance_block,
            "level_crossing_delay_min": self.level_crossing_delay_min,
        }
        fused = fuse_sources(gnss, signalling)
        fused["congestion_index"] = self.congestion_index
        validated = validate_telemetry(fused)

        validated.update(
            {
                "train_no": self.train_no,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "next_station": next_stop.name if next_stop else None,
                "last_station": self._last_stop_name(),
                "journey_complete": self.journey_complete,
                "progress_pct": round(self.progress_km / self.route.total_distance_km * 100, 1),
            }
        )
        return validated

    def inject_event(self, event: str, minutes: float = 8.0):
        if event == "signal_delay":
            self.signal_delay_min = round(self.signal_delay_min + minutes, 1)
        elif event == "maintenance_block":
            self._maintenance_ticks_left = max(self._maintenance_ticks_left, int(minutes / SIM_MINUTES_PER_TICK))
        elif event == "level_crossing":
            self.level_crossing_delay_min = round(self.level_crossing_delay_min + minutes, 1)
        elif event == "congestion":
            self.congestion_index = min(1.0, self.congestion_index + minutes / 10)


_SIMULATORS: dict[str, TrainSimulator] = {}


def get_or_create_simulator(train_no: str) -> Optional[TrainSimulator]:
    """Returns a live simulator for trains with route+schedule data on
    disk, or None for trains that should fall back to static telemetry.
    Registers the train in SQL the first time it's created, so a train
    someone just looked up is immediately findable everywhere else."""
    if train_no in _SIMULATORS:
        return _SIMULATORS[train_no]
    route_data = load_route_data(train_no)
    if route_data is None:
        return None
    sim = TrainSimulator(train_no=train_no, route=route_data)
    _SIMULATORS[train_no] = sim
    try:
        origin = route_data.stops[0].name
        destination = route_data.stops[-1].name
        upsert_train(
            train_no,
            name=f"{origin} - {destination} Express",
            origin=origin,
            destination=destination,
            has_live_route=True,
        )
    except Exception:
        pass  # DB being briefly unavailable shouldn't break the simulation
    return sim


def reset_simulator(train_no: str) -> Optional[TrainSimulator]:
    _SIMULATORS.pop(train_no, None)
    return get_or_create_simulator(train_no)


async def run_simulation_loop():
    """Advances every active simulator on a fixed cadence, independent of
    whether anything is connected over the websocket. Without this, a
    plain REST poll of /telemetry would never see the train move - only a
    live websocket connection would have advanced it.

    Every tick is also appended to the TelemetryLog SQL table, so the
    real-time feed is durably stored, not just held in memory - and is
    what ml/training/train_from_sql.py later trains the ETA model on."""
    import asyncio

    while True:
        for sim in list(_SIMULATORS.values()):
            sim.tick()
            try:
                log_telemetry(sim.train_no, sim.telemetry())
            except Exception:
                pass  # a transient DB hiccup shouldn't kill the simulation loop
        await asyncio.sleep(REAL_TICK_SECONDS)
