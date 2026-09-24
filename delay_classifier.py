def classify_delay(current_delay_min: float, signal_delay_min: float, congestion_index: float, maintenance_block: int) -> dict:
    scores = {
        "signalling": signal_delay_min,
        "congestion": congestion_index * 20,
        "maintenance": 15 if maintenance_block else 0,
        "operational": max(current_delay_min - signal_delay_min, 0),
    }
    cause = max(scores, key=scores.get)
    severity = "low"
    if current_delay_min >= 30:
        severity = "high"
    elif current_delay_min >= 10:
        severity = "medium"
    return {"likely_cause": cause, "severity": severity}
