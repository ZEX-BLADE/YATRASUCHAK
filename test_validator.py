from backend.services.validator import validate_telemetry

def test_speed_is_clamped():
    assert validate_telemetry({"speed_kmph": 999})["speed_kmph"] == 160.0
