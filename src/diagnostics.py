import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def dtw_distance(y_true, y_pred, window=10):
    """
    Dynamic Time Warping distance between two 1D sequences, restricted to a
    Sakoe-Chiba band of the given radius around the diagonal. Full O(n*m)
    DTW is infeasible at this project's test-set sizes; forecast/target
    sequences here are the same length and only ever drift by a few steps,
    so a small band gives the same answer as full DTW while keeping memory
    at O(m) (two rolling rows) and time at O(n * window).
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)

    n = len(y_true)
    m = len(y_pred)
    window = max(window, abs(n - m))

    prev_row = np.full(m + 1, np.inf)
    curr_row = np.full(m + 1, np.inf)
    prev_row[0] = 0.0

    for i in range(1, n + 1):
        curr_row.fill(np.inf)
        j_lo = max(1, i - window)
        j_hi = min(m, i + window)
        for j in range(j_lo, j_hi + 1):
            cost = abs(y_true[i - 1] - y_pred[j - 1])
            curr_row[j] = cost + min(prev_row[j], curr_row[j - 1], prev_row[j - 1])
        prev_row, curr_row = curr_row, prev_row

    return prev_row[m] / (n + m)


def evaluate_regression(y_true, y_pred, dtw_window=10):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    dtw = dtw_distance(y_true, y_pred, window=dtw_window)
    return {"MAE": mae, "RMSE": rmse, "R2": r2, "DTW": dtw}


def print_metrics(metrics):
    print(f"MAE  : {metrics['MAE']:.6f}")
    print(f"RMSE : {metrics['RMSE']:.6f}")
    print(f"R^2  : {metrics['R2']:.6f}")
    print(f"DTW  : {metrics['DTW']:.6f}")


def persistence_baseline_metrics(y_true, y_lag1):
    """
    "Predict the last known value" baseline (copy V_Lag1 forward as the
    forecast), evaluated with the same metrics as a real model. A real
    model that scores close to (or worse than) this baseline is relying on
    persistence rather than learning genuine dynamics -- the same failure
    mode FCF found via RF/XGBoost feature importance on Lag1 (~0.8), which
    motivated the Delta-Target Reformulation.
    """
    return evaluate_regression(y_true, y_lag1)


def lag1_feature_importance(model, feature_cols, window_size, lag1_col="V_Lag1"):
    """
    Extract the feature importance of V_Lag1 from a trained RandomForestModel
    / XGBoostModel. Both models flatten (window_size, n_features) windows
    into a flat (window_size * n_features,) vector before training (see
    windowing.reshape_for_random_forest), in row-major order -- so
    V_Lag1's importance appears once per window position (window_size
    entries total, one per past timestep), not just once.

    Returns
    -------
    dict with "per_timestep" (array of length window_size) and "total"
    (their sum) -- "total" is the number comparable to FCF's reported
    ~0.8 finding, since it aggregates every window position's copy of the
    feature into one number.
    """
    importances = model.feature_importance()
    n_features = len(feature_cols)
    assert len(importances) == window_size * n_features, (
        f"expected {window_size * n_features} importances, got {len(importances)} "
        "-- feature_cols/window_size don't match the model's training input"
    )
    lag1_idx = feature_cols.index(lag1_col)
    per_timestep = importances.reshape(window_size, n_features)[:, lag1_idx]
    return {"per_timestep": per_timestep, "total": per_timestep.sum()}
