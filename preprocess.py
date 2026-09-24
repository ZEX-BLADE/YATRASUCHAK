from pathlib import Path
import pandas as pd

TARGET = "actual_remaining_time_min"
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

def load_dataset(path: str | Path):
    df = pd.read_csv(path)
    df = df.dropna(subset=FEATURES + [TARGET]).copy()
    return df[FEATURES], df[TARGET]
