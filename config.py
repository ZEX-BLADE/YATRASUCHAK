from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = BASE_DIR / "ml" / "models" / "eta_xgboost.joblib"
SAMPLE_DATA_PATH = BASE_DIR / "ml" / "data" / "sample" / "train_eta_sample.csv"
ROUTE_PATH = BASE_DIR / "data" / "routes" / "12301_route.geojson"
SCHEDULE_PATH = BASE_DIR / "data" / "schedules" / "12301_schedule.json"
