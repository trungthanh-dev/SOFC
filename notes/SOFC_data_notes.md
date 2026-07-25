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