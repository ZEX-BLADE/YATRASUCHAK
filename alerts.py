from fastapi import APIRouter

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

@router.get("/{train_no}")
def get_alerts(train_no: str):
    return {
        "train_no": train_no,
        "alerts": [
            {
                "type": "caution",
                "message": "Moderate congestion detected near next block section.",
            }
        ],
    }
