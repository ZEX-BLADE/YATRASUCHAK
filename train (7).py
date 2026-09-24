from pydantic import BaseModel, Field

class TrainStartRequest(BaseModel):
    train_no: str = Field(..., examples=["12301"])

class TrainStartResponse(BaseModel):
    train_no: str
    status: str
    message: str
