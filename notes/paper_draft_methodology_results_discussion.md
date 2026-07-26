# Ranh giới dự đoán được của hệ SOFC: Methodology, Results, Discussion (bản thảo)

*Khung chủ đạo: SOFC là trọng tâm, AI là công cụ để trả lời câu hỏi kỹ thuật "cái gì dự đoán trước được để hỗ trợ vận hành/giám sát hệ SOFC, cái gì không, và vì sao". Dùng số liệu đã kiểm định cuối cùng (multi-seed, mục 35 của `SOFC_data_notes.md`), không dùng số liệu 1-lần-chạy đã bị sửa lại.*

---

## 2. Methodology (Phương pháp)

### 2.1. Hệ thống và dữ liệu

Dữ liệu đến từ 1 hệ SOFC cogeneration thương mại thật, công suất danh định 1.5 kW, ngăn xếp 27 cell, vận hành ở 3 mode công suất (500W/1000W/1500W) và nhiệt độ stack 600–1000°C, ghi log qua phần mềm điều khiển chuyên dụng với chu kỳ lấy mẫu $\Delta t = 30$ giây. Bộ dữ liệu công khai này (`caapel/SOFC`) gắn liền với công bố gốc của Beloev et al. (2025), vốn chỉ dùng nó cho bài toán **nowcasting**:

$$\hat V_t = f_\theta(\mathbf{u}_t), \qquad \mathbf{u}_t = \text{cảm biến khác đo tại cùng thời điểm } t.$$

Nghiên cứu này đặt lại bài toán theo hướng **true forecasting**. Gọi $y_t \in \{V_t, W_t\}$ là đại lượng mục tiêu tại bước thời gian rời rạc $t$, và $\mathbf{X}_t \in \mathbb{R}^{w \times d}$ là cửa sổ $w$ bước quá khứ của $d$ đặc trưng cảm biến, kết thúc tại $t$:

$$\mathbf{X}_t = \big(\mathbf{x}_{t-w+1}, \mathbf{x}_{t-w+2}, \ldots, \mathbf{x}_t\big), \qquad \mathbf{x}_\tau \in \mathbb{R}^d.$$

Mục tiêu là học ánh xạ $f_\theta: \mathbb{R}^{w\times d} \to \mathbb{R}$ sao cho $\hat y_{t+h} \approx y_{t+h}$ với $h \in \mathcal{H} = \{1, 5, 10, 20\}$ (tương ứng $h\cdot\Delta t \in \{30\text{s},\, 2.5\text{'},\, 5\text{'},\, 10\text{'}\}$), **chỉ dùng thông tin tại và trước $t$** — khác biệt căn bản với công thức nowcasting ở trên, vốn không có khái niệm "trước/sau".

Dữ liệu thô gồm 32.843 dòng, 47 cột (45 cảm biến định danh dạng mã nội bộ `VDxxxx`, đã ánh xạ sang tên vật lý theo tài liệu gốc của tác giả — nhiệt độ tại 15 vị trí, lưu lượng khí, tốc độ quạt/bơm, dòng điện $I$, điện áp $V$, công suất $W$, với ràng buộc đại số đúng tuyệt đối $W_t = V_t \cdot I_t$). Khoảng thời gian thu thập trải dài gần 10 tháng (2024-04-23 → 2025-02-18), nhưng không liên tục: log được ghi thành **8 phiên đo rời rạc** (run) $R = \{r_1, \ldots, r_8\}$, cách nhau từ vài giờ đến ~10 tháng.

### 2.2. Làm sạch dữ liệu và cấu trúc run-aware

Pipeline làm sạch tái lập đúng quy trình của Beloev et al. và được xác nhận khớp tuyệt đối với số liệu paper công bố ở mọi bước trung gian: loại 12 cột cảm biến hỏng (giá trị hằng số 3000), loại 92 dòng lỗi cảm biến nhiệt độ T17, loại 18.324 dòng có $V=0$ (giai đoạn khởi động/hot-standby/tắt máy) — còn lại **14.427 dòng**, khớp chính xác số liệu paper gốc. Sau khi loại 3 run suy biến, dữ liệu còn **13.496 dòng, 5 run** ($R = \{r_1,\ldots,r_5\}$, độ dài $n_1, \ldots, n_5$).

Vì dữ liệu gồm nhiều phiên đo rời rạc, mọi phép biến đổi có tính "nhìn lại quá khứ" (đặc trưng lag/rolling, cửa sổ trượt) **bắt buộc phải giới hạn trong từng run riêng biệt**. Với đặc trưng lịch sử bậc $k$ (lag, rolling mean/std, slope), giá trị tại dòng $t$ thuộc run $r$ chỉ được tính từ $\{y_\tau : \tau \le t,\ \tau \in r\}$ — nếu không ràng buộc này, dòng đầu tiên của 1 phiên đo sẽ "mượn" giá trị của phiên đo trước đó (cách đó có thể tới 10 tháng) làm giá trị lag, gây rò rỉ thông tin sai hoàn toàn.

Tương tự, tập chỉ số neo hợp lệ (anchor) cho cửa sổ trượt với horizon $h$ trong run $r$ (độ dài $n_r$) là:

$$\mathcal{T}_r^{(h)} = \{\, t : w \le t \le n_r - h \,\}, \qquad |\mathcal{T}_r^{(h)}| = \max(n_r - w - h + 1,\ 0),$$

và toàn bộ tập mẫu huấn luyện/kiểm tra là hợp của các tập này trên từng run riêng biệt, $\mathcal{T}^{(h)} = \bigcup_{r \in R} \mathcal{T}_r^{(h)}$ — không có cặp $(\mathbf{X}_t, y_{t+h})$ nào bắc cầu qua 2 run khác nhau. Số mẫu thực tế thu được khớp chính xác với công thức trên (kiểm tra biên), xác nhận việc triển khai đúng.

Dữ liệu được chia train/validation/test theo đơn vị *cả run* (không theo dòng), giữ nguyên thứ tự thời gian (run huấn luyện luôn xảy ra trước run kiểm tra):

| Tập | Số run | Số dòng | Tỉ lệ |
|---|---|---|---|
| Train | 3 (đầu tiên theo thời gian) | 9.198 | 68.2% |
| Validation | 1 | 2.073 | 15.4% |
| Test | 1 (gần nhất theo thời gian) | 2.225 | 16.5% |

với window size $w=20$ (10 phút quá khứ).

### 2.3. Hai cách đặt lại bài toán: Raw-target và Delta-Target Reformulation

**Raw-target:** $\hat y_{t+h} = f_\theta(\mathbf{X}_t)$, huấn luyện bằng cách tối thiểu hoá hàm mất mát trên $y_{t+h}$ trực tiếp.

**Delta-Target Reformulation:** gọi $y_t$ là *anchor* (giá trị đã biết tại thời điểm hiện tại), định nghĩa biến thiên cần dự đoán

$$\Delta_{t+h} = y_{t+h} - y_t,$$

và huấn luyện $g_\theta(\mathbf{X}_t) \to \hat\Delta_{t+h}$ trên $\Delta_{t+h}$ thay vì $y_{t+h}$. Giá trị dự đoán được tái tạo bằng phép cộng đơn giản:

$$\hat y_{t+h} = y_t + \hat\Delta_{t+h}.$$

Cách đặt lại này triệt tiêu trực tiếp "lối tắt" phổ biến của raw-target — chép lại $y_t$ — vì dưới delta-target, chiến lược đó tương đương với $\hat\Delta_{t+h}=0$, một điểm khởi đầu trung lập chứ không còn là điểm tối ưu miễn phí.

### 2.4. Kiến trúc model

5 kiến trúc được huấn luyện độc lập cho mỗi horizon $h\in\mathcal H$ (Random Forest, XGBoost, LSTM, TCN — mỗi model học 1 hàm $f_\theta^{(h)}$ hoặc $g_\theta^{(h)}$ riêng cho từng horizon) và 1 kiến trúc Encoder–Decoder dự đoán đồng thời cả 4 horizon (Seq2Seq LSTM, học chung 1 hàm $F_\theta: \mathbb{R}^{w\times d}\to\mathbb{R}^{|\mathcal H|}$).

- **Random Forest / XGBoost**: $\mathbf X_t$ được làm phẳng thành vector $\mathbb{R}^{w\cdot d}$; 300 cây.
- **LSTM**: 2 lớp, 128 đơn vị ẩn; tại bước cuối cửa sổ, trạng thái ẩn $h_w$ được đưa qua 1 lớp fully-connected để ra $\hat\Delta_{t+h}$ (hoặc $\hat y_{t+h}$). Huấn luyện bằng Huber loss $\mathcal{L}_\delta(e) = \tfrac12 e^2$ nếu $|e|\le\delta$, ngược lại $\delta(|e|-\tfrac12\delta)$ (với $e = y-\hat y$), cùng gradient clipping và early stopping theo validation loss.
- **TCN**: 4 khối temporal-convolution nhân quả (causal), dilation $d_l = 2^{l}$ tại lớp $l$, tổng receptive field $\mathrm{RF} = 1 + 2(k-1)\sum_l d_l$ với kernel size $k=3$; khởi tạo trọng số $\mathcal N(0, 0.01)$ theo Bai et al. (2018); ép buộc thuật toán tất định trên GPU.
- **Seq2Seq LSTM**: encoder đọc $\mathbf X_t$ ra trạng thái nền $(h_T, c_T)$; decoder tự hồi quy (autoregressive) qua $|\mathcal H|=4$ bước, mỗi bước nhận dự đoán bước trước làm đầu vào, sinh $\hat\Delta_{t+h_1}, \ldots, \hat\Delta_{t+h_4}$ tuần tự từ cùng 1 trạng thái nền.

Toàn bộ pipeline triển khai bằng Python/PyTorch/scikit-learn/XGBoost, huấn luyện cục bộ (RF/XGBoost) và trên GPU Colab (LSTM/TCN/Seq2Seq).

### 2.5. Khung đánh giá — 4 công cụ bắt buộc

**Chỉ số đánh giá.** Với $n$ mẫu kiểm tra, $y_i, \hat y_i$:

$$\mathrm{MAE} = \frac{1}{n}\sum_i |y_i-\hat y_i|, \quad
\mathrm{RMSE} = \sqrt{\frac{1}{n}\sum_i (y_i-\hat y_i)^2}, \quad
R^2 = 1 - \frac{\sum_i (y_i-\hat y_i)^2}{\sum_i (y_i-\bar y)^2}.$$

Để đo độ lệch hình dạng theo thời gian (không chỉ theo từng điểm), dùng thêm **Dynamic Time Warping** với dải Sakoe–Chiba bán kính $\rho=10$ — quy hoạch động $D(i,j) = |y_i-\hat y_j| + \min\{D(i-1,j), D(i,j-1), D(i-1,j-1)\}$ giới hạn trong $|i-j|\le\rho$, độ phức tạp $O(n\rho)$ thay vì $O(n^2)$.

**(i) Persistence baseline bắt buộc.** Mọi model được đối chiếu với baseline

$$\hat y^{\text{persist}}_{t+h} = y_t \quad (\text{tương đương } \hat\Delta_{t+h}=0),$$

ngưỡng tối thiểu để 1 model được công nhận là "học được điều gì đó", không chỉ là "tốt hơn 1 model khác". Nguyên tắc phản ánh khuyến nghị đang được nhấn mạnh trở lại trong cộng đồng dự báo chuỗi thời gian (Beck et al., 2025) nhưng chưa từng áp dụng cho bài toán SOFC trong các công bố đã tra cứu (mục 4.2).

**(ii) Shrinkage ratio và correlation — chẩn đoán hành vi model dưới Delta-Target.** Với $\Delta$ (thật) và $\hat\Delta$ (dự đoán) trên tập kiểm tra, định nghĩa

$$\mathrm{shrink} = \frac{\mathrm{std}(\hat\Delta)}{\mathrm{std}(\Delta)}, \qquad \rho_{\Delta} = \mathrm{corr}(\Delta, \hat\Delta).$$

$\mathrm{shrink}\ll 1$ với $\rho_\Delta$ thấp cho biết model "co rúm" dự đoán về gần 0 (chiến lược an toàn dưới loss lồi khi tín hiệu nhiễu); $\mathrm{shrink}\gtrsim 1$ với $\rho_\Delta$ thấp cho biết model dự đoán biến động đúng độ lớn nhưng gần như ngẫu nhiên (overfit nhiễu, cộng dồn sai số lên anchor).

**(iii) Oracle-decomposition.** Với $W_t = V_t\cdot I_t$, thay từng thừa số bằng giá trị thật (oracle) trong khi thừa số còn lại giữ ở mức persistence, để cô lập nút thắt cổ chai:

$$\hat W^{(A)}_{t+h} = V_{t+h}\cdot I_t, \qquad \hat W^{(B)}_{t+h} = V_t \cdot I_{t+h}, \qquad \hat W^{(C)}_{t+h} = V_{t+h}\cdot I_{t+h}\ (\equiv W_{t+h},\text{ sanity check}).$$

**(iv) Multi-seed validation.** Với model có yếu tố ngẫu nhiên (LSTM, TCN, Seq2Seq), huấn luyện lặp lại với $S=5$ seed độc lập $\{42,\ldots,46\}$, thu được $\{\mathrm{MAE}^{(1)}_m,\ldots,\mathrm{MAE}^{(S)}_m\}$, báo cáo

$$\mu_m = \frac{1}{S}\sum_{s=1}^{S}\mathrm{MAE}^{(s)}_m, \qquad \sigma_m = \sqrt{\frac{1}{S}\sum_{s=1}^S (\mathrm{MAE}^{(s)}_m-\mu_m)^2}.$$

So với 1 giá trị cố định (persistence $p$, không có phương sai): kết luận "thắng thật" khi $p - \mu_m > \sigma_m$. So giữa 2 model/biến thể ngẫu nhiên: kết luận "khác biệt thật" khi $|\mu_1-\mu_2| > \sigma_1+\sigma_2$ — ngưỡng có chủ đích bảo thủ. Nguyên tắc này bắt nguồn từ quan sát thực nghiệm: dù cố định seed, huấn luyện GPU của kiến trúc tuần tự không tất định tuyệt đối (các phép toán cuDNN không đảm bảo tái lập bit-for-bit), nên 1 lần chạy đơn lẻ không đủ để phân biệt tín hiệu thật với nhiễu huấn luyện (minh chứng cụ thể ở mục 3.1, 4.4).

**Thực nghiệm bổ sung — đưa thông tin ngoại sinh đã biết trước.** Để kiểm tra liệu 1 giá trị tương lai đã biết trước ($I_{t+h}$, mô phỏng setpoint 1 bộ điều khiển tự đặt ra) có cải thiện dự đoán $V$ không, cửa sổ đặc trưng được mở rộng thêm 1 kênh không đổi theo thời gian:

$$\mathbf{X}'_t = \mathbf{X}_t \,\Vert\, \big(\underbrace{I_{t+h}, \ldots, I_{t+h}}_{w\text{ lần}}\big)^\top \in \mathbb{R}^{w\times(d+1)},$$

(nối theo chiều đặc trưng, giá trị $I_{t+h}$ lặp lại giống nhau ở mọi bước thời gian trong cửa sổ). Với Seq2Seq (dự đoán đồng thời $|\mathcal H|$ horizon), mở rộng thêm $|\mathcal H|$ kênh, mỗi kênh ứng với $I_{t+h}$ của 1 horizon.

---

## 3. Results

### 3.1. Câu hỏi (a): Điện áp `V` có dự đoán trước được không?

**Ngưỡng tham chiếu.** Vì điện áp SOFC biến đổi tương đối mượt trong khung thời gian 30 giây–10 phút, bản thân baseline persistence đã rất mạnh: MAE 0.20V (h=1) đến 1.69V (h=20), R² từ 0.99 xuống 0.87. Đây là ngưỡng mọi model phải vượt qua để được coi là có giá trị dự báo thật.

**Raw-target thất bại một cách có hệ thống.** Cả 5 kiến trúc raw-target (RF, XGBoost, LSTM, TCN, Seq2Seq) đều **thua persistence ở mọi horizon** đã thử nghiệm. Phân tích feature-importance cho thấy nguyên nhân: các model raw-target dựa ngày càng nhiều vào đặc trưng "giá trị điện áp gần nhất" khi horizon tăng (từ 52% tổng importance ở h=1 lên tới 85% ở h=20 đối với Random Forest) — tức là càng dự báo xa, model càng phải bám chặt vào "chép lại quá khứ" vì không tìm được tín hiệu nào khác đủ mạnh, nhưng vẫn không tái tạo được persistence hoàn hảo, nên luôn thua chính chiến lược "không làm gì".

**Delta-Target Reformulation — hiệu quả khác nhau theo họ model, đã kiểm định qua multi-seed.** Sau khi kiểm định lại bằng 5 seed độc lập (thay cho kết luận sơ bộ dựa trên 1 lần chạy), kết quả cuối cùng như sau (MAE, so với persistence cùng horizon):

| Model | h=1 | h=5 | h=10 | h=20 |
|---|---|---|---|---|
| Persistence (cố định) | 0.201 | 0.703 | 1.143 | 1.690 |
| **LSTM-delta** | 0.199±0.008 (hòa) | 0.728±0.026 (hòa) | **1.093±0.027 (−4.4%, thắng thật)** | **1.553±0.036 (−8.1%, thắng thật)** |
| TCN-delta | 0.203±0.002 (+1.0%, thua không đáng kể) | **0.675±0.018 (−3.9%, thắng thật)** | 1.110±0.048 (hòa) | **1.598±0.046 (−5.5%, thắng thật)** |
| Seq2Seq-delta | 0.271±0.042 (**+34.6%, thua rõ rệt**) | 0.750±0.027 (**+6.8%, thua thật**) | 1.205±0.074 (hòa) | 1.654±0.141 (hòa, độ lệch chuẩn quá lớn) |
| RF-delta / XGBoost-delta | thua persistence 45–450% ở mọi horizon | | | |

**Cơ chế thất bại của RF/XGBoost-delta.** Áp dụng công cụ chẩn đoán ở mục 2.5(ii): RF-delta và XGBoost-delta cho $\mathrm{shrink} \approx 0.8$–$1.4$ (biên độ dự đoán đúng cỡ biên độ thật) nhưng $\rho_\Delta$ chỉ $0.10$–$0.32$ (tương quan rất yếu với $\Delta$ thật) — nghĩa là 2 model này dự đoán $\hat\Delta$ với biên độ hợp lý nhưng gần như ngẫu nhiên, tương đương cộng thêm nhiễu vào anchor thay vì tín hiệu thật, giải thích vì sao chúng thua cả persistence. Ngược lại, LSTM/TCN/Seq2Seq-delta cho $\mathrm{shrink}$ rất thấp ($0.04$–$0.46$): cơ chế tối ưu hoá gradient dưới Huber loss tự nhiên hội tụ về chiến lược an toàn $\hat\Delta\approx 0$ khi tín hiệu nhiễu — vô tình tái tạo lại chính persistence — rồi cộng thêm 1 phần tín hiệu thật tăng dần theo horizon ($\rho_\Delta$ tăng từ $\sim 0.1$ ở $h=1$ lên $\sim 0.4$ ở $h=20$ đối với cả 3 kiến trúc). Đây là lý do 2 họ model (cây quyết định vs. mạng tuần tự) phản ứng ngược chiều nhau dưới cùng 1 phép đặt lại bài toán.

**Kết luận (a): điện áp có dự đoán trước được, nhưng chỉ với kiến trúc và horizon phù hợp.** `LSTM` kết hợp Delta-Target Reformulation là model **duy nhất** cho kết quả thắng persistence *có kiểm định thống kê* ở cả 2 horizon dài (h=10, h=20), không có horizon nào thua thật. Đây là bằng chứng thực nghiệm rõ ràng nhất cho việc hệ thống SOFC có tồn tại 1 phần động lực học có thể khai thác được ngoài xu hướng quán tính đơn thuần, tại horizon từ 5 phút trở lên.

Đáng chú ý: kết luận ban đầu (dựa trên 1 lần chạy duy nhất) từng xác định **Seq2Seq-delta** là model tốt học được nhiều nhất (thắng persistence tới 15.3% ở h=20). Sau kiểm định 5 seed, phát hiện này **không lặp lại được** — trung bình 5 seed cho thấy Seq2Seq-delta thực chất **thua persistence rõ rệt** ở horizon ngắn và chỉ hòa (không thắng có ý nghĩa) ở horizon dài. Kết quả ban đầu là 1 lần chạy may mắn, không đại diện. Phát hiện này tự nó là 1 minh chứng cụ thể cho tầm quan trọng của kỷ luật (iii) ở mục 2.5 (thảo luận thêm ở mục 4.4).

### 3.2. Câu hỏi (b): Công suất `W` có dự đoán trước được không?

Công suất — đại lượng trực tiếp liên quan đến quyết định điều phối năng lượng — là 1 bài toán khó hơn điện áp về bản chất. Persistence-floor của `W` sập rất nhanh theo horizon (R² từ 0.91 ở h=1 xuống còn **0.008** ở h=20 — gần như không còn giá trị dự báo), phản ánh việc công suất có thể đổi bậc thang đột ngột khi hệ chuyển mode vận hành (500/1000/1500W).

Toàn bộ **10/12 tổ hợp model** (5 kiến trúc × raw/delta, trừ 2 trường hợp) đều thua persistence ở mọi horizon. Duy nhất **Seq2Seq (raw-target, không phải delta) tại h=20 thắng thật** (−6.0% so với persistence) — trường hợp thắng duy nhất trong toàn bộ 24 tổ hợp model×horizon đã thử cho công suất. Delta-Target Reformulation, vốn hiệu quả rõ rệt cho điện áp, ở đây chỉ có tác dụng kéo raw-target *về gần bằng* persistence (không vượt qua), và mất hẳn ý nghĩa ở horizon dài.

**Kết luận (b): công suất về cơ bản KHÔNG dự đoán trước được từ lịch sử cảm biến thuần túy** — đây không phải hạn chế của model mà là hạn chế cấu trúc của bài toán, được làm rõ dứt điểm ở mục 3.3.

### 3.3. Cơ chế: tại sao công suất khó hơn — thực nghiệm oracle-decomposition

Vì `W = V × I` đúng tuyệt đối về đại số, có thể cô lập chính xác đóng góp của từng biến vào độ khó dự đoán `W` bằng cách thay từng biến bằng giá trị *thật* (oracle) trong khi biến còn lại vẫn ở mức persistence:

| Horizon | Persistence `W` | Oracle-`V` + Persistence-`I` | Persistence-`V` + Oracle-`I` |
|---|---|---|---|
| 1 | 6.49 | 8.08 (**+24%, tệ hơn**) | **1.11 (−83%)** |
| 5 | 25.24 | 31.01 (**+23%, tệ hơn**) | **3.78 (−85%)** |
| 10 | 39.10 | 46.26 (**+18%, tệ hơn**) | **6.22 (−84%)** |
| 20 | 47.40 | 53.21 (**+12%, tệ hơn**) | **8.25 (−83%)** |

Kết quả dứt điểm: biết trước `V(t+h)` hoàn hảo mà vẫn thiếu thông tin `I` tương lai khiến dự đoán `W` **tệ hơn cả không làm gì**; ngược lại chỉ cần biết trước `I(t+h)` (dù `V` vẫn ở mức persistence) đã giảm sai số 83–85% ở mọi horizon. Nói cách khác: gần như toàn bộ độ khó của bài toán `W` nằm ở việc không biết trước `I` — dòng điện do operator/tải điều khiển, có thể thay đổi theo quyết định vận hành bất kỳ lúc nào, không mang cấu trúc thời gian nào để học từ lịch sử cảm biến thuần túy. `V` (phản ứng điện hóa của stack) chỉ đóng góp một phần biến động nhỏ, gần như nhiễu nền so với biến động của `I`.

### 3.4. Câu hỏi (c): Biết trước lệnh vận hành có giúp dự đoán điện áp tốt hơn không?

Nếu độ khó của `W` nằm ở việc thiếu thông tin `I` tương lai, câu hỏi tự nhiên tiếp theo: liệu cung cấp thông tin đó (mô phỏng 1 bộ điều khiển thật biết trước setpoint dòng điện của chính mình) có cải thiện dự đoán `V` không? Thực nghiệm này đưa `I(t+h)` vào làm 1 kênh đặc trưng riêng (broadcast dọc theo toàn bộ cửa sổ thời gian, không làm phẳng), huấn luyện lại LSTM/TCN/Seq2Seq-delta, kiểm định qua 5 seed:

| Kiến trúc | h=1 | h=5 | h=10 | h=20 |
|---|---|---|---|---|
| LSTM-delta | hòa (+1.2%) | **−12.9% (thắng thật)** | hòa (−3.1%) | hòa (−1.0%) |
| TCN-delta | hòa (−1.5%) | hòa (−3.4%) | **−6.7% (thắng thật)** | hòa, sát ngưỡng (−4.8%) |
| Seq2Seq-delta | hòa (−15.4%, độ lệch chuẩn baseline lớn) | hòa (−4.2%) | hòa (−6.6%) | hòa (−7.0%) |

**Kết luận (c):** 11/12 tổ hợp kiến trúc×horizon cho chiều hướng cải thiện (không phải phân bố ngẫu nhiên), và 2/12 vượt ngưỡng kiểm định bảo thủ để khẳng định chắc chắn là hiệu ứng thật (LSTM h=5: −12.9%; TCN h=10: −6.7%). Không tổ hợp nào cho thấy việc biết trước `I(t+h)` làm tệ đi. Kết luận: **biết trước lệnh vận hành tương lai có xu hướng thật sự giúp dự đoán điện áp**, dù hiệu ứng khiêm tốn và một phần bị nhiễu huấn luyện che khuất ở phần lớn tổ hợp còn lại.

---

## 4. Discussion

### 4.1. Tổng hợp: ranh giới dự đoán được của hệ SOFC

Ba thực nghiệm ở mục 3 cùng vẽ nên 1 bức tranh nhất quán: **khả năng dự đoán trước của 1 tín hiệu SOFC phụ thuộc vào việc nó là phản ứng nội tại của hệ thống hay là kết quả của quyết định vận hành bên ngoài.** Điện áp — phản ứng điện hóa của ngăn xếp fuel cell trước điều kiện vận hành — mang đủ cấu trúc thời gian để 1 model tuần tự (LSTM) kết hợp Delta-Target Reformulation khai thác được, đặc biệt ở horizon từ 5 phút trở lên. Công suất — về bản chất là tích của điện áp với dòng điện do operator/tải quyết định — gần như không mang cấu trúc thời gian nội tại nào để học, vì thành phần chi phối nó (`I`) là 1 tín hiệu ngoại sinh, không phải quá trình vật lý liên tục. Khi thông tin ngoại sinh đó được cung cấp tường minh (dù chỉ 1 phần, thông qua thực nghiệm (c)), khả năng dự đoán điện áp cải thiện thêm — củng cố thêm cho cách diễn giải này.

### 4.2. Định vị so với literature SOFC hiện có

4 công bố liên quan trực tiếp nhất đã được đối chiếu (Beloev et al. 2025 — paper gốc dataset; Li et al. 2022 và Tofigh/Salehi 2024 — 2 công bố duy nhất tìm được có làm true forecasting thật trên dữ liệu SOFC, dùng kiến trúc Encoder-Decoder LSTM/GRU và CNN-NARX tương ứng; Testasecca et al. 2024 — digital twin SOFC dựa trên dữ liệu vận hành thực tế 6 tháng). Không công bố nào trong số này đối chiếu kết quả với baseline persistence, và không công bố nào áp dụng Delta-Target Reformulation hay phân tích hệ thống theo nhiều horizon dự báo tường minh (h=1/5/10/20) — đây là khoảng trống mà nghiên cứu này lấp vào. Đáng chú ý, kết quả nowcasting ở Testasecca et al. (2024) — tree-based (Random Forest/XGBoost/Gradient Boosting) vượt trội deep learning (LSTM/ANN) trên 1 hệ SOFC hoàn toàn khác — cho thấy pattern quan sát được ở nghiên cứu này (mục 3.1, 3.3: cây quyết định gặp khó khăn đặc thù với Delta-Target) không phải hiện tượng riêng của 1 dataset.

### 4.3. Ý nghĩa kỹ thuật và khuyến nghị thiết kế

Với người thiết kế hệ giám sát/digital twin cho SOFC, 4 kết luận thực nghiệm ở mục 3 chuyển hóa thành 4 khuyến nghị cụ thể:

1. **Luôn kiểm định bất kỳ model dự báo nào (dù kiến trúc gì) với baseline persistence trước khi triển khai.** Nghiên cứu này cho thấy phần lớn model raw-target, và thậm chí một số cấu hình delta-target (RF/XGBoost, Seq2Seq ở horizon ngắn), thực chất tệ hơn "không làm gì" — 1 sai lầm chỉ có thể phát hiện được qua bước kiểm định này.
2. **Module giám sát điện áp chủ động là khả thi ngay** với LSTM kết hợp Delta-Target Reformulation, ở horizon tới 10 phút — đủ để hỗ trợ cảnh báo sớm/lên kế hoạch bảo trì mà không cần thông tin gì thêm ngoài lịch sử cảm biến.
3. **Không nên kỳ vọng dự đoán công suất/năng lượng chính xác chỉ từ lịch sử cảm biến.** Muốn hỗ trợ quyết định điều phối năng lượng (dispatch), hệ thống cần tích hợp lịch trình vận hành đã lên kế hoạch (từ hệ thống quản lý năng lượng - EMS) làm đầu vào tường minh, thay vì cố "đoán mù" từ dữ liệu quá khứ.
4. **Kiến trúc điều khiển dự đoán (MPC) hoặc digital twin nên đưa setpoint đã biết trước (ví dụ dòng điện dự kiến đặt ra) làm 1 kênh đầu vào tường minh cho module dự báo điện áp** — thực nghiệm (c) cho thấy đây là hướng có cơ sở thực nghiệm ủng hộ, dù cần kiến trúc chuyên biệt hơn (thay vì chỉ ghép kênh thô) để khai thác triệt để.

### 4.4. Bài học phương pháp luận: vì sao multi-seed validation không phải tùy chọn

Một phát hiện phụ nhưng có giá trị phương pháp luận đáng kể: kết luận ban đầu của chính nghiên cứu này (dựa trên 1 lần huấn luyện cho mỗi cấu hình) đã xác định sai model tốt nhất — Seq2Seq-delta được cho là chứng minh "học thật" rõ nhất (thắng persistence 15.3% ở h=20), trong khi kiểm định lại qua 5 seed độc lập cho thấy con số đó là 1 lần chạy may mắn, và trung bình thực tế của Seq2Seq-delta **thua persistence rõ rệt** ở horizon ngắn. Nguyên nhân là các kiến trúc tuần tự (LSTM/TCN/Seq2Seq) huấn luyện trên GPU không đảm bảo tất định tuyệt đối dù cố định seed ngẫu nhiên, và biên độ dao động tự nhiên giữa các lần chạy (5–15% MAE) cùng cỡ với hiệu ứng đang muốn đo lường. Đây là minh chứng cụ thể, có số liệu, cho khuyến nghị đang được nhấn mạnh trong cộng đồng dự báo chuỗi thời gian: **không nên rút kết luận về hiệu năng model ngẫu nhiên từ 1 lần huấn luyện duy nhất** — và là lý do phương pháp multi-seed validation (mục 2.5.iii) được đưa vào làm 1 phần cốt lõi của khung đánh giá, không phải bước bổ sung.

### 4.5. Giới hạn

Nghiên cứu này giới hạn ở 1 hệ SOFC, 1 bộ dữ liệu công khai duy nhất — chưa có cơ sở để khẳng định các phát hiện (đặc biệt ranh giới forecastable/non-forecastable giữa `V` và `W`) tổng quát hóa cho mọi cấu hình SOFC khác. Hyperparameter của các kiến trúc deep learning kế thừa từ 1 nghiên cứu dự báo khác (không cùng domain), chưa được tinh chỉnh riêng cho dữ liệu SOFC. Hướng "biết trước lệnh vận hành" (mục 3.4) mới thử nghiệm với cách ghép kênh đặc trưng đơn giản (broadcast), chưa áp dụng kiến trúc NARX chuyên biệt như một số công bố liên quan. Cuối cùng, do bộ dữ liệu không có nhãn sự cố/lỗi vận hành thực tế, hướng ứng dụng "cảnh báo bất thường" dựa trên residual dự báo — dù có cơ sở lý thuyết từ chính kết quả ở đây — chưa được kiểm chứng thực nghiệm.
