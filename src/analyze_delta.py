"""
Deep-dive into WHY Delta-Target Reformulation helps LSTM/TCN/Seq2Seq at every
horizon but only helps RF/XGBoost at h=1 (see notes/SOFC_data_notes.md
section 19 for the raw result table this explains).

Two angles, both computed from artifacts already on disk (no retraining):
  1. Persistence floor: what "predict delta=0" (anchor forward) scores, per
     horizon -- the baseline every delta model must beat.
  2. Delta-variance shrinkage: std(delta_pred) / std(delta_true) per model
     per horizon. A ratio << 1 means the model is regressing toward
     delta=0 (i.e. collapsing back toward the same persistence shortcut
     Delta-Target was supposed to remove) instead of tracking real swings.
  3. (RF/XGBoost only) V_Lag1 feature importance across all 4 horizons, raw
     vs delta -- extends the h=1-only check in section 14.3.

Requires: outputs/predictions_cache/{model}_delta/h{h}.npz (already merged
locally per section 20) and outputs/models_saved/{random_forest,xgboost}(_delta)/h{h}.pkl.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WINDOW_SIZE, FORECAST_HORIZONS
from features import prepare_data, get_features, TARGET
from windowing import split_by_run, create_sliding_window_delta
from diagnostics import evaluate_regression, lag1_feature_importance
from models.random_forest import RandomForestModel
from models.xgboost_model import XGBoostModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_CSV_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "DataTime_export.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
PRED_DIR = os.path.join(OUTPUT_DIR, "predictions_cache")
MODEL_DIR = os.path.join(OUTPUT_DIR, "models_saved")

DELTA_MODELS_PER_H = ["random_forest_delta", "xgboost_delta", "lstm_delta", "tcn_delta"]
SEQ2SEQ_DELTA_DIR = "seq2seq_delta"


def load_per_h_npz(model_dir, horizon):
    path = os.path.join(PRED_DIR, model_dir, f"h{horizon}.npz")
    d = np.load(path)
    return d["y_true"], d["y_pred"]


def load_seq2seq_npz():
    path = os.path.join(PRED_DIR, SEQ2SEQ_DELTA_DIR, "predictions.npz")
    d = np.load(path)
    return d["y_true"], d["y_pred"]  # (n, 4) each, columns == FORECAST_HORIZONS order


def main():
    df = prepare_data(path=RAW_CSV_PATH)
    _, _, test_df = split_by_run(df)
    feat_cols = get_features(df)
    X_test, y_test, rid_test = test_df[feat_cols], test_df[TARGET], test_df["run_id"]

    print("=" * 78)
    print("1) PERSISTENCE FLOOR (predict delta=0, i.e. y_hat = anchor) per horizon")
    print("=" * 78)
    anchors, delta_trues = {}, {}
    persistence_rows = []
    for h in FORECAST_HORIZONS:
        _, delta_te, anchor_te = create_sliding_window_delta(X_test, y_test, rid_test, window_size=WINDOW_SIZE, horizon=h)
        anchors[h] = anchor_te
        delta_trues[h] = delta_te
        y_true = anchor_te + delta_te
        metrics = evaluate_regression(y_true, anchor_te)
        metrics["horizon"] = h
        metrics["std_delta_true"] = float(np.std(delta_te))
        persistence_rows.append(metrics)
    pers_df = pd.DataFrame(persistence_rows)[["horizon", "MAE", "RMSE", "R2", "DTW", "std_delta_true"]]
    print(pers_df.to_string(index=False))

    print()
    print("=" * 78)
    print("2) DELTA-VARIANCE SHRINKAGE: std(delta_pred) / std(delta_true) per model/horizon")
    print("=" * 78)
    shrink_rows = []
    for model_dir in DELTA_MODELS_PER_H:
        for h in FORECAST_HORIZONS:
            y_true, y_pred = load_per_h_npz(model_dir, h)
            anchor_te = anchors[h]
            assert len(y_true) == len(anchor_te), f"{model_dir} h={h}: length mismatch, re-run split/window with same config"
            delta_true = y_true - anchor_te
            delta_pred = y_pred - anchor_te
            # sanity check: recovered delta_true should match the saved delta_te exactly
            resid = np.max(np.abs(delta_true - delta_trues[h]))
            std_true = np.std(delta_true)
            std_pred = np.std(delta_pred)
            corr = np.corrcoef(delta_true, delta_pred)[0, 1]
            shrink_rows.append({
                "model": model_dir, "horizon": h,
                "std_delta_true": std_true, "std_delta_pred": std_pred,
                "shrink_ratio": std_pred / std_true, "corr": corr,
                "sanity_resid_max": resid,
            })
    # seq2seq_delta: one file, 4 horizon columns
    y_true_all, y_pred_all = load_seq2seq_npz()
    for i, h in enumerate(FORECAST_HORIZONS):
        anchor_te = anchors[h]
        # seq2seq_delta test set length can differ slightly from the per-h windows
        # (single window per sample covering all horizons) -- align on min length
        n = min(len(y_true_all), len(anchor_te))
        delta_true = y_true_all[:n, i] - anchor_te[:n]
        delta_pred = y_pred_all[:n, i] - anchor_te[:n]
        std_true = np.std(delta_true)
        std_pred = np.std(delta_pred)
        corr = np.corrcoef(delta_true, delta_pred)[0, 1]
        shrink_rows.append({
            "model": "seq2seq_delta", "horizon": h,
            "std_delta_true": std_true, "std_delta_pred": std_pred,
            "shrink_ratio": std_pred / std_true, "corr": corr,
            "sanity_resid_max": np.nan,
        })

    shrink_df = pd.DataFrame(shrink_rows)
    print(shrink_df.to_string(index=False))
    shrink_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "delta_shrinkage_analysis.csv"), index=False)

    print()
    print("=" * 78)
    print("3) V_Lag1 feature importance -- RF/XGBoost, raw vs delta, all 4 horizons")
    print("=" * 78)
    fi_rows = []
    for family_name, cls, dirs in [
        ("RandomForest", RandomForestModel, ("random_forest", "random_forest_delta")),
        ("XGBoost", XGBoostModel, ("xgboost", "xgboost_delta")),
    ]:
        for variant, model_dir in zip(("raw", "delta"), dirs):
            for h in FORECAST_HORIZONS:
                model_path = os.path.join(MODEL_DIR, model_dir, f"h{h}.pkl")
                if not os.path.exists(model_path):
                    print(f"  (skip {model_dir} h={h}: {model_path} not found)")
                    continue
                model = cls()
                model.load(model_path)
                fi = lag1_feature_importance(model, feat_cols, WINDOW_SIZE)
                fi_rows.append({
                    "family": family_name, "variant": variant, "horizon": h,
                    "lag1_importance_total": fi["total"],
                })
    fi_df = pd.DataFrame(fi_rows)
    print(fi_df.to_string(index=False))
    fi_df.to_csv(os.path.join(OUTPUT_DIR, "reports", "delta_lag1_importance.csv"), index=False)


if __name__ == "__main__":
    main()
