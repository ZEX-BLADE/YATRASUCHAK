from backend.services.eta_predictor import fallback_predict

def test_fallback_prediction_positive():
    features = {
        "speed_kmph": 92,
        "distance_to_station_km": 38,
        "historical_travel_time_min": 31,
        "previous_delay_min": 6,
        "congestion_index": 0.4,
        "expected_dwell_min": 3,
        "signal_delay_min": 2,
        "maintenance_block": 0,
        "level_crossing_delay_min": 1,
    }
    assert fallback_predict(features) > 0
