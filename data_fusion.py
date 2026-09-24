from .validator import validate_telemetry

def fuse_sources(gnss: dict, signalling: dict | None = None) -> dict:
    signalling = signalling or {}
    fused = dict(gnss)
    fused["signal_delay_min"] = signalling.get("signal_delay_min", fused.get("signal_delay_min", 0))
    fused["maintenance_block"] = signalling.get("maintenance_block", fused.get("maintenance_block", 0))
    fused["level_crossing_delay_min"] = signalling.get(
        "level_crossing_delay_min", fused.get("level_crossing_delay_min", 0)
    )
    return validate_telemetry(fused)
