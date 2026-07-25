WINDOW_SIZE = 20

FORECAST_HORIZONS = [1, 5, 10, 20]

RANDOM_STATE = 42

# Confirmed run_id split (after features.prepare_data()'s run remap 0..4):
# run 3 (2073 rows) and run 4 (2225 rows) are the two chronologically most
# recent, healthiest runs (full V range, high I-nonzero rate) -- held out
# for val/test so no future data leaks into train, same chronological-split
# philosophy as FCF's dataset.time_series_split(), just at run granularity.
TRAIN_RUNS = [0, 1, 2]
VAL_RUNS = [3]
TEST_RUNS = [4]
