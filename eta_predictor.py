from datetime import datetime, timedelta, timezone
from pathlib import Path
import math

try:
    from backend.utils.config import MODEL_PATH
except ImportError:
    from utils.config import MODEL_PATH

FEATURES = [
    "speed_kmph",
    "current_delay_min",
    "distance_to_station_km",
    "historical_travel_time_min",
    "previous_delay_min",
    "congestion_index",
    "expected_dwell_min",
    "signal_delay_min",
    "maintenance_block",
    "level_crossing_delay_min",
]

_model = None

def _load_model():
    global _model
    if _model is not None:
        return _model
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib
        _model = joblib.load(MODEL_PATH)
        return _model
    except Exception:
        return None

def fallback_predict(features: dict) -> float:
    speed = max(float(features.get("speed_kmph", 40)), 10)
    distance = float(features.get("distance_to_station_km", 10))
    base_by_speed = distance / speed * 60
    historical = float(features.get("historical_travel_time_min", base_by_speed))
    congestion = float(features.get("congestion_index", 0)) * 10
    signal = float(features.get("signal_delay_min", 0))
    dwell = float(features.get("expected_dwell_min", 0))
    crossing = float(features.get("level_crossing_delay_min", 0))
    maintenance = 8 if int(features.get("maintenance_block", 0)) else 0
    previous = max(float(features.get("previous_delay_min", 0)), 0) * 0.12

    prediction = (
        0.55 * base_by_speed +
        0.45 * historical +
        congestion +
        signal +
        0.25 * dwell +
        crossing +
        maintenance +
        previous
    )
    return max(1.0, prediction)

def predict_remaining_minutes(features: dict) -> tuple[float, str]:
    model = _load_model()
    if model is None:
        return round(fallback_predict(features), 2), "fallback-estimator"

    row = [[float(features.get(k, 0)) for k in FEATURES]]
    pred = float(model.predict(row)[0])
    return round(max(pred, 1.0), 2), "xgboost"

def arrival_iso(minutes: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
