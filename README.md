# Hướng dẫn sử dụng ToolRecap V4 (Phase 4 Factual Scanner & Evidence Store)

ToolRecap V4 là ứng dụng Windows Portable thế hệ mới tự động tóm tắt và dựng video recap từ video nguồn.

---

## 1. Trạng thái hiện tại: Phase 4 Factual Scanner & Full Episode Evidence Store

> **LƯU Ý TRUNG THỰC VỀ TIẾN ĐỘ & BẢN DỰNG:**
> Hiện tại dự án đã hoàn thành **Phase 4 (Factual Scanner, Stable Evidence IDs & Full Episode Evidence Store)**:
> - **Hệ thống chuẩn bị nguồn cục bộ hoàn chỉnh**: Mô-đun `toolrecap_v4.analysis` xử lý trích xuất phụ đề, bóc tách âm thanh, nhận diện tiếng nói và lưu trữ tạo tác chuẩn bị có kiểm soát chất lượng.
> - **Thứ tự ưu tiên trích xuất hội thoại nghiêm ngặt**:
>   1. Phụ đề rời tiếng Anh (Sidecar text: SRT, VTT, ASS) với khả năng làm sạch thẻ định dạng.
>   2. Phụ đề nhúng trong tệp video (Embedded text: SRT, ASS, SSA, VTT, MOV_TEXT).
>   3. Phụ đề dạng ảnh bằng OCR cục bộ (Bitmap OCR: PGS `.sup`, VobSub `.sub`/`.idx` qua RapidOCR ONNX với cổng kiểm soát chất lượng chống rác/lặp ký tự).
>   4. Nhận dạng giọng nói (Speech-to-Text: `faster-whisper` trên luồng âm thanh chính được chọn, phân đoạn cửa sổ có đo tín hiệu năng lượng, chống trùng lặp lề).
> - **Lựa chọn luồng âm thanh thông minh**: Phân biệt rành mạch chỉ số luồng trong container (`global_index`) và thứ tự luồng âm thanh (`audio_ordinal`), tự động ưu tiên ngôn ngữ chính, lọc bỏ luồng bình luận/thuyết minh khi có luồng đối thoại chuẩn.
> - **Bộ nhớ đệm & Lưu trữ chuẩn xác**: Định danh bộ nhớ đệm dựa trên băm nội dung tệp thực tế (`SHA-256`), không dựa riêng thời gian sửa đổi (mtime). Lưu tạo tác tập phim đã chuẩn bị vào `%LOCALAPPDATA%\ToolRecapV4\prepared\<mã_dự_án>\<tập>.json` và `manifest.json`.
> - **Scanner factual qua text-only Gateway**:
>   - Chia transcript theo biên cue, thời lượng và kích thước request JSON đã serialize thực tế.
>   - Cue dài được chia thành các technical part lossless, giữ `cue_id`, timestamp và toàn bộ ký tự; không cắt/cap lời thoại.
>   - Prompt Scanner chỉ chứa metadata kỹ thuật, source basename/ID và transcript chunk. Recap Prompt không đi vào Scanner.
>   - Response được kiểm tra nghiêm ngặt về identity, kiểu timestamp, giới hạn episode/chunk, cue provenance, category, modality, confidence và uncertainty; dữ liệu sai không bị clamp hoặc tự sửa identity.
>   - Technical repair có giới hạn và chỉ chạy lại chunk lỗi. Chunk hợp lệ được cache, kiểm hash và dùng lại khi resume.
> - **Stable Evidence IDs & Full Episode Evidence Store**:
>   - Ứng dụng cấp ID deterministic dạng `E01-EV-001` sau validation, độc lập thứ tự network response.
>   - Evidence revision phụ thuộc transcript/artifact, model, reasoning, prompt/schema/validation và chunk policy; không phụ thuộc parallelism, Recap Prompt, voice hoặc render settings.
>   - Lưu immutable JSON + atomic manifest theo project/revision; hỗ trợ get, get-many, toàn episode và truy vấn mọi observation overlap một time range.
>   - Không xếp hạng, top-K, fuzzy dedupe hoặc lọc nhân vật/subplot; mọi observation factual hợp lệ đều được giữ.
> - **Workflow kiểm soát chặt chẽ**:
>   - Khi dự án đã có Final JSON hợp lệ hoặc được import từ trước: chạy thẳng vào luồng dựng (render), thực hiện chính xác 0 lượt gọi Gateway và 0 lượt chạy chuẩn bị nguồn.
>   - Khi chưa có Final JSON và Scanner model đã cấu hình: source preparation → factual Scanner → Evidence Store → trạng thái `EVIDENCE_READY`, sau đó dừng có kiểm soát trước Phase 5.
>   - Fresh install chưa cấu hình Scanner model dừng rõ ràng ở `PREPARED`; ID model là free text, provider-neutral. Settings cũ được migrate nguyên literal từ `gateway_sub_model`.
> - **CHƯA CÓ CÁC TÍNH NĂNG PHASE 5+**: Season Evidence Catalog, Season Planner, general scene Vision, Output Writers và Final JSON generation CHƯA được triển khai. Phase 3 Vision OCR vẫn chỉ dùng crop phụ đề bitmap.
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
- `projects/<project_id>/scanner/<revision>/`: Raw response có giới hạn, chunk Scanner đã validate và manifest hash-verified.
- `projects/<project_id>/evidence/<revision>/`: Full Episode Evidence immutable và revision manifest atomic.
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
