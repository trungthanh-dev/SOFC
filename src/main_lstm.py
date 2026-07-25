"""
Train LSTM (direct forecast, one model per horizon) on the SOFC voltage
dataset. Meant for Colab (GPU) -- see notebooks/SOFC_Colab_Forecasting.ipynb,
which just cd's into src/ and runs `python main_lstm.py`.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_sliding_window
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
        print(f"\n=== LSTM h={h} ===")
        Xw_tr, yw_tr = create_sliding_window(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
        Xw_te, yw_te = create_sliding_window(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)

        model = LSTMModel(hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)
        model.train(Xw_tr, yw_tr, verbose=True)
        y_pred = model.predict(Xw_te)

        metrics = evaluate_regression(yw_te, y_pred)
        print_metrics(metrics)
        metrics["horizon"] = h
        results.append(metrics)

        os.makedirs(os.path.join(OUTPUT_DIR, "models_saved", "lstm"), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DIR, "predictions_cache", "lstm"), exist_ok=True)
        model.save(os.path.join(OUTPUT_DIR, "models_saved", "lstm", f"h{h}.pt"))
        np.savez(os.path.join(OUTPUT_DIR, "predictions_cache", "lstm", f"h{h}.npz"), y_true=yw_te, y_pred=y_pred)

    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    results_df = pd.DataFrame(results)[["horizon", "MAE", "RMSE", "R2", "DTW"]]
    results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "lstm_results.csv"), index=False)
    print(results_df)


if __name__ == "__main__":
    main()
