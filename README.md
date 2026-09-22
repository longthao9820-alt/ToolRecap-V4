# Hướng dẫn sử dụng ToolRecap V4 (Phase 3 Source Preparation Pipeline)

ToolRecap V4 là ứng dụng Windows Portable thế hệ mới tự động tóm tắt và dựng video recap từ video nguồn.

---

## 1. Trạng thái hiện tại: Phase 3 Source Preparation Pipeline

> **LƯU Ý TRUNG THỰC VỀ TIẾN ĐỘ & BẢN DỰNG:**
> Hiện tại dự án đã hoàn thành **Phase 3 (Source Preparation Pipeline & Subtitle/Audio Processing)**:
> - **Hệ thống chuẩn bị nguồn cục bộ hoàn chỉnh**: Mô-đun `toolrecap_v4.analysis` xử lý trích xuất phụ đề, bóc tách âm thanh, nhận diện tiếng nói và lưu trữ tạo tác chuẩn bị có kiểm soát chất lượng.
> - **Thứ tự ưu tiên trích xuất hội thoại nghiêm ngặt**:
>   1. Phụ đề rời tiếng Anh (Sidecar text: SRT, VTT, ASS) với khả năng làm sạch thẻ định dạng.
>   2. Phụ đề nhúng trong tệp video (Embedded text: SRT, ASS, SSA, VTT, MOV_TEXT).
>   3. Phụ đề dạng ảnh bằng OCR cục bộ (Bitmap OCR: PGS `.sup`, VobSub `.sub`/`.idx` qua RapidOCR ONNX với cổng kiểm soát chất lượng chống rác/lặp ký tự).
>   4. Nhận dạng giọng nói (Speech-to-Text: `faster-whisper` trên luồng âm thanh chính được chọn, phân đoạn cửa sổ có đo tín hiệu năng lượng, chống trùng lặp lề).
> - **Lựa chọn luồng âm thanh thông minh**: Phân biệt rành mạch chỉ số luồng trong container (`global_index`) và thứ tự luồng âm thanh (`audio_ordinal`), tự động ưu tiên ngôn ngữ chính, lọc bỏ luồng bình luận/thuyết minh khi có luồng đối thoại chuẩn.
> - **Bộ nhớ đệm & Lưu trữ chuẩn xác**: Định danh bộ nhớ đệm dựa trên băm nội dung tệp thực tế (`SHA-256`), không dựa riêng thời gian sửa đổi (mtime). Lưu tạo tác tập phim đã chuẩn bị vào `%LOCALAPPDATA%\ToolRecapV4\prepared\<mã_dự_án>\<tập>.json` và `manifest.json`.
> - **Workflow kiểm soát chặt chẽ**:
>   - Khi dự án đã có Final JSON hợp lệ hoặc được import từ trước: chạy thẳng vào luồng dựng (render), thực hiện chính xác 0 lượt gọi Gateway và 0 lượt chạy chuẩn bị nguồn.
>   - Khi chưa có Final JSON: quy trình thực hiện kiểm tra tính toàn vẹn nguồn, chạy chuẩn bị nguồn tuần tự từng tập (`E01`, `E02`, ...), tạo transcript và lưu manifest chuẩn bị, chuyển trạng thái dự án sang `PREPARED`, sau đó dừng có kiểm soát tại ranh giới Phase 3 với ngoại lệ `AnalysisPipelineUnavailableError` (do Scanner đa phương thái chưa triển khai).
> - **CHƯA CÓ CÁC TÍNH NĂNG PHASE 4+**: Multimodal Scanner, Season Catalog, Season Planner, Output Writers độc lập và Output Directory resolver CHƯA được triển khai (thuộc các giai đoạn tiếp theo).
> - **CHƯA CÓ BẢN DỰNG EXE**: Chưa chạy đóng gói `build_portable.py` / PyInstaller; chưa có tệp `ToolRecapV4.exe` trong `dist/` hoặc bản nén trong `release/`.
> - **MỤC TIÊU CẬP NHẬT CHƯA XÁC MINH PHÁT HÀNH**: Cấu hình kho cập nhật đích `longthao9820-alt/ToolRecap-V4` là định danh cấu hình, chưa có bản release thực tế trên remote.

---

## 2. Cách mở ứng dụng (Khi có bản dựng)

> **CẢNH BÁO:** Hiện tại chưa có tệp EXE trong thư mục dự án. Các bước dưới đây sẽ áp dụng sau khi chạy quy trình đóng gói ở các giai đoạn tiếp theo:

- **Cách 1 (Thư mục chạy ngay sau khi build):**
  Vào thư mục `dist/ToolRecapV4` và nhấp đúp chuột vào tệp:
  `ToolRecapV4.exe`

- **Cách 2 (Bản nén phát hành sau khi build):**
  Mở thư mục `release`, giải nén tệp `ToolRecapV4-v4.0.0-windows-portable.zip` ra bất kỳ đâu, rồi nhấp đúp vào `ToolRecapV4.exe` bên trong.

> **Ghi chú:** Ứng dụng tích hợp sẵn FFmpeg, FFprobe và bộ kiểm tra hợp lệ (`--selfcheck`), không cần cài đặt thêm Python hay phần mềm phụ trợ bên ngoài.

---

## 3. Dịch vụ bên ngoài cần chuẩn bị

1. **AI Gateway (9router):**
   - Địa chỉ mặc định: `http://127.0.0.1:20128`.
   - Scanner model và Finalizer model (nhập ID model tự do, provider-neutral).
   - Nhập API key trong **Cài đặt -> 1. AI Gateway**.

2. **VoiceStudio (Tạo giọng đọc):**
   - Local: `http://127.0.0.1:3900`.
   - Remote: Cấu hình URL Tailscale (ví dụ `https://<tên-máy>.ts.net:8443`).

---

## 4. Cách sử dụng (Quy trình 1 chạm A–Z)

1. **Khởi động ứng dụng:** Nhấp đúp chuột vào `ToolRecapV4.exe`.
2. **Chọn video nguồn:** Bấm "Chọn tệp" hoặc "Chọn thư mục".
3. **Cài đặt & Kịch bản:**
   - Bấm nút **"⚙ Cài đặt"**.
   - Kiểm tra AI Gateway, nhập chỉ dẫn kịch bản (Prompt - BẮT BUỘC), chọn giọng đọc (12 mẫu thiết kế sẵn).
   - Bấm **"Lưu cài đặt"**.
4. **Bắt đầu:** Bấm nút **"BẮT ĐẦU"**.
5. **Nhận kết quả:** Bấm nút **"Mở thư mục xuất"** để xem video recap hoàn chỉnh và phụ đề.

---

## 5. Dữ liệu lưu ở đâu?

Tất cả dữ liệu làm việc, cấu hình và tệp tạm được lưu riêng biệt trong thư mục `%LOCALAPPDATA%\ToolRecapV4\`:
- `prepared/`: Dữ liệu tập phim đã chuẩn bị và manifest (`prepared/<mã_dự_án>/<tập>.json`, `manifest.json`).
- `cache/analysis/`: Bộ nhớ đệm phân tích và trích xuất phụ đề/âm thanh content-addressable.
- `sub_analysis/`: Checkpoint phân tích (`sub_analysis/<mã_dự_án>.txt`).
- `final/`: Kịch bản Final JSON (`final/<mã_dự_án>.json`).
- `raw/`: Phản hồi thô từ AI Gateway (`raw/<mã_dự_án>.txt`).
- `projects/`: Trạng thái dự án (`projects/<mã_dự_án>.json`).
- `checkpoints/`: Tiến trình từng bước (`checkpoints/<mã_dự_án>/<mã_checkpoint>.json`).
- `settings/`: Cài đặt hệ thống (`settings/settings.json`, kho cập nhật `longthao9820-alt/ToolRecap-V4`).
- `secrets/`: Khóa bí mật API mã hóa Windows DPAPI (`secrets/credentials.dpapi`).
- `outputs/`: Video recap xuất ra (`outputs/<mã_dự_án>/`).

---

## 6. Khả năng tương thích và bảo mật

- **DPAPI Entropy:** Giữ nguyên chuỗi entropy gốc `b"ToolRecapV3_DPAPI_SecretStorage_v1"` để đảm bảo tương thích giải mã dữ liệu an toàn.
- **Schema Version:** Giữ nguyên schema `3.0` và tệp `recap_v3_schema.json` cho bộ dựng video.
- **Cập nhật:** Kho lưu trữ cập nhật đích được cấu hình là `longthao9820-alt/ToolRecap-V4` (chỉ là giá trị cấu hình định danh, chưa được xác minh phát hành thực tế / no release verified).
