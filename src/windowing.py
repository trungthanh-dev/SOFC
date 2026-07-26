import numpy as np
import pandas as pd

from config import WINDOW_SIZE, FORECAST_HORIZONS, TRAIN_RUNS, VAL_RUNS, TEST_RUNS


def split_by_run(df, train_runs=TRAIN_RUNS, val_runs=VAL_RUNS, test_runs=TEST_RUNS):
    train_df = df[df["run_id"].isin(train_runs)].copy()
    val_df = df[df["run_id"].isin(val_runs)].copy()
    test_df = df[df["run_id"].isin(test_runs)].copy()
    return train_df, val_df, test_df


def _iter_runs(X: pd.DataFrame, y: pd.Series, run_id: pd.Series):
    """
    Yield (X_run, y_run) for each run_id, in order of first appearance.
    Every windowing function below loops over this instead of X/y directly,
    so a window/lag never spans two run_id's -- SOFC's 8 (now 5) runs are
    chronologically disjoint (gaps of hours to months apart), unlike FCF's
    per-ship series which are one continuous run each.
    """
    for rid in pd.unique(run_id):
        mask = (run_id == rid).to_numpy()
        yield X.iloc[mask], y.iloc[mask]


def create_sliding_window(X: pd.DataFrame, y: pd.Series, run_id: pd.Series, window_size=WINDOW_SIZE, horizon=1):
    """
    Run-aware counterpart of FCF's window.create_sliding_window(): one
    (window, single-horizon-target) pair per direct-forecast sample.

    Returns
    -------
    X_window : (samples, window_size, features)
    y_window : (samples,)
    """
    X_window, y_window = [], []
    for X_run, y_run in _iter_runs(X, y, run_id):
        n = len(X_run) - window_size - horizon + 1
        for i in range(max(n, 0)):
            X_window.append(X_run.iloc[i:i + window_size].values)
            y_window.append(y_run.iloc[i + window_size + horizon - 1])
    return np.array(X_window), np.array(y_window)


def create_sliding_window_delta(X: pd.DataFrame, y: pd.Series, run_id: pd.Series, window_size=WINDOW_SIZE, horizon=1):
    """
    Run-aware counterpart of FCF's window.create_sliding_window_delta().
    Target is y(now + horizon) - y(now), "now" = last row of the window
    (no leakage, same anchor definition as FCF). Fixes persistence bias:
    copying Lag1 now predicts delta=0, which is only right when V doesn't
    change.

    Returns
    -------
    X_window : (samples, window_size, features)
    delta_window : (samples,) -- y(now + horizon) - y(now)
    anchor_window : (samples,) -- y(now), to reconstruct: anchor + delta_hat
    """
    X_window, delta_window, anchor_window = [], [], []
    for X_run, y_run in _iter_runs(X, y, run_id):
        n = len(X_run) - window_size - horizon + 1
        for i in range(max(n, 0)):
            anchor = y_run.iloc[i + window_size - 1]
            target = y_run.iloc[i + window_size + horizon - 1]
            X_window.append(X_run.iloc[i:i + window_size].values)
            anchor_window.append(anchor)
            delta_window.append(target - anchor)
    return np.array(X_window), np.array(delta_window), np.array(anchor_window)


def create_seq2seq_window(X: pd.DataFrame, y: pd.Series, run_id: pd.Series, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE):
    """
    Run-aware counterpart of FCF's window.create_seq2seq_window(): one
    (window, all-horizons-target) pair per sample.

    Returns
    -------
    X_window : (samples, window_size, features)
    y_window : (samples, n_horizons)
    """
    max_h = max(horizons)
    X_window, y_window = [], []
    for X_run, y_run in _iter_runs(X, y, run_id):
        n = len(X_run) - window_size - max_h + 1
        for i in range(max(n, 0)):
            X_window.append(X_run.iloc[i:i + window_size].values)
            targets = [y_run.iloc[i + window_size + h - 1] for h in horizons]
            y_window.append(targets)
    return np.array(X_window), np.array(y_window)


def create_seq2seq_window_delta(X: pd.DataFrame, y: pd.Series, run_id: pd.Series, horizons=FORECAST_HORIZONS, window_size=WINDOW_SIZE):
    """
    Delta-target counterpart of create_seq2seq_window(), run-aware version
    of FCF's window.create_seq2seq_window_delta(). One anchor per sample
    (last row of the window), shared across all horizon columns.

    Returns
    -------
    X_window : (samples, window_size, features)
    delta_window : (samples, n_horizons)
    anchor_window : (samples,)
    """
    max_h = max(horizons)
    X_window, delta_window, anchor_window = [], [], []
    for X_run, y_run in _iter_runs(X, y, run_id):
        n = len(X_run) - window_size - max_h + 1
        for i in range(max(n, 0)):
            anchor = y_run.iloc[i + window_size - 1]
            deltas = [y_run.iloc[i + window_size + h - 1] - anchor for h in horizons]
            X_window.append(X_run.iloc[i:i + window_size].values)
            anchor_window.append(anchor)
            delta_window.append(deltas)
    return np.array(X_window), np.array(delta_window), np.array(anchor_window)


def reshape_for_random_forest(X: np.ndarray):
    """Reshape 3D sliding-window data into 2D for Random Forest / XGBoost."""
    return X.reshape(X.shape[0], -1)


def augment_with_future_exogenous(X_window, X_df, exo_series, run_id, window_size, horizons):
    """
    Append known-in-advance future value(s) of an exogenous series (e.g. I,
    the operator-set current setpoint -- known to whoever sets it, unlike a
    target that must be forecast) as extra feature channel(s) on a 3D
    sliding window, for sequence models (LSTM/TCN/Seq2Seq). One channel per
    horizon in `horizons`, each holding exo(t+h) broadcast across all
    window_size timesteps (a constant-covariate injection -- no model-code
    changes needed since input_size is auto-detected from X.shape[2]).

    For a direct-forecast model (one model per horizon), pass a single-
    element `horizons` list. For Seq2Seq (predicts all horizons from one
    window), pass the full horizons list -- this mirrors a real controller
    knowing its whole planned command trajectory, not just the next step.

    Reuses create_sliding_window() on the exogenous column itself so the
    alignment (same run-aware windows, same sample order) matches X_window
    exactly -- see notes/SOFC_data_notes.md section 29 (RF/XGBoost version
    of this same idea, done via flat concatenation instead).

    Returns
    -------
    (samples, window_size, n_features + len(horizons))
    """
    n_samples = X_window.shape[0]
    channels = []
    for h in horizons:
        _, future_vals = create_sliding_window(X_df, exo_series, run_id, window_size=window_size, horizon=h)
        # A single horizon's own windowing (n = len(run) - window_size - h + 1)
        # can yield more samples than a multi-horizon window built against
        # max(horizons) (Seq2Seq's n = len(run) - window_size - max(horizons) + 1).
        # Both iterate the same run from i=0 in the same order, so truncating
        # to the shared count keeps every sample's window position aligned.
        assert len(future_vals) >= n_samples, (
            f"h={h}: got {len(future_vals)} future values, need at least {n_samples} "
            "to align with X_window -- horizons must not exceed X_window's own max horizon"
        )
        future_vals = future_vals[:n_samples]
        channels.append(np.repeat(future_vals[:, None, None], window_size, axis=1))
    return np.concatenate([X_window] + channels, axis=2)
