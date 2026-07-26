"""
Experiment 3, TCN -- see main_lstm_delta_given_i.py for the full rationale
(notes/SOFC_data_notes.md section 28-29). Mirrors main_tcn_delta.py plus one
extra feature channel (I(t+h), broadcast across the window). Meant for
Colab (GPU).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_sliding_window_delta, augment_with_future_exogenous
from diagnostics import evaluate_regression, print_metrics
from models.tcn import TCNModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

I_COL = "I"


def main():
    df = prepare_data(path=RAW_CSV_PATH)
    train_df, val_df, test_df = split_by_run(df)
    feat_cols = get_features(df)

    X_train, y_train, rid_train = train_df[feat_cols], train_df[TARGET], train_df["run_id"]
    X_test, y_test, rid_test = test_df[feat_cols], test_df[TARGET], test_df["run_id"]
    I_train, I_test = train_df[I_COL], test_df[I_COL]

    results = []
    for h in FORECAST_HORIZONS:
        print(f"\n=== TCN-delta-given-I h={h} ===")
        Xw_tr, delta_tr, _ = create_sliding_window_delta(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
        Xw_te, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)

        Xw_tr = augment_with_future_exogenous(Xw_tr, X_train, I_train, rid_train, WINDOW_SIZE, [h])
        Xw_te = augment_with_future_exogenous(Xw_te, X_test, I_test, rid_test, WINDOW_SIZE, [h])

        model = TCNModel(num_channels=(32, 32, 32, 32), kernel_size=3, dropout=0.1, epochs=150, patience=10)
        model.train(Xw_tr, delta_tr, verbose=True)
        delta_pred = model.predict(Xw_te)
        y_pred = anchor_te + delta_pred
        y_true = anchor_te + delta_te

        metrics = evaluate_regression(y_true, y_pred)
        print_metrics(metrics)
        metrics["horizon"] = h
        results.append(metrics)

        os.makedirs(os.path.join(OUTPUT_DIR, "models_saved", "tcn_delta_given_i"), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DIR, "predictions_cache", "tcn_delta_given_i"), exist_ok=True)
        model.save(os.path.join(OUTPUT_DIR, "models_saved", "tcn_delta_given_i", f"h{h}.pt"))
        np.savez(os.path.join(OUTPUT_DIR, "predictions_cache", "tcn_delta_given_i", f"h{h}.npz"), y_true=y_true, y_pred=y_pred)

    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    results_df = pd.DataFrame(results)[["horizon", "MAE", "RMSE", "R2", "DTW"]]
    results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "tcn_delta_given_i_results.csv"), index=False)
    print(results_df)


if __name__ == "__main__":
    main()
