"""
Multi-seed version of experiment 3 (notes/SOFC_data_notes.md section 31):
a single run per config couldn't separate a real effect of knowing I(t+h)
from LSTM/TCN/Seq2Seq's own run-to-run training noise. This repeats
baseline vs given-I across SEEDS random seeds per architecture, reports
mean +/- std MAE per (arch, variant, horizon), and flags whether the gap
between the two means clears their combined std -- a simple, conservative
"is this a real effect or just noise" check.

LSTMModel/Seq2SeqLSTMModel gained a `seed` constructor param for this
(TCNModel already had one, ported from FCF for the same reason -- see its
docstring). Delta-target only (the already-proven-best V strategy, section
19/22). Meant for Colab (GPU) -- 3 archs x 2 variants x 5 seeds x 4
horizons; LSTM/TCN train one model per horizon, Seq2Seq trains all 4 at
once, ~15-25 min total based on section 30/31's single-run timings.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import (
    split_by_run, create_sliding_window_delta, create_seq2seq_window_delta,
    augment_with_future_exogenous,
)
from diagnostics import evaluate_regression
from models.lstm import LSTMModel
from models.tcn import TCNModel
from models.seq2seq_lstm import Seq2SeqLSTMModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

I_COL = "I"
SEEDS = [42, 43, 44, 45, 46]


def run_direct(model_cls, model_kwargs, data, use_future_i, seed):
    """LSTM/TCN: one model per horizon (direct-forecast)."""
    X_train, y_train, rid_train, X_test, y_test, rid_test, I_train, I_test = data
    maes = {}
    for h in FORECAST_HORIZONS:
        Xw_tr, delta_tr, _ = create_sliding_window_delta(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
        Xw_te, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
        if use_future_i:
            Xw_tr = augment_with_future_exogenous(Xw_tr, X_train, I_train, rid_train, WINDOW_SIZE, [h])
            Xw_te = augment_with_future_exogenous(Xw_te, X_test, I_test, rid_test, WINDOW_SIZE, [h])

        model = model_cls(seed=seed, **model_kwargs)
        model.train(Xw_tr, delta_tr, verbose=False)
        y_pred = anchor_te + model.predict(Xw_te)
        y_true = anchor_te + delta_te
        maes[h] = evaluate_regression(y_true, y_pred)["MAE"]
    return maes


def run_seq2seq(model_kwargs, data, use_future_i, seed):
    X_train, y_train, rid_train, X_test, y_test, rid_test, I_train, I_test = data
    Xw_tr, delta_tr, _ = create_seq2seq_window_delta(X_train, y_train, rid_train, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE)
    Xw_te, delta_te, anchor_te = create_seq2seq_window_delta(X_test, y_test, rid_test, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE)
    if use_future_i:
        Xw_tr = augment_with_future_exogenous(Xw_tr, X_train, I_train, rid_train, WINDOW_SIZE, FORECAST_HORIZONS)
        Xw_te = augment_with_future_exogenous(Xw_te, X_test, I_test, rid_test, WINDOW_SIZE, FORECAST_HORIZONS)

    model = Seq2SeqLSTMModel(horizons=FORECAST_HORIZONS, seed=seed, **model_kwargs)
    model.train(Xw_tr, delta_tr, verbose=False)
    y_pred = anchor_te[:, None] + model.predict(Xw_te)
    y_true = anchor_te[:, None] + delta_te

    return {h: evaluate_regression(y_true[:, i], y_pred[:, i])["MAE"] for i, h in enumerate(FORECAST_HORIZONS)}


def main():
    df = prepare_data(path=RAW_CSV_PATH)
    train_df, val_df, test_df = split_by_run(df)
    feat_cols = get_features(df)
    data = (
        train_df[feat_cols], train_df[TARGET], train_df["run_id"],
        test_df[feat_cols], test_df[TARGET], test_df["run_id"],
        train_df[I_COL], test_df[I_COL],
    )

    archs = {
        "LSTM": (run_direct, LSTMModel, dict(hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)),
        "TCN": (run_direct, TCNModel, dict(num_channels=(32, 32, 32, 32), kernel_size=3, dropout=0.1, epochs=150, patience=10)),
        "Seq2Seq": (run_seq2seq, None, dict(hidden_size=128, num_layers=2, dropout=0.1, epochs=150, patience=10)),
    }

    rows = []
    t_start = time.time()
    n_runs = len(archs) * 2 * len(SEEDS)
    run_i = 0
    for arch_name, (run_fn, model_cls, kwargs) in archs.items():
        for use_future_i in (False, True):
            variant = "given_I" if use_future_i else "baseline"
            for seed in SEEDS:
                run_i += 1
                t0 = time.time()
                if arch_name == "Seq2Seq":
                    maes = run_fn(kwargs, data, use_future_i, seed)
                else:
                    maes = run_fn(model_cls, kwargs, data, use_future_i, seed)
                elapsed = time.time() - t0
                for h, mae in maes.items():
                    rows.append({"arch": arch_name, "variant": variant, "seed": seed, "horizon": h, "MAE": mae})
                mae_str = ", ".join(f"h{h}={mae:.3f}" for h, mae in maes.items())
                print(f"[{run_i}/{n_runs}] {arch_name}/{variant}/seed={seed} ({elapsed:.0f}s): {mae_str}")

    total_min = (time.time() - t_start) / 60
    print(f"\nTotal time: {total_min:.1f} min")

    raw_df = pd.DataFrame(rows)
    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    raw_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "given_i_multiseed_raw.csv"), index=False)

    summary = raw_df.groupby(["arch", "variant", "horizon"])["MAE"].agg(["mean", "std"]).reset_index()
    summary.to_csv(os.path.join(OUTPUT_DIR, "reports", "given_i_multiseed_summary.csv"), index=False)

    print(f"\n=== Summary (mean +/- std MAE across {len(SEEDS)} seeds) ===")
    print(summary.to_string(index=False))

    print("\n=== Verdict per arch/horizon (gap vs combined std) ===")
    verdicts = []
    for arch_name in archs:
        for h in FORECAST_HORIZONS:
            base = summary[(summary.arch == arch_name) & (summary.variant == "baseline") & (summary.horizon == h)].iloc[0]
            given = summary[(summary.arch == arch_name) & (summary.variant == "given_I") & (summary.horizon == h)].iloc[0]
            gap = base["mean"] - given["mean"]
            combined_std = base["std"] + given["std"]
            if gap > combined_std:
                verdict = "given_I THAT SU TOT HON"
            elif -gap > combined_std:
                verdict = "given_I THAT SU TE HON"
            else:
                verdict = "KHONG PHAN BIET DUOC (trong nhieu)"
            print(f"{arch_name} h={h}: baseline={base['mean']:.3f}+/-{base['std']:.3f}  "
                  f"given_I={given['mean']:.3f}+/-{given['std']:.3f}  gap={gap:+.3f}  -> {verdict}")
            verdicts.append({"arch": arch_name, "horizon": h, "baseline_mean": base["mean"], "baseline_std": base["std"],
                              "given_i_mean": given["mean"], "given_i_std": given["std"], "gap": gap, "verdict": verdict})

    pd.DataFrame(verdicts).to_csv(os.path.join(OUTPUT_DIR, "reports", "given_i_multiseed_verdict.csv"), index=False)


if __name__ == "__main__":
    main()
