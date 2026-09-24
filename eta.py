from pydantic import BaseModel

class ETAResponse(BaseModel):
    train_no: str
    next_station: str
    predicted_remaining_time_min: float
    predicted_arrival_iso: str
    current_delay_min: float
    model_source: str
