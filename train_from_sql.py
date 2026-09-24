"""
Train the ETA model on the *real* telemetry the backend has been logging
to SQL (TelemetryLog), instead of - or in addition to - the synthetic
`ml/data/sample/train_eta_sample.csv`.

There's no separately-recorded "actual arrival time" column to supervise
on, so the label is reconstructed from the log itself: every row stores
which station it's heading to (`next_station`); the moment that value
changes to something else (or the journey completes) tells us exactly
when the train actually reached it. So for every row logged while
`next_station == X`, the target is:

    actual_remaining_time_min = (timestamp the train reached X) - (this row's timestamp)

That reproduces the same `actual_remaining_time_min` target and feature
set (`ml/preprocessing/preprocess.py: FEATURES`) the synthetic-CSV model
already used, so `eta_predictor.py` picks up whichever model is newer
without any code changes.

Usage:
    python ml/training/train_from_sql.py
or via the API: POST /api/model/retrain
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from ml.preprocessing.preprocess import FEATURES, TARGET
from backend.database.connection import get_session
from backend.database.models_db import TelemetryLog
from backend.utils.config import MODEL_PATH

MIN_ROWS_TO_TRAIN = 30


class InsufficientData(Exception):
    pass


def build_training_frame() -> pd.DataFrame:
    with get_session() as db:
        rows = db.query(TelemetryLog).order_by(TelemetryLog.train_no, TelemetryLog.timestamp).all()
        records = [
            {
                "train_no": r.train_no,
                "timestamp": r.timestamp,
                "next_station": r.next_station,
                **{f: getattr(r, f) for f in FEATURES},
            }
            for r in rows
        ]

    if not records:
        return pd.DataFrame(columns=FEATURES + [TARGET])

    df = pd.DataFrame(records)
    labeled_rows = []

    for train_no, group in df.groupby("train_no"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        # arrival_time[station] = timestamp of the first row where
        # next_station is no longer that station (i.e. the train reached it)
        for i in range(len(group)):
            current_station = group.loc[i, "next_station"]
            if not current_station:
                continue
            arrival_ts = None
            for j in range(i + 1, len(group)):
                if group.loc[j, "next_station"] != current_station:
                    arrival_ts = group.loc[j, "timestamp"]
                    break
            if arrival_ts is None:
                continue  # train hasn't reached this station yet in the log
            remaining_min = (arrival_ts - group.loc[i, "timestamp"]).total_seconds() / 60.0
            if remaining_min <= 0:
                continue
            row = {f: group.loc[i, f] for f in FEATURES}
            row[TARGET] = remaining_min
            labeled_rows.append(row)

    return pd.DataFrame(labeled_rows, columns=FEATURES + [TARGET])


def train_from_sql() -> dict:
    df = build_training_frame()
    if len(df) < MIN_ROWS_TO_TRAIN:
        raise InsufficientData(
            f"Only {len(df)} labeled telemetry rows in the database so far "
            f"(need at least {MIN_ROWS_TO_TRAIN}). Let the simulation run "
            f"longer - or start more trains - then retrain."
        )

    df = df.dropna(subset=FEATURES + [TARGET])
    X, y = df[FEATURES], df[TARGET]

    test_size = 0.2 if len(df) >= 50 else max(1, int(len(df) * 0.1)) / len(df)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)

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
        "r2": float(r2_score(y_test, pred)) if len(y_test) > 1 else None,
        "rows": int(len(df)),
        "features": FEATURES,
        "source": "sql_telemetry_log",
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    return metrics


if __name__ == "__main__":
    print(train_from_sql())
