# ToolRecap V4 — Báo cáo Phase 2

**Ngày hoàn tất:** 22/09/2026  
**Phase:** Safe Provider-Neutral Gateway & Video Transport Elimination  
**Trạng thái:** Hoàn tất và đã được phê duyệt  
**Repository:** `C:\Users\Long\Desktop\ToolRecap_V4`  
**Branch:** `main`

## 1. Git checkpoint

**Commit trước Phase 2:**

```text
f7cba8b274c8dcb9f6852a898c41848be3b248fa
docs: add approved V4 migration plan
```

**Commit Phase 2:**

```text
3010e873763ce69c5b6bb2ee3c2c8cc1aee68005
refactor: remove whole-video AI transport
```

Commit gồm 10 tệp, 1.675 dòng thêm và 1.387 dòng xóa. V4 không có Git remote. V2 và V3 không bị sửa.

## 2. Mục tiêu và kết quả

Phase 2 xóa hoàn toàn đường gửi video gốc của V3 khỏi production V4 và tạo Gateway provider-neutral chỉ hỗ trợ:

- Text request.
- Structured JSON response.
- Ảnh tĩnh JPEG/PNG được xác minh.

Kết quả chính:

- Không còn API production nhận source video để gửi AI.
- Không còn base64 video, video data URI hoặc video MIME payload.
- Không gửi local video path thay cho upload.
- Không suy capability từ tên model/provider.
- Workflow không có Final JSON dừng rõ ràng, không fallback về V3 whole-video.
- Workflow có Final JSON hợp lệ/imported vẫn render hoặc resume với 0 Gateway call.

## 3. Production files thay đổi

1. `toolrecap_v4/gateway.py`
2. `toolrecap_v4/errors.py`
3. `toolrecap_v4/workflow.py`
4. `toolrecap_v4/__init__.py`
5. `toolrecap_v4/ui/settings_dialog.py`
6. `pyproject.toml`
7. `README.md`
8. `IMPLEMENTATION_REPORT.md`

## 4. Tests thay đổi

1. `tests/test_gateway.py`
2. `tests/test_workflow.py`

Các test bắt buộc whole-video transport được thay bằng negative safety tests. Regression render, import, resume, source integrity và publication collision được giữ.

## 5. Whole-video code đã xóa

Production code không còn:

- `StreamingChatPayload`
- `submit_chat_analysis`
- `validate_model_video_capability`
- `validate_model_prime_capability`
- `SUPPORTED_VIDEO_EXTENSIONS`
- `DEFAULT_MAX_FILE_SIZE_BYTES`
- Video MIME payload generation
- `data:video/...` URI generation
- Whole-source video base64 streaming
- Whole-season raw-video request
- Model capability inference theo model-name string

Không để dormant production API có thể bật lại upload video.

## 6. Gateway public API sau Phase 2

- `GatewayClient.submit_text_chat(...)`
- `GatewayClient.submit_image_chat(...)`
- `GatewayClient.validate_model_availability(...)`
- `validate_and_reencode_image(...)`
- `extract_json_from_text(...)`
- `sanitize_message(...)`
- `GatewayResult`

`submit_text_chat` chỉ nhận text. Ảnh chỉ đi qua API image riêng.

## 7. Image safety boundary

Cho phép:

- JPEG thật.
- PNG thật.
- Ảnh tĩnh một frame.

Validation không tin extension hoặc MIME do caller cung cấp. Gateway kiểm tra magic bytes trước Pillow, giới hạn format decoder, decode ảnh rồi encode lại để loại metadata và trailing data.

Từ chối:

- Video giả ảnh.
- MP4/MKV/MOV/AVI/WEBM.
- GIF/APNG động và multi-frame media.
- Binary tùy ý hoặc `application/octet-stream` giả ảnh.
- Caller-provided raw data URI.
- Ảnh vượt giới hạn byte, dimensions hoặc số lượng.
- Pillow decompression bomb.

Runtime dependency thêm:

```text
Pillow>=10.0.0
```

## 8. Request measurement

Gateway đo body JSON đã serialize thực tế và lưu metadata an toàn:

- Phase/type.
- Model ID.
- Serialized request bytes.
- Retry attempt.
- Image count.
- HTTP status.
- Request duration.

Không log:

- API key.
- Authorization header.
- VoiceStudio credentials.
- Full prompt/body mặc định.

Successful model content được trả nguyên vẹn; secret redaction chỉ áp dụng diagnostics/error text.

## 9. Error classification

Gateway phân biệt:

- Connection failure.
- Request timeout.
- HTTP 401.
- HTTP 403.
- HTTP 404/invalid endpoint.
- HTTP 408.
- HTTP 429.
- HTTP 5xx.
- Payload/context rejection khi nhận diện được.
- Malformed API envelope.
- Missing choices/message/content.
- Empty API response.
- Malformed model JSON.
- Unsupported media.
- Cancellation.

HTTP status và root cause được giữ trong error object phù hợp; không gom thành `Gateway failed`.

## 10. Retry và cancellation

Retry áp dụng có giới hạn cho:

- Lỗi kết nối tạm thời.
- Recoverable timeout.
- HTTP 408.
- HTTP 429.
- HTTP 5xx phù hợp.

Không blind retry:

- 401/403.
- Invalid endpoint/model configuration.
- Deterministic malformed request.
- Unsupported media.

Retry dùng bounded attempts, exponential backoff, finite `Retry-After`, và kiểm tra cancellation trong lúc chờ. Cancellation được propagate, không chuyển thành transport failure rồi retry.

## 11. Workflow trạng thái Phase 2

### Có Final JSON hợp lệ hoặc imported

```text
Final JSON
→ 0 Gateway calls
→ VoiceStudio/render/resume như V3
```

### Chưa có Final JSON

```text
Analysis required
→ AnalysisPipelineUnavailableError
→ không upload video
→ không gọi Gateway
→ không tạo Final JSON giả
→ không gọi VoiceStudio/render
→ lưu FAILED state và diagnostics
```

Đây là trạng thái tạm thời đúng của Phase 2 trước khi Phase 3 source preparation được triển khai.

## 12. Kết quả kiểm thử thực tế

### Full suite

```text
python -m pytest --basetemp="C:\Users\Long\AppData\Local\Temp\kilo\pytest_v4_phase2"
237 passed in 33.75s
```

### Gateway focused suite

```text
33 passed in 0.96s
```

### Kiểm tra bổ sung

- `compileall`: đạt, 0 lỗi.
- Import package/module: đạt.
- `git diff --check`: đạt.
- Production API absence assertions: đạt.
- No-video negative transport tests: đạt.

Không chạy paid/live AI call trong Phase 2.

## 13. Search whole-video references

### Production code

Không còn occurrence hợp lệ của:

```text
StreamingChatPayload
submit_chat_analysis
validate_model_video_capability
SUPPORTED_VIDEO_EXTENSIONS
DEFAULT_MAX_FILE_SIZE_BYTES
data:video
video/*
```

`base64` còn trong `gateway.py` chỉ phục vụ JPEG/PNG tĩnh đã được decode, xác minh và encode lại.

### Tests

Tên API cũ chỉ còn trong negative assertions nhằm ngăn đường video upload xuất hiện trở lại.

### Documentation/history

Approved migration plan và historical reports có thể nhắc kiến trúc V3 cũ để giải thích lý do chuyển đổi; không phải production API.

## 14. Bảo toàn hệ thống V3/V4

Phase 2 không thay đổi:

- Schema version `3.0`.
- `recap_v3_schema.json`.
- DPAPI entropy `ToolRecapV3_DPAPI_SecretStorage_v1`.
- VoiceStudio.
- Audio Mix.
- Renderer/GPU.
- Media probing.
- Notifications.
- Updater algorithms.
- Final JSON render/resume.

## 15. Deviations và giới hạn

Không có deviation kiến trúc so với kế hoạch được duyệt.

An toàn được siết thêm:

- Text API và image API tách riêng.
- Không special-case model ID `sub`, `prime` hoặc tên provider.
- Response body có giới hạn.
- Image byte tổng và từng ảnh có giới hạn cấu hình.
- Successful model response không bị credential redaction làm biến dạng.

Chưa thực hiện trong Phase 2:

- Source preparation.
- Subtitle/OCR/STT pipeline.
- Scanner.
- Evidence IDs/Store.
- Season Catalog/Planner.
- General Vision.
- Output Writer/merge.
- Output Directory resolver.
- Portable EXE build.

## 16. Trạng thái đóng Phase 2

- Phase 2 commit tồn tại và đã được phê duyệt.
- Phase 2 no-video transport guarantees tiếp tục được giữ ở Phase 3.
- V2/V3 không bị sửa.
- Repo V4 độc lập, không remote.
- Phase 2 hoàn tất trước khi Phase 3 bắt đầu.
