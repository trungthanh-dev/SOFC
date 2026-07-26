import pandas as pd

from preprocessing import load_and_clean

TARGET = "V"

# W = V * I algebraically (verified: residual ~1e-6 on rows with I>0), so it
# leaks the target directly -- same reasoning as FCF's LEAKAGE_KEYWORDS
# (ShaftPower/ShaftTorque/RotationSpeed excluded when predicting fuel).
LEAKAGE_COLUMNS = ["W"]

# Confirmed via load_and_clean() + describe() per run_id: these 3 runs sit at
# or just above the V=0 filter threshold for their entire length (run0: V in
# [0.3, 0.9], run2: V in [0.3, 0.4], run3: mean 1.28/std 2.17 with one spike
# to 12.6) -- not representative generating segments, just noise-floor V
# that happened to clear the raw V!=0 filter.
DEGENERATE_RUNS = [0, 2, 3]

# Lag / rolling-window / slope features built from the target itself, same
# construction as FCF's add_target_history_features(): every value uses
# ONLY past rows (.shift() applied before .rolling()), so none of these can
# leak the current or future timestep.
TARGET_LAG_STEPS = (1, 5)
TARGET_ROLLING_WINDOWS = (5,)
TARGET_SLOPE_WINDOWS = (5,)


def remove_leakage_features(df, leakage_columns=LEAKAGE_COLUMNS):
    return df.drop(columns=leakage_columns, errors="ignore")


def remove_degenerate_runs(df, degenerate_runs=DEGENERATE_RUNS):
    df = df[~df["run_id"].isin(degenerate_runs)].copy()
    order = df["run_id"].drop_duplicates().tolist()
    remap = {old: new for new, old in enumerate(order)}
    df["run_id"] = df["run_id"].map(remap)
    return df


def add_target_history_features(
    df,
    target=TARGET,
    lag_steps=TARGET_LAG_STEPS,
    rolling_windows=TARGET_ROLLING_WINDOWS,
    slope_windows=TARGET_SLOPE_WINDOWS,
    prefix="V",
):
    """
    Add Lag/RollingMean/RollingStd/Slope features built from the target,
    same formulas as FCF's preprocessing.add_target_history_features() --
    but grouped by run_id, since SOFC's runs are chronologically disjoint
    (gaps of hours to months) unlike FCF's one-run-per-ship series. Without
    grouping, the first row of run N would silently use run N-1's last V
    value as its "Lag1", which isn't real history -- it's a different
    operating session entirely.

    The first `max(lag_steps + rolling_windows + slope_windows)` rows of
    EACH run will have NaN in these new columns (no in-run history yet) --
    fill_missing_per_run() must be re-run after this, same as FCF re-runs
    handle_missing() after this step.
    """
    df = df.copy()
    g = df.groupby("run_id", group_keys=False)[target]

    for lag in lag_steps:
        df[f"{prefix}_Lag{lag}"] = g.shift(lag)

    shifted = g.shift(1)
    shifted_by_run = shifted.groupby(df["run_id"])
    for window in rolling_windows:
        df[f"{prefix}_RollingMean{window}"] = (
            shifted_by_run.rolling(window).mean().reset_index(level=0, drop=True)
        )
        df[f"{prefix}_RollingStd{window}"] = (
            shifted_by_run.rolling(window).std().reset_index(level=0, drop=True)
        )

    for window in slope_windows:
        df[f"{prefix}_Slope{window}"] = (g.shift(1) - g.shift(1 + window)) / window

    return df


def fill_missing_per_run(df, columns):
    """
    ffill then bfill, computed independently within each run_id, so the
    leading NaNs that add_target_history_features() introduces at the start
    of each run only ever get filled from THAT run's own values -- never
    bleed in from a different (chronologically distant) run.
    """
    df = df.copy()
    df[columns] = df.groupby("run_id")[columns].transform(lambda s: s.ffill().bfill())
    return df


def get_features(df, target=TARGET):
    return [col for col in df.columns if col not in (target, "run_id")]


def prepare_data(path=None, target=TARGET, leakage_columns=None):
    """
    Full data-prep pipeline for the forecasting phase (on top of the
    paper-faithful load_and_clean()): drop leakage column(s), drop the
    3 degenerate runs, remap run_id to a contiguous 0..n-1 range, then add
    target-history (Lag/Rolling/Slope) features, run-aware.

    target="V" (default, voltage forecasting): drops W (=V*I exactly, leaks
    the target). target="W" (power forecasting): V and I are legitimate
    historical features (not leakage -- W(t+h) for h>=1 is still strictly
    future), so leakage_columns defaults to none unless overridden.
    """
    if leakage_columns is None:
        leakage_columns = LEAKAGE_COLUMNS if target == TARGET else []

    df = load_and_clean(path) if path else load_and_clean()
    df = remove_leakage_features(df, leakage_columns)
    df = remove_degenerate_runs(df)

    history_cols_before = set(df.columns)
    df = add_target_history_features(df, target=target, prefix=target)
    history_cols = [c for c in df.columns if c not in history_cols_before]
    df = fill_missing_per_run(df, history_cols)

    return df
