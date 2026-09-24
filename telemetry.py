from pydantic import BaseModel

class Telemetry(BaseModel):
    train_no: str
    latitude: float
    longitude: float
    speed_kmph: float
    current_delay_min: float
    distance_to_station_km: float
    previous_delay_min: float
    congestion_index: float
    expected_dwell_min: float
    signal_delay_min: float
    maintenance_block: int
    level_crossing_delay_min: float
    timestamp: str
