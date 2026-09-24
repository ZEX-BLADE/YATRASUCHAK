import sys

from fastapi import APIRouter, HTTPException

try:
    from backend.database.repository import count_telemetry_rows
    from backend.utils.config import MODEL_PATH, BASE_DIR
except ImportError:
    from database.repository import count_telemetry_rows
    from utils.config import MODEL_PATH, BASE_DIR

# The `ml` package lives at the project root, alongside `backend/` - not
# inside it. `from ml.training... import` only resolves if the project
# root is on sys.path, which is guaranteed when running
# `uvicorn backend.main:app` from the root, but NOT when running
# `cd backend && uvicorn main:app`. Make sure it's there either way.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

router = APIRouter(prefix="/api/model", tags=["model"])


@router.get("/status")
def status():
    return {
        "model_present": MODEL_PATH.exists(),
        "telemetry_rows_logged": count_telemetry_rows(),
    }


@router.post("/retrain")
def retrain():
    """Retrains the ETA model on whatever real telemetry has accumulated
    in SQL so far (see ml/training/train_from_sql.py). Falls back to
    reporting how much more data is needed rather than failing silently."""
    try:
        from ml.training.train_from_sql import train_from_sql, InsufficientData
    except ImportError as e:  # pragma: no cover - only if ml deps missing
        raise HTTPException(status_code=500, detail=f"Training dependencies unavailable: {e}")

    try:
        metrics = train_from_sql()
    except InsufficientData as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"ok": True, "metrics": metrics}
