import pandas as pd

RAW_PATH = "data/raw/DataTime_export.csv"

RENAME_MAP = {
    'VD0000': 'impl_spd2', 'VD0008': 'pump_spd', 'VD0012': 'I', 'VD0016': 'V', 'VD0020': 'W',
    'VD0028': 'Q_CH4', 'VD0032': 'impl_spd1', 'VD0036': 'Q_CH4_N2', 'VD0040': 'P_NG', 'VD44': 'O2',
    'VD208': 'T3', 'VD212': 'T4', 'VD216': 'T5', 'VD224': 'T7', 'VD232': 'T9', 'VD244': 'T12',
    'VD260': 'T16', 'VD264': 'T17', 'VD272': 'T19', 'VD276': 'T20', 'VD280': 'T21', 'VD284': 'T22',
    'VD288': 'T23', 'VD292': 'T24', 'VD296': 'T25', 'VD300': 'T26', 'VD304': 'T27', 'VD308': 'T28',
    'VD316': 'T30', 'VD320': 'T31',
}
JUNK_COLS = ['MCGS_TIMEMS', 'VD48', 'VD0004', 'VD0024']

def load_and_clean(path=RAW_PATH, min_run_length=50, internal_gap_s=60):
    """
    Đọc + làm sạch dữ liệu SOFC theo pipeline khớp paper (Beloev et al., 2025),
    cộng thêm bước phân run cho true forecasting (phần mở rộng riêng).
    Trả về DataFrame: index=MCGS_TIME, 29 feature vật lý + V (target) + run_id.
    Kỳ vọng: shape (14350, 31), 8 run.
    """
    df = pd.read_csv(path)
    df = df.rename(columns=RENAME_MAP)
    df['MCGS_TIME'] = pd.to_datetime(df['MCGS_TIME'])
    df = df.set_index('MCGS_TIME').sort_index()

    means = df.mean(numeric_only=True)
    dead_cols = means.index[(means - 3000).abs() <= 0.1]
    df = df.drop(columns=JUNK_COLS + list(dead_cols))

    df = df[df['T17'] != 3000]   # 92 dòng
    df = df[df['V'] != 0]        # 18324 dòng

    gap_s = df.index.to_series().diff().dt.total_seconds()
    run_id = (gap_s > internal_gap_s).cumsum()
    run_sizes = run_id.value_counts()
    valid_runs = run_sizes[run_sizes >= min_run_length].index

    df = df[run_id.isin(valid_runs)].copy()
    df['run_id'] = run_id[run_id.isin(valid_runs)]

    order = df['run_id'].drop_duplicates().tolist()
    remap = {old: new for new, old in enumerate(order)}
    df['run_id'] = df['run_id'].map(remap)

    return df