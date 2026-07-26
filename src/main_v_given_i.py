"""
Experiment 3 (notes/SOFC_data_notes.md section 28): does forecasting V(t+h)
improve if I(t+h) is given as a KNOWN exogenous input, instead of forecast
blind? Motivated by section 27's oracle-decomposition finding -- I is the
operator-set setpoint (known in advance to whoever sets it), so a real MPC
controller would know its own future I command. This mirrors the NARX-style
conditioning used by Tofigh/Salehi 2024 (Journal of Power Sources) found in
the literature search (section 24).

Reuses create_sliding_window() on the I column itself to get I(t+h) aligned
to the same window positions as the V windows (no new windowing code needed),
then appends it as one extra feature to the flattened RF/XGBoost input.
Trains both raw-target and delta-target V models, with and without the
I(t+h) feature, so the improvement from adding it is isolated cleanly.

Runs locally, no GPU needed.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_sliding_window, create_sliding_window_delta, reshape_for_random_forest
from diagnostics import evaluate_regression
from models.random_forest import RandomForestModel
from models.xgboost_model import XGBoostModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")

I_COL = "I"


def augment_with_future_I(Xw2d, X_df, I_series, rid, window_size, horizon):
    """Append I(t+h) (future/exogenous, known-in-advance current) as one
    extra column to an already-flattened (samples, window_size*n_features)
    array. Reuses create_sliding_window on the I column itself so the
    alignment (same run-aware windows, same sample order) matches Xw2d
    exactly -- no new windowing logic."""
    _, I_future = create_sliding_window(X_df, I_series, rid, window_size=window_size, horizon=horizon)
    assert len(I_future) == Xw2d.shape[0]
    return np.hstack([Xw2d, I_future.reshape(-1, 1)])


def main():
    df = prepare_data(path=RAW_CSV_PATH, target=TARGET)  # target="V" (default)
    train_df, val_df, test_df = split_by_run(df)
    feat_cols = get_features(df, target=TARGET)

    X_train, y_train, rid_train = train_df[feat_cols], train_df[TARGET], train_df["run_id"]
    X_test, y_test, rid_test = test_df[feat_cols], test_df[TARGET], test_df["run_id"]
    I_train, I_test = train_df[I_COL], test_df[I_COL]

    model_families = [
        ("random_forest", RandomForestModel, dict(n_estimators=300)),
        ("xgboost", XGBoostModel, dict(n_estimators=300)),
    ]

    all_results = []

    for name, cls, kwargs in model_families:
        for variant in ("raw", "delta"):
            for use_future_I in (False, True):
                tag = f"{name}_{variant}{'_given_I' if use_future_I else ''}"
                results = []
                for h in FORECAST_HORIZONS:
                    if variant == "raw":
                        Xw_tr, yw_tr = create_sliding_window(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
                        Xw_te, yw_te = create_sliding_window(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
                        Xw_tr2d, Xw_te2d = reshape_for_random_forest(Xw_tr), reshape_for_random_forest(Xw_te)
                        train_target, test_anchor, test_target_true = yw_tr, None, yw_te
                    else:
                        Xw_tr, delta_tr, _ = create_sliding_window_delta(X_train, y_train, rid_train, window_size=WINDOW_SIZE, horizon=h)
                        Xw_te, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
                        Xw_tr2d, Xw_te2d = reshape_for_random_forest(Xw_tr), reshape_for_random_forest(Xw_te)
                        train_target, test_anchor, test_target_true = delta_tr, anchor_te, anchor_te + delta_te

                    if use_future_I:
                        Xw_tr2d = augment_with_future_I(Xw_tr2d, X_train, I_train, rid_train, WINDOW_SIZE, h)
                        Xw_te2d = augment_with_future_I(Xw_te2d, X_test, I_test, rid_test, WINDOW_SIZE, h)

                    t0 = time.time()
                    model = cls(**kwargs)
                    model.train(Xw_tr2d, train_target)
                    pred = model.predict(Xw_te2d)
                    y_pred = pred if variant == "raw" else test_anchor + pred
                    elapsed = time.time() - t0

                    metrics = evaluate_regression(test_target_true, y_pred)
                    metrics["horizon"] = h
                    metrics["model"] = tag
                    results.append(metrics)
                    print(f"[{tag}] h={h}  MAE={metrics['MAE']:.4f} RMSE={metrics['RMSE']:.4f} "
                          f"R2={metrics['R2']:.4f} DTW={metrics['DTW']:.4f}  ({elapsed:.1f}s)")

                all_results.extend(results)

    os.makedirs(os.path.join(OUTPUT_DIR, "reports"), exist_ok=True)
    results_df = pd.DataFrame(all_results)[["model", "horizon", "MAE", "RMSE", "R2", "DTW"]]
    results_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "v_given_i_results.csv"), index=False)
    print("\n", results_df.to_string(index=False))


if __name__ == "__main__":
    main()
