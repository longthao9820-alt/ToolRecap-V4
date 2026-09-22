# Hướng dẫn sử dụng ToolRecap V4 (Phase 1 Baseline)

ToolRecap V4 là ứng dụng Windows Portable thế hệ mới tự động tóm tắt và dựng video recap từ video nguồn.

---

## 1. Trạng thái hiện tại: Phase 1 Baseline

> **LƯU Ý TRUNG THỰC VỀ TIẾN ĐỘ & BẢN DỰNG:**
> Hiện tại dự án đang ở mốc hoàn thành **Phase 1 (Baseline Migration & Isolated Repository)**:
> - Đã khởi tạo cấu trúc độc lập ToolRecap V4 từ commit cơ sở V3 `b4c09c358a438d847444a4994cec9c1d11297e8d`.
> - Đã chuyển đổi namespace `toolrecap_v3` -> `toolrecap_v4`, nhận diện thương hiệu V4, phiên bản v4.0.0, đường dẫn lưu trữ riêng biệt `%LOCALAPPDATA%\ToolRecapV4\`.
> - **CHƯA CÓ BẢN DỰNG EXE**: Chưa chạy đóng gói `build_portable.py` / PyInstaller; chưa có tệp `ToolRecapV4.exe` trong `dist/` hoặc bản nén trong `release/`.
> - **CHƯA SẴN SÀNG PRODUCTION**: Mã nguồn ở giai đoạn baseline kỹ thuật, chưa được kiểm chứng phát hành (no release verified).
> - **MỤC TIÊU CẬP NHẬT CHƯA XÁC MINH PHÁT HÀNH**: Cấu hình kho cập nhật đích `longthao9820-alt/ToolRecap-V4` là định danh cấu hình, chưa có bản release thực tế trên remote.
> - **Hành vi luồng xử lý video (whole-video transport / Sub-Prime) hiện vẫn được giữ nguyên từ V3 baseline.**
> - Kiến trúc V4 đầy đủ (Scanner từng phần, Season Catalog, Season Planner, các Output Writer độc lập, Selective Vision, bộ giải quyết thư mục xuất) sẽ được triển khai lần lượt từ Phase 2 trở đi theo kế hoạch `TOOLRECAP_V4_MIGRATION_PLAN.md`.
> - Toàn bộ 215 bài kiểm thử baseline đã được chuyển đổi sang V4 và chạy đạt 100%.

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
