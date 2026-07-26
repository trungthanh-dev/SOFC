"""
Experiment 3, Seq2Seq LSTM -- see main_lstm_delta_given_i.py for the full
rationale (notes/SOFC_data_notes.md section 28-29). Mirrors
main_seq2seq_delta.py plus 4 extra feature channels, one per horizon
(I(t+1), I(t+5), I(t+10), I(t+20), each broadcast across the window) --
since Seq2Seq predicts all 4 horizons from one encoder window, giving it
its own whole future I trajectory mirrors a real controller that knows its
full planned command sequence, not just the next step. Meant for Colab (GPU).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_seq2seq_window_delta, augment_with_future_exogenous
from diagnostics import evaluate_regression, print_metrics
from models.seq2seq_lstm import Seq2SeqLSTMModel

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

    Xw_tr, delta_tr, _ = create_seq2seq_window_delta(X_train, y_train, rid_train, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE)
    Xw_te, delta_te, anchor_te = create_seq2seq_window_delta(X_test, y_test, rid_test, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE)

    Xw_tr = augment_with_future_exogenous(Xw_tr, X_train, I_train, rid_train, WINDOW_SIZE, FORECAST_HORIZONS)
    Xw_te = augment_with_future_exogenous(Xw_te, X_test, I_test, rid_test, WINDOW_SIZE, FORECAST_HORIZONS)
    print("train window:", Xw_tr.shape, delta_tr.shape, " test window:", Xw_te.shape, delta_te.shape)

    model = Seq2SeqLSTMModel(horizons=FORECAST_HORIZONS, hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)
    model.train(Xw_tr, delta_tr, verbose=True)
    delta_pred = model.predict(Xw_te)

    # anchor_te is "now" (last row of window), same for every horizon column.
    y_pred = anchor_te[:, None] + delta_pred
    y_true = anchor_te[:, None] + delta_te

    results = []
    for i, h in enumerate(FORECAST_HORIZONS):
        print(f"\n--- horizon {h} ---")
        metrics = evaluate_regression(y_true[:, i], y_pred[:, i])
        print_metrics(metrics)
        metrics["horizon"] = h
        results.append(metrics)

    os.makedirs(os.path.join(OUTPUT_DIR, "models_saved", "seq2seq_delta_given_i"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "predictions_cache", "seq2seq_delta_given_i"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)

    model.save(os.path.join(OUTPUT_DIR, "models_saved", "seq2seq_delta_given_i", "model.pt"))
    np.savez(os.path.join(OUTPUT_DIR, "predictions_cache", "seq2seq_delta_given_i", "predictions.npz"), y_true=y_true, y_pred=y_pred)

    results_df = pd.DataFrame(results)[["horizon", "MAE", "RMSE", "R2", "DTW"]]
    results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "seq2seq_delta_given_i_results.csv"), index=False)
    print(results_df)


if __name__ == "__main__":
    main()
