def validate_telemetry(data: dict) -> dict:
    cleaned = dict(data)
    cleaned["speed_kmph"] = max(0.0, min(float(cleaned.get("speed_kmph", 0)), 160.0))
    cleaned["current_delay_min"] = max(-30.0, min(float(cleaned.get("current_delay_min", 0)), 720.0))
    cleaned["distance_to_station_km"] = max(0.0, float(cleaned.get("distance_to_station_km", 0)))
    cleaned["congestion_index"] = max(0.0, min(float(cleaned.get("congestion_index", 0)), 1.0))
    cleaned["maintenance_block"] = int(bool(cleaned.get("maintenance_block", 0)))
    return cleaned
