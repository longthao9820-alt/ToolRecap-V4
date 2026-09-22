# Hướng dẫn sử dụng ToolRecap V4 (Phase 2 Safe Gateway & Transport Boundary)

ToolRecap V4 là ứng dụng Windows Portable thế hệ mới tự động tóm tắt và dựng video recap từ video nguồn.

---

## 1. Trạng thái hiện tại: Phase 2 Safe Gateway & Transport Boundary

> **LƯU Ý TRUNG THỰC VỀ TIẾN ĐỘ & BẢN DỰNG:**
> Hiện tại dự án đã hoàn thành **Phase 2 (Safe Gateway & Transport Boundary)**:
> - **Đã loại bỏ hoàn toàn API gửi whole-video**: Toàn bộ các API truyền tệp video nguyên bản (`StreamingChatPayload`, `submit_chat_analysis`, `validate_model_video_capability`, `DEFAULT_MAX_FILE_SIZE_BYTES`, `SUPPORTED_VIDEO_EXTENSIONS`) đã bị xóa khỏi production code.
> - **AI Gateway an toàn, trung lập nhà cung cấp**: Chỉ hỗ trợ văn bản/JSON và ảnh tĩnh đã được kiểm định (`validate_and_reencode_image`, `submit_text_chat`, `submit_image_chat`), kiểm tra tính sẵn sàng model trung lập (`validate_model_availability`).
> - **Phụ thuộc runtime**: Đã khai báo `Pillow>=10.0.0` trong `pyproject.toml` phục vụ kiểm tra và chuẩn hóa ảnh tĩnh.
> - **Workflow kiểm soát chặt chẽ**:
>   - Khi dự án đã có Final JSON hợp lệ hoặc được import từ trước: chạy thẳng vào luồng dựng (render), thực hiện chính xác 0 lượt gọi Gateway.
>   - Khi cần phân tích video nhưng chưa có Final JSON: quy trình dừng ngay lập tức với ngoại lệ tường minh `AnalysisPipelineUnavailableError` trước khi đọc tệp nguồn, trước mọi lượt gọi Gateway, trước khi ghi checkpoint sub/raw, trước voice và trước render. Trạng thái dự án ghi nhận `FAILED`.
> - **CHƯA CÓ CÁC TÍNH NĂNG PHASE 3+**: Scanner từng phần, Season Catalog, Season Planner, Vision Extraction, Output Writers độc lập và Output Directory resolver CHƯA được triển khai.
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
   - Sub model (phân tích) và Prime model (tổng hợp kịch bản).
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
