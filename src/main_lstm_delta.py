"""
Delta-Target Reformulation for LSTM: train on y(t+h) - y(t) instead of the
raw future value, reconstruct y_hat(t+h) = anchor + delta_hat before
evaluating. Raw-target baseline (main_lstm.py) is left untouched. Meant
for Colab (GPU).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_sliding_window_delta
from diagnostics import evaluate_regression, print_metrics
from models.lstm import LSTMModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


def main():
    df = prepare_data(path=RAW_CSV_PATH)
    train_df, val_df, test_df = split_by_run(df)
    feat_cols = get_features(df)

    X_train, y_train, rid_train = train_df[feat_cols], train_df[TARGET], train_df["run_id"]
    X_test, y_test, rid_test = test_df[feat_cols], test_df[TARGET], test_df["run_id"]

    results = []
    for h in FORECAST_HORIZONS:
        print(f"\n=== LSTM-delta h={h} ===")
        Xw_tr, delta_tr, _ = create_sliding_window_delta(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
        Xw_te, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)

        model = LSTMModel(hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)
        model.train(Xw_tr, delta_tr, verbose=True)
        delta_pred = model.predict(Xw_te)
        y_pred = anchor_te + delta_pred
        y_true = anchor_te + delta_te

        metrics = evaluate_regression(y_true, y_pred)
        print_metrics(metrics)
        metrics["horizon"] = h
        results.append(metrics)

        os.makedirs(os.path.join(OUTPUT_DIR, "models_saved", "lstm_delta"), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DIR, "predictions_cache", "lstm_delta"), exist_ok=True)
        model.save(os.path.join(OUTPUT_DIR, "models_saved", "lstm_delta", f"h{h}.pt"))
        np.savez(os.path.join(OUTPUT_DIR, "predictions_cache", "lstm_delta", f"h{h}.npz"), y_true=y_true, y_pred=y_pred)

    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    results_df = pd.DataFrame(results)[["horizon", "MAE", "RMSE", "R2", "DTW"]]
    results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "lstm_delta_results.csv"), index=False)
    print(results_df)


if __name__ == "__main__":
    main()
