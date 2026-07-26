"""
Multi-seed validation of the flagship claim (notes/SOFC_data_notes.md
sections 19/22): does Delta-Target Reformulation on LSTM/TCN/Seq2Seq
genuinely beat the trivial persistence baseline for V, with the margin
growing at longer horizons -- especially Seq2Seq-delta at h=20 (-15.3% in
the original single run, section 19)? That conclusion rested on ONE run
per model. This repeats each delta-target model across SEEDS random seeds,
reports mean +/- std MAE, and checks whether persistence (a fixed number,
no training/randomness involved) falls outside the model's
[mean - std, mean + std] band -- i.e. whether the "win" survives training
noise, using the same conservative logic as main_given_i_multiseed.py.

Runs LSTM-delta, TCN-delta, Seq2Seq-delta only (RF/XGBoost-delta are
already deterministic -- fixed random_state, no need to re-run). Meant for
Colab (GPU) -- 3 archs x 5 seeds x 4 horizons, LSTM/TCN train one model per
horizon, Seq2Seq trains all 4 at once; ~10-15 min based on section 33's
timing for a similar-sized sweep.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_sliding_window_delta, create_seq2seq_window_delta
from diagnostics import evaluate_regression
from models.lstm import LSTMModel
from models.tcn import TCNModel
from models.seq2seq_lstm import Seq2SeqLSTMModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

SEEDS = [42, 43, 44, 45, 46]


def run_direct(model_cls, model_kwargs, data, seed):
    """LSTM/TCN: one model per horizon (direct-forecast)."""
    X_train, y_train, rid_train, X_test, y_test, rid_test = data
    maes = {}
    for h in FORECAST_HORIZONS:
        Xw_tr, delta_tr, _ = create_sliding_window_delta(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
        Xw_te, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)

        model = model_cls(seed=seed, **model_kwargs)
        model.train(Xw_tr, delta_tr, verbose=False)
        y_pred = anchor_te + model.predict(Xw_te)
        y_true = anchor_te + delta_te
        maes[h] = evaluate_regression(y_true, y_pred)["MAE"]
    return maes


def run_seq2seq(model_kwargs, data, seed):
    X_train, y_train, rid_train, X_test, y_test, rid_test = data
    Xw_tr, delta_tr, _ = create_seq2seq_window_delta(X_train, y_train, rid_train, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE)
    Xw_te, delta_te, anchor_te = create_seq2seq_window_delta(X_test, y_test, rid_test, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE)

    model = Seq2SeqLSTMModel(horizons=FORECAST_HORIZONS, seed=seed, **model_kwargs)
    model.train(Xw_tr, delta_tr, verbose=False)
    y_pred = anchor_te[:, None] + model.predict(Xw_te)
    y_true = anchor_te[:, None] + delta_te

    return {h: evaluate_regression(y_true[:, i], y_pred[:, i])["MAE"] for i, h in enumerate(FORECAST_HORIZONS)}


def persistence_mae(X_test, y_test, rid_test):
    """Fixed number per horizon -- no training, no randomness."""
    maes = {}
    for h in FORECAST_HORIZONS:
        _, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
        y_true = anchor_te + delta_te
        maes[h] = evaluate_regression(y_true, anchor_te)["MAE"]
    return maes


def main():
    df = prepare_data(path=RAW_CSV_PATH)
    train_df, val_df, test_df = split_by_run(df)
    feat_cols = get_features(df)
    data = (
        train_df[feat_cols], train_df[TARGET], train_df["run_id"],
        test_df[feat_cols], test_df[TARGET], test_df["run_id"],
    )
    X_test, y_test, rid_test = data[3], data[4], data[5]

    persist = persistence_mae(X_test, y_test, rid_test)
    print("Persistence MAE (fixed, no seed):", {h: round(v, 4) for h, v in persist.items()})

    archs = {
        "LSTM-delta": (run_direct, LSTMModel, dict(hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)),
        "TCN-delta": (run_direct, TCNModel, dict(num_channels=(32, 32, 32, 32), kernel_size=3, dropout=0.1, epochs=150, patience=10)),
        "Seq2Seq-delta": (run_seq2seq, None, dict(hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)),
    }

    rows = []
    t_start = time.time()
    n_runs = len(archs) * len(SEEDS)
    run_i = 0
    for arch_name, (run_fn, model_cls, kwargs) in archs.items():
        for seed in SEEDS:
            run_i += 1
            t0 = time.time()
            if arch_name == "Seq2Seq-delta":
                maes = run_fn(kwargs, data, seed)
            else:
                maes = run_fn(model_cls, kwargs, data, seed)
            elapsed = time.time() - t0
            for h, mae in maes.items():
                rows.append({"arch": arch_name, "seed": seed, "horizon": h, "MAE": mae})
            mae_str = ", ".join(f"h{h}={mae:.3f}" for h, mae in maes.items())
            print(f"[{run_i}/{n_runs}] {arch_name}/seed={seed} ({elapsed:.0f}s): {mae_str}")

    total_min = (time.time() - t_start) / 60
    print(f"\nTotal time: {total_min:.1f} min")

    raw_df = pd.DataFrame(rows)
    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    raw_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "delta_vs_persistence_multiseed_raw.csv"), index=False)

    summary = raw_df.groupby(["arch", "horizon"])["MAE"].agg(["mean", "std"]).reset_index()
    summary.to_csv(os.path.join(OUTPUT_DIR, "reports", "delta_vs_persistence_multiseed_summary.csv"), index=False)

    print(f"\n=== Summary (mean +/- std MAE across {len(SEEDS)} seeds) vs fixed persistence ===")
    verdicts = []
    for arch_name in archs:
        for h in FORECAST_HORIZONS:
            row = summary[(summary.arch == arch_name) & (summary.horizon == h)].iloc[0]
            mean, std = row["mean"], row["std"]
            p = persist[h]
            gap = p - mean  # positive => model beats persistence on average
            if gap > std:
                verdict = "model THAT SU THANG persistence"
            elif -gap > std:
                verdict = "model THAT SU THUA persistence"
            else:
                verdict = "KHONG PHAN BIET DUOC (trong nhieu)"
            pct = (mean - p) / p * 100
            print(f"{arch_name} h={h}: model={mean:.3f}+/-{std:.3f}  persistence={p:.3f}  "
                  f"({pct:+.1f}%)  -> {verdict}")
            verdicts.append({"arch": arch_name, "horizon": h, "model_mean": mean, "model_std": std,
                              "persistence": p, "gap": gap, "pct_vs_persistence": pct, "verdict": verdict})

    pd.DataFrame(verdicts).to_csv(os.path.join(OUTPUT_DIR, "reports", "delta_vs_persistence_multiseed_verdict.csv"), index=False)


if __name__ == "__main__":
    main()
