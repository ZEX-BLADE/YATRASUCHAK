from pathlib import Path
import sys, joblib
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.preprocessing.preprocess import load_dataset

DATA = ROOT / "ml" / "data" / "sample" / "train_eta_sample.csv"
MODEL = ROOT / "ml" / "models" / "eta_xgboost.joblib"

X, y = load_dataset(DATA)
_, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
model = joblib.load(MODEL)
pred = model.predict(X_test)

print({
    "MAE": mean_absolute_error(y_test, pred),
    "RMSE": mean_squared_error(y_test, pred) ** 0.5,
    "R2": r2_score(y_test, pred),
})
