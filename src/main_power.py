"""
Train Random Forest + XGBoost (direct forecast, one model per horizon) to
forecast Power (W) instead of Voltage (V) -- same pipeline as main.py, just
a different target. W = V * I exactly (see features.py), so V and I stay
in the feature set (legitimate historical info, not leakage) while W itself
is dropped from features via get_features(df, target="W").

Runs locally, no GPU needed. Meant as a fast first look before committing to
the full Colab retrain for LSTM/TCN/Seq2Seq (see main_lstm.py etc. for the
voltage-target precedent this mirrors).
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features
from windowing import split_by_run, create_sliding_window, reshape_for_random_forest
from diagnostics import evaluate_regression
from models.random_forest import RandomForestModel
from models.xgboost_model import XGBoostModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

TARGET = "W"


def main():
    df = prepare_data(path=RAW_CSV_PATH, target=TARGET)
    print("shape:", df.shape)
    print(df.groupby("run_id").size())

    train_df, val_df, test_df = split_by_run(df)
    print(f"train/val/test rows: {len(train_df)}/{len(val_df)}/{len(test_df)}")

    feat_cols = get_features(df, target=TARGET)
    X_train, y_train, rid_train = train_df[feat_cols], train_df[TARGET], train_df["run_id"]
    X_test, y_test, rid_test = test_df[feat_cols], test_df[TARGET], test_df["run_id"]

    # (save_dir_name, results_csv_name, model_class, kwargs)
    model_families = [
        ("random_forest_power", "rf_power", RandomForestModel, dict(n_estimators=300)),
        ("xgboost_power", "xgb_power", XGBoostModel, dict(n_estimators=300)),
    ]

    for name, csv_name, cls, kwargs in model_families:
        results = []
        for h in FORECAST_HORIZONS:
            Xw_tr, yw_tr = create_sliding_window(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
            Xw_te, yw_te = create_sliding_window(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
            Xw_tr2d, Xw_te2d = reshape_for_random_forest(Xw_tr), reshape_for_random_forest(Xw_te)

            t0 = time.time()
            model = cls(**kwargs)
            model.train(Xw_tr2d, yw_tr)
            y_pred = model.predict(Xw_te2d)
            elapsed = time.time() - t0

            metrics = evaluate_regression(yw_te, y_pred)
            metrics["horizon"] = h
            results.append(metrics)
            print(f"[{name}] h={h}  MAE={metrics['MAE']:.4f} RMSE={metrics['RMSE']:.4f} "
                  f"R2={metrics['R2']:.4f} DTW={metrics['DTW']:.4f}  ({elapsed:.1f}s)")

            os.makedirs(os.path.join(OUTPUT_DIR, "models_saved", name), exist_ok=True)
            os.makedirs(os.path.join(OUTPUT_DIR, "predictions_cache", name), exist_ok=True)
            model.save(os.path.join(OUTPUT_DIR, "models_saved", name, f"h{h}.pkl"))
            np.savez(os.path.join(OUTPUT_DIR, "predictions_cache", name, f"h{h}.npz"),
                     y_true=yw_te, y_pred=y_pred)

        os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
        results_df = pd.DataFrame(results)[["horizon", "MAE", "RMSE", "R2", "DTW"]]
        results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", f"{csv_name}_results.csv"), index=False)
        print(results_df)


if __name__ == "__main__":
    main()
