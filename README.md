# Hướng dẫn sử dụng ToolRecap V4 (Phase 10 AI Gateway Settings)

ToolRecap V4 là ứng dụng Windows Portable thế hệ mới tự động tóm tắt và dựng video recap từ video nguồn.

---

## 1. Trạng thái hiện tại: Phase 10 AI Gateway Settings UI

> **LƯU Ý TRUNG THỰC VỀ TIẾN ĐỘ & BẢN DỰNG:**
> Hiện tại dự án đã hoàn thành **Phase 10 (AI Gateway Settings UI & Secure Migration)**:
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
> - **Complete Season Evidence Catalog**:
>   - Mỗi episode theo thứ tự canonical đều có metadata row, kể cả episode hoàn tất với 0 Evidence.
>   - Mỗi Evidence hợp lệ có đúng 1 Catalog item giữ nguyên ID, timestamp, factual observation, entities, modality, uncertainty và detail hash liên kết về Full Evidence.
>   - Completeness ledger xác minh episode/evidence counts, duplicate/missing/unexpected IDs, episode manifest hashes, evidence revision và ordered IDs digest.
>   - Catalog hash canonical không chứa timestamp tạo, PID, random UUID, local path hoặc cấu hình downstream.
> - **Lossless Catalog packing & capacity preflight**:
>   - Packed format `season-catalog-packed-v1` dùng string/source/episode/entity tables và columnar item rows để loại bỏ cấu trúc lặp.
>   - `unpack(pack(catalog)) == catalog`; không cắt text, bỏ Evidence, bỏ episode hoặc thay Unicode.
>   - Đo actual canonical/packed UTF-8 bytes. Không có explicit capacity profile thì trạng thái trung thực là `UNKNOWN`; nếu có thì chỉ báo `FIT` hoặc `EXCEEDS_CONFIGURED_LIMIT`, không bỏ dữ liệu.
>   - Catalog và packed artifact được lưu atomic, hash-verified và reuse khi evidence dependencies không đổi.
> - **Season Planner — editorial AI stage đầu tiên**:
>   - Raw Recap Prompt được đưa vào Planner nguyên văn, cùng complete packed Catalog, canonical episode mapping, durations, Catalog hash và Evidence revision.
>   - Planner tự quyết định output count, story arcs, cross-episode connections, secondary-character/subplot coverage; ứng dụng không chấm điểm hoặc xếp hạng story.
>   - Planner protocol chỉ chấp nhận `REQUEST_EVIDENCE` hoặc `PLANNER_DRAFT`, với validation identity/schema nghiêm ngặt và bounded technical repair.
> - **Exact Full Evidence Fetch**:
>   - Planner chỉ được yêu cầu exact Evidence IDs hoặc exact episode millisecond ranges.
>   - ID/range sai bị reject, không fuzzy match hoặc clamp. Range fetch trả toàn bộ Evidence overlap và explicit completeness metadata.
>   - Full Evidence được lấy từ authoritative Evidence Store và kiểm detail hash với Catalog trước khi gửi lại Planner.
> - **Planner session/resume**:
>   - Planner rounds hữu hạn, raw response được lưu bounded trước validation, completed rounds/evidence fetch/draft được checkpoint atomic và reuse sau restart.
>   - Capacity preflight đo serialized request bytes thực; unknown capacity giữ `UNKNOWN`, explicit overflow dừng mà không bỏ Catalog/Evidence.
> - **Selective Visual Evidence**:
>   - Chỉ các range do Planner Draft yêu cầu mới được xử lý; frame được trích local bằng FFmpeg, giới hạn bộ nhớ, chuẩn hóa JPEG và gửi qua safe image Gateway.
>   - Visual request/frame/Visual Evidence IDs do ứng dụng cấp deterministic; textual `E##-EV-###` không bị đổi.
>   - Vision contract factual-only, strict frame/timestamp identity, ambiguity được giữ; cache/revision tách extraction khỏi interpretation.
>   - Draft không có visual request tạo explicit complete empty manifest với 0 frame và 0 Vision call.
> - **Final Planner refinement & locked Season Plan**:
>   - Final refinement nhận raw prompt nguyên văn, complete Catalog, Planner Draft, authoritative Full Evidence và complete Visual Evidence.
>   - AI quyết định output count/order; ứng dụng giữ nguyên order và cấp canonical `out_001`, `out_002`, ... sau validation.
>   - `season_plan.json` được hash, ghi atomic, khóa immutable và reuse khi semantic dependencies không đổi.
> - **Independent per-output Writers**:
>   - Locked Season Plan tạo đúng một Writer job cho mỗi canonical `out_###`; output count/order/identity không thể bị Writer thay đổi.
>   - Mỗi Writer nhận raw Recap Prompt nguyên văn, exact locked plan entry, authoritative Full Evidence, authoritative Visual Evidence, controlled source mapping/ranges và output language.
>   - Writer requests dùng text/JSON only; không gửi video, audio, frame bytes hoặc Writer output của job khác.
>   - Bounded parallelism, per-output cache/resume, full raw-response checkpoint/recovery và partial-failure preservation được hỗ trợ.
>   - Structured extraction chỉ best-effort (`PARSED`, `UNPARSED`, `INVALID_FOR_PHASE9`); Phase 8 không gọi AI repair và không khẳng định semantic validity.
> - **Per-output strict validation & targeted repair**:
>   - Mỗi `out_###` được parse/validate độc lập bằng deterministic issue codes; valid sibling không bị gọi repair hoặc thay đổi.
>   - Chỉ output invalid nhận bounded AI repair với raw prompt, locked brief, exact errors và authoritative Evidence/Visual Evidence.
>   - Original Writer response, repair attempts, validation results và validated output được giữ riêng, hash/checkpoint để resume.
> - **Deterministic Final JSON schema 3.0**:
>   - Application mapping giữ canonical Season Plan order, không AI merge, không rerank/rewrite narration.
>   - Final artifact được kiểm bằng canonical validator/schema 3.0 rồi ghi atomic và reuse theo semantic revision.
>   - Locked zero-output plan không bị bịa output; hiện dừng rõ bằng `ZeroOutputError` vì canonical application validator không chấp nhận outputs rỗng.
> - **AI Gateway Settings UI**:
>   - Endpoint và API Key có thể cấu hình trực tiếp; API key masked và chỉ lưu qua Windows DPAPI, không nằm trong `settings.json`.
>   - Scanner model/reasoning/parallelism/chunk duration và Vision model/reasoning được expose đúng backend hiện tại.
>   - Finalizer model/reasoning là user-facing canonical setting cho Planner, final refinement, Writer và repair.
>   - Legacy stage-specific values khác nhau được giữ nguyên khi chỉ mở/Cancel; chỉ explicit Save với unified Finalizer mới đồng bộ các stage.
>   - `Test Scanner` và `Test Finalizer` dùng unsaved form values trong background, không cần project, không save ngầm và không tạo analysis artifacts.
> - **Workflow kiểm soát chặt chẽ**:
>   - Khi dự án đã có Final JSON hợp lệ hoặc được import từ trước: chạy thẳng vào luồng dựng (render), thực hiện chính xác 0 lượt gọi Gateway và 0 lượt chạy chuẩn bị nguồn.
>   - Khi các model cần thiết đã cấu hình: ... → independent Writers → targeted validation/repair → schema 3.0 Final JSON → `FINAL_JSON_READY`, sau đó dừng trước Phase 10/11.
>   - Fresh install chưa cấu hình Scanner model dừng rõ ràng ở `PREPARED`; ID model là free text, provider-neutral. Settings cũ được migrate nguyên literal từ `gateway_sub_model`.
> - **CHƯA CÓ CÁC TÍNH NĂNG PHASE 11+**: verified VoiceStudio/Audio Mix/render integration, Output Directory Resolver, packaging và real production acceptance CHƯA được triển khai.
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
- `projects/<project_id>/catalog/<catalog-hash-prefix>/<packing-version-hash>/`: canonical Catalog, packed Catalog và COMPLETE manifest; `catalog/active.json` là dependency-verified checkpoint pointer.
- `projects/<project_id>/planning/<planner-session-id>/`: Planner session, bounded raw responses, round/fetch manifests và `planner_draft.json`.
- `projects/<project_id>/visual/<visual-revision>/`: selective Visual Evidence và completeness manifest.
- `projects/<project_id>/plans/<plan-revision>/season_plan.json`: locked, immutable Season Plan.
- `projects/<project_id>/writers/<season-plan-hash>/<out_###>/`: per-output context manifest, full raw response, best-effort draft extraction and response-complete manifest.
- `projects/<project_id>/finalization/<revision>/`: validated outputs, repair provenance, canonical `final.json` and COMPLETE manifest.
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
