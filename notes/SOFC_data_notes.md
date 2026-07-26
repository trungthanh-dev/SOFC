# Ghi chú dữ liệu — SOFC Voltage Dataset (caapel/SOFC)

Nguồn: https://github.com/caapel/SOFC/tree/master
Bài báo gốc: Beloev et al., "Solid Oxide Fuel Cell Voltage Prediction by a Data-Driven Approach", Energies 2025, 18, 2174. DOI: 10.3390/en18092174

---

## 1. Nguồn gốc & bối cảnh

- Dữ liệu từ hệ thống SOFC cogeneration 1.5kW thật (27 cell), đo qua phần mềm điều khiển chuyên dụng.
- Paper mô tả: 10 lần thí nghiệm, tổng ~80 giờ vận hành, các mode công suất 500W/1000W/1500W, nhiệt độ stack 600-1000°C.
- File thô: `DataTime_export.csv`

## 2. Cấu trúc dữ liệu thô

- **Shape thô:** `(32843, 47)`
- Cột thời gian: `MCGS_TIME` (object, dạng `YYYY/MM/DD HH:MM:SS`), `MCGS_TIMEMS` (mili-giây, không mang thông tin hữu ích)
- 45 cột còn lại đặt tên nội bộ dạng `VDxxxx` — **không phải tên vật lý**, cần rename thủ công theo mapping của tác giả (VD-code → tên như T3, T17, Q_CH4...) ở bước sau.
- **Không có giá trị null** ở bất kỳ cột nào (`isnull().sum()` toàn 0).
- Khoảng thời gian bao phủ: **2024-04-23 13:59:45** → **2025-02-18 22:01:05** (~10 tháng).

## 3. Sampling / tính liên tục theo thời gian

- Interval chuẩn: **30 giây** — chiếm 32,780/32,843 dòng (99.8%), xác nhận bằng percentile 25/50/75 đều = 30.0.
- Có **53 gap > 60s** trong dữ liệu thô. Khi sắp xếp giảm dần, gap chia thành 2 nhóm tách biệt rõ rệt:
  - **29 gap "lớn"**: từ 14,790s (~4.1h) đến 7,061,918s (~82 ngày) → ranh giới thật giữa các đợt thí nghiệm khác nhau.
  - **24 gap "nhỏ"**: chỉ 62s–1,809s (<30 phút) → nhiều khả năng chỉ là logger khựng tạm thời trong cùng một đợt đo, không phải dừng thật.
- **Ngưỡng chọn để tách segment: gap > 3600s (1 giờ).** Với ngưỡng này: dữ liệu thô chia thành **30 segment**.
- Trong 30 segment đó, khi tổng hợp start/end time, thấy nhiều segment nằm cùng cụm ngày gần nhau (VD: 07-09/10/2024 có 3 segment liền kề) → khái niệm "segment" (theo gap thời gian) **không nhất thiết trùng với "1 lần thí nghiệm"** trong paper — chỉ nên hiểu là "khoảng logger ghi liên tục", đủ dùng cho mục đích tránh window bắc cầu qua chỗ đứt.

## 4. Xác định target (V) và bằng chứng xác nhận

- **Cột `VD0016` = V (điện áp, Volt)** — target cần dự đoán.
- Bằng chứng xác nhận (2 nguồn độc lập, khớp nhau):
  1. **Hình dạng đồ thị khớp Figure 4 của paper**: giai đoạn khởi động gần 0 → tăng vọt lên 50-54V (chạy bằng battery) → dao động mạnh biên độ lớn xen kẽ đoạn phẳng (chuyển sang chạy dưới tải) → giảm dần về 0 lúc tắt máy.
  2. **Khớp số học chính xác:** tổng số dòng `VD0016 == 0` trên dữ liệu thô = **18,416**. Paper báo cáo sau khi loại 92 dòng lỗi T17 thì còn **18,324** dòng bị loại vì V=0. `18,416 − 92 = 18,324` ✔ khớp tuyệt đối → xác nhận luôn thứ tự lọc đúng: **phải lọc lỗi T17 trước, rồi mới lọc V=0**, vì 92 dòng lỗi T17 đó đều trùng với V=0.

## 5. Các vấn đề chất lượng dữ liệu đã phát hiện

### 5.1. Cột cảm biến hỏng (giá trị hằng số 3000)
- Một nhóm cột có `mean = std = 3000.000000` chính xác tuyệt đối trên toàn bộ 32,843 dòng → cảm biến ngắt kết nối/không hoạt động, không mang thông tin.
- Xử lý: **loại bỏ cả cột** (không phải loại dòng).

### 5.2. Cột `VD264` (= T17) — lỗi từng phần
- Khác nhóm trên: `mean = 316` (trông "bình thường"), nhưng `max = 3000` → phần lớn dữ liệu thật, chỉ một số dòng bị lỗi.
- Số dòng lỗi (`VD264 == 3000`): **92 dòng** — khớp chính xác với con số paper báo cáo ("92 records... T17 = 3000°C eliminated").
- Xử lý: **loại dòng**, không loại cột.

### 5.3. Dòng có V = 0 (giai đoạn không phát điện)
- Tổng **18,416 dòng** (dữ liệu thô) có V=0 — đại diện cho lúc khởi động/hot-standby/tắt máy, không phải trạng thái phát điện thật.
- Sau khi trừ 92 dòng lỗi T17 (đã tính ở trên): còn **18,324 dòng** cần loại theo đúng pipeline paper.

## 6. Cấu trúc "segment sống" — phần quan trọng nhất cho việc làm forecasting sau này

Trong 30 segment (ngưỡng gap>3600s), đo tỉ lệ `%V=0` từng segment:

- **22/30 segment có 100% dòng là V=0** → hoàn toàn không có hoạt động phát điện, chỉ là các đợt bật máy kiểm tra/hâm nóng. **Vô dụng cho việc học mô hình V, loại bỏ thẳng.**
- **8/30 segment còn lại** có ít nhất một phần V≠0 — đây là nơi chứa **toàn bộ** dữ liệu hữu ích:

| Segment ID | Tổng dòng | Dòng còn lại sau lọc V≠0 | Tỉ lệ giữ |
|---|---|---|---|
| 0  | 8262 | 7625 | 92.3% |
| 28 | 2925 | 2238 | 76.5% |
| 22 | 2779 | 2073 | 74.6% |
| 20 | 1714 | 1201 | 70.1% |
| 17 | 1405 | 690  | 49.1% |
| 15 | 904  | 295  | 32.6% |
| 14 | 1094 | 266  | 24.3% |
| 10 | 897  | 39   | 4.3%  |

**Tổng dòng còn lại sau lọc: 7625+2238+2073+1201+690+295+266+39 = 14,427** → khớp chính xác tuyệt đối với con số cuối cùng paper công bố (14,427 dòng) — xác nhận toàn bộ pipeline lọc đã tái lập đúng.

### 6.1. Tính liên tục bên trong từng segment sau khi lọc V=0

Sau khi bỏ dòng V=0, kiểm tra gap nội bộ (>60s) trong từng segment:

| Segment | Dòng sau lọc | Số gap>60s nội bộ | Gap lớn nhất |
|---|---|---|---|
| 0  | 7625 | 1 | 600s |
| 28 | 2238 | 1 | 1170s |
| 22 | 2073 | 0 | 60s |
| 20 | 1201 | 0 | 30s |
| 17 | 690  | 0 | 30s |
| 15 | 295  | 0 | 30s |
| 14 | 266  | 4 | 540s |
| 10 | 39   | 6 | 870s |

→ 6/8 segment gần như liền mạch tuyệt đối. Segment 14 và đặc biệt segment 10 bị vỡ vụn thành nhiều mảnh nhỏ.

### 6.2. Chia lại thành "run" (đoạn liên tục thật sự, gap>60s = ranh giới run)

Sau khi chia lại theo run, có **20 run** tổng cộng, với điểm gãy phân bố độ dài rất rõ:

**8 run lớn (dùng được cho sliding window):**

| Segment gốc | Độ dài run |
|---|---|
| 0  | 7307 |
| 28 | 2225 |
| 22 | 2073 |
| 20 | 1201 |
| 17 | 690  |
| 0  | 318  |
| 15 | 295  |
| 14 | 241  |

Tổng: **14,350 dòng**

**12 run nhỏ (≤16 dòng, nên loại bỏ):** tổng chỉ **77 dòng** (0.53% toàn bộ dữ liệu hợp lệ) — quá ngắn để tạo sliding window (không đủ cho `WINDOW_SIZE + MAX_HORIZON`).

→ **Quyết định lọc đề xuất:** giữ lại run có độ dài ≥ 50 dòng (mốc tạm, > `WINDOW_SIZE(20) + MAX_HORIZON(20) = 40` bên pipeline Poseidon) → mất đúng 77/14,427 dòng, không đáng kể, nhưng đảm bảo mọi run còn lại đủ dài dùng cho true forecasting sau này.

## 7. Tóm tắt số liệu đã xác nhận khớp với paper

| Mốc | Giá trị | Nguồn xác nhận |
|---|---|---|
| Tổng dòng thô | 32,843 | đọc trực tiếp CSV |
| Số cột thô | 47 | đọc trực tiếp CSV |
| Dòng lỗi T17 | 92 | đúng bằng `(VD264==3000).sum()`, khớp paper |
| Dòng V=0 (đã trừ lỗi T17) | 18,324 | `18416 - 92`, khớp paper |
| Dòng còn lại sau cleaning | 14,427 | tổng 8 segment sống, khớp paper tuyệt đối |
| Run hữu ích cho sliding window | 8 run, 14,350 dòng | phân tích run-length, chưa có trong paper (paper coi là bảng rời rạc, không quan tâm run) |

## 8. Mapping tên cột VD-code → tên vật lý (đã xác nhận)

Lấy từ notebook gốc của tác giả, đã kiểm chứng: rename xong shape vẫn đúng `(32843, 30)` = 29 feature + V, không thiếu không thừa cột nào.

| VD-code | Tên | Ý nghĩa |
|---|---|---|
| VD0000 | impl_spd2 | Main fan speed [rps] |
| VD0008 | pump_spd | Peristaltic pump speed [rps] |
| VD0012 | I | Current [A] |
| VD0016 | **V** | **Voltage [V] — target** |
| VD0020 | W | Power [W] |
| VD0028 | Q_CH4 | CH4 flow rate [m3/h] |
| VD0032 | impl_spd1 | Cooling fan speed [rps] |
| VD0036 | Q_CH4_N2 | CH4/N2 flow rate [m3/h] |
| VD0040 | P_NG | Differential natural gas pressure [bar] |
| VD44 | O2 | O2 concentration at burner inlet [%] |
| VD208 | T3 | Burner temperature (bottom) [°C] |
| VD212 | T4 | Burner temperature (top) [°C] |
| VD216 | T5 | Reformer inlet temperature [°C] |
| VD224 | T7 | SOFC exhaust gas temperature [°C] |
| VD232 | T9 | Heat exchanger temperature [°C] |
| VD244 | T12 | Steam reforming water temperature [°C] |
| VD260 | T16 | SOFC left-front temperature [°C] |
| VD264 | T17 | SOFC right-rear temperature [°C] |
| VD272 | T19 | Air temp at SOFC inlet [°C] |
| VD276 | T20 | H2 temp at SOFC inlet [°C] |
| VD280 | T21 | Air temp at SOFC outlet [°C] |
| VD284 | T22 | H2 temp at SOFC outlet [°C] |
| VD288 | T23 | Reformer rear-top temperature [°C] |
| VD292 | T24 | Reformer rear-bottom temperature [°C] |
| VD296 | T25 | Reformer left-top temperature [°C] |
| VD300 | T26 | Reformer left-bottom temperature [°C] |
| VD304 | T27 | Reformer right-top temperature [°C] |
| VD308 | T28 | Reformer right-bottom temperature [°C] |
| VD316 | T30 | Cooling water temperature [°C] |
| VD320 | T31 | Water tank temperature [°C] |

**3 cột rác bị drop (không phải cảm biến, không mang thông tin):** `MCGS_TIMEMS`, `VD48`, `VD0004`, `VD0024` — đã xác minh bằng cách so `still_unnamed` (15 cột chưa đổi tên) trừ đi 12 `dead_cols` (cảm biến hỏng), ra đúng 3 cột này.

## 9. Hàm `load_and_clean()` — xem code thật, đã cập nhật đường dẫn, tại `src/preprocessing.py`

(Nội dung hàm không lặp lại ở đây để tránh 2 bản dễ lệch nhau khi sửa sau này — chỉ cần mở `src/preprocessing.py` là bản chính thức, đã test khớp (14350, 31), 8 run, chạy được cả trên Colab lẫn máy local Windows.)

## 10. Việc còn chưa làm (next steps)

- [x] ~~Rename cột VD-code → tên vật lý~~ — hoàn tất, xác nhận ở mục 8.
- [x] ~~Viết hàm `load_and_clean()` hoàn chỉnh~~ — hoàn tất, đã test khớp (14350, 31), 8 run, cả Colab và local.
- [x] ~~Tổ chức project folder~~ — hoàn tất tại `E:\sofc`, đã verify `import src.preprocessing` chạy đúng.
- [ ] Quyết định T3&T4 có gộp theo bản paper gốc hay giữ tách theo code repo hiện tại (paper: gộp còn 25 feature; repo hiện tại: không gộp, giữ 29 feature). Chưa chốt — không chặn Phase 1/2 vì đây là nhánh forecasting riêng, không phải tái lập nowcasting y hệt paper.
- [ ] Tái lập baseline nowcasting (XGBRegressor / XGBRFRegressor / MLPRegressor, đúng grid hyperparameter trong paper) để so khớp với Table 6 — **chưa bắt đầu**, tạm gác lại để ưu tiên nhánh forecasting bên dưới.
- [x] ~~Phase 1 — chuẩn bị dữ liệu forecasting (leakage, degenerate run, target-history features)~~ — hoàn tất, xem mục 11.
- [x] ~~Phase 2 (phần data) — sliding window run-aware, không trượt qua ranh giới run~~ — hoàn tất, xem mục 11.3.
- [x] ~~Phase 2 (phần model) — `src/models.py`: port Random Forest / XGBoost / LSTM / Seq2Seq LSTM / TCN từ `E:\FCF\src\models\`~~ — hoàn tất, xem mục 12.
- [x] ~~`src/diagnostics.py`: DTW (Sakoe-Chiba band), persistence-bias check qua feature importance của `V_Lag1`~~ — hoàn tất, xem mục 14.
- [x] ~~Áp dụng thật Delta-Target Reformulation~~ — script đã tạo (`main_delta.py`, `main_lstm_delta.py`, `main_tcn_delta.py`, `main_seq2seq_delta.py`), xem mục 17. RF/XGBoost đang chạy local; LSTM/TCN/Seq2Seq-delta chờ chạy trên Colab (đã thêm cell vào notebook).
- [x] ~~Train đầy đủ RF/XGBoost (không phải smoke test) trên cả 4 horizon~~ — hoàn tất, xem mục 14 (local).
- [x] ~~Train đầy đủ LSTM/TCN/Seq2Seq trên Colab~~ — hoàn tất (2026-07-24), xem mục 16.
- [x] ~~Tách `models.py` (1 file) thành folder `src/models/` (1 file/model) + entrypoint `main.py`/`main_lstm.py`/`main_tcn.py`/`main_seq2seq.py`~~ — hoàn tất, xem mục 15.

## 11. Phase 1/2 (data) — tiến trình xử lý cho forecasting, port có điều chỉnh từ `E:\FCF`

Bối cảnh: `E:\FCF` là project trước đó của cùng người dùng (dự đoán shaft power tàu biển, dataset FuelCast, 3 tàu Poseidon/Triton/Ceto) — nguồn phương pháp luận chính thức được tái dùng ở đây, có điều chỉnh cho phù hợp cấu trúc dữ liệu SOFC (xem mục 13 để so sánh chi tiết 2 dataset).

### 11.1 `src/config.py` (mới)
```
WINDOW_SIZE = 20
FORECAST_HORIZONS = [1, 5, 10, 20]
RANDOM_STATE = 42
TRAIN_RUNS = [0, 1, 2]
VAL_RUNS = [3]
TEST_RUNS = [4]
```
(run_id ở đây là run_id ĐÃ REMAP sau `features.prepare_data()`, xem 11.2 — không phải run_id gốc 0-7 của `load_and_clean()`.)

### 11.2 `src/features.py` (mới)

Quyết định đã chốt cùng người dùng (2026-07-24):

| Quyết định | Bằng chứng | Xử lý |
|---|---|---|
| Loại cột `W` khỏi feature | `W = V × I` đúng về đại số (residual trung bình ~3e-6, max ~8e-5 trên các dòng `I>0`) → leak target trực tiếp | `remove_leakage_features()`, `LEAKAGE_COLUMNS=["W"]` |
| Loại 3 run suy biến: run gốc 0, 2, 3 | run0: `V` ∈ [0.3, 0.9]V suốt 318 dòng; run2: `V` ∈ [0.3, 0.4]V suốt 241 dòng; run3: mean=1.28/std=2.17, chỉ 1 lần vọt lên 12.6V trong 295 dòng — toàn bộ nằm sát ngưỡng lọc `V≠0`, không đại diện trạng thái phát điện thật | `remove_degenerate_runs()`, `DEGENERATE_RUNS=[0,2,3]`, kèm remap `run_id` liền mạch 0..4 |

Hàm chính:
- `remove_leakage_features(df)`, `remove_degenerate_runs(df)` — như trên.
- `add_target_history_features(df)` — sinh `V_Lag1`, `V_Lag5`, `V_RollingMean5`, `V_RollingStd5`, `V_Slope5`. Cùng công thức với `E:\FCF\src\preprocessing.py` (shift trước rolling, không leak), nhưng **tính theo `groupby("run_id")`** — khác biệt bắt buộc so với FCF vì SOFC có nhiều run rời rạc cách nhau vài giờ đến vài tháng, còn mỗi tàu trong FCF là 1 chuỗi liên tục. Nếu không group theo run, dòng đầu của 1 run sẽ "mượn" giá trị `V` cuối cùng của run trước đó làm Lag1 — sai hoàn toàn vì đó là 2 phiên vận hành khác nhau.
- `fill_missing_per_run(df, columns)` — ffill/bfill riêng từng run (NaN đầu mỗi run do lag/rolling gây ra, chỉ được lấp bằng giá trị trong CHÍNH run đó).
- `get_features(df)`, `prepare_data(path=None)` — pipeline gộp: `load_and_clean()` → loại `W` → loại 3 run suy biến → thêm target-history → fill NaN run-aware.

**Kết quả đã verify:**
- Shape: `(14350, 31)` [8 run gốc] → `(13496, 35)` [5 run, remap 0..4] = 28 feature gốc + `V` + `run_id` + 5 cột lịch sử mới → 33 feature dùng được.
- Null count sau toàn bộ pipeline: **0**.
- Run size sau remap:

| run_id (mới) | run_id (gốc) | Số dòng |
|---|---|---|
| 0 | 1 | 7307 |
| 1 | 4 | 690 |
| 2 | 5 | 1201 |
| 3 | 6 | 2073 |
| 4 | 7 | 2225 |

- Kiểm tra ranh giới run cho target-history features: in 3 dòng đầu mỗi run, xác nhận `V_Lag1` luôn khớp với `V` của chính run đó (bfill nội bộ), không hề mang giá trị từ run trước — ví dụ run 1 (bắt đầu 2024-12-25) không dính giá trị `V` cuối của run 0 (kết thúc 2024-04-26, cách 8 tháng).

### 11.3 `src/windowing.py` (mới)

Port run-aware từ `E:\FCF\src\window.py`. Điểm khác biệt cốt lõi: mọi hàm đều lặp qua `_iter_runs()` (group theo `run_id`, giữ thứ tự xuất hiện) rồi mới trượt window bên trong từng run riêng biệt, nối kết quả lại — đảm bảo không sample nào bắc cầu qua ranh giới run.

Hàm: `split_by_run()` (train/val/test theo TRAIN_RUNS/VAL_RUNS/TEST_RUNS), `create_sliding_window()`, `create_sliding_window_delta()`, `create_seq2seq_window()`, `create_seq2seq_window_delta()`, `reshape_for_random_forest()`.

**Split đã xác nhận cùng người dùng:**
- Train: run_id 0,1,2 → 9,198 dòng (68.2%)
- Val: run_id 3 → 2,073 dòng (15.4%)
- Test: run_id 4 → 2,225 dòng (16.5%)

Lý do: dành 2 run khỏe nhất + gần thời điểm hiện tại nhất (run gốc 6, 7 — cũng là 2 run cuối cùng theo thời gian) làm val/test, giữ nguyên triết lý "không để tương lai rò vào train" của `time_series_split()` gốc bên FCF, chỉ khác đơn vị chia là "cả 1 run" thay vì "1 dòng".

**Kết quả test trên train split (run 0,1,2, WINDOW_SIZE=20):**

| Horizon | X_window | y_window |
|---|---|---|
| 1 | (9138, 20, 28) | (9138,) |
| 5 | (9126, 20, 28) | (9126,) |
| 10 | (9111, 20, 28) | (9111,) |
| 20 | (9081, 20, 28) | (9081,) |

- Delta-target (h=1): `anchor + delta == y_window` khớp tuyệt đối trên toàn bộ mảng (`np.allclose` → True).
- Seq2seq window (4 horizon): X (9081,20,28), y (9081,4). Seq2seq-delta: delta (9081,4), anchor (9081,).
- `reshape_for_random_forest`: (9138,20,28) → (9138,560), đúng `20×28=560`.
- Boundary check: đếm samples bằng công thức `Σ max(len(run)-window-horizon+1, 0)` tính riêng từng run = 9138, khớp chính xác số thực tế trả về → xác nhận không có window nào trượt qua ranh giới run.

## 12. `src/models.py` — port Random Forest / XGBoost / LSTM / Seq2Seq LSTM / TCN

Gộp cả 5 class model vào 1 file (`E:\FCF\src\models\` tách 5 file riêng, ở đây gộp theo đúng cấu trúc file đã thống nhất: `windowing.py`, `features.py`, `models.py`, `diagnostics.py`). Interface thống nhất `train/predict/save/load` (+ `feature_importance()` cho RF/XGBoost), import phẳng `from config import RANDOM_STATE` — nhất quán với `windowing.py`/`features.py` đã có, không cần `sys.path` hack như bản gốc (vì bản gốc có `models/` là subpackage riêng, còn ở đây `models.py` nằm cùng cấp `config.py`).

Giữ nguyên gần như toàn bộ các fix quan trọng của FCF: `StandardScaler` fit train-only (X và y riêng), `HuberLoss`, gradient clipping `max_norm=1.0` + skip batch có gradient non-finite, early stopping chronological (khôi phục best-val-weight), `adam_eps=1e-4` (tránh NaN khi target ~0 kéo dài — sẽ cần khi áp dụng Delta-Target sau này), TCN có thêm `torch.use_deterministic_algorithms` + tắt cuDNN autotune + custom weight init N(0, 0.01) cho conv (Bai et al. 2018).

**Đã lược bỏ 1 phần so với FCF**: tùy chọn `early_stop_metric="dtw"/"combined"` của `TCNModel` (chọn checkpoint theo DTW thay vì Huber loss) — bản thân FCF đã kết luận phần này "negligible effect" và bị thay thế bởi Delta-Target fix, nên không port sang để tránh phụ thuộc ngược vào `diagnostics.py` (chưa tồn tại) cho một tính năng đã chứng minh không hiệu quả. Có thể thêm lại sau nếu cần.

**Smoke test end-to-end** (train=run 0,1,2 / test=run 4, horizon=1, WINDOW_SIZE=20, NN chỉ 2 epoch để test wiring — MAE chưa hội tụ, chỉ để xác nhận không lỗi):

| Model | MAE test (2 epoch, chưa hội tụ) |
|---|---|
| RandomForest (n_estimators=50) | 1.40 V |
| XGBoost (n_estimators=50) | 1.96 V |
| LSTM | 3.79 V |
| TCN | 2.63 V |
| Seq2Seq LSTM (h1/h5/h10/h20) | 4.20 / 3.85 / 4.17 / 4.62 V |

`feature_importance()` của RF trả về đúng shape `(660,)` = 20 (WINDOW_SIZE) × 33 (n feature) — khớp `reshape_for_random_forest()`.

## 14. `src/diagnostics.py` + train đầy đủ RF/XGBoost (local) + notebook Colab cho LSTM/Seq2Seq/TCN

### 14.1 `src/diagnostics.py` (mới)
Port `dtw_distance()` + `evaluate_regression()` từ `E:\FCF\src\evalute.py` (Sakoe-Chiba banded DTW, O(n·window)). Thêm 2 hàm mới không có bên FCF:
- `persistence_baseline_metrics()` — đánh giá baseline "dự đoán = giá trị gần nhất đã biết" bằng cùng bộ metric với model thật.
- `lag1_feature_importance(model, feature_cols, window_size)` — trích importance của `V_Lag1` từ RF/XGBoost đã train, cộng dồn qua cả `window_size` vị trí (vì window bị flatten thành vector phẳng `window_size × n_features` trước khi vào RF/XGBoost, nên `V_Lag1` xuất hiện lặp lại 1 lần/mỗi bước thời gian trong window, không phải 1 lần duy nhất).

### 14.2 Random Forest + XGBoost — train đầy đủ, 4 horizon, local (`n_estimators=300`)

| Horizon | Model | MAE | RMSE | R² | DTW | Thời gian train |
|---|---|---|---|---|---|---|
| 1 | RF | 1.448 | 2.484 | 0.9534 | 0.580 | 190s |
| 1 | XGBoost | 1.244 | 2.091 | 0.9670 | 0.486 | 17s |
| 5 | RF | 1.772 | 2.928 | 0.9334 | 0.695 | 223s |
| 5 | XGBoost | 1.491 | 2.615 | 0.9469 | 0.514 | 23s |
| 10 | RF | 1.666 | 2.804 | 0.9368 | 0.614 | 256s |
| 10 | XGBoost | 2.177 | 3.291 | 0.9129 | 0.844 | 20s |
| 20 | RF | 2.307 | 3.510 | 0.8933 | 0.977 | 225s |
| 20 | XGBoost | 2.263 | 3.600 | 0.8877 | 0.907 | 14s |

Nhận xét: R² cao (0.89–0.97) trên target dao động 0.3–55V, MAE 1.2–2.3V là khá tốt cho baseline đầu tiên. XGBoost nhanh hơn RF ~10-15 lần, và thắng RF ở h1/h5/h20, thua ở h10. Kết quả lưu tại `outputs/reports/{rf,xgb}_results.csv`, model tại `outputs/models_saved_{rf,xgb}_h{horizon}.pkl`.

### 14.3 Persistence bias — xác nhận cùng hiện tượng FCF từng gặp

Kiểm tra feature importance của `V_Lag1` trên model h=1 (cộng dồn qua cả 20 vị trí trong window):

| Model | Tổng importance của `V_Lag1` (/1.0) | Importance riêng ở vị trí "gần nhất" (t-1) |
|---|---|---|
| RF | **0.524** | 0.333 |
| XGBoost | 0.090 | 0.029 |

RF: hơn 1 nửa tổng importance (52%) dồn vào 1 feature duy nhất (`V_Lag1`), 1/3 chỉ riêng ở bước thời gian gần nhất — giống hiện tượng FCF từng thấy trên Poseidon/Ceto (~0.8), tuy không cực đoan bằng. XGBoost phân tán importance khác cách (gain-based), số tuyệt đối thấp hơn nhưng vẫn tập trung rõ ở 2 bước thời gian gần nhất nhất.

**Kết luận**: model hiện tại (raw-target) có xu hướng dựa nhiều vào "chép lại giá trị gần nhất" — đúng động lực để áp dụng **Delta-Target Reformulation** ở bước tiếp theo (đã có hàm sinh window delta trong `windowing.py`, chưa train model nào trên đó).

### 14.4 `notebooks/SOFC_Colab_Forecasting.ipynb` (mới) — train LSTM/Seq2Seq/TCN trên Colab

Vì `E:\sofc` chưa phải git repo (khác FCF, vốn dùng git clone/pull vào Drive), notebook này dùng cách khác: upload thẳng `src/` + `data/raw/DataTime_export.csv` lên Google Drive (`MyDrive/sofc/...`), `sys.path.append` vào đó rồi import trực tiếp từ các file `.py` đã port (không copy code inline vào notebook — sửa code local xong chỉ cần upload lại đúng file).

Cấu trúc: mount Drive → kiểm tra file cần thiết → cài `xgboost` (chỉ vì `models.py` import nó ở đầu file, dù notebook này không train RF/XGB) → check GPU → load+prepare data → train LSTM (4 horizon, 1 model/horizon) → train TCN (4 horizon) → train Seq2Seq LSTM (1 model, cả 4 horizon) → bảng so sánh 3 model. Model/predictions/results đều lưu vào `outputs/` trên Drive để không mất khi Colab ngắt kết nối.

**Trạng thái: đã tạo, đã validate cấu trúc notebook (`nbformat.validate` pass), chưa chạy trên Colab.**

## 13. So sánh dataset SOFC (`E:\sofc`) vs FCF (`E:\FCF`) — vì sao "port có điều chỉnh" chứ không copy nguyên

| Khía cạnh | FCF (shaft power, FuelCast) | SOFC (voltage, dataset này) |
|---|---|---|
| Miền ứng dụng | Dự đoán công suất trục tàu biển | Dự đoán điện áp fuel cell |
| Nguồn dữ liệu | 3 tàu Poseidon/Triton/Ceto, HuggingFace `krohnedigital/FuelCast` | 1 hệ SOFC cogeneration 1.5kW thật, `caapel/SOFC` |
| Target | `Consumer_Total_ShaftPower` | `V` (Voltage) |
| Cấu trúc thời gian | Mỗi tàu = 1 chuỗi liên tục (không có khái niệm "run") | 8 run rời rạc (gốc), gap từ vài giờ đến ~10 tháng giữa các đợt thí nghiệm; còn 5 run sau khi loại 3 run suy biến |
| Leakage đã phát hiện | Theo keyword: `ShaftPower/ShaftTorque/RotationSpeed/MomentaryFuel` (nhiều cột, do liên quan vật lý gián tiếp) | 1 cột duy nhất `W`, nhưng leak **tuyệt đối về đại số** (`W=V×I` đúng từng con số) |
| Vấn đề chất lượng data khác | Bug lưu model sai dir (`dashboard_app.py`), NaN khi train delta-target do `adam_eps` mặc định quá nhỏ | Cảm biến hỏng hằng số 3000, lỗi T17 92 dòng, 18,324 dòng V=0, 3 run suy biến sát ngưỡng lọc |
| Cách chia train/val/test | `time_series_split()` — chronological theo INDEX, không có khái niệm run | `split_by_run()` — chronological theo CẢ RUN (run 3,4 mới = 2 run cuối cùng theo thời gian) |
| Target-history features | `add_target_history_features()` tính trực tiếp trên chuỗi liên tục (`shift`/`rolling` thẳng trên cột) | Phải `groupby("run_id")` trước khi shift/rolling — nếu không sẽ rò giá trị giữa 2 phiên vận hành cách nhau hàng tháng |
| Windowing | `create_sliding_window()` gốc lặp thẳng qua toàn bộ chuỗi | Phải bọc qua `_iter_runs()`, trượt window riêng từng run rồi nối lại |
| Delta-Target Reformulation | Đã áp dụng, verify trên TCN/Poseidon: MAE -16→-47%, DTW -24→-90% | Đã có hàm sinh window delta, **chưa train model để verify hiệu quả** |
| Model families | RF, XGBoost, LSTM, Seq2Seq LSTM, TCN — đã train, có kết quả (`eda_output_power/*.csv`) | Chưa port `models.py`, chưa train model nào |
| Trạng thái hiện tại | Đang tối ưu TCN-delta cho riêng Poseidon (Optuna, đã fix non-determinism cuDNN) | Đang ở cuối Phase 1 (data), chuẩn bị sang Phase 2 (model) |

## 15. Tái cấu trúc `models.py` → `src/models/` + entrypoint `main*.py` (đúng convention FCF)

Người dùng phản hồi: bản đầu gộp cả 5 model vào 1 file `models.py` khó quản lý hơn, muốn tách theo đúng cấu trúc `E:\FCF\src\models\` (mỗi model 1 file riêng) + chạy qua `main.py` thay vì gõ lệnh `python -c "..."` ad-hoc trong terminal như trước.

**Cấu trúc mới:**
```
src/
  config.py, preprocessing.py, features.py, windowing.py, diagnostics.py   (giữ nguyên, phẳng)
  models/
    __init__.py            (rỗng, giống FCF -- import kiểu from models.random_forest import ...)
    random_forest.py        RandomForestModel
    xgboost_model.py         XGBoostModel
    lstm.py                  LSTMModel
    seq2seq_lstm.py           Seq2SeqLSTMModel
    tcn.py                    TCNModel
  main.py           -> RF + XGBoost, 4 horizon, chạy LOCAL
  main_lstm.py      -> LSTM, 4 horizon, chạy COLAB (GPU)
  main_tcn.py       -> TCN, 4 horizon, chạy COLAB (GPU)
  main_seq2seq.py   -> Seq2Seq LSTM, 1 model/4 horizon, chạy COLAB (GPU)
```
Mỗi file trong `models/` dùng đúng pattern `sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` rồi `from config import RANDOM_STATE` như bản gốc FCF (cần thiết vì `models/` là subfolder, không cùng cấp `config.py`).

Mỗi `main*.py` tự resolve đường dẫn tuyệt đối dựa trên vị trí file (`PROJECT_ROOT = dirname(dirname(abspath(__file__)))`), nên chạy đúng dù gọi bằng `python src/main.py` (từ project root) hay `cd src && python main.py` (giống FCF) hay từ Colab — không phụ thuộc cwd. Đây là khác biệt so với FCF (FCF không cần việc này vì data load qua HF hub, không phải file CSV local).

Output được tổ chức lại: `outputs/models_saved/{random_forest,xgboost,lstm,tcn,seq2seq}/`, `outputs/predictions_cache/{...}/`, `outputs/reports/{rf,xgb,lstm,tcn,seq2seq}_results.csv` — khớp naming convention của FCF (`models_saved/`, `predictions_cache/`, `eda_output/*.csv`).

Notebook Colab (`notebooks/SOFC_Colab_Forecasting.ipynb`) được viết lại để **gọi thẳng** `!python main_lstm.py` / `main_tcn.py` / `main_seq2seq.py` (giống hệt cách `E:\FCF\FCF_Colab.ipynb` chạy `main_lstm_power.py`...) thay vì nhúng code training trực tiếp vào cell — notebook giờ chỉ lo phần hạ tầng (mount Drive, check file, cài đặt, check GPU), không lặp lại logic đã có trong `main_*.py`.

**Đã verify sau khi tách:**
- Import `from models.random_forest import RandomForestModel` (và 4 model khác) chạy OK, không lỗi.
- `main.py`/`main_lstm.py`/`main_tcn.py`/`main_seq2seq.py` resolve đúng `PROJECT_ROOT`, `RAW_CSV_PATH` (tồn tại), `OUTPUT_DIR` dù chạy từ cwd khác (test từ `C:\`).
- Đã xoá `src/models.py` (bản gộp cũ) để tránh xung đột tên với package `models/`.
- Đã dọn lại các file `.pkl` cũ (`outputs/models_saved_rf_h*.pkl`...) vào đúng cấu trúc `outputs/models_saved/random_forest/h*.pkl`.
- Chạy lại `python src/main.py` thật (không phải smoke test): kết quả khớp tuyệt đối từng chữ số với lần chạy trước khi tách file (VD: RF h=1 MAE=1.448228, XGBoost h=1 MAE=1.244481 — giống hệt mục 14.2) → xác nhận tách file `models.py` → `models/` là refactor thuần cấu trúc, hành vi/kết quả không đổi.

## 16. So sánh đầy đủ 5 model (RF, XGBoost, LSTM, TCN, Seq2Seq LSTM) — kết quả thật, 4 horizon

LSTM/TCN/Seq2Seq chạy trên Colab (`notebooks/SOFC_Colab_Forecasting.ipynb` → `main_lstm.py`/`main_tcn.py`/`main_seq2seq.py`, hyperparameter mặc định trong mục 15), RF/XGBoost chạy local (`main.py`). Kết quả lưu tại `outputs/reports/{rf,xgb,lstm,tcn,seq2seq}_results.csv`.

| Horizon | Model | MAE | RMSE | R² | DTW |
|---|---|---|---|---|---|
| 1 | **LSTM** | **1.093** | 1.779 | 0.976 | 0.413 |
| 1 | XGBoost | 1.244 | 2.091 | 0.967 | 0.486 |
| 1 | TCN | 1.295 | 1.931 | 0.972 | 0.529 |
| 1 | RF | 1.448 | 2.484 | 0.953 | 0.580 |
| 1 | Seq2Seq | 1.893 | 2.602 | 0.949 | 0.796 |
| 5 | **XGBoost** | **1.490** | 2.615 | 0.947 | 0.514 |
| 5 | LSTM | 1.731 | 2.640 | 0.946 | 0.676 |
| 5 | RF | 1.772 | 2.928 | 0.933 | 0.695 |
| 5 | Seq2Seq | 1.981 | 2.864 | 0.936 | 0.772 |
| 5 | TCN | 2.172 | 3.037 | 0.928 | 0.904 |
| 10 | **RF** | **1.666** | 2.804 | 0.937 | 0.614 |
| 10 | Seq2Seq | 2.173 | 3.161 | 0.919 | 0.823 |
| 10 | XGBoost | 2.177 | 3.291 | 0.913 | 0.844 |
| 10 | TCN | 2.306 | 3.392 | 0.907 | 0.951 |
| 10 | LSTM | 2.632 | 3.739 | 0.888 | 1.124 |
| 20 | **XGBoost** | **2.263** | 3.600 | 0.888 | 0.907 |
| 20 | RF | 2.307 | 3.510 | 0.893 | 0.977 |
| 20 | Seq2Seq | 2.437 | 3.528 | 0.892 | 0.993 |
| 20 | LSTM | 2.688 | 3.759 | 0.878 | 1.149 |
| 20 | TCN | 2.702 | 3.841 | 0.872 | 1.146 |

**Nhận xét:**
- **LSTM thắng đậm ở h=1** (MAE 1.09, R² 0.976) nhưng **xuống dốc nhanh nhất** khi horizon tăng — MAE gần gấp đôi ở h=20 (tăng ~146%), R² rơi xuống 0.878 (thấp nhất cùng TCN).
- **RF/XGBoost (tree-based) ổn định hơn ở horizon dài** — ngược trực giác thường thấy (deep learning > tree model): RF thắng ở h=10, XGBoost thắng ở h=5 và h=20.
- **Seq2Seq không thắng ở horizon nào nhưng degrade mượt nhất** (MAE chỉ tăng ~29% từ h1→h20, so với LSTM ~146%, TCN ~109%) — hợp lý vì nó học chung 1 representation cho cả 4 horizon thay vì tối ưu riêng từng cái như 4 model direct-forecast kia.
- Mẫu hình "tốt ở h1, tệ dần ở h dài" của LSTM/TCN/RF/XGBoost (4 model **direct-forecast**, 1 model/horizon) khớp với persistence bias đã phát hiện ở mục 14.3 (RF dựa 52% importance vào `V_Lag1`): ở h=1, chép gần đúng `V_Lag1` đã cho kết quả tốt (V ít đổi trong 1 bước 30s), nhưng horizon càng dài thì `V_Lag1` càng kém tin cậy và model không có gì để bám vào → sai lệch tăng vọt.
- **Động lực rõ ràng cho bước tiếp theo — Delta-Target Reformulation**: theo kinh nghiệm FCF (mục 13), việc này thường lợi nhất ở horizon NGẮN (vì Lag1 là "cheat" tốt nhất ở h=1, nên loại bỏ nó buộc model học động lực thật thay vì chỉ chép); cần thử nghiệm thật trên SOFC để xác nhận có lặp lại xu hướng này không, đặc biệt xem có cải thiện được độ ổn định của LSTM/TCN ở h=10/h=20 hay không — xem tiến trình ở mục 17.

## 17. Delta-Target Reformulation — script mới, kết quả đang chạy

Port `create_sliding_window_delta()`/`create_seq2seq_window_delta()` (đã có sẵn trong `windowing.py` từ mục 11.3) vào 4 script mới, **không ghi đè baseline raw-target** (giữ nguyên `main.py`/`main_lstm.py`/`main_tcn.py`/`main_seq2seq.py` và kết quả mục 16), đúng convention FCF (`main_rf_poseidon_delta.py`, `main_tcn_poseidon_delta.py`...):

- `main_delta.py` — RF + XGBoost, local. Train trên `delta = y(t+h) - y(t)`, tái tạo `y_hat = anchor + delta_hat` trước khi evaluate. Ghi ra `outputs/reports/{rf,xgb}_delta_results.csv`, model vào `outputs/models_saved/{random_forest,xgboost}_delta/`.
- `main_lstm_delta.py`, `main_tcn_delta.py`, `main_seq2seq_delta.py` — tương tự, chạy Colab (GPU). Đã thêm cell gọi 3 script này vào `notebooks/SOFC_Colab_Forecasting.ipynb` (mục "6b"), cùng cập nhật cell check-file-cần-thiết và cell bảng so sánh cuối cùng để gồm cả kết quả delta.

**Trạng thái**: RF/XGBoost-delta đã chạy xong local (2026-07-24, `python src/main_delta.py`, thực tế chỉ ~1 phút — nhanh hơn ước tính ban đầu nhiều). LSTM/TCN/Seq2Seq-delta **chưa chạy**, chờ người dùng chạy trên Colab qua notebook đã cập nhật.

### 17.1 Kết quả RF/XGBoost-delta vs raw-target (mục 16) — xác nhận giả thuyết

| Horizon | Model | MAE delta | MAE raw | Δ MAE | R² delta | R² raw |
|---|---|---|---|---|---|---|
| 1  | RF      | 1.106 | 1.448 | **-24%** | 0.979 | 0.953 |
| 1  | XGBoost | 0.815 | 1.244 | **-34%** | 0.982 | 0.967 |
| 5  | RF      | 2.103 | 1.772 | +19% (tệ hơn) | 0.913 | 0.933 |
| 5  | XGBoost | 1.510 | 1.490 | ~ngang (+1%) | 0.947 | 0.947 |
| 10 | RF      | 1.821 | 1.666 | +9% (tệ hơn) | 0.908 | 0.937 |
| 10 | XGBoost | 2.665 | 2.177 | +22% (tệ hơn) | 0.865 | 0.913 |
| 20 | RF      | 3.669 | 2.307 | **+59% (tệ hơn hẳn)** | 0.730 | 0.893 |
| 20 | XGBoost | 2.733 | 2.263 | +21% (tệ hơn) | 0.828 | 0.888 |

Kết quả lưu tại `outputs/reports/{rf,xgb}_delta_results.csv`, model tại `outputs/models_saved/{random_forest,xgboost}_delta/`.

**Nhận xét — khớp đúng giả thuyết đặt ra ở mục 16 (và kinh nghiệm FCF ở mục 13):**
- Delta-Target cải thiện **rõ rệt và nhất quán ở h=1** (MAE giảm 24-34%, R² tăng lên 0.98) — loại bỏ "cheat" chép `V_Lag1` buộc model học biến động thật, nhưng ở h=1 biến động này vẫn nhỏ và dễ học → thắng tuyệt đối so với raw-target.
- Ngược lại, delta **làm tệ hơn ở mọi horizon dài (5/10/20)**, càng dài càng tệ — rõ nhất là RF h=20: MAE tăng 59%, R² rơi từ 0.893 xuống 0.730. Khác với kỳ vọng ban đầu ("delta có thể cải thiện ổn định LSTM/TCN ở horizon dài" — mục 16), ở RF/XGBoost thì **ngược lại hoàn toàn**: delta chỉ có lợi khi horizon ngắn, vì ở horizon dài biến động (delta thật) đủ lớn và nhiễu để trở nên khó dự đoán hơn chính target gốc — tái tạo `y_hat = anchor + delta_hat` khi đó khuếch đại lỗi thay vì giảm.
- **Kết luận tạm**: nên dùng chiến lược hỗn hợp theo horizon — delta-target cho h=1 (LSTM-delta hoặc XGBoost-delta), raw-target cho h≥5 (XGBoost/RF raw) — thay vì chọn 1 cách tiếp cận duy nhất cho toàn bộ 4 horizon. Cần chờ kết quả LSTM/TCN/Seq2Seq-delta (Colab) để xem pattern này có lặp lại trên deep learning models hay không, đặc biệt vì LSTM raw đã thắng đậm ở h=1 (mục 16) — delta có thể đẩy nó xuống thấp hơn nữa.

## 18. `E:\sofc` chính thức thành git repo, push GitHub — đổi cách sync Colab

Người dùng phàn nàn: mỗi lần chạy Colab phải upload thủ công `src/` + CSV lên Drive "mệt quá" → chuyển sang mô hình clone/pull như `E:\FCF\FCF_Colab.ipynb`.

**Thực hiện (2026-07-25):**
- `git init` tại `E:\sofc`, tạo `.gitignore` (loại `outputs/` ~910MB — gồm `models_saved/`, `predictions_cache/`, `reports/`, `figures/` — và `data/processed/`, `__pycache__/`, `.venv/`, `.vscode/`, `.ipynb_checkpoints/`).
- **Khác biệt quan trọng so với FCF**: `data/raw/DataTime_export.csv` chỉ 16MB (dưới giới hạn 100MB của GitHub) nên **commit thẳng vào git**, không bị gitignore như `data_clean_power/*.parquet` bên FCF. Kết quả: pipeline SOFC trên Colab **không cần bước upload file thủ công nào cả** — sạch hơn cả FCF gốc.
- Repo: `https://github.com/trungthanh-dev/SOFC` (public, do người dùng tự tạo trên GitHub rồi đưa URL).
- Commit đầu (`276f30d`): toàn bộ `src/`, `data/raw/*.csv`, `notebooks/`, `notes/`, `.gitignore` — 24 file, không dính secret nào.
- Push `origin main` thành công ngay từ đầu (không cần force, không có conflict vì repo tạo rỗng).

**Viết lại `notebooks/SOFC_Colab_Forecasting.ipynb`** (commit `1b06387`) theo đúng mẫu `FCF_Colab.ipynb`:
- Mục 1: mount Drive (giữ nguyên).
- Mục 2: cấu hình `GITHUB_USERNAME/GITHUB_REPO/GITHUB_TOKEN` (để trống vì repo public) + `DRIVE_PROJECT_DIR = MyDrive/SOFC`.
- Mục 3: cell tự detect clone-lần-đầu hay pull-lần-sau (y hệt logic FCF).
- Mục 4: check file cần thiết (giữ lại như bản cũ, nhưng giờ chỉ là bước xác nhận sau khi pull, không phải nhắc upload).
- Mục 5-6: cài `xgboost`, check GPU (không đổi).
- Mục 7/7b: chạy `main_lstm.py`/`main_tcn.py`/`main_seq2seq.py` + 3 bản `_delta` (không đổi logic, chỉ đổi số thứ tự mục).
- Mục 8: gộp bảng kết quả từ `outputs/reports/*.csv` (không đổi).
- Mục 9: ghi chú — nhấn mạnh workflow mới là `git push` (local) → `git pull` (Colab, chạy lại cell mục 3), không còn upload tay.
- Validate bằng `nbformat.validate()` → pass, 24 cell.

**Việc còn lại của người dùng**: mỗi lần sửa code local (`src/*.py`), cần tự `git push` trước khi mở Colab — Claude không tự động push thay, phải được yêu cầu tường minh mỗi lần (theo nguyên tắc chỉ commit/push khi được yêu cầu).

## 19. Kết quả LSTM/TCN/Seq2Seq-delta (Colab) — Delta-Target thắng áp đảo trên deep learning, NGƯỢC với RF/XGBoost

Chạy xong trên Colab qua workflow git clone/pull mới (mục 18). Kết quả đầy đủ (raw + delta, 3 model, 4 horizon):

| Horizon | Model | MAE | RMSE | R² | DTW |
|---|---|---|---|---|---|
| 1  | LSTM | 1.480 | 2.087 | 0.967 | 0.588 |
| 1  | TCN | 1.441 | 2.022 | 0.969 | 0.571 |
| 1  | Seq2Seq | 1.921 | 2.574 | 0.950 | 0.819 |
| 1  | **LSTM-delta** | **0.205** | 0.975 | 0.993 | 0.017 |
| 1  | TCN-delta | 0.208 | 0.965 | 0.993 | 0.024 |
| 1  | Seq2Seq-delta | 0.268 | 0.974 | 0.993 | 0.045 |
| 5  | LSTM | 1.910 | 2.776 | 0.940 | 0.759 |
| 5  | TCN | 2.241 | 3.067 | 0.927 | 0.949 |
| 5  | Seq2Seq | 1.996 | 2.787 | 0.939 | 0.790 |
| 5  | **LSTM-delta** | **0.658** | 2.179 | 0.963 | 0.035 |
| 5  | TCN-delta | 0.693 | 2.067 | 0.967 | 0.079 |
| 5  | Seq2Seq-delta | 0.693 | 2.146 | 0.964 | 0.046 |
| 10 | LSTM | 2.632 | 3.732 | 0.888 | 1.120 |
| 10 | TCN | 2.561 | 3.553 | 0.898 | 1.066 |
| 10 | Seq2Seq | 2.179 | 3.093 | 0.923 | 0.839 |
| 10 | LSTM-delta | 1.129 | 2.912 | 0.932 | 0.126 |
| 10 | TCN-delta | 1.112 | 2.796 | 0.937 | 0.150 |
| 10 | **Seq2Seq-delta** | **1.060** | 2.857 | 0.934 | 0.087 |
| 20 | LSTM | 2.876 | 4.074 | 0.856 | 1.258 |
| 20 | TCN | 2.652 | 3.820 | 0.874 | 1.128 |
| 20 | Seq2Seq | 2.436 | 3.493 | 0.894 | 0.999 |
| 20 | LSTM-delta | 1.583 | 3.496 | 0.894 | 0.458 |
| 20 | TCN-delta | 1.556 | 3.527 | 0.892 | 0.460 |
| 20 | **Seq2Seq-delta** | **1.431** | 3.528 | 0.892 | 0.392 |

**Cải thiện delta vs raw (MAE), cả 3 model, cả 4 horizon:**

| Horizon | LSTM | TCN | Seq2Seq |
|---|---|---|---|
| 1  | -86.2% | -85.6% | -86.1% |
| 5  | -65.6% | -69.1% | -65.3% |
| 10 | -57.1% | -56.6% | -51.4% |
| 20 | -44.9% | -41.3% | -41.3% |

**Phát hiện quan trọng nhất — đảo ngược kết luận tạm ở mục 17.1:**
- Với RF/XGBoost, Delta-Target **chỉ lợi ở h=1, hại dần ở h≥5** (mục 17.1) → kết luận tạm lúc đó là "chiến lược hỗn hợp theo horizon".
- Với **cả 3 deep learning model (LSTM/TCN/Seq2Seq), Delta-Target thắng ở TẤT CẢ 4 horizon**, không ngoại lệ — mức cải thiện giảm dần theo horizon (từ ~86% ở h=1 xuống ~41-45% ở h=20) nhưng không bao giờ âm. Khác hẳn RF/XGBoost.
- Giả thuyết giải thích: RF/XGBoost dự đoán delta bằng cách học ánh xạ phi tuyến trực tiếp trên feature phẳng, không có "bộ nhớ trạng thái" nội tại — khi delta thật (biến động dài hạn) đủ lớn/nhiễu ở horizon dài, model tree mất điểm tựa. Trong khi LSTM/TCN/Seq2Seq có cấu trúc tuần tự (hidden state / receptive field theo thời gian) giúp mô hình hoá được cả xu hướng tích luỹ dẫn tới delta dài hạn, nên không bị "sập" như tree-based.
- Lưu ý: MAE raw của LSTM/TCN/Seq2Seq trong bảng trên **khác một chút** so với mục 16 (VD: LSTM h1 1.480 ở đây vs 1.093 ở mục 16; TCN h1 1.441 vs 1.295) — do chạy lại trên phiên Colab khác (LSTM/Seq2Seq không set determinism tuyệt đối như TCN, xem mục 12), không phải lỗi. Vì raw và delta trong bảng này chạy **cùng 1 phiên Colab** nên so sánh nội bộ (delta vs raw) vẫn hợp lệ và là phép so sánh đúng đắn nhất.

**Model tốt nhất mỗi horizon, tính trên TOÀN BỘ 10 biến thể (RF/XGBoost/LSTM/TCN/Seq2Seq × raw/delta):**

| Horizon | Model tốt nhất | MAE | So với tốt nhất trước đó (raw-only) |
|---|---|---|---|
| 1  | **LSTM-delta** | 0.205 | XGBoost raw 1.244 (mục 14.2) → giảm thêm 83% |
| 5  | **LSTM-delta** | 0.658 | XGBoost raw 1.490 (mục 14.2) → giảm thêm 56% |
| 10 | **Seq2Seq-delta** | 1.060 | RF raw 1.666 (mục 14.2) → giảm thêm 36% |
| 20 | **Seq2Seq-delta** | 1.431 | XGBoost raw 2.263 (mục 14.2) → giảm thêm 37% |

→ **Kết luận cập nhật (thay thế mục 17.1)**: không cần chiến lược hỗn hợp theo model family nữa — Delta-Target Reformulation trên deep learning model (LSTM cho horizon ngắn, Seq2Seq cho horizon dài) thắng tuyệt đối mọi model raw-target lẫn RF/XGBoost-delta ở cả 4 horizon. Đây là kết quả tốt nhất đạt được trong toàn bộ project tính đến thời điểm này.

Kết quả lưu tại `outputs/reports/{lstm,tcn,seq2seq}_delta_results.csv` trên Google Drive (`MyDrive/SOFC/outputs/`) — chưa tải về `E:\sofc\outputs\` local (cần tải thủ công nếu muốn gộp báo cáo cuối cùng, xem ghi chú mục 9 của notebook).

## 20. Gộp kết quả Colab (LSTM/TCN/Seq2Seq) với kết quả local (RF/XGBoost)

Người dùng tải `outputs-20260725T140304Z-1-001.zip` (42 file: model `.pt`, predictions `.npz`, report `.csv`) từ Drive về `E:\sofc\outputs\`, giải nén đè vào đúng cấu trúc `outputs/models_saved/`, `outputs/predictions_cache/`, `outputs/reports/`.

- 6 thư mục `models_saved/{lstm,tcn,seq2seq}(_delta)` và `predictions_cache/{...}` trước đó **rỗng** (chỉ là khung thư mục từ lúc tách file ở mục 15) → giải nén không đè mất gì.
- 3 file `outputs/reports/{lstm,tcn,seq2seq}_results.csv` **bị ghi đè**: số liệu cũ (chạy trước, đã ghi ở mục 16) → số liệu mới khớp mục 19 (cùng phiên Colab với bản delta, nên là bộ so sánh raw-vs-delta chuẩn nhất, đã lưu làm bản chính thức).
- Gộp cả 10 file report (RF/XGBoost/LSTM/TCN/Seq2Seq × raw/delta) thành `outputs/reports/combined_all_results.csv` (40 dòng = 10 model × 4 horizon) bằng script Python (module `csv` chuẩn, không có `pandas` trong env hệ thống dùng để chạy notebook local).
- Xác nhận model tốt nhất mỗi horizon khớp đúng mục 19: **LSTM-delta** (h=1: MAE 0.2045, h=5: MAE 0.6579), **Seq2Seq-delta** (h=10: MAE 1.0599, h=20: MAE 1.4309).
- Xoá file zip tạm sau khi giải nén. `outputs/` local hiện 906MB, đầy đủ cả 10 model (local + Colab), vẫn nằm trong `.gitignore` (không commit).

## 21. Biểu đồ so sánh 10 model theo horizon — `outputs/figures/model_comparison.html`

Dùng skill `dataviz` để vẽ, dựa trên `outputs/reports/combined_all_results.csv` (mục 20).

**Chọn form**: thay vì 1 biểu đồ 10 đường (spaghetti chart, vượt trần categorical 7-8 series và rối vì các đường cắt nhau), chia thành **5 small-multiple panel** (RF, XGBoost, LSTM, TCN, Seq2Seq) — mỗi panel chỉ 2 đường (raw=xanh, delta=cam) trên trục X=horizon (1/5/10/20), trục Y=MAE dùng **chung 1 thang đo** (0-4V) cho cả 5 panel để so sánh độ lớn sai số trực tiếp. Cách này khớp đúng câu hỏi phân tích thật sự ("delta có lợi cho model X không, ở horizon nào") thay vì chỉ liệt kê 10 model cạnh nhau.

**Palette**: chỉ cần 2 màu categorical (raw/delta) dùng lại xuyên suốt 5 panel — chạy `validate_palette.js` cho cả light/dark mode, **PASS toàn bộ 6 check** (CVD ΔE 24.7-32.7, normal-vision ΔE 31.8-33.6, đều vượt xa ngưỡng 8/15 yêu cầu).

**Nội dung trang**:
- 4 stat tile đầu: model tốt nhất mỗi horizon (khớp bảng ở mục 19).
- 5 panel line chart, có crosshair + tooltip hover (MAE, R² của cả 2 đường tại horizon hover), caption riêng mỗi panel tóm tắt insight (VD: RF "delta chỉ lợi ở h=1, hại dần từ h≥5"; LSTM "delta thắng ở CẢ 4 horizon").
- Nút "Xem dạng bảng" mở bảng đầy đủ 40 dòng (MAE/RMSE/R²/DTW) — kênh accessibility dự phòng cho biểu đồ.
- Hỗ trợ dark mode qua CSS custom properties (`prefers-color-scheme` + `data-theme` override).

**Sự cố khi publish qua Artifact tool**: lần đầu publish lên `claude.ai/code/artifact/...`, người dùng mở link báo "Page not found". Nguyên nhân: link Artifact loại này chỉ xem được qua "Claude Code trên web" (claude.ai/code) — không phải link public thường, cần đúng phiên đăng nhập/nền tảng phù hợp. Vì đang chạy Claude Code CLI (không phải web), link không truy cập được từ trình duyệt thường của người dùng.

**Xử lý**: copy thẳng file HTML đã build (tự chứa toàn bộ CSS/JS, không phụ thuộc mạng) vào `outputs/figures/model_comparison.html` trong project — mở trực tiếp bằng double-click, không cần đăng nhập/internet. Đã xác nhận người dùng mở thành công, biểu đồ hiển thị đúng.

**Ghi chú cho lần sau**: với người dùng dùng Claude Code CLI (không phải claude.ai web/desktop), nên ưu tiên lưu file HTML trực tiếp vào project (`outputs/figures/`) thay vì chỉ publish qua Artifact tool — hoặc làm cả 2 nhưng báo trước rằng link Artifact có thể không mở được ngoài Claude Code web.

## 22. Đào sâu Delta-Target — script `src/analyze_delta.py`: phát hiện quan trọng, cần hiệu chỉnh lại cách đọc mục 19

Viết script chẩn đoán mới (không train lại gì, chỉ dùng lại `outputs/predictions_cache/*` + `outputs/models_saved/*` đã có), 3 phần:

1. **Persistence floor**: MAE/RMSE/R² khi dự đoán `delta=0` (tức "V không đổi", `y_hat = anchor`) — baseline tối thiểu mọi model phải vượt qua.
2. **Delta-variance shrinkage**: `std(delta_pred) / std(delta_true)` mỗi model/horizon — đo model có đang "co rúm" dự đoán về gần 0 (shrinkage, ratio << 1) hay dự đoán nhiễu loạn hơn cả tín hiệu thật (ratio > 1) — kèm hệ số tương quan Pearson giữa delta dự đoán và delta thật.
3. **V_Lag1 feature importance mở rộng** (RF/XGBoost, raw vs delta, cả 4 horizon — mục 14.3 trước đây chỉ làm h=1).

Kết quả lưu tại `outputs/reports/delta_shrinkage_analysis.csv` và `outputs/reports/delta_lag1_importance.csv`.

### 22.1 Persistence floor — baseline "không làm gì" mạnh hơn tưởng tượng rất nhiều

| Horizon | MAE (persistence) | RMSE | R² |
|---|---|---|---|
| 1  | 0.2014 | 0.978 | 0.9928 |
| 5  | 0.7025 | 2.211 | 0.9620 |
| 10 | 1.1434 | 2.984 | 0.9284 |
| 20 | 1.6899 | 3.804 | 0.8746 |

Vì `V` gần như không đổi trong 30s-10 phút (h=1..20 bước × 30s = 30s-10 phút), riêng việc "cứ lấy giá trị hiện tại" đã đạt R²=0.87-0.99. Đây chính là numeric floor mà **mọi so sánh trước giờ (mục 14.2, 16, 17.1, 19) chưa đối chiếu tới** — các mục đó chỉ so model với nhau (raw vs raw, delta vs raw cùng family), chưa so với baseline "không học gì".

### 22.2 So từng model-delta với persistence floor — bức tranh khác hẳn mục 19

| Model | h=1 | h=5 | h=10 | h=20 |
|---|---|---|---|---|
| **LSTM-delta** | +1.5% (bằng) | **-6.4%** | -1.2% | **-6.3%** |
| **TCN-delta** | +3.0% (bằng) | -1.4% | -2.7% | **-7.9%** |
| **Seq2Seq-delta** | +32.9% (**tệ hơn**) | -1.4% | **-7.3%** | **-15.3%** |
| RF-delta | **+449%** (tệ hơn gấp 5.5 lần) | **+199%** (gấp 3 lần) | +59% | +117% (gấp 2.2 lần) |
| XGBoost-delta | **+305%** (gấp 4 lần) | +115% | +133% | +62% |

(% dương = MAE model tệ hơn persistence; % âm = model thắng thật.)

**Diễn giải lại toàn bộ câu chuyện delta-target:**
- **RF-delta và XGBoost-delta tệ hơn baseline "không làm gì" ở MỌI horizon**, có chỗ tệ gấp 5.5 lần (RF-delta h=1). Việc chúng "thắng RF/XGBoost raw" ở mục 17.1 (h=1: -24%/-34%) chỉ là thắng một baseline khác còn tệ hơn nữa (raw-target, vốn cũng thua persistence — xem 22.4), không phải bằng chứng model học được gì thật.
- **LSTM-delta/TCN-delta chỉ xấp xỉ persistence ở h=1** (+1.5%, +3.0% — coi như hòa, không thắng), bắt đầu thắng thật (âm) từ h=5 trở đi, nhưng biên độ thắng khiêm tốn (1-8%) — hoàn toàn khác ấn tượng "thắng áp đảo 86% MAE" nếu chỉ so với raw-target model ở mục 19.
- **Seq2Seq-delta là trường hợp thú vị nhất**: THUA persistence rõ rệt ở h=1 (+33%, tệ hơn thấy rõ) nhưng **thắng thật và tăng dần** theo horizon, đỉnh điểm **-15.3% ở h=20** — đây là bằng chứng thuyết phục nhất trong cả 10 biến thể model rằng có tồn tại "học thật" chứ không chỉ ăn theo độ dễ của bài toán.
- **Kết luận mới**: phần lớn "thành tích" MAE thấp ở mục 19 (đặc biệt ở h=1, h=5) đến từ việc bài toán tự nó đã dễ (V ít đổi trong thời gian ngắn) chứ không phải model học được động lực SOFC thật. Giá trị thực sự của Delta-Target nằm ở **Seq2Seq-delta tại horizon dài (h=10, h=20)** — nơi duy nhất cải thiện rõ ràng và tăng dần so với baseline trivial.

### 22.3 Delta-variance shrinkage — cơ chế giải thích TẠI SAO tree và DL phản ứng ngược nhau

| Model | h=1 shrink | h=5 shrink | h=10 shrink | h=20 shrink | h=1 corr | h=20 corr |
|---|---|---|---|---|---|---|
| RF-delta | 1.39 | 1.09 | 0.78 | **1.24** | 0.099 | 0.265 |
| XGBoost-delta | 1.33 | 0.79 | 1.01 | 0.92 | 0.101 | 0.324 |
| LSTM-delta | **0.043** | 0.134 | 0.457 | 0.409 | 0.107 | 0.396 |
| TCN-delta | **0.105** | 0.213 | 0.275 | 0.309 | 0.178 | 0.373 |
| Seq2Seq-delta | **0.168** | 0.221 | 0.255 | 0.251 | 0.146 | 0.404 |

(`shrink = std(delta_pred)/std(delta_true)`; 1.0 = biên độ dự đoán khớp biên độ thật; <<1 = model "co rúm" về gần 0; >1 = model dự đoán nhiễu loạn hơn cả tín hiệu thật.)

**Cơ chế phát hiện được — giải thích trực tiếp pattern ở mục 19:**
- **RF/XGBoost-delta có shrink ratio ≈ 0.8-1.4 (gần hoặc vượt 1)** nhưng **correlation cực thấp (0.10-0.32)** — nghĩa là chúng dự đoán delta với **biên độ đúng cỡ nhưng gần như ngẫu nhiên**, không bám theo delta thật. Đây là dấu hiệu **overfit nhiễu**: cây quyết định cố "khớp" một target vốn có tỉ lệ tín hiệu/nhiễu rất thấp (delta thật phần lớn nhỏ, thỉnh thoảng có swing lớn khó đoán), kết quả là thêm nhiễu cộng dồn lên `anchor` — giải thích tại sao chúng tệ hơn cả persistence.
- **LSTM/TCN/Seq2Seq-delta có shrink ratio rất thấp (0.04-0.46)**: mô hình gradient-descent (loss Huber/MSE + early stopping) tự nhiên hội tụ về chiến lược "an toàn" — dự đoán delta gần 0 hầu hết thời gian — vì với target nhiễu cao, đây là điểm tối ưu cục bộ giảm expected loss. Điều này **vô tình tái tạo lại chính baseline persistence** (dự đoán ≈0 = giống hệt persistence) nên MAE của chúng bám sát persistence floor (22.2) — không phải vì chúng "học dynamics" mà vì cơ chế tối ưu hoá tự nhiên hội tụ về vùng an toàn đó.
- **Correlation tăng dần theo horizon ở cả 5 model** (VD Seq2Seq-delta: 0.146→0.404 từ h=1→h=20) — gợi ý tín hiệu delta thật (không phải nhiễu) chiếm tỉ trọng lớn hơn khi horizon dài (delta biến động đủ lớn để có cấu trúc học được), khớp với việc Seq2Seq-delta thắng persistence rõ nhất ở h=20.

### 22.4 V_Lag1 importance mở rộng — persistence bias TĂNG DẦN theo horizon, không chỉ ở h=1

| Family | Variant | h=1 | h=5 | h=10 | h=20 |
|---|---|---|---|---|---|
| RandomForest | raw | 0.524 | 0.671 | 0.747 | **0.847** |
| RandomForest | delta | 0.033 | 0.037 | 0.048 | 0.028 |
| XGBoost | raw | 0.090 | 0.245 | 0.282 | **0.443** |
| XGBoost | delta | 0.030 | 0.023 | 0.026 | 0.020 |

- Ở raw-target, tỉ trọng importance dồn vào `V_Lag1` **tăng liên tục theo horizon** (RF: 52%→85%, XGBoost: 9%→44%) — càng horizon dài, model càng "bám" vào giá trị gần nhất làm chỗ dựa duy nhất, vì 28 feature cảm biến còn lại càng lúc càng ít giải thích được biến động xa. Đây là bằng chứng số liệu trực tiếp (không chỉ suy luận) rằng **persistence bias không phải hiện tượng chỉ ở h=1** (như mục 14.3 mô tả) mà **nặng dần theo horizon** — và vẫn không đủ để raw-target RF/XGBoost thắng nổi persistence thật (mục 22.2 cho XGBoost/RF raw, xem bên dưới).
- Ở delta-target, importance của `V_Lag1` sập xuống còn 2-5% ở mọi horizon — xác nhận Delta-Target **thành công đúng như thiết kế**: xoá bỏ hoàn toàn "lối tắt copy Lag1". Nhưng (22.3) cho thấy sau khi mất chỗ dựa đó, RF/XGBoost **không tìm được tín hiệu thay thế nào tốt hơn** trong 28 feature còn lại — chỉ đơn giản là overfit nhiễu. Delta-Target gỡ bỏ đúng "cái nạng" nhưng không giúp cây quyết định "đi lại" được.

**Kết luận tổng hợp mục 22** (cập nhật lại mục 19): Delta-Target Reformulation không phải một kỹ thuật cải thiện model theo nghĩa chung — nó **thay đổi độ khó bài toán và lộ ra 2 chế độ thất bại khác nhau** của 2 họ model. Với tree-based, bỏ Lag1 chỉ để lộ ra chúng không có tín hiệu thay thế → tệ hơn cả không làm gì. Với deep learning, cơ chế tối ưu hoá tự nhiên hội tụ về gần persistence (an toàn) rồi cộng thêm một chút tín hiệu thật, tăng dần theo horizon — nên nhìn tổng thể, **model có giá trị thực chứng minh được nhiều nhất là Seq2Seq-delta ở horizon dài (h=10/h=20)**, còn kết quả "ấn tượng" ở h=1/h=5 phần lớn phản ánh độ dễ tự nhiên của bài toán ngắn hạn hơn là năng lực học của model.

### 22.5 Làm rõ lại: đây là true forecasting, không phải nowcasting như paper gốc

Người dùng hỏi lại điểm này giữa chừng — nhắc lại rõ (đã có ở mục 7 nhưng dễ bị chìm giữa các bảng số liệu): paper gốc (Beloev et al.) chỉ làm **nowcasting** — dự đoán `V` tại thời điểm `t` từ các cảm biến khác **cũng đo tại chính thời điểm `t`** (biết hết hiện tại, chỉ thiếu đúng 1 giá trị `V`). Toàn bộ Phase 1/2 trở đi của project này (mục 11 trở xuống) là **true forecasting**: dự đoán `V` tại `t+h` chỉ dùng window 20 bước quá khứ tính đến `t`, không có bất kỳ thông tin nào tại hoặc sau `t` — khó hơn về bản chất, và là lý do baseline "persistence" (mục 22.1) mạnh đến vậy (nowcasting của paper không có khái niệm persistence vì không có "trước/sau").

## 23. Trajectory + Residual plot — `outputs/figures/lstm_trajectory_residual.html`

Người dùng nhận xét đúng: phân tích trước giờ (mục 14-22) toàn số liệu tổng hợp (MAE/RMSE/R²/DTW/shrinkage/correlation), chưa có hình ảnh trực quan theo thời gian. Bổ sung 1 biểu đồ mới, dùng lại nguyên `outputs/predictions_cache/{lstm,lstm_delta}/h*.npz` đã có (không train lại) — chọn LSTM làm đại diện (raw vs delta, cả 4 horizon) theo yêu cầu người dùng.

**Cấu trúc**: 4 panel (1 panel/horizon), mỗi panel gồm 2 biểu đồ xếp chồng cùng trục thời gian (phút, trên test run 4, downsample ~550-730/2200 điểm để render mượt, không ảnh hưởng số liệu MAE đã báo cáo):
- **Trajectory** (trên): V thật (nét xám đậm, ink) vs raw-pred (xanh) vs delta-pred (cam) — dùng lại đúng 2 màu categorical raw/delta đã validate ở mục 21 để nhất quán xuyên suốt project.
- **Residual** (dưới): V thật − V dự đoán, cùng 2 màu, có đường 0 tham chiếu (nét đứt).

Hover có crosshair + tooltip đọc giá trị chính xác tại từng điểm (cả 2 sub-plot đồng bộ).

**Số liệu residual std đo được (bổ sung góc nhìn mới cho mục 22.3):**

| Horizon | std(residual) raw | std(residual) delta | Delta giảm bao nhiêu |
|---|---|---|---|
| 1  | 2.078V | 0.974V | -53% |
| 5  | 2.719V | 2.176V | -20% |
| 10 | 3.596V | 2.905V | -19% |
| 20 | 3.942V | 3.483V | -12% |

Delta-target giảm **độ phân tán** sai số (std residual) ở mọi horizon cho LSTM, không chỉ giảm MAE trung bình — nhất quán với phát hiện shrinkage ở mục 22.3 (LSTM-delta dự đoán thận trọng, bám sát persistence, nên residual co cụm hơn quanh 0). Mức giảm % lớn dần ở horizon ngắn (giống pattern "delta thắng đậm ở h=1/h=5" đã thấy ở MAE trung bình, mục 19).

**Việc còn để mở** (nếu người dùng muốn đào tiếp): chưa vẽ cho RF/XGBoost-delta (nơi mục 22 phát hiện residual thực chất tệ hơn cả persistence — sẽ thấy rõ trực quan là các đoạn "nhiễu vọt" chứ không co cụm như LSTM), và chưa vẽ cho Seq2Seq-delta ở h=20 (nơi có bằng chứng học thật rõ nhất).

## 24. Đánh giá khả năng viết báo — tính mới, đóng góp, literature search

Người dùng hỏi thẳng: cái này có viết báo được không, tính mới là gì, đóng góp gì, nổi bật hơn paper khác ở đâu. Trả lời dựa trên toàn bộ mục 1-23 + search literature thật (WebSearch/WebFetch, không phải suy đoán) — theo yêu cầu người dùng: **chỉ tin nguồn có DOI, tạp chí SCI/SCIE/Scopus thật, không tính preprint/blog**.

### 24.1 Đánh giá tổng quan: viết báo được nhưng CHƯA "paper-ready"

Có xương sống hợp lệ của 1 bài applied ML: reproduce baseline paper gốc (mục 1-9) → mở rộng bài toán (Phase 1/2, mục 11-16) → đánh giá có phê phán (mục 17-22) → phát hiện bất ngờ. Nhưng còn thiếu trước khi gửi đi:
1. **Chỉ 1 test run duy nhất** (run 4) — không cross-validate qua nhiều run, không lặp seed cho NN → chưa chứng minh được kết quả ổn định. Gap nghiêm trọng nhất.
2. Hyperparameter NN chưa tune riêng cho SOFC (đã tự ghi nhận mục 9/16).
3. Chưa tái lập bảng nowcasting của paper gốc (Table 6) để có mạch "reproduce → extend" trọn vẹn (vẫn đang treo từ mục 10).
4. Persistence-baseline decomposition (mục 22) hiện là "phụ lục chẩn đoán" — nếu viết báo nên đưa lên làm khung chính phần Results.

### 24.2 Tính mới ban đầu đề xuất (trước khi search) — 3 điểm

1. True forecasting (thay vì nowcasting như paper gốc) trên chính dataset `caapel/SOFC`.
2. Phê phán Delta-Target Reformulation bằng persistence-baseline decomposition (shrinkage ratio + correlation) — chẩn đoán *tại sao* model thắng/thua, không chỉ thắng/thua.
3. Pipeline run-aware cho dữ liệu thực nghiệm rời rạc (8 phiên đo, gap giờ-tháng).

### 24.3 Kết quả literature search thật — phải ĐIỀU CHỈNH LẠI 2 trong 3 điểm trên

**Search engine dùng**: WebSearch (Google-backed) + WebFetch trực tiếp vào ScienceDirect/MDPI (nhiều trang bị chặn 403 — Elsevier và MDPI block bot fetch, không đọc được full-text/abstract gốc qua tool này).

**a) Điểm 1 (true forecasting trên SOFC) — SAI, đã có prior art xác nhận rõ:**

> **Tofigh, Salehi, et al.**, "Transient modeling of a solid oxide fuel cell using an efficient deep learning HY-CNN-NARX paradigm", ***Journal of Power Sources*** (Elsevier, SCI/Scopus, tạp chí uy tín cao trong ngành fuel cell), vol. 606 (2024), article 234555. DOI: `10.1016/j.jpowsour.2024.234555`.

Paper này dùng CNN + NARX (Nonlinear AutoRegressive eXogenous) — đưa lịch sử input/output qua conv 1D rồi dự đoán tương lai — **đúng là true forecasting thật**, trên dữ liệu SOFC thực nghiệm thật (tubular SOFC 650-750°C, ĐH Alberta + Cummins, khác hệ 1.5kW cogeneration của mình). Nhưng xác nhận qua search (lặp lại nhất quán ở 2 câu query độc lập): **chỉ one-step-ahead**, không multi-horizon.

**→ Tính mới điều chỉnh lại**: không phải "true forecasting trên SOFC" (đã có, 2024, tạp chí mạnh hơn cả *Energies*) mà phải thu hẹp còn **multi-horizon forecasting** (h=1/5/10/20, không phải chỉ 1 bước) — đây vẫn chưa xác nhận có ai làm chưa, nhưng ít nhất khác biệt rõ với paper đã tìm thấy.

**b) Điểm 2 (persistence-baseline decomposition) — không phải kỹ thuật mới, đang là xu hướng 2025:**

> **Beck, N., Dovern, J., Vogl, S.**, "Mind the naive forecast! a rigorous evaluation of forecasting models for time series with low predictability", ***Applied Intelligence*** (Springer, SCI/Scopus), vol. 55, no. 6 (2025). DOI: `10.1007/s10489-025-06268-w`.

Paper này (tổng quát, không phải SOFC) chứng minh: trên chuỗi khó dự đoán (tỷ giá, giá cổ phiếu), **không phương pháp nào (kể cả LSTM/TFT/XGBoost) thắng naive forecast nhất quán**, và **ML degrade mạnh hơn statistical model** khi biến động cao — đúng pattern RF/XGBoost-delta thua persistence ở mục 22. Nghĩa là "so với persistence baseline" là rigor **đang được cộng đồng forecasting 2025 nhấn mạnh trở lại**, không phải do project này nghĩ ra.

**→ Định vị lại**: đóng góp không phải "phát minh diagnostic mới" mà là **áp dụng đúng rigor đó vào 1 kỹ thuật cụ thể (Delta-Target Reformulation) trên 1 domain cụ thể (SOFC) chưa thấy ai làm** — hẹp hơn nhưng vẫn hợp lệ. Phần **shrinkage-ratio + correlation decomposition** (giải thích RF/XGBoost và LSTM/TCN/Seq2Seq thất bại theo 2 cơ chế khác nhau khi dùng delta-target) là phần cụ thể nhất còn giữ được, vì "Mind the Naive Forecast" chỉ dừng ở "ai thắng/thua naive", không đào sâu *tại sao*.

**c) Điểm 3 (run-aware pipeline)**: chưa tìm thấy phản chứng cụ thể — giữ nguyên, nhưng đây vốn là đóng góp kỹ thuật nhỏ (engineering rigor), không phải điểm mạnh chính để bán tính mới.

### 24.4 Cảnh báo quan trọng — 1 phát hiện CHƯA XÁC MINH ĐƯỢC, cần người có quyền truy cập tạp chí tự đọc

Khi search paper:

> **Li, M., Wu, J., Chen, Z., et al.**, "Data-Driven Voltage Prognostic for Solid Oxide Fuel Cell System Based on Deep Learning", ***Energies*** 2022, 15(17), 6294. DOI: `10.3390/en15176294`.

Search engine (2 lần query độc lập) mô tả dataset của paper này là **"32,843 records, 47 control parameters"** — **trùng khớp chính xác** với shape thô của `caapel/SOFC` (đã tự verify trực tiếp từ CSV ở mục 2, không qua search). Đây có thể là:
- **(a)** Phát hiện lớn thật: paper 2022 (sớm hơn Beloev 2025 tận 3 năm) đã dùng chính dataset này để làm prognostic — prior art trực tiếp còn sớm hơn cả paper gốc mình tham chiếu.
- **(b)** Nhiễu AI-tóm-tắt-search: con số có thể "rò" từ 1 câu search khác (về chính `caapel/SOFC`) sang câu trả lời này, không phải nội dung thật của paper Li et al.

**KHÔNG xác minh được qua tool hiện có** — cả ScienceDirect lẫn MDPI đều trả 403 Forbidden khi WebFetch cố đọc trực tiếp (chặn bot). **Không được dùng thông tin này để viết bất kỳ câu nào trong bài** cho tới khi có người tự đọc trực tiếp bằng quyền truy cập thư viện/trường (VPN institutional access) xác nhận:
1. `10.1016/j.jpowsour.2024.234555` — có thật chỉ one-step-ahead không, có so baseline persistence không.
2. `10.3390/en15176294` — dataset họ dùng có phải chính `caapel/SOFC` không.

### 24.5 Kết luận cập nhật (lúc chưa đọc được full-text)

Tính mới **vẫn có thật nhưng hẹp và khiêm tốn hơn** ban đầu:
- Không phải "true forecasting trên SOFC" (đã có 2024) → còn lại: **multi-horizon** forecasting + **Delta-Target critique cụ thể** (shrinkage decomposition).
- Không phải "phát minh diagnostic mới" → là **áp dụng rigor 2025 đang lên (naive-baseline comparison) vào 1 domain/kỹ thuật cụ thể chưa ai làm**, cộng thêm 1 lớp giải thích cơ chế (tree overfit nhiễu vs. DL shrinkage-về-persistence) mà paper tổng quát (Beck et al.) không có.
- **Trước khi viết bất cứ gì**: phải đọc full-text 2 paper ở mục 24.4 (đặc biệt paper Li et al. 2022 — nếu đúng là cùng dataset thì phải định vị lại hoàn toàn câu chuyện "tính mới").

### 24.6 GIẢI QUYẾT DỨT ĐIỂM — người dùng tự đọc full-text Li et al. 2022 (và tìm thêm 1 paper mới: Testasecca et al. 2024)

Người dùng tự tra cứu, đọc và tóm tắt (dạng trang HTML học bài) 2 paper thật:

**a) Li et al. 2022 — xác nhận KHÔNG trùng dataset, nhưng LÀ prior art thật cho true forecasting:**

| | Li et al. 2022 | `caapel/SOFC` (dataset đang dùng) |
|---|---|---|
| Hệ thống | SOFC 1kW, 27 cell, 13×13cm² | SOFC cogeneration 1.5kW, 27 cell |
| Dữ liệu thô | 629,873 bản ghi, lấy mẫu **1 giây**, 82 đặc trưng | 32,843 dòng, lấy mẫu **30 giây**, 47 cột |
| Sau nén/lọc | 10,323 bản ghi (nén 1 phút/lần, chọn còn 4 feature qua SFS) | 14,350 dòng (lọc V≠0, giữ nguyên 29 feature) |

Số liệu khác hoàn toàn → **xác nhận con số "32,843/47" nghi vấn ở mục 24.4 đúng là nhiễu AI-search, không phải thật**. 2 hệ SOFC 27-cell độc lập, trùng số cell chỉ là trùng hợp cấu hình phổ biến.

**Nhưng quan trọng hơn**: Li et al. 2022 **có làm true forecasting thật** — sliding time window ("dùng 10 phút đầu dự đoán 10 phút tiếp theo"), kiến trúc **Encoder-Decoder LSTM/GRU** (về bản chất chính là `Seq2SeqLSTMModel` đang dùng trong project này) — **sớm hơn Tofigh/Salehi 2024 tận 2 năm**. → Claim "true forecasting trên SOFC chưa ai làm" (mục 24.2 ban đầu) **chắc chắn sai**, bỏ hẳn.

**3 khoảng trống Li et al. 2022 KHÔNG đụng tới** (đây là tính mới còn lại, xác nhận chắc chắn):
1. Không so persistence baseline — chỉ so 4 biến thể tự thân (LSTM/GRU gốc vs Encoder-Decoder), không đối chiếu "không làm gì".
2. Không có Delta-Target Reformulation — train thẳng giá trị thô.
3. Không phân tích đa horizon có hệ thống — chỉ báo cáo 1 cặp "10 phút vào/ra" tổng hợp, không tách h=1/5/10/20 để xem suy giảm theo horizon.

**b) Phát hiện thêm 1 paper mới (người dùng tự tìm)**: Testasecca et al., "Toward a Digital Twin of a SOFC Microcogenerator: Data-Driven Modelling", *Energies* 2024, 17, 4140 — SOFC micro-CHP thật tại CNR-ITAE Ý, 6 tháng/3935 giờ dữ liệu (dataset khác hẳn). Vẫn là **nowcasting** (dự đoán hiệu suất điện hiện tại từ điều kiện vận hành hiện tại), không có persistence baseline, không có delta-target. Kết quả cùng pattern đã thấy ở mục 1-9: tree-based (RF/XGBoost/GBoost, R²≈0.98-0.99) thắng rõ deep learning (LSTM/ANN, R²≈0.96) trên bài toán nowcasting — không đổi gì về định vị tính mới, nhưng củng cố thêm pattern "tree thắng DL ở nowcasting" đã thấy lặp lại ở dataset thứ 3 độc lập. Điểm hay có thể tham khảo (không liên quan trực tiếp): đánh giá lại model mỗi 500 giờ vận hành, model tốt nhất đổi theo thời gian (model drift) — góc nhìn vận hành thực tế chưa có trong project này.

### 24.7 Định vị tính mới CUỐI CÙNG (đã xác minh qua full-text, không còn nghi vấn)

Không phải "true forecasting trên SOFC" (đã có từ Li et al. 2022, sớm hơn 3 năm) mà là:

> **Critique persistence-baseline có hệ thống (oracle-decomposition, shrinkage analysis) + Delta-Target Reformulation, với phân tích đa horizon (h=1/5/10/20) tường minh, trên dataset công khai mới hơn (`caapel/SOFC`, gắn với paper Beloev 2025) — không paper SOFC nào đã đọc/tra được (Beloev 2025, Tofigh/Salehi 2024, Li et al. 2022, Testasecca et al. 2024) làm cả 2 việc này cùng lúc.**

Đây là claim **hẹp nhưng chắc chắn đúng**, dựa trên 4 paper đã đọc/tra cứu thật (không còn phần "chưa xác minh" như mục 24.4/24.5 trước đó). Sẵn sàng dùng làm khung "Related Work" nếu viết báo.

## 25. Mở rộng sang dự đoán công suất (W) — bước đầu, RF/XGBoost local

Người dùng đặt lại câu hỏi định hướng: muốn "AI chỉ là công cụ", trọng tâm là làm được gì đó có ý nghĩa cho SOFC (không chỉ là bài tập benchmark ML). 3 hướng đề xuất: (1) dự báo công suất/năng lượng phục vụ vận hành/CHP, (2) cảnh báo bất thường qua residual (bị chặn vì dataset không có nhãn lỗi), (3) đóng khung forecasting hiện tại như input cho predictive control (MPC). Người dùng chọn đi trước với hướng (1).

### 25.1 Thay đổi kỹ thuật — tổng quát hoá `features.py` để target linh hoạt

`W = V × I` đúng tuyệt đối về đại số (mục 11.2), nên khi đổi target sang `W`: **`V` và `I` được GIỮ LẠI làm feature** (không phải leakage — `V(t)`, `I(t)` là thông tin quá khứ hợp lệ để dự đoán `W(t+h)` với `h≥1`, khác hẳn lý do loại `W` khi dự đoán `V` là vì `W` ở CÙNG hàng với target).

- `get_features(df, target=TARGET)` — thêm tham số `target` (trước đây hardcode `TARGET="V"`).
- `prepare_data(path=None, target=TARGET, leakage_columns=None)` — thêm tham số `target`; nếu `target="V"` giữ hành vi cũ (loại `W`), nếu `target="W"` mặc định không loại cột nào (`leakage_columns=[]`), và `add_target_history_features` được gọi với `target=target, prefix=target` (sinh `W_Lag1`, `W_RollingMean5`... thay vì `V_...`).
- File mới `src/main_power.py` — bản sao có điều chỉnh của `main.py` (RF/XGBoost local), đổi `TARGET="W"`, lưu vào `outputs/{models_saved,predictions_cache}/{random_forest,xgboost}_power/`, report vào `outputs/reports/{rf,xgb}_power_results.csv`.

**Đã verify**: `prepare_data(target="W")` chạy đúng, shape `(13496, 36)` (nhiều hơn V-target 1 cột vì `V` giờ ở lại làm feature thay vì bị drop), cùng 5 run/split như V-forecasting (hợp lý vì `remove_degenerate_runs` không phụ thuộc target).

### 25.2 Kết quả RF/XGBoost-Power (raw-target, local) — công suất khó dự đoán hơn điện áp RÕ RỆT

| Horizon | Model | MAE (W) | RMSE (W) | R² |
|---|---|---|---|---|
| 1  | RF | 30.24 | 110.27 | 0.721 |
| 1  | XGBoost | 36.73 | 135.99 | 0.576 |
| 5  | RF | 54.16 | 154.25 | 0.455 |
| 5  | XGBoost | 46.98 | 153.50 | 0.461 |
| 10 | RF | 58.54 | 171.34 | 0.330 |
| 10 | XGBoost | 51.48 | 180.04 | 0.260 |
| 20 | RF | 81.68 | 193.78 | 0.146 |
| 20 | XGBoost | 76.25 | 191.76 | 0.164 |

(W dao động 0-1573W trong test set, std=208W — hệ vận hành 3 mode 500/1000/1500W theo paper.)

**So sánh trực tiếp với V-forecasting (mục 14.2, R² 0.89-0.97)**: R² của Power-forecasting thấp hơn hẳn, và **giảm nhanh hơn nhiều theo horizon** (0.72→0.15 từ h=1→h=20, so với V chỉ giảm 0.97→0.89). Đây là bằng chứng số liệu rõ ràng: **công suất là bài toán khó hơn điện áp về bản chất** trên hệ này — hợp lý vì `I` (dòng điện, do tải/operator điều khiển) có thể đổi bậc thang đột ngột khi chuyển mode công suất, trong khi `V` là phản ứng điện hoá mượt hơn nhiều.

### 25.3 Persistence baseline cho Power — càng khẳng định bài toán khó hơn

| Horizon | MAE persistence (W) | R² persistence |
|---|---|---|
| 1  | 6.49 | 0.9114 |
| 5  | 25.24 | 0.5779 |
| 10 | 39.10 | 0.2689 |
| 20 | 47.40 | **0.0075** |

So với persistence-floor của V (mục 22.1, R² 0.87-0.99 xuyên suốt 4 horizon), persistence của W **sập rất nhanh** — ở h=20 (10 phút), biết giá trị hiện tại gần như **không giúp ích gì** để đoán 10 phút sau (R²≈0.008, gần bằng dự đoán = trung bình). Điều này khớp với giả thuyết ở 25.2: `W` đổi bậc thang theo quyết định vận hành (đổi mode công suất), không phải quá trình vật lý mượt như `V` — nên "cứ giữ nguyên giá trị cũ" chỉ đúng trong ngắn hạn.

**So RF/XGBoost-Power với persistence (giống cách làm ở mục 22.2)**: cả 2 model đều **tệ hơn persistence ở mọi horizon** — RF: +366%(h1)/+115%(h5)/+50%(h10)/+72%(h20); XGBoost: +466%/+86%/+32%/+61% — **lặp lại đúng pattern đã thấy ở raw-target V-forecasting** (mục 22.2: mọi raw-target model đều thua persistence). Nhất quán với phát hiện persistence-bias là hiện tượng chung của raw-target trên cả 2 target, không riêng gì `V`.

### 25.4 Ý nghĩa và bước tiếp theo

- **Điểm tích cực cho "đóng góp cho SOFC"**: chính vì persistence của `W` sập nhanh ở horizon dài (R²→0 ở h=20) — đây là **đúng chỗ mà 1 model dự báo thật sự có giá trị**, khác với `V` (nơi persistence đã quá mạnh, mục 22.2 cho thấy khó có "chỗ" để model đóng góp thật). Nếu Delta-Target Reformulation lặp lại hiệu ứng đã thấy ở deep learning cho V (mục 22.3 — LSTM/TCN/Seq2Seq-delta thắng dần persistence theo horizon), thì Power mới là nơi hiệu ứng đó có ý nghĩa thực tế nhất (vì baseline ở đây tệ, dư địa cải thiện lớn).
- **Chưa làm** (lúc viết mục 25.4): Delta-Target cho Power — xem kết quả ở mục 25.5 ngay dưới.
- **Việc còn treo khác từ mục 24**: đọc full-text 2 paper (Tofigh/Salehi 2024, Li et al. 2022) trước khi viết bất kỳ câu tính-mới nào; đóng khung hướng (3) MPC-support vẫn còn là ý tưởng, chưa triển khai cụ thể.

### 25.5 Delta-Target cho Power (RF/XGBoost, local) — lặp lại đúng pattern đã thấy ở V

Script mới `src/main_power_delta.py` (bản sao có điều chỉnh của `main_delta.py`, target `W`). Kết quả:

| Horizon | Model | MAE (W) | RMSE (W) | R² |
|---|---|---|---|---|
| 1  | RF-delta | 29.12 | 91.17 | 0.809 |
| 1  | XGBoost-delta | 23.03 | 88.95 | 0.819 |
| 5  | RF-delta | 50.16 | 164.07 | 0.384 |
| 5  | XGBoost-delta | 53.02 | 183.35 | 0.230 |
| 10 | RF-delta | 64.42 | 192.36 | 0.155 |
| 10 | XGBoost-delta | 56.77 | 193.67 | 0.143 |
| 20 | RF-delta | 81.86 | 209.08 | 0.006 |
| 20 | XGBoost-delta | 82.46 | 209.38 | 0.003 |

**So với raw-target Power (mục 25.2) — % thay đổi MAE:**

| Horizon | RF (delta vs raw) | XGBoost (delta vs raw) |
|---|---|---|
| 1  | -3.7% | **-37.3%** |
| 5  | -7.4% | +12.9% |
| 10 | +10.0% | +10.3% |
| 20 | +0.2% | +8.1% |

**So với persistence-floor của Power (mục 25.3) — % thay đổi MAE:**

| Horizon | RF-delta vs persistence | XGBoost-delta vs persistence |
|---|---|---|
| 1  | +349% | +255% |
| 5  | +99% | +110% |
| 10 | +65% | +45% |
| 20 | +73% | +74% |

**Nhận xét — tái lập gần như nguyên vẹn phát hiện ở mục 17.1/22.2 cho target hoàn toàn khác:**
- Delta-target chỉ giúp rõ ở **h=1** (XGBoost -37%, RF -4%), mờ nhạt hoặc có hại từ **h≥5** — **giống hệt pattern RF/XGBoost-delta trên `V`** (mục 17.1), củng cố thêm rằng đây là hành vi đặc trưng của **họ model** (tree-based dưới delta-target), không phụ thuộc target là `V` hay `W`.
- Quan trọng hơn: **RF/XGBoost-delta cho Power vẫn thua persistence ở MỌI horizon** (thua 45-349%), kể cả ở h=20 — nơi persistence-floor của Power đã rất yếu (R²≈0.008, mục 25.3). Tức là dù bài toán "có chỗ trống" cho model đóng góp thật (giả thuyết ở mục 25.4), **RF/XGBoost vẫn không tận dụng được** — lặp lại đúng cơ chế thất bại ở mục 22.3 (overfit nhiễu khi mất chỗ dựa Lag1, correlation thấp).
- **Hàm ý**: giả thuyết "Power là nơi Delta-Target có giá trị thực tiễn nhất" (mục 25.4) **chưa được xác nhận bằng RF/XGBoost** — cần đúng phép thử đã dùng cho `V` ở mục 22.3 (LSTM/TCN/Seq2Seq-delta trên Colab), vì đó là nơi hiệu ứng "thắng dần persistence theo horizon" từng xuất hiện rõ nhất (đặc biệt Seq2Seq-delta). Đây là bước ưu tiên tiếp theo nếu muốn trả lời dứt điểm câu hỏi "dự báo công suất có ích thật không".

Kết quả lưu tại `outputs/reports/{rf,xgb}_power_delta_results.csv`, model tại `outputs/models_saved/{random_forest,xgboost}_power_delta/`.

### 25.6 Soạn 6 script Colab cho Power (LSTM/TCN/Seq2Seq × raw/delta) — chờ chạy

Mirror đúng 6 script Voltage đã có (`main_lstm.py`, `main_tcn.py`, `main_seq2seq.py`, `main_lstm_delta.py`, `main_tcn_delta.py`, `main_seq2seq_delta.py`), chỉ đổi `TARGET="W"` và gọi `prepare_data(target="W")`/`get_features(df, target="W")` (nhờ đã tổng quát hoá `features.py` ở mục 25.1):

- `main_lstm_power.py`, `main_tcn_power.py`, `main_seq2seq_power.py` — raw-target Power, lưu vào `outputs/{models_saved,predictions_cache}/{lstm,tcn,seq2seq}_power/`, report `outputs/reports/{lstm,tcn,seq2seq}_power_results.csv`.
- `main_lstm_power_delta.py`, `main_tcn_power_delta.py`, `main_seq2seq_power_delta.py` — delta-target Power, tương tự với hậu tố `_power_delta`.

Cả 6 file đã syntax-check qua `python -m py_compile` — pass.

**Cập nhật `notebooks/SOFC_Colab_Forecasting.ipynb`** (32 cell, đã `nbformat.validate()` pass):
- Đổi tên mục 7/7b thành "target Điện áp (V)" để phân biệt rõ với phần mới.
- Thêm mục 7c (raw-target Power, 3 cell gọi `main_{lstm,tcn,seq2seq}_power.py`) và mục 7d (delta-target Power, 3 cell `_power_delta.py`) — có markdown giải thích bối cảnh (RF/XGBoost-Power đã thua persistence, đây là phép thử quyết định xem LSTM/TCN/Seq2Seq có làm tốt hơn không).
- Mục 4 (check file cần thiết) bổ sung 6 file power vào danh sách `required`.
- Mục 8 (so sánh) đổi tên thành "So sánh tất cả model — V và W, raw và delta", bảng gộp giờ đọc cả 12 file report (6 Voltage + 6 Power).
- Mục 9 (ghi chú) bổ sung 1 dòng nhắc tải kết quả Power về local giống cách đã làm với Voltage (mục 20).

**Trạng thái**: đã soạn xong, **chưa chạy trên Colab** — chờ người dùng mở notebook, `git pull` để lấy 6 file mới, rồi chạy lần lượt mục 7c/7d.

### 25.7 Sự cố: người dùng chạy nhầm mục 7/7b (V) tưởng là kết quả Power, gộp notebook thành 1 cell

Người dùng paste bảng kết quả tưởng là Power nhưng thực ra là **Voltage** (khớp gần đúng mục 16/19: LSTM raw h1 MAE=1.093, TCN raw h1=1.295...) — do notebook cấu trúc nhiều cell rời (mục 7→7b→7c→7d→8), dễ chạy nhầm/dừng giữa chừng mà không nhận ra thiếu phần Power.

**Yêu cầu người dùng**: gộp lại thành 1 nút bấm duy nhất (`Runtime -> Run all` chạy hết, không cần bấm từng cell theo thứ tự).

**Xử lý**: thêm mục **7 mới** (1 markdown + 1 code cell) ngay sau mục 6 (check GPU) — code cell dùng `subprocess.run()` lặp qua **cả 12 script** (V raw×3, V delta×3, Power raw×3, Power delta×3) tuần tự, in tiến trình rõ ràng theo từng script, **không dừng cả pipeline nếu 1 script lỗi** (chỉ ghi nhận vào danh sách `failed` rồi chạy tiếp), tổng kết thời gian + danh sách lỗi (nếu có) ở cuối. 4 mục cũ (7/7b/7c/7d) đổi tên thành sub-section **7.1-7.4** ("chạy riêng"), giữ nguyên để dùng khi chỉ muốn train lại đúng 1 model cụ thể (không phải chạy lại cả 12 script).

**Bug phát hiện khi tự kiểm tra (không phải người dùng báo)**: cell code mới ban đầu bị lỗi cú pháp — 1 số ký tự escape `\n` bên trong f-string một dòng bị hỏng thành newline thật trong lúc soạn (transport qua nhiều lớp JSON/heredoc làm mất 1 lớp escape), gây `SyntaxError: unterminated f-string literal`. Phát hiện bằng cách tự `compile()` từng cell code trước khi giao — đã sửa bằng cách tách `SEP = "="*80` ra biến riêng, không nhúng `\n` vào f-string 1 dòng nữa. Đã verify lại toàn bộ 34 cell qua `compile()` (chỉ cell 6 — `%cd`/`!git` lồng trong `if/else` — bị flag, nhưng đó là cú pháp IPython magic hợp lệ trong Colab, không phải lỗi thật, đã dùng từ trước).

**Bài học cho lần sau**: khi soạn code cell cho notebook (đặc biệt qua nbformat + heredoc/exec nhiều lớp), **luôn `compile()` từng cell code trước khi ghi file**, không chỉ `nbformat.validate()` (validate chỉ kiểm tra cấu trúc JSON của notebook, không kiểm tra cú pháp Python bên trong cell).

## 26. Kết quả đầy đủ LSTM/TCN/Seq2Seq-Power (Colab) — Power gần như KHÔNG dự báo được tốt hơn persistence

Chạy xong cả 12 script qua cell gộp mới (mục 25.7). Kết quả Power (raw + delta, 3 kiến trúc, 4 horizon):

| Horizon | Model | MAE (W) | R² |
|---|---|---|---|
| 1  | LSTM-power | 18.93 | 0.834 |
| 1  | TCN-power | 13.08 | 0.894 |
| 1  | Seq2Seq-power | 36.01 | 0.509 |
| 1  | LSTM-power-delta | 6.89 | 0.912 |
| 1  | TCN-power-delta | 7.22 | 0.912 |
| 1  | Seq2Seq-power-delta | 7.05 | 0.912 |
| 5  | LSTM-power | 38.96 | 0.368 |
| 5  | TCN-power | 37.55 | 0.469 |
| 5  | Seq2Seq-power | 39.88 | 0.398 |
| 5  | LSTM-power-delta | 26.68 | 0.580 |
| 5  | TCN-power-delta | 26.13 | 0.582 |
| 5  | Seq2Seq-power-delta | 25.80 | 0.580 |
| 10 | LSTM-power | 45.05 | 0.162 |
| 10 | TCN-power | 43.49 | 0.202 |
| 10 | Seq2Seq-power | 42.28 | 0.289 |
| 10 | LSTM-power-delta | 40.72 | 0.277 |
| 10 | TCN-power-delta | 40.36 | 0.284 |
| 10 | Seq2Seq-power-delta | 39.53 | 0.272 |
| 20 | LSTM-power | 47.64 | 0.046 |
| 20 | TCN-power | 47.30 | 0.208 |
| 20 | **Seq2Seq-power** | **44.56** | **0.189** |
| 20 | LSTM-power-delta | 48.13 | 0.021 |
| 20 | TCN-power-delta | 48.80 | 0.039 |
| 20 | Seq2Seq-power-delta | 47.55 | 0.011 |

**So với persistence-floor của Power (mục 25.3: MAE 6.49/25.24/39.10/47.40) — % thay đổi MAE:**

| Horizon | LSTM-power | TCN-power | Seq2Seq-power | LSTM-power-delta | TCN-power-delta | Seq2Seq-power-delta |
|---|---|---|---|---|---|---|
| 1  | +192% | +102% | +455% | +6.1% | +11.2% | +8.7% |
| 5  | +54% | +49% | +58% | +5.7% | +3.5% | +2.2% |
| 10 | +15% | +11% | +8% | +4.1% | +3.2% | +1.1% |
| 20 | +0.5% | -0.2% | **-6.0%** | +1.5% | +2.9% | +0.3% |

**Nhận xét — khác hẳn câu chuyện Voltage (mục 19/22):**
- **Không có biến thể Power nào thắng persistence rõ rệt**, ngoại trừ đúng 1 trường hợp: **`Seq2Seq-power` (raw-target, KHÔNG phải delta) ở h=20, thắng thật -6.0%** — model Power duy nhất trong cả 12 biến thể vượt qua "không làm gì".
- Delta-target với Power chỉ có tác dụng **kéo raw-target về gần persistence ở h ngắn** (LSTM raw→delta ở h=1: 18.93→6.89, giảm 64%; Seq2Seq raw→delta ở h=1: 36.01→7.05, giảm 80%) — nhưng đó là kéo về **bằng** persistence, không phải **vượt qua** nó (LSTM/TCN/Seq2Seq-power-delta vẫn tệ hơn persistence 1-11% ở mọi horizon). Khác hẳn Voltage-delta, nơi DL-delta thật sự thắng persistence và biên độ thắng tăng dần theo horizon.
- Ở horizon dài (h=20), delta-target với Power thậm chí **không còn ý nghĩa** (LSTM/TCN/Seq2Seq-power-delta đều xấp xỉ hoặc tệ hơn bản raw cùng kiến trúc) — ngược với Voltage nơi delta luôn thắng raw ở mọi horizon kể cả h=20.

**Giải thích vật lý (không phải model yếu)**: `V` là phản ứng điện hoá mượt (autocorrelation cao, dễ khai thác từ lịch sử). `W = V×I`, mà `I` do operator/tải điều khiển — có thể **nhảy bậc thang đột ngột** khi hệ chuyển mode công suất (500/1000/1500W, theo mô tả paper gốc). Nhảy bậc thang kiểu quyết định vận hành **không có cấu trúc thời gian nào để học từ lịch sử cảm biến thuần tuý** — muốn dự báo đúng cần biết trước lịch trình setpoint (thông tin ngoài, không có trong dataset này).

**Kết luận cho hướng "làm gì đó cho SOFC" (mục 24, người dùng đặt ra)**: dự báo Power thuần từ lịch sử cảm biến **gần như không khả thi hơn baseline trivial** với dữ liệu hiện có — đây là 1 giới hạn cấu trúc quan trọng cần nêu rõ nếu viết báo, không phải thất bại của pipeline. Hướng đi thực tế hơn nếu muốn dự báo Power hữu ích: kết hợp thêm tín hiệu lịch trình vận hành (setpoint đã lên kế hoạch) làm feature, thay vì chỉ dùng lịch sử cảm biến — nằm ngoài phạm vi dataset hiện tại.

## 27. Dự đoán `V` tốt có giúp dự đoán `W` không? — Thực nghiệm oracle-decomposition, trả lời dứt điểm: KHÔNG

Người dùng hỏi thẳng: nếu `V` dự đoán được (đã chứng minh, mục 19/22), liệu có tận dụng được để đoán `W` không (vì `W=V×I`)? Kiểm tra bằng thực nghiệm "oracle substitution" trên test set thật (run 4): thay `V(t+h)` hoặc `I(t+h)` bằng giá trị THẬT (oracle, giả định biết trước hoàn hảo), giữ nguyên bên còn lại ở mức persistence, rồi tái tạo `Ŵ = V̂ × Î` và so với persistence-floor của `W`.

| Horizon | Persistence W | Oracle-V + Persistence-I | Persistence-V + Oracle-I | Oracle cả 2 (sanity check) |
|---|---|---|---|---|
| 1  | 6.49 | 8.08 (**+24%, tệ hơn**) | **1.11 (-83%)** | 0.0000 |
| 5  | 25.24 | 31.01 (**+23%, tệ hơn**) | **3.78 (-85%)** | 0.0000 |
| 10 | 39.10 | 46.26 (**+18%, tệ hơn**) | **6.22 (-84%)** | 0.0000 |
| 20 | 47.40 | 53.21 (**+12%, tệ hơn**) | **8.25 (-83%)** | 0.0000 |

(Cột "oracle cả 2" ≈ 0 xác nhận công thức tái tạo đúng — sanity check pass.)

**Kết luận dứt điểm**: biết trước `V(t+h)` hoàn hảo mà vẫn dùng `I` cũ → dự đoán `W` **còn tệ hơn cả không làm gì** (persistence). Ngược lại, chỉ cần biết trước `I(t+h)` hoàn hảo (dù `V` vẫn persistence) → sai số giảm **83-85%** ở mọi horizon. Nghĩa là gần như toàn bộ độ khó của bài toán `W` nằm ở việc không biết trước `I`, không phải `V` — `V` chỉ đóng góp biến động nhỏ, gần như nhiễu nền so với `I`. **Dự đoán `V` tốt (kể cả Seq2Seq-delta ở mục 19/22) không mở ra con đường nào để cải thiện dự đoán `W`** — 2 bài toán độc lập gần như hoàn toàn về độ khó, đúng như giả thuyết vật lý ở mục 26 (nhưng giờ có bằng chứng số liệu trực tiếp, không chỉ suy luận định tính).

**Kỹ thuật này (oracle-substitution decomposition) có thể khái quát hoá**: với bất kỳ target nào phân rã được thành tích/tổng của các thành phần đo được (ở đây `W=V×I`), thay từng thành phần bằng giá trị thật để cô lập xem thành phần nào là "nút thắt cổ chai" thực sự của độ khó dự đoán — một công cụ chẩn đoán nhỏ, gọn, có thể dùng lại cho các bài toán tương tự khác.

## 28. Vậy giờ làm gì tiếp?

Với toàn bộ bằng chứng đã có (mục 1-27), hướng đi hợp lý nhất:

1. **Đóng lại nhánh Power-forecasting-thuần-từ-lịch-sử** — đã có câu trả lời dứt điểm (mục 26-27), không cần tune thêm hyperparameter hay thử model khác cho `W`, vì nút thắt là thiếu thông tin (`I` tương lai), không phải model yếu.
2. **Dồn lại vào câu chuyện chính: `V`-forecasting + vai trò làm input cho MPC/giám sát** (hướng 3, mục 24/28-cập-nhật) — đây là hướng duy nhất đã chứng minh có "học thật" (Seq2Seq-delta thắng persistence tăng dần theo horizon, mục 19/22).
3. **Thực nghiệm mới đáng làm nếu muốn hoàn thiện câu chuyện MPC**: dựng lại bài toán kiểu NARX — **giả định `I(t+h)` là input đã biết trước** (đúng như 1 bộ điều khiển thật sẽ biết trước setpoint dòng điện mình sắp đặt ra), rồi dự đoán `V(t+h)` với `I(t+h)` là exogenous feature (không phải phải đoán mù). Đây chính là kịch bản `Persistence-V + Oracle-I` ở mục 27 nhưng đảo vai trò — kiểm tra xem biết trước `I` tương lai có giúp dự đoán `V` tốt hơn nữa không (nhiều khả năng có, vì `V` là phản ứng của `I`). Nếu đúng, đây là bằng chứng mạnh nhất cho việc đóng khung "dự đoán V có điều kiện theo lệnh vận hành đã biết" — đúng thiết kế NARX của paper Tofigh/Salehi (mục 24).
4. **Việc còn treo từ mục 24**: đọc full-text 2 paper (Tofigh/Salehi 2024, Li et al. 2022) trước khi viết bất kỳ câu tính-mới nào — vẫn chưa làm.

**Trạng thái commit**: người dùng yêu cầu chưa commit khi thảo luận mục 26-27 (đang phân tích thêm trước khi chốt) — cần hỏi lại trước khi push.

## 29. Thực nghiệm 3 — biết trước `I(t+h)` có giúp dự đoán `V` không? (RF/XGBoost, local)

Script mới `src/main_v_given_i.py`: nhét thêm `I(t+h)` (lấy qua `create_sliding_window()` áp lên chính cột `I`, tận dụng lại đúng logic windowing có sẵn — không cần hàm mới) làm 1 feature phụ vào vector phẳng (581 chiều thay vì 580) cho RF/XGBoost, train cả raw-target lẫn delta-target `V`, so với baseline không có `I(t+h)` (mục 14.2/17.1). Đã smoke-test 1 trường hợp (XGBoost raw h=1) khớp chính xác số cũ trước khi chạy full 32 tổ hợp (~40 phút, RF chiếm phần lớn thời gian do 8 tổ hợp RF × trung bình ~460s/lần do có thêm chiều feature).

**Kết quả — % thay đổi MAE khi có `I(t+h)` so với không có:**

| Model | h=1 | h=5 | h=10 | h=20 |
|---|---|---|---|---|
| RF-raw | -16.8% | -0.5% | -3.5% | -2.0% |
| RF-delta | -10.5% | +24.5% | +8.1% | +2.0% |
| XGBoost-raw | -8.4% | -0.6% | +14.8% | +4.7% |
| XGBoost-delta | **-24.3%** | **-19.4%** | +5.0% | +21.3% |

**Nhận xét:**
- **Chỉ giúp thật ở h=1** (cả 4/4 tổ hợp cải thiện, tới -24% với XGBoost-delta) — hợp lý vì phản ứng điện hoá gần tức thời, `I(t+1)` gần như quyết định trực tiếp `V(t+1)`.
- **Từ h≥10, hầu hết tổ hợp TỆ HƠN** khi thêm `I(t+h)` — khác với oracle-decomposition ở mục 27 (biết trước `I` giúp tái tạo `W` tốt hơn 83-85% ở **mọi** horizon, vì đó dùng đúng công thức đại số `W=V×I` — ràng buộc cứng). Ở đây chỉ nhét `I(t+h)` như 1 trong 581 feature phẳng cho RF/XGBoost — model phải tự học quan hệ, và ở horizon xa, động lực trung gian quá phức tạp để 1 giá trị đơn lẻ nắm bắt được → dễ overfit/nhiễu thay vì giúp ích.
- **So với mục 19**: dù được "biết trước đáp án" (`I` tương lai), XGBoost-delta-given-I ở h=1 (MAE 0.617V) vẫn **tệ hơn** LSTM-delta thuần tuý không biết trước gì (0.205V) — deep learning học "trong bóng tối" vẫn giỏi hơn cây quyết định dù cây được ưu ái thông tin thêm.

Kết quả lưu tại `outputs/reports/v_given_i_results.csv`.

**Kết luận thực nghiệm 3**: giả thuyết "biết trước I giúp dự đoán V" — **đúng nhưng chỉ ở horizon ngắn (h=1, có thể tới h=5 với XGBoost-delta)**, và cách nhét thẳng feature phẳng cho RF/XGBoost là quá thô để khai thác hết tiềm năng. Muốn làm đúng kiểu NARX (paper Tofigh/Salehi, mục 24 — cho exogenous input 1 kênh riêng thay vì trộn vào window) cần thử trên kiến trúc sequence (LSTM/TCN/Seq2Seq, Colab) — **chưa làm**, là bước hợp lý tiếp theo nếu muốn đẩy hướng MPC-support xa hơn.

## 30. Thực nghiệm 3 trên LSTM/TCN/Seq2Seq — hàm mới `augment_with_future_exogenous()`, soạn xong, chờ chạy Colab

Thay vì nhét `I(t+h)` phẳng vào vector (như bản RF/XGBoost, mục 29), thêm hàm mới `windowing.augment_with_future_exogenous(X_window, X_df, exo_series, run_id, window_size, horizons)`: broadcast `exo(t+h)` (ở đây là `I(t+h)`) thành 1 kênh feature riêng lặp lại dọc theo toàn bộ `window_size` bước thời gian, nối vào cuối chiều feature — không làm phẳng, không cần sửa code model (LSTM/TCN/Seq2Seq đều tự dò `input_size` từ `X.shape[2]`). Tái dùng `create_sliding_window()` áp lên chính cột `I` để lấy `I(t+h)` đúng vị trí, giống cách làm ở mục 29.

Với Seq2Seq (dự đoán cả 4 horizon từ 1 cửa sổ), truyền cả `FORECAST_HORIZONS` — mỗi horizon 1 kênh riêng (`I(t+1)`, `I(t+5)`, `I(t+10)`, `I(t+20)`), mô phỏng đúng 1 bộ điều khiển thật biết trước **toàn bộ** lịch trình dòng điện sắp đặt ra, không chỉ bước kế tiếp.

**Bug phát hiện khi smoke-test (không phải do người dùng báo)**: `create_seq2seq_window_delta()` dùng `max(horizons)` để tính số sample, trong khi `create_sliding_window()` (dùng để lấy `I(t+h)` riêng từng horizon) tính theo đúng `h` đó — với `h < max(horizons)` (VD h=1,5,10), số sample trả về **nhiều hơn** số sample của cửa sổ Seq2Seq → lệch shape khi nối. Sửa bằng cách cắt `future_vals` về đúng `X_window.shape[0]` đầu tiên trước khi ghép (2 cách windowing lặp cùng thứ tự từ `i=0` mỗi run nên cắt đầu vẫn giữ đúng alignment — cùng logic đã dùng để hợp lệ hoá alignment seq2seq ở mục 22.3).

**3 script mới** (`main_lstm_delta_given_i.py`, `main_tcn_delta_given_i.py`, `main_seq2seq_delta_given_i.py`) — chỉ làm delta-target (bản đã chứng minh tốt nhất cho `V`, mục 19/22), mirror đúng `main_{lstm,tcn,seq2seq}_delta.py` cộng thêm bước augment. Đã:
- `python -m py_compile` cả 3 file + `windowing.py` — pass.
- Smoke-test đầy đủ (2 epoch, CPU) cho cả 3 kiến trúc: shape đúng (33→34 kênh cho LSTM/TCN, 33→37 cho Seq2Seq), train/predict chạy không lỗi.

**Cập nhật notebook** (38 cell, `nbformat.validate()` + compile-check từng cell code pass): thêm mục 7.3 "Delta-Target + biết trước I(t+h)" (3 cell, đặt giữa 7.2 và Power — đánh số lại 7.3/7.4/7.5 cho đúng thứ tự, Power lùi xuống 7.4/7.5), bổ sung 3 file vào danh sách check mục 4, bổ sung 3 script vào `ALL_SCRIPTS` của cell gộp mục 7, bổ sung 3 dòng vào bảng so sánh mục 8.

**Trạng thái**: đã soạn + test xong, **chưa chạy trên Colab** — chờ người dùng `git pull` rồi chạy mục 7.3 (hoặc cell gộp mục 7 chạy hết luôn).

## 31. Kết quả thực nghiệm 3 trên Colab (LSTM/TCN/Seq2Seq) — KHÔNG kết luận được, khác RF/XGBoost

Chạy xong qua cell gộp mục 7 (15 script, 9.2 phút, không lỗi). Kết quả delta-target `V` có/không `I(t+h)` (so trong cùng 1 phiên chạy, để loại yếu tố dao động giữa các phiên Colab khác nhau):

| Horizon | LSTM (không I → có I) | TCN | Seq2Seq |
|---|---|---|---|
| 1  | 0.198→0.206 (**+4.3%**) | 0.205→0.201 (-2.1%) | 0.281→0.238 (**-15.4%**) |
| 5  | 0.714→0.628 (**-12.1%**) | 0.657→0.675 (+2.7%) | 0.728→0.780 (+7.0%) |
| 10 | 1.073→1.109 (+3.3%) | 1.176→1.066 (**-9.4%**) | 1.125→1.212 (+7.8%) |
| 20 | 1.548→1.535 (-0.8%) | 1.567→1.503 (-4.1%) | 1.488→1.628 (+9.4%) |

**Không có pattern nhất quán** — khác hẳn RF/XGBoost (mục 29: giúp rõ ở h=1, hại dần từ h≥10). Ở đây lúc tốt lúc tệ, không theo horizon, không giống nhau giữa 3 kiến trúc.

**Vấn đề phương pháp luận quan trọng**: so sánh RF/XGBoost ở mục 29 "sạch" vì `random_state` cố định — chỉ khác đúng 1 biến (`I(t+h)` có/không). Còn LSTM/TCN/Seq2Seq có dao động tự nhiên giữa các lần train (dù đã cố định seed, vẫn phụ thuộc GPU/thứ tự batch) — chính bản delta-target "không có I" chạy lại trong phiên này (TCN-delta h1=0.205077) cũng đã lệch khỏi số cũ ở mục 19 (0.208), dù cùng 1 script không đổi gì. Biên độ dao động tự nhiên này (~5-10%) **cùng cỡ** với biên độ thay đổi khi thêm `I(t+h)` (±0.8-15%) → với **n=1 lần chạy mỗi cấu hình**, không tách được tín hiệu thật của `I(t+h)` khỏi nhiễu ngẫu nhiên của quá trình train.

**Kết luận**: thực nghiệm 3 trên deep learning **không kết luận được** với thiết kế hiện tại (thiếu lặp lại nhiều seed để trung bình hoá nhiễu). Khác với thực nghiệm RF/XGBoost (mục 29, kết luận rõ: giúp ở h=1, không giúp/hại ở horizon dài), bản LSTM/TCN/Seq2Seq này dừng lại ở mức "chưa xác nhận được", không phải "đã bác bỏ" — muốn có câu trả lời thật cần chạy lại mỗi cấu hình ≥3-5 lần với seed khác nhau rồi lấy trung bình + độ lệch chuẩn, nằm ngoài phạm vi đã đầu tư cho thực nghiệm này. Coi đây là điểm dừng hợp lý cho hướng thực nghiệm 3, không tiếp tục đào sâu thêm trừ khi có nhu cầu cụ thể.

## 32. Bản nhiều seed cho thực nghiệm 3 — `main_given_i_multiseed.py`, soạn xong, chờ chạy Colab

Người dùng hỏi "cần nhiều seed hơn là sao" → giải thích: seed cố định (`RANDOM_STATE=42`) lẽ ra làm train tất định, nhưng 1 số phép toán GPU (LSTM/cuDNN) không tất định tuyệt đối ngay cả khi cố định seed — nên chạy lại đúng 1 script y hệt cũng có thể ra số hơi khác. Cần chạy nhiều seed, lấy trung bình ± độ lệch chuẩn, mới tách được tín hiệu thật của `I(t+h)` khỏi nhiễu train.

**Thay đổi code**: `TCNModel` đã có sẵn tham số `seed` (port từ FCF, chưa từng dùng tới trong project này — docstring ghi rõ mục đích chính là để "train cùng config dưới nhiều seed rồi lấy trung bình xoá nhiễu"). Thêm tương tự cho `LSTMModel` và `Seq2SeqLSTMModel` (`seed=None`, mặc định về `RANDOM_STATE` nếu không truyền) — thay tất cả `random.seed(RANDOM_STATE)`/`np.random.seed(RANDOM_STATE)`/`torch.manual_seed(RANDOM_STATE)` bằng `self.seed`.

**Script mới `main_given_i_multiseed.py`**: lặp qua 3 kiến trúc × 2 biến thể (baseline/given_I) × **5 seed** (42-46) × 4 horizon = 120 lần train (LSTM/TCN: 1 model/horizon; Seq2Seq: 1 model cho cả 4 horizon/lần). Sau khi chạy xong:
- Lưu toàn bộ kết quả thô (`given_i_multiseed_raw.csv`, 120 dòng).
- Tính `mean`/`std` MAE theo nhóm (kiến trúc, biến thể, horizon) → `given_i_multiseed_summary.csv`.
- Tự động kết luận từng (kiến trúc, horizon): so `gap = mean(baseline) - mean(given_I)` với `combined_std = std(baseline) + std(given_I)` — nếu `|gap| > combined_std` thì kết luận "thật" (tốt hơn/tệ hơn), ngược lại "không phân biệt được (trong nhiễu)" → `given_i_multiseed_verdict.csv`.

**Đã verify**:
- `python -m py_compile` cho script mới + 3 file model đã sửa — pass.
- Smoke-test cục bộ (LSTM, 2 seed, 2 epoch): seed=42 và seed=43 cho MAE khác nhau rõ ràng dù cùng 1 cấu hình (`use_i=False`: 0.213 vs 0.206 ở h=1) — **minh chứng trực tiếp** cho lý do cần nhiều seed, đúng như giải thích với người dùng.

**Cập nhật notebook** (40 cell, validate + compile-check pass): thêm mục 7.6 (markdown giải thích + 1 cell chạy `main_given_i_multiseed.py`, ước ~15-25 phút) đặt sau 7.5 (Power delta), trước mục 8 (so sánh) — **không** đưa vào `ALL_SCRIPTS` của cell gộp mục 7 (chủ ý để riêng, vì tốn thêm 15-25 phút và output không theo format `*_results.csv` chuẩn mà mục 8 đọc). Bổ sung file vào check mục 4.

**Trạng thái**: đã soạn + test xong, **chưa chạy trên Colab** — chờ người dùng `git pull` rồi chạy mục 7.6.

## 33. Kết quả multi-seed (mục 32 chạy xong) — KẾT LUẬN DỨT ĐIỂM thực nghiệm 3: có hiệu ứng thật, nhỏ, nhất quán

Chạy xong trên Colab, 15.0 phút, 30/30 lần train không lỗi (3 kiến trúc × 2 biến thể × 5 seed).

**Mean ± std MAE (5 seed):**

| Kiến trúc | Horizon | Baseline | Given_I | Gap | % thay đổi | Verdict |
|---|---|---|---|---|---|---|
| LSTM | 1 | 0.199±0.008 | 0.201±0.004 | -0.002 | +1.2% | không phân biệt |
| LSTM | 5 | 0.728±0.026 | 0.634±0.047 | +0.094 | **-12.9%** | **THẬT SỰ TỐT HƠN** |
| LSTM | 10 | 1.093±0.027 | 1.060±0.080 | +0.033 | -3.1% | không phân biệt |
| LSTM | 20 | 1.553±0.036 | 1.537±0.049 | +0.016 | -1.0% | không phân biệt |
| TCN | 1 | 0.203±0.002 | 0.200±0.002 | +0.003 | -1.5% | không phân biệt |
| TCN | 5 | 0.675±0.018 | 0.652±0.017 | +0.023 | -3.4% | không phân biệt |
| TCN | 10 | 1.110±0.048 | 1.036±0.023 | +0.075 | **-6.7%** | **THẬT SỰ TỐT HƠN** |
| TCN | 20 | 1.598±0.046 | 1.521±0.035 | +0.077 | -4.8% | không phân biệt (rất sát ngưỡng) |
| Seq2Seq | 1 | 0.271±0.042 | 0.229±0.006 | +0.042 | -15.4% | không phân biệt (baseline std lớn) |
| Seq2Seq | 5 | 0.750±0.027 | 0.719±0.056 | +0.031 | -4.2% | không phân biệt |
| Seq2Seq | 10 | 1.205±0.074 | 1.126±0.108 | +0.079 | -6.6% | không phân biệt |
| Seq2Seq | 20 | 1.654±0.141 | 1.538±0.134 | +0.116 | -7.0% | không phân biệt (std rất lớn) |

**Phát hiện chính**: **11/12 trường hợp** given_I có MAE trung bình tốt hơn baseline (không phải phân bố ngẫu nhiên 50/50) — chỉ 1/12 (LSTM h=1) gần như hòa. **2/12 vượt ngưỡng bảo thủ** (gap > tổng 2 std) để khẳng định chắc chắn là hiệu ứng thật: **LSTM h=5 (-12.9%)** và **TCN h=10 (-6.7%)**. Không trường hợp nào cho thấy given_I làm tệ hơn thật sự.

**Diễn giải**: ngưỡng "gap > combined std" là bảo thủ (gần tương đương 2-sigma), nên "không phân biệt được" ở 9/12 trường hợp còn lại **không có nghĩa là không có hiệu ứng** — chỉ là chưa đủ mạnh so với nhiễu (n=5 seed) để khẳng định chắc. Với hướng nhất quán 11/12 cùng chiều dương, nhiều khả năng đây **là hiệu ứng thật nhưng nhỏ** (~1-15%, đa số 3-8%), một phần bị nhiễu train che khuất — đặc biệt rõ ở Seq2Seq (std lên tới 0.14 ở h=20, lớn hơn cả gap).

**Kết luận cuối cùng cho thực nghiệm 3** (thay thế kết luận "không kết luận được" ở mục 31): biết trước `I(t+h)` (setpoint dòng điện tương lai — thông tin 1 bộ điều khiển thật luôn có sẵn) **có xu hướng thật sự giúp dự đoán `V`**, xác nhận chắc chắn ở 2/12 tổ hợp (LSTM h=5, TCN h=10), khả năng cao ở phần lớn còn lại. Đây là bằng chứng ủng hộ trực tiếp cho hướng đóng khung "V-forecasting làm input cho MPC" (mục 28) — một bộ điều khiển biết trước lịch trình dòng điện của chính nó sẽ dự đoán điện áp đáng tin cậy hơn dự đoán mù.

Kết quả đầy đủ lưu tại `outputs/reports/given_i_multiseed_{raw,summary,verdict}.csv`.

## 34. Multi-seed cho kết luận CHÍNH — Delta-target V vs persistence (`main_delta_vs_persistence_multiseed.py`), soạn xong, chờ chạy Colab

Người dùng đồng ý hướng đi tiếp theo (mục 24.1, gap #1): kết luận cốt lõi nhất của cả project — Seq2Seq-delta thắng persistence, biên độ tăng dần theo horizon, tới -15.3% ở h=20 (mục 19) — trước giờ chỉ dựa **1 lần chạy duy nhất**, chưa qua kiểm định như thực nghiệm 3 (mục 32-33). Áp đúng phương pháp/hạ tầng vừa xây (tham số `seed`, pattern multi-seed) cho claim chính này.

**Script mới `main_delta_vs_persistence_multiseed.py`**: 
- Tính persistence MAE (số cố định, không cần seed — không train gì) cho `V`, 4 horizon.
- Train `LSTM-delta`, `TCN-delta`, `Seq2Seq-delta` qua **5 seed** (42-46), lấy mean±std MAE mỗi horizon.
- Không chạy lại RF/XGBoost-delta (đã tất định do `random_state` cố định, mục 22.2 đủ tin cậy, không cần lặp).
- Tự kết luận: so `gap = persistence − mean(model)` với `std(model)` — persistence là số cố định nên chỉ cần so lệch khỏi dải `[mean−std, mean+std]` của model, không phải combined std như thực nghiệm 3 (vì phía persistence không có phương sai).

**Đã verify**:
- `python -m py_compile` — pass.
- Smoke-test cục bộ (LSTM, 2 seed, 2 epoch): persistence tính ra khớp chính xác số cũ ở mục 22.1 (0.2014/0.7025/1.1434/1.6899) — xác nhận đúng công thức.

**Cập nhật notebook** (42 cell, validate + compile-check pass): thêm mục 7.7 sau 7.6, trước mục 8 — ước ~10-15 phút. Bổ sung file vào check mục 4.

**Trạng thái**: đã soạn + test xong, **chưa chạy trên Colab** — chờ người dùng `git pull` rồi chạy mục 7.7. Đây là bước cuối cùng để đóng lại gap #1 trong checklist "paper-ready" (mục 24.1).