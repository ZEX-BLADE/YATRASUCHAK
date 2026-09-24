from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

try:
    from backend.database.connection import Base
except ImportError:
    from database.connection import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Train(Base):
    """A train the system knows about. Created the first time anyone looks
    it up (via /api/trains/search, /api/train/start, or any /api/train/{no}
    endpoint) - so 'finding' a train registers it, and every other endpoint
    keyed by train_no is then talking about the same persisted record."""

    __tablename__ = "trains"

    train_no = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    origin = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    has_live_route = Column(Boolean, default=False)  # True if route+schedule data exists on disk
    first_seen_at = Column(DateTime(timezone=True), default=_utcnow)
    last_seen_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    telemetry_logs = relationship("TelemetryLog", back_populates="train", cascade="all, delete-orphan")

    def as_dict(self, live_status: dict | None = None) -> dict:
        out = {
            "train_no": self.train_no,
            "name": self.name,
            "origin": self.origin,
            "destination": self.destination,
            "has_live_route": self.has_live_route,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }
        if live_status:
            out["live"] = live_status
        return out


class TelemetryLog(Base):
    """One row per simulated tick - the durable, queryable real-time-data
    history. This is what /api/train/{no}/history reads from and what the
    ML model in ml/training/train_from_sql.py trains on."""

    __tablename__ = "telemetry_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    train_no = Column(String, ForeignKey("trains.train_no"), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    latitude = Column(Float)
    longitude = Column(Float)
    speed_kmph = Column(Float)
    current_delay_min = Column(Float)
    distance_to_station_km = Column(Float)
    historical_travel_time_min = Column(Float)
    previous_delay_min = Column(Float)
    congestion_index = Column(Float)
    expected_dwell_min = Column(Float)
    signal_delay_min = Column(Float)
    maintenance_block = Column(Integer)
    level_crossing_delay_min = Column(Float)
    next_station = Column(String, nullable=True)
    last_station = Column(String, nullable=True)
    progress_pct = Column(Float, nullable=True)

    train = relationship("Train", back_populates="telemetry_logs")

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "speed_kmph": self.speed_kmph,
            "current_delay_min": self.current_delay_min,
            "distance_to_station_km": self.distance_to_station_km,
            "historical_travel_time_min": self.historical_travel_time_min,
            "previous_delay_min": self.previous_delay_min,
            "congestion_index": self.congestion_index,
            "expected_dwell_min": self.expected_dwell_min,
            "signal_delay_min": self.signal_delay_min,
            "maintenance_block": self.maintenance_block,
            "level_crossing_delay_min": self.level_crossing_delay_min,
            "next_station": self.next_station,
            "last_station": self.last_station,
            "progress_pct": self.progress_pct,
        }


Index("ix_telemetry_train_ts", TelemetryLog.train_no, TelemetryLog.timestamp)
