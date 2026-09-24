from pathlib import Path
import sys
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.preprocessing.preprocess import load_dataset, FEATURES

DATA = ROOT / "ml" / "data" / "sample" / "train_eta_sample.csv"
MODEL = ROOT / "ml" / "models" / "eta_xgboost.joblib"
METRICS = ROOT / "ml" / "evaluation" / "metrics.json"

def main():
    X, y = load_dataset(DATA)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = XGBRegressor(
        n_estimators=350,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=42,
    )
    model.fit(X_train, y_train)

    pred = model.predict(X_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, pred)),
        "rmse": float(mean_squared_error(y_test, pred) ** 0.5),
        "r2": float(r2_score(y_test, pred)),
        "rows": int(len(X)),
        "features": FEATURES,
    }

    MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL)
    METRICS.write_text(__import__("json").dumps(metrics, indent=2), encoding="utf-8")

    print("Model saved:", MODEL)
    print(metrics)

if __name__ == "__main__":
    main()
