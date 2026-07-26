"""
Delta-Target Reformulation for Random Forest + XGBoost, Power (W) target:
train on W(t+h) - W(t) instead of the raw future value, reconstruct
y_hat(t+h) = anchor + delta_hat before evaluating. Mirrors main_delta.py
(voltage target) -- see notes/SOFC_data_notes.md section 25 for why Power
is a harder, higher-value target for this reformulation (persistence
itself is much weaker for W than for V at long horizons).

Runs locally, no GPU needed.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features
from windowing import split_by_run, create_sliding_window_delta, reshape_for_random_forest
from diagnostics import evaluate_regression
from models.random_forest import RandomForestModel
from models.xgboost_model import XGBoostModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

TARGET = "W"


def main():
    df = prepare_data(path=RAW_CSV_PATH, target=TARGET)
    train_df, val_df, test_df = split_by_run(df)
    feat_cols = get_features(df, target=TARGET)

    X_train, y_train, rid_train = train_df[feat_cols], train_df[TARGET], train_df["run_id"]
    X_test, y_test, rid_test = test_df[feat_cols], test_df[TARGET], test_df["run_id"]

    # (save_dir_name, results_csv_name, model_class, kwargs)
    model_families = [
        ("random_forest_power_delta", "rf_power_delta", RandomForestModel, dict(n_estimators=300)),
        ("xgboost_power_delta", "xgb_power_delta", XGBoostModel, dict(n_estimators=300)),
    ]

    for name, csv_name, cls, kwargs in model_families:
        results = []
        for h in FORECAST_HORIZONS:
            Xw_tr, delta_tr, _ = create_sliding_window_delta(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
            Xw_te, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
            Xw_tr2d, Xw_te2d = reshape_for_random_forest(Xw_tr), reshape_for_random_forest(Xw_te)

            t0 = time.time()
            model = cls(**kwargs)
            model.train(Xw_tr2d, delta_tr)
            delta_pred = model.predict(Xw_te2d)
            y_pred = anchor_te + delta_pred
            y_true = anchor_te + delta_te
            elapsed = time.time() - t0

            metrics = evaluate_regression(y_true, y_pred)
            metrics["horizon"] = h
            results.append(metrics)
            print(f"[{name}] h={h}  MAE={metrics['MAE']:.4f} RMSE={metrics['RMSE']:.4f} "
                  f"R2={metrics['R2']:.4f} DTW={metrics['DTW']:.4f}  ({elapsed:.1f}s)")

            os.makedirs(os.path.join(OUTPUT_DIR, "models_saved", name), exist_ok=True)
            os.makedirs(os.path.join(OUTPUT_DIR, "predictions_cache", name), exist_ok=True)
            model.save(os.path.join(OUTPUT_DIR, "models_saved", name, f"h{h}.pkl"))
            np.savez(os.path.join(OUTPUT_DIR, "predictions_cache", name, f"h{h}.npz"),
                     y_true=y_true, y_pred=y_pred)

        os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
        results_df = pd.DataFrame(results)[["horizon", "MAE", "RMSE", "R2", "DTW"]]
        results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", f"{csv_name}_results.csv"), index=False)
        print(results_df)


if __name__ == "__main__":
    main()
