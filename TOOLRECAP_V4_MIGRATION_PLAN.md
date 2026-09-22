# ToolRecap V4 — Kế hoạch chuyển đổi đã kiểm chứng

Ngày kiểm chứng: 22/09/2026. Trạng thái: CHỈ LẬP KẾ HOẠCH, CHỜ PHÊ DUYỆT.

Không triển khai V4, không sửa V2/V3, không bắt đầu Phase 1. Bản sao kiểm toán nằm ngoài V4, dưới `C:\Users\Long\AppData\Local\Temp\kilo\toolrecap-audit-v2-20260922` và `toolrecap-audit-v3-20260922`. Thư mục V4 ban đầu trống; Git tìm thấy là repo cha `C:\Users\Long`, branch main chưa có HEAD, không phải repo V4 riêng. Không sử dụng repo cha để commit dự án sau này.

## 1. Kết quả kiểm chứng và repository drift

| Nguồn | Commit Codex audit | HEAD hiện tại và remote HEAD | Drift |
|---|---|---|---|
| V2 `longthao9820-alt/tool-recap-v2` | `a01a0d8436958d342b2ff135d44f84d46efc6568` | `a01a0d8436958d342b2ff135d44f84d46efc6568` | Không; không có file thay đổi giữa hai mốc |
| V3 `longthao9820-alt/ToolRecap-V3` | `b4c09c358a438d847444a4994cec9c1d11297e8d` | `b4c09c358a438d847444a4994cec9c1d11297e8d` | Không; không có file thay đổi giữa hai mốc |

Bản sao kiểm toán sạch sau kiểm tra. Kiểm thử thực tế trong audit:

- V2: `pytest --basetemp="C:\Users\Long\AppData\Local\Temp\kilo\pytest_v2_run"`: 557 collected, **537 passed, 20 skipped**, 60.24 giây.
- V3: `pytest --basetemp="C:\Users\Long\AppData\Local\Temp\kilo\pytest_v3_run"`: **215 passed**, 38.03 giây.
- Dùng basetemp riêng tránh lỗi dọn thư mục pytest trên Windows. Không chạy lại suite chỉ để xác nhận cùng kết quả.
- Các số 201/205 trong tài liệu V3 cũ không thay thế kết quả 215 hiện tại. Baseline Codex người dùng cung cấp khớp kết quả kiểm thử này.
- Đây là kiểm thử hai nguồn hiện hữu, không phải nghiệm thu V4 hoặc bằng chứng đã xử lý season thật.

### Bản đồ chứng cứ quan trọng

Đường dẫn dưới đây tương đối với từng repository; số dòng theo commit đã khóa.

| Kết luận | Chứng cứ mã nguồn |
|---|---|
| V3 gửi video gốc dạng base64 | `gateway.py:53` `StreamingChatPayload`; dòng 126–171 tạo data URI từ MIME và đọc/encode byte file gốc |
| V3 Sub rồi Prime | `workflow.py:614` `submit_chat_analysis`; `:648` lưu Sub; `:679` `submit_text_chat` |
| Final JSON lưu trước render | `workflow.py:717–746` validate và save; render bắt đầu sau đó |
| Resume ưu tiên Final JSON | `workflow.py:574–580`; cần bổ sung kiểm tra dependency trong V4 |
| Bỏ qua output đã render | `workflow.py:779–814`, fingerprint + tồn tại file + SHA-256 |
| Output mặc định V3 khác yêu cầu V4 | `workflow.py:349–353`, `:419–423`: managed root/outputs/project_id |
| Schema renderer 3.0 | `schemas/recap_v3_schema.json`; không đổi thành 4.0 |
| V3 runtime từ chối zero-output | `validator.py:175–177`; `renderer.py` cũng từ chối project không output |
| V2 enabled-Gateway bypass legacy | `analyzer/engine.py:277–369`; `CanonicalProjectFinalizer.finalize` tại dòng 357 |
| V2 Scanner còn dính editorial policy | `analyzer/evidence.py:482–526`, tự tạo `EditorialPolicy.from_prompt` |
| V2 có cắt transcript quá lớn | `analyzer/evidence.py:244–301` `cap_single_cue_text`, thêm `... [capped]` |
| V2 timestamp chưa đủ strict | `analyzer/evidence.py:136–172` clamp và ghi đè episode ID |
| V2 packing có inverse | `analyzer/final_json.py:91–295`, `pack_scanner_observations` / `unpack_scanner_observations` |
| V2 Finalizer vẫn một request lớn | `analyzer/final_json.py:719–799`, đo bytes, gửi project, repair cả JSON |
| V2 subtitle cache chưa hash nội dung sidecar | `subtitles/cache.py:26–56`, key chứa source stats/track, thiếu content hash asset |
| STT donor cần cải tiến RAM/pinning | `narration.py:503–525` đọc toàn WAV để tính energy; `:530–632` tải model chưa khóa revision; `:635–682` truyền cả audio file cho STT |
| V3 DPAPI entropy phải giữ | `secrets.py:22`, `ToolRecapV3_DPAPI_SecretStorage_v1` |

## 2. Giữ gì, sửa gì trong đề xuất Codex

**Giữ nguyên quyết định đúng:** V3 là nền ứng dụng; V2 là nguồn tham khảo chọn lọc; V4 là đích mới. Giữ V3 UI, workflow, VoiceStudio, audio/render/GPU, quản lý nguồn, publication, updater, bảo mật. Bỏ whole-video transport. Adapt subtitle/OCR/STT/Scanner từ V2. Không đưa legacy editorial pipeline vào V4.

**Bổ sung hoặc thay thế:**

1. Thay Finalizer một request toàn season bằng Catalog + Season Planner + fetch + locked plan + writers độc lập + repair từng output + merge.
2. Stable evidence IDs, store truy xuất đầy đủ, checkpoint từng bước và dependency keys.
3. Live episode/season acceptance là bắt buộc, không còn optional.
4. Output mặc định là thư mục bên cạnh working folder, không dùng managed outputs mặc định V3.
5. Không port `cap_single_cue_text`, clamp evidence tùy ý, prompt-derived Scanner policy, STT energy đọc toàn WAV, cache sidecar dựa riêng metadata.
6. “Giữ nguyên validator/renderer” phải hiểu là giữ hợp đồng và logic ổn định; V4 cần thay đổi nhỏ, có kiểm thử, để chấp nhận kết quả zero-output ở workflow và để publication staging không lọt vào Output Directory.
7. V3 Final JSON-first resume hiện dựa tồn tại artifact; V4 phải kiểm tra provenance và dependency, nếu không thay prompt vẫn có thể dùng JSON cũ.
8. V3 render fingerprint không bao gồm thư mục đích; skip hiện có thể tham chiếu file ở thư mục cũ. V4 cần publication manifest gắn đúng đích, không làm phát sinh AI call.
9. Catalog không giải quyết vô hạn context. Nếu complete catalog không vừa, phải báo lỗi capacity cụ thể; không cắt bỏ dữ liệu, không giả vờ planner đã hiểu toàn season.

## 3. Kiến trúc production đã xác minh

### V3 hiện tại

Discovery direct-child/natural order; fingerprint và probe; `StreamingChatPayload` gửi toàn video gốc qua `image_url` chứa video data URI; Sub nhận video và prompt; lưu Sub text; Prime nhận Sub text + prompt + metadata/schema; validate; lưu Final JSON; VoiceStudio; Audio Mix/FFmpeg/GPU; publication/checkpoints.

Streaming giúp tránh nạp toàn video vào RAM khi encode, **không** làm thay đổi sự thật rằng toàn video được upload. Không suy đoán khả năng video của model qua tên model hoặc dùng local Windows path làm dữ liệu remote.

### V2 hiện tại

Chuẩn bị nguồn/subtitle/STT; Scanner chunks từng episode; evidence cache; khi Gateway bật thì gọi canonical project Finalizer; technical validation và repair. Legacy connector/candidate vẫn được khởi tạo/tham chiếu, và nhánh offline vẫn có logic cũ. Vì vậy không được copy toàn `AnalysisEngine` sang V4.

Scanner V2 chủ yếu transcript; Vision hiện phục vụ OCR bitmap crop, không phải general scene understanding. General Vision, stable IDs và staged Finalizer là chức năng mới V4.

## 4. Phạm vi file V3 giữ và sửa

### Giữ implementation, chỉ đổi namespace/branding khi cần

- `cancellation.py`, `discovery.py`.
- `voice_studio.py`: presets, auto/local/remote, WAV validation, HTTP và hủy.
- `subtitles.py`: SRT renderer-facing, khác package subtitle preparation mới.
- `schemas/recap_v3_schema.json`, `schemas/schema.py`: schema version 3.0.
- `secrets.py`: DPAPI, entropy tương thích; không đổi entropy chỉ vì branding.
- `ui/notifications.py`: thông báo/sound/taskbar.
- `updater/archive.py`, `helper.py`, `semver.py`: thuật toán archive safety/rollback/version.
- `media.py`: probe/render audio selection/GPU/binary lookup hiện hữu. Inspection subtitle bổ sung qua adapter; chỉ sửa shared code nếu kiểm thử chứng minh cần thiết.

### Sửa có giới hạn

| File/module | Công việc |
|---|---|
| `gateway.py` | Xóa video payload/API/capability; text/JSON/image-only; đo payload, lỗi/retry/cancellation |
| `workflow.py` | Thay analysis half; staged resume/dependency; zero-output; resolver và publication destination |
| `persistence.py` | Atomic artifacts/manifest APIs; không dùng sub_analysis làm dependency hợp lệ |
| `validator.py` | Tách/bao dùng validation một output; zero-output cho V4 orchestration; giữ strict nonempty output validation |
| `renderer.py` | Giữ render/audio/voice; điều chỉnh staging publication ra managed staging nếu cần; không gửi zero-output vào renderer |
| `settings.py` | Scanner/Finalizer, Vision/chunk/parallel, source prep/model versions/capacity |
| `ui/settings_dialog.py` | UX Gateway theo V2, test hai model độc lập, không gợi ý model theo nhà cung cấp |
| `ui/worker.py` | Local Executor, orchestrator, progress và cancellation |
| `ui/main_window.py` | Giữ layout; phase progress, output mode auto/manual, trạng thái resume |
| `errors.py` | Lỗi theo phase và nguyên nhân, không gom Finalizer failed |
| `__init__.py` | Interface mới, xóa export video transport |
| `__version__.py`, `__main__.py`, `main.py` | Nhận diện V4 |
| `selfcheck.py` | FFmpeg/FFprobe + OCR/STT native deps + managed model directories |
| `build_portable.py`, `repackage.py`, `pyproject.toml` | Tên V4, dependencies pinned, binaries/data hooks |
| updater manager/validator/init, `update_helper.py` | Asset/marker/repository V4; không trỏ nhầm release V3 |
| `README.md`, `IMPLEMENTATION_REPORT.md` | Tài liệu tiếng Việt, kiến trúc và bằng chứng thực tế |

Regression transport video cũ được thay bằng test cấm video; không giữ kỳ vọng hành vi bị cấm chỉ để đủ 215 test cũ.

## 5. Donor V2 chính xác và giới hạn adaptation

| Module | Symbols/logic chọn lọc |
|---|---|
| `media.py` | `select_english_audio_stream`, `parse_stream_metadata`, nguyên tắc typed probe |
| `subtitles/models.py` | `SubtitleCue`, `SubtitleTrack`, stream metadata, language normalization; không mang render-domain models dư thừa |
| `subtitles/discovery.py` | `extract_episode_identifiers`, `extract_show_prefix`, `match_episode`, `detect_sidecar_metadata`, `discover_sidecars`, `build_embedded_tracks`, `select_best_english_subtitles` |
| `subtitles/parsers.py` | `parse_srt`, `parse_vtt`, `parse_ass` cho ASS/SSA, timestamp/text normalization |
| `subtitles/pipeline.py` | `SubtitlePipeline`, `extract_and_parse`, `get_episode_subtitles`, FFmpeg text/bitmap demux |
| `subtitles/pgs.py` | `parse_pgs_sup`, RLE/palette decoding |
| `subtitles/vobsub.py` | `parse_vobsub_idx`, `parse_spu_packet`, `extract_vobsub_events`, `extract_spu_events_from_stream` |
| `subtitles/ocr.py` | `OcrModelManager`, `OcrAdapter`, model hashes, quality gate, cropped Vision fallback |
| `subtitles/cache.py` | Atomic write/dependency concepts; key được thay để hash actual assets |
| `narration.py` | `extract_audio_from_video`, `ensure_local_whisper_model`, `transcribe_local_whisper`; không mang narration generator cũ |
| `analyzer/evidence.py` | `ScannerChunkPlan`, `plan_scanner_chunks`, `EvidenceScanner`, đo payload/chunk concurrency; bỏ policy và truncate/clamp |
| `analyzer/prompts.py` | Factual evidence schema/prompt, bỏ editorial directives |
| `analyzer/final_json.py` | Packing/inverse, raw prompt boundary, `FinalJsonIssue`, technical repair pattern; không copy one-huge-finalizer lifecycle |
| `api_client.py` | Retry classification/global slots/redaction/image encoding/payload measurement; triển khai bằng httpx V3 |
| `domain/cache.py` | `EvidenceCacheManager` ideas; không mang hierarchy cache |
| `projects.py` | Wiring source prep/dependency signature, không queue/UI/render |
| `settings.py` và UI Gateway V2 | UX/fields Scanner-Finalizer; tuyệt đối không plaintext secrets |

### Loại bỏ hoàn toàn khỏi production V4

`analyzer/connection.py`; `analyzer/candidates/{discovery,consolidation,verifier}.py`; candidate-driven `analyzer/finalizer.py`; `domain/policy.py`; PipelineHealth/hierarchy/candidate/ranking/compact editorial summaries; hierarchy/connection/candidate caches; legacy zero-output verifier; offline visual recap; legacy narration Scanner/Finalizer; V2 renderer/voice/Piper/UI/updater/GPU/audio mixer.

`coverage.py` không port nguyên module. Chỉ xây completeness ledger kỹ thuật, không chấm điểm hoặc lọc nội dung.

## 6. Cấu trúc V4 dự kiến

```text
toolrecap_v4/
  analysis/
    models.py                  # PreparedEpisode, Transcript, Evidence, Catalog, Plan
    dependencies.py            # signatures + dependency invalidation
    cache.py                   # atomic artifacts/manifests
    orchestrator.py            # LocalExecutor + AnalysisOrchestrator
    evidence_store.py          # EvidenceIdAllocator, EvidenceStore
    resume.py                  # reconcile staged checkpoints
    source_prep/
      probe.py
      audio.py
      transcript.py
      stt.py                   # bounded local STT windows/model manager
      subtitles/
        models.py
        discovery.py
        parsers.py
        pipeline.py
        cache.py
        ocr.py
        pgs.py
        vobsub.py
    scanner/
      prompts.py
      chunking.py
      schema.py
      service.py               # ScannerService
    vision/
      requests.py              # validated factual requests + budget ledger
      frames.py                # FrameExtractor
      service.py               # VisionScanner
    finalizer/
      catalog.py               # SeasonCatalogBuilder
      packing.py               # deterministic lossless packing/inverse
      prompts.py
      routing.py               # measured one-shot/staged decision
      planner.py               # SeasonPlanner
      evidence_fetch.py        # EvidenceFetcher
      plan_store.py            # locked plan checkpoint
      writer.py                # OutputWriter
      validation.py            # OutputValidator + plan technical checks
      repair.py                # OutputRepairer
      merge.py                 # deterministic project assembly
  output_paths.py              # resolve_output_directory
  gateway.py
  workflow.py
  persistence.py
  settings.py
  errors.py
  renderer.py
  voice_studio.py
  media.py
  subtitles.py
  validator.py
  cancellation.py
  discovery.py
  secrets.py
  schemas/recap_v3_schema.json
  ui/
  updater/
```

Các tên trên xác định trách nhiệm, không bắt buộc tạo lớp cho mọi hàm. Dùng dataclass/hàm và persistence hiện có; không thêm framework orchestration, event bus hoặc vector DB.

## 7. Local Source Preparation

### Quy trình

1. Discovery V3; chốt ordered mapping `E01...En` và source fingerprints trước chạy song song.
2. Probe duration/video/audio/subtitle; duration thật làm chuẩn.
3. Chọn English program audio; tránh commentary/descriptive theo metadata. Nếu metadata thiếu, ghi rõ fallback/uncertainty, không khẳng định English khi không có chứng cứ.
4. Khám phá sidecar và embedded; kiểm tra đúng show/episode; forced-only không được coi English Full.
5. Ưu tiên English Full text sử dụng được: SRT, ASS/SSA, VTT; embedded text qua FFmpeg.
6. Bitmap PGS/VobSub: demux, decode crop, OCR local, quality gate; OCR Vision chỉ khi flag bật.
7. Không có transcript hợp lệ: STT từ audio stream đã chọn, không mặc định track đầu.
8. Chuẩn hóa milliseconds, cue order, provenance và transcript hash; lưu atomic.

### Bảo đảm kỹ thuật

- Phân biệt global stream index với audio ordinal: không đưa global index nhầm vào `0:a:N`. Contract `AudioSelection` lưu cả hai; FFmpeg map dùng rõ loại index.
- Không coi OCR/STT lỗi hoặc không cài engine là episode im lặng thành công. Silence/no-audio là trạng thái riêng có chứng cứ; không suy diễn visual action từ transcript rỗng.
- Nếu transcript rỗng thật, Scanner có thể phát yêu cầu Vision có phạm vi; thiếu Vision phải giữ uncertainty, không bịa evidence.
- STT xử lý các cửa sổ audio hữu hạn trên đĩa, offset timestamp về episode; overlap được xử lý theo nguồn thời gian, không bỏ câu tùy ý. Không load cả season hoặc whole audio vào RAM, kể cả energy check.
- Tách giới hạn CPU/OCR/STT khỏi Scanner network parallelism; model local không nhân bản theo mỗi episode.
- Model OCR/STT khóa version/revision và checksum manifest; tải vào `.partial`, xác minh xong mới promote. Hủy tải không để model nửa vời thành cache hit.
- Cache subtitle hash cả `.idx` và `.sub` khi VobSub; hash selected sidecar content và identity embedded stream. Inventory selection cần kiểm tra lại để phát hiện sidecar mới trở thành lựa chọn tốt hơn.
- Cancellation kiểm tra giữa probe, demux, OCR, download, STT windows, cache commit; không trả artifact COMPLETE khi bị hủy.

## 8. Scanner factual và stable Evidence IDs

### Scanner

Input chỉ metadata kỹ thuật + transcript chunk + timestamps. Không truyền Recap Prompt, derived policy hoặc output quota. Prompt yêu cầu factual observations, nguồn chứng cứ, uncertainty; không ranking, chọn story hoặc viết recap.

Chunk theo thời lượng và actual serialized payload. Cue quá dài được chia losslessly thành phần có `cue_id`, `part_index`, timestamp gốc; không dùng `... [capped]`. Kích thước envelope không vừa thì lỗi capacity rõ ràng.

Validate strict `episode_id`, source, integer ms, `0 <= start_ms < end_ms <= duration`, chunk grounding và evidence schema. Không tự clamp observation hoặc ghi đè episode sai. Sửa kỹ thuật bounded chỉ chunk lỗi; các chunk đạt giữ nguyên.

Parallelism hữu hạn, shared Gateway slot guard cho Scanner/OCR/Vision; queue có backpressure, không tạo toàn season futures không giới hạn.

### Evidence schema nội bộ

```json
{
  "evidence_id": "E03-EV-021",
  "episode_id": "E03",
  "source_id": "src_003",
  "start_ms": 1862000,
  "end_ms": 1907000,
  "category": "dialogue",
  "observation": "Nội dung quan sát factual nguyên vẹn",
  "dialogue": [{"cue_id": "E03-CUE-310", "text": "Lời thoại"}],
  "entities": ["Beth", "Jamie"],
  "modality": "subtitle",
  "confidence": null,
  "uncertainty": [],
  "visual_refs": [],
  "provenance": {"chunk_id": "E03-CH-017", "artifact_hash": "..."}
}
```

Confidence không có thì `null`, không tự gán xác suất. Modality có thể subtitle/OCR/STT/visual/mixed. Giữ observations mâu thuẫn cùng provenance; không ép thành một sự thật.

### ID stability

- ID do app cấp sau validation, không tin ID model tự đặt.
- Identity đầy đủ: `(project_id, evidence_revision, evidence_id)`; request luôn kèm revision/hash. ID hiển thị giữ `E03-EV-021`.
- Scanner chunk kết quả được lưu bất biến ngay khi hợp lệ. Sau khi episode đủ chunks, sắp deterministic theo chunk order, time/category/content digest và duplicate occurrence; cấp số trong transaction manifest. Không phụ thuộc thứ tự response song song.
- Registry lưu canonical digest/provenance với ID; retry/resume dùng cùng artifact giữ nguyên ID. Không fuzzy-dedup observations tương tự.
- Visual evidence thêm bằng append-only allocator sau evidence đã có; không đánh lại số cũ.
- Re-scan do dependency đổi tạo revision mới; giữ revision cũ cho diagnostics/plan cũ, không dùng lại một ID cũ với nghĩa khác trong cùng revision. Không hứa ID bất biến xuyên qua hai lần AI tạo nội dung khác nhau.

## 9. Full Evidence Store

Dùng immutable JSON artifacts per chunk/episode và index/manifest atomic theo project revision; không cần DB mới. `EvidenceStore.get(id, revision)`, `get_many(ids)`, `query_range(episode,start,end,revision)`.

Range query trả tất cả observations overlap, thứ tự deterministic; không top-K, similarity hoặc chọn “quan trọng”. Batch fetch được phép nhưng có total/count/completeness/hash để không nhầm trang đầu là toàn bộ.

Mọi accepted observation truy xuất được. Chỉ bỏ một request response chưa hợp lệ khỏi active store; raw diagnostics giữ nội bộ. Index và manifests chỉ trỏ blob đã ghi hoàn tất. Artifact thiếu/hash sai không là cache hit. GC không xóa blob còn được locked plan/output tham chiếu.

## 10. Complete Season Evidence Catalog và packing

### Schema

```text
catalog_version, project_id, evidence_revision, catalog_hash
ordered_episodes[]:
  episode_id, source_id, source_basename, duration_ms,
  evidence_count, evidence_manifest_hash, transcript_status
items[]:
  evidence_id, episode_id, source_id, start_ms, end_ms,
  category, entities, factual_observation, modality, uncertainty,
  detail_hash, visual_refs
completeness:
  expected_episode_count, actual_episode_count,
  expected_evidence_count, actual_evidence_count, ids_digest
```

Một entry cho **mỗi** evidence object. Episode có 0 observations vẫn có row metadata/status; episode scan lỗi không được coi complete.

`factual_observation` giữ nguyên ý factual, không tóm tắt bằng app hoặc cắt độ dài. Full dialogue/provenance/chi tiết vẫn local và có thể fetch; catalog là projection có schema công khai, không giả là bản sao mọi trường full evidence. Nếu observation dựa vào quotation thiết yếu, giữ quotation đó trong catalog observation.

### Packing

Áp dụng repeated-field elimination, source/episode tables, entity/string tables, columnar rows, integer milliseconds. Adapt packing/inverse V2; định nghĩa `season-catalog-v1`, không ép decoder cũ lên schema mới.

Bắt buộc `unpack(pack(catalog)) == catalog`; IDs/counts/timestamps/factual text giữ đúng. Đo actual UTF-8 request sau packing. Không cam kết tỷ lệ nén cố định.

**Giới hạn context:** complete packed catalog phải vừa cùng prompt/contract và output reserve của Planner. Nếu không vừa: thử packing lossless phù hợp hơn; nếu vẫn không vừa, lưu checkpoint và báo `CATALOG_CONTEXT_CAPACITY`. Không gửi các tập thành các quyết định biên tập cô lập, không bỏ episode, không tự tóm tắt editorial. Model/capacity lớn hơn là nhu cầu bên ngoài thật sự, không được che bằng timeout.

## 11. Selective Visual Evidence

`EvidenceRequest` loại visual có episode, integer range, questions, reason, requested existing IDs và snapshot hash. Scanner hoặc Planner có thể yêu cầu; request không được chứa local path/FFmpeg command tự do.

Validate episode tồn tại, range hữu hạn hợp lệ. Mặc định reject range vượt nguồn; chỉ chuẩn hóa rounding tolerance nhỏ có version và diagnostics, không âm thầm clamp một yêu cầu khác nghĩa. Merge overlapping ranges để tái sử dụng extraction nhưng giữ mapping tất cả questions/request IDs.

FFmpeg chỉ scan vùng yêu cầu, chọn scene-change/keyframes; fallback interval hữu hạn. Lấy decoded frame PTS thực, không gán timestamp dự kiến của lệnh seek. Giữ aspect ratio/DAR, JPEG <=1280x720, quality mặc định khoảng 80. Không upload video/clip hoặc whole audio.

### Budget khác safety cap

- Default automatic pass: 6 frames/range, 24 frames/episode, một pass.
- Soft budget không phải quyết định story: AI có thể yêu cầu thêm vì thiếu chứng cứ.
- Đề xuất safety profile ban đầu có version: tối đa 12 frames/request, 96 unique frames/episode/project analysis revision, 3 vòng explicit visual follow-up sau automatic pass, 8 vòng evidence negotiation; encoded image <=1 MiB/frame và tổng request phải fit Gateway capacity. Các số này là bảo vệ tài nguyên có thể điều chỉnh có kiểm thử, không output quota.
- Ledger lưu counts/hash trên đĩa; restart không reset để chạy vô tận. Cache hit không tốn lượt extraction/AI mới.
- OCR crop có budget riêng, chunk theo cue và total request/cost ceiling; không dùng 24 scene frames để cắt mất subtitle OCR. Nếu OCR Vision quá ngân sách, chuyển STT local khi hợp lệ hoặc báo lỗi, không âm thầm bỏ cue.
- Repeated identical request trả cache; lặp không tạo evidence mới thì trả lỗi no-progress. Chạm cap: báo evidence chưa đủ, không đánh dấu completed hoặc đổi thành zero-output.
- Vision off: không request nào chứa ảnh, bao gồm OCR fallback. Planner biết capability unavailable, không nhầm với “không có sự kiện”.

Visual response thành evidence mới có frame IDs/hashes/PTS, liên kết original evidence. Không tự nâng confidence hoặc xóa uncertainty từ text nếu chưa có chứng cứ.

## 12. Season Planner và evidence-fetch protocol

Planner là người quyết định biên tập duy nhất ở cấp season. Input: model/reasoning, raw prompt nguyên vẹn, ordered mapping mọi episode, durations, complete catalog, metadata, planning contract/capabilities.

Response là discriminated union:

```text
request_evidence:
  planning_session_id, catalog_hash, request_id,
  requests: ids | episode_time_range | visual

propose_plan:
  planning_session_id, catalog_hash, proposed_plan
```

`EvidenceFetcher` kiểm tra IDs thuộc đúng project/revision/episode. ID bịa hoặc cũ bị reject, không substitute tương tự. Range trả toàn bộ overlap và explicit empty khi thật sự không có; không chuyển empty thành giả evidence.

Fetch response chứa exact objects, ID/hash/timestamps, request ID, completeness và phần planner context cần thiết. Nếu batch quá lớn, phân trang có cursor/checkpoint và pending IDs; không silently gửi subset. Mọi request phải fit context đã đo, gồm conversation state. Không giả định HTTP chat có trí nhớ qua request.

Planner requests/transcript được lưu; mỗi turn có complete catalog hoặc conversation input chứa complete catalog còn nằm trong context, plus structured planning state và requested evidence. Nếu tổng context không vừa, dừng đúng phase/capacity; không xóa lịch sử factual quan trọng để chạy tiếp giả tạo.

Visual enrichment trước lock làm evidence revision/catalog hash mới; planner được cập nhật complete catalog và delta trước khi chấp nhận plan. Đây là continuation, không rerun source prep/Scanner. Khi lock thì không còn pending required evidence.

## 13. Season Editorial Plan và lock

```json
{
  "plan_version": "1",
  "project_id": "project_001",
  "plan_revision": "...",
  "catalog_hash": "...",
  "prompt_hash": "...",
  "finalizer_signature": "...",
  "status": "LOCKED",
  "season_context": "Bối cảnh toàn season do AI viết",
  "outputs": [
    {
      "output_id": "out_001",
      "title_concept": "...",
      "editorial_thesis": "...",
      "story_arc": "...",
      "episode_ids": ["E01", "E03", "E06"],
      "required_evidence_ids": ["E01-EV-034", "E03-EV-012", "E06-EV-055"],
      "cross_episode_context": "...",
      "writer_constraints": {}
    }
  ],
  "unresolved_requests": [],
  "empty_result_reason": null
}
```

Invariant được khóa khi phê duyệt Phase 1: AI quyết định outputs và thứ tự, kể cả 0 output. Sau khi response Season Editorial Plan vượt technical validation, ứng dụng tự cấp canonical IDs deterministic `out_001`, `out_002`, `out_003` theo đúng thứ tự AI trả. Không tin model cấp canonical IDs; không sort theo importance, không thêm output. Schema ví dụ phía trên là plan nội bộ sau khi ứng dụng cấp IDs.

Technical plan validation: schema, all IDs resolve, đúng snapshot, episode references hợp lệ, không trùng output IDs, pending requests đã xử lý. Không đánh giá thesis/story hay secondary-character value.

Lưu `season_plan.json` atomic cùng dependency manifest và evidence closure hashes. Plan đã lock bất biến. Writer thất bại không mở lại plan. Nếu AI writer yêu cầu thay phạm vi/story cần plan revision rõ ràng, không tự replan toàn season.

Zero-output chỉ hợp lệ khi AI trả plan hoàn chỉnh explicit empty, không phải timeout/response missing/repair exhaustion. Lưu Final JSON `outputs: []`, trạng thái `COMPLETED_NO_OUTPUT`, không gọi voice/renderer và không legacy zero-output verifier.

## 14. Per-output Writer

Mỗi `out_NNN` một request/job riêng; mặc định sequential để dễ resume, concurrency hữu hạn có thể bật sau kiểm thử. Input chứa raw prompt, plan hash, season_context, output definition, requested full evidence, relevant cross-episode context, required source mapping/durations, V3 output contract.

AI quyết narration/hook/title/segments/clip/time/order/dialogue. App không rewrite editorial content.

Writer response wrapper nội bộ:

```text
output_id, plan_hash, renderer_output, evidence_usage_by_segment
```

`renderer_output.render_id` bằng locked output ID; provenance wrapper không nhập Final JSON vì V3 cấm extra fields.

Writer có thể fetch evidence đã có bằng protocol chuẩn, không tự tìm file. Visual mới sau lock không tự sửa whole-season catalog/plan: trả `PLAN_EVIDENCE_GAP`, giữ output đạt; chỉ deliberate plan revision mới cho phép enrichment. Mặc định hoàn thành evidence negotiation trước lock như yêu cầu.

Nếu riêng một output vượt context/output capacity, không tự tách thành nhiều recap hay cắt segment. Lưu phase failure, báo capacity; sau này có thể bổ sung AI-defined segmented writing trong cùng output bằng thay đổi được duyệt, không coi đã hỗ trợ trong bản này.

## 15. Validate và repair độc lập

`OutputValidator` dùng schema `$defs/output` cùng V3 runtime rules, có thể validate bằng project envelope một output để tái sử dụng validator. Trả issues có code, JSON path, observed/expected; không sửa trực tiếp JSON.

Kiểm tra:

- Output/segment ID hợp lệ, unique casefold; title Windows-safe.
- Source basename exact match, không absolute path/traversal.
- Integer ms, không bool/NaN/float; `start < end <= actual duration`.
- Subtitle cue relative-to-segment, trong duration.
- Required fields/type; narration/source_audio/subtitles phù hợp renderer và policy kỹ thuật đã chốt.
- Evidence citations tồn tại và time/source grounding; không so “story hay/dở”.
- Cross-output title collision kiểm tra trước lock nếu có title và sau mỗi writer theo plan order. Chỉ output gây collision được repair, không đổi tên output đã đạt.
- Narration duration nếu có không vượt clip. Duration thực của VoiceStudio kiểm tra ở render; render retry không tự gọi Writer hoặc sửa narration.

Repair mặc định tối đa 2 lần/output/attempt chain, ghi checkpoint. Request chỉ invalid output + exact errors + minimum mapping/duration/schema/context; không gửi toàn season hoặc valid outputs. Malformed model JSON giữ raw response bounded và yêu cầu format repair riêng; không dùng heuristic “sửa JSON” làm thay đổi nội dung.

Repair exhaustion giữ phase/output ID/raw diagnostics, chưa COMPLETE. Retry explicit không làm mất outputs đã đạt; automatic không vòng lặp vô hạn.

## 16. Deterministic Final JSON merge và renderer compatibility

Root giữ:

```text
schema_version = "3.0"
project_id
project_name
sources[]
outputs[]
```

Nguồn cần `source_file`; duration/fingerprint optional trong schema nhưng V4 lưu duration đã probe và canonical source mapping. Fingerprint có absolute path chỉ dùng local; không chuyển nguyên fingerprint local vào Gateway.

Output: `render_id`, `title`, `segments` (ít nhất một segment). Segment: `segment_id`, `source_file`, `start_ms`, `end_ms`, `type` (`narration` hoặc `original_dialogue`), `narration`, `source_audio`, `subtitles`; optional `narration_duration_ms`. Cues gồm `start_ms`, `end_ms`, `text`, tương đối segment. `additionalProperties:false` tại root/output/segment/source.

Schema file hiện cho phép `outputs: []`; runtime V3 từ chối. V4 điều chỉnh validator/orchestrator có kiểm soát để xử lý empty completion, không đổi schema_version và không ép renderer render empty list. Các output không rỗng giữ toàn bộ strict behavior.

Merge chỉ dựng root từ metadata local + source map + renderer_output đã validated, theo locked plan order. Không sửa title/narration/time/clip, không thêm/bớt output. Validate cross-output uniqueness và root; mismatch thiếu/extra output là technical error. Canonical serialize/hash, save Final JSON **trước mọi synthesis/render**.

## 17. Tự chọn one-shot hoặc staged

Mặc định staged cho season/multi-episode hoặc capacity không rõ. User không cần chọn mode.

One-shot chỉ khi một project nhỏ được đo an toàn: scope, episode/evidence count, actual request bytes, estimated input tokens (tokenizer khi có; conservative estimate khi không), output reserve, known configured/provider context/output limits và response-risk history cùng model signature. Không chỉ kiểm tra một ngưỡng byte cố định.

Invariant được khóa khi phê duyệt Phase 1: chỉ One-Shot result hoàn chỉnh, đã validate toàn bộ mới được trở thành canonical Final JSON. Nếu response truncated, malformed, context-rejected, incomplete hoặc không phải canonical result hoàn toàn hợp lệ: chỉ giữ raw response cho bounded local diagnostics; tuyệt đối không tái sử dụng partially extracted editorial outputs làm production artifacts và không đánh dấu output riêng lẻ là completed. Chuyển staged bằng source-preparation/Scanner artifacts đã hợp lệ. Không dùng video trong kiến trúc Finalizer mới; việc triển khai invariant thuộc phase Finalizer, không Phase 1.

Cả Planner, fetch, Writer, repair phải preflight capacity, không chỉ initial request. Known limits là profile/configuration, không đoán theo model name. Endpoint đổi không invalidates semantic artifacts nhưng cần refresh capability/capacity probe.

## 18. Checkpoints, atomicity và resume

Managed root `%LOCALAPPDATA%\ToolRecapV4\`:

```text
settings/ secrets/ models/ updates/
projects/<project_id>/
  project.json
  dependencies.json
  prepared/<episode>/
  transcripts/<episode>/
  scanner/<episode>/<chunk>/
  evidence/<revision>/
  vision/requests/ frames/ observations/
  catalog/<hash>/
  planning/<session>/
  season_plan.json
  writers/out_001/ out_002/ ...
  final/final.json
  checkpoints/
  diagnostics/
render-work/
```

Mỗi artifact manifest: type/schema version/dependency digest/content hash/status. Temporary write cùng volume, flush/close, atomic replace; publish manifest cuối. Project lock ngăn hai workers ghi cùng revision. COMPLETE chỉ sau blob + manifest hợp lệ.

Resume reconcile phase state: interrupted RUNNING thành pending/resumable; không coi partial artifact hợp lệ. Load final matching trước; nếu không thì locked plan; tiếp completed output; tiếp evidence/catalog/prep. Ví dụ out_001–005 valid, out_006 failed, out_007 pending: chỉ chạy out_006 rồi out_007.

Lưu raw successful response trước parse/validate để crash sau nhận response có thể phục hồi không gọi lại. Không hứa exactly-once phía provider khi mất kết nối sau provider xử lý nhưng chưa nhận/lưu response; retry đó phải ghi rõ ambiguous transport result, dùng request ID/idempotency khi Gateway thực sự hỗ trợ.

Imported Final JSON có provenance `imported_render_only`, không tự analysis dù đổi AI settings/prompt. Source mutation vẫn `SourceChangedError`, không âm thầm thay file; tạo project mới để dùng source mới.

## 19. Ma trận cache/invalidation

| Thay đổi | Giữ | Invalidates |
|---|---|---|
| Source video đổi | Artifacts cũ chỉ diagnostic | Project hiện tại fail source integrity; project mới tạo dependencies mới |
| Selected sidecar/embedded identity/parser/normalizer đổi | Probe và artifacts episode khác | Transcript episode bị ảnh hưởng, Scanner tương ứng, catalog, plan, outputs phụ thuộc, Final JSON |
| STT audio/model revision/settings đổi | Probe/subtitle phù hợp, tập không dùng STT | STT transcript liên quan và downstream |
| OCR model/version đổi | Track/probe, transcript không qua OCR | OCR artifacts liên quan và downstream |
| Scanner model/reasoning/prompt/schema/chunk policy đổi | Prep/transcript | Scanner closure liên quan, catalog/plan/outputs/Final JSON |
| Scanner parallelism đổi | Mọi valid semantic artifacts | Không invalidation |
| Recap Prompt/metadata editorial đổi | Prep/transcript/Scanner/visual factual/catalog | Plan, writers, Final JSON |
| Finalizer model/reasoning/planner prompt đổi | Prep/Scanner/store/catalog | Plan, writers, Final JSON |
| Writer prompt/schema version đổi | Prep/store/catalog/plan nếu planning contract không đổi | Writers affected, Final JSON |
| Visual setting/request/frame algorithm đổi | Text evidence/transcript | Affected visual artifacts; merged catalog/plan/downstream nếu dùng |
| Vision on/off | Text evidence; old visual blobs lưu lịch sử | Rebuild active evidence snapshot theo policy, không dùng ảnh cũ như Vision-on khi policy off |
| Endpoint/API key đổi | Valid artifacts | Không semantic invalidation; chỉ capability probe |
| Voice/Audio Mix/GPU/render setting đổi | Final JSON và toàn analysis | Render fingerprints liên quan; 0 AI |
| Output Directory đổi | Analysis/Final JSON/render content khi có thể | Publication destination verification/copy; 0 AI |
| Render retry | Toàn analysis | Chỉ render chưa đạt; 0 AI |
| Restart không đổi, valid Final JSON | Tất cả | 0 AI |

Plan phụ thuộc complete season catalog nên thay evidence một tập khiến whole-season plan cần xét lại, không chỉ output từng dùng tập đó. Outputs phụ thuộc plan input hash, output definition, evidence closure, prompt/writer signature. Chỉ reuse khi dependency digest thực sự bằng nhau; không khẳng định “không ảnh hưởng story” do app tự đoán. Khi evidence snapshot thay đổi, default invalidate downstream plan-derived outputs bảo thủ.

Final JSON cache hit yêu cầu manifest/closure hợp lệ, không chỉ file tồn tại. Subtitle content rehash cần thực hiện khi kiểm tra dependency; không OCR/STT/AI nếu unchanged.

## 20. Gateway, payload boundaries và bảo mật

Gateway API chỉ nhận text/JSON và ảnh đã được Local Executor xác minh. Không nhận source video path/blob; allowlist JPEG/PNG thực, giới hạn dimensions/bytes; không chỉ dựa extension/MIME do caller đưa.

| Phase | Payload được gửi |
|---|---|
| Scanner text | Scanner model/reasoning, factual prompt, episode/source basename-ID, non-secret hash khi cần, duration/chunk bounds, exact transcript parts và technical metadata |
| Bitmap OCR Vision | Cropped subtitle image, episode/stream/timestamp, OCR-only instruction; không Recap Prompt |
| General Vision | Reduced selected still frames, actual PTS, episode/range/questions, relevant factual context; không whole scene clip |
| Season Planner | Finalizer model/reasoning, raw Recap Prompt nguyên vẹn, complete ordered mapping/durations/catalog, project metadata và plan contract |
| Evidence follow-up | Exact requested objects/IDs/hashes/timestamps, request ID, snapshot và relevant planner context/completeness |
| Output Writer | Raw prompt, locked plan context/output definition, full requested evidence, relevant cross-episode/visual observations, source mapping/durations, V3 output contract |
| Output Repair | Một invalid output, deterministic issues, minimum necessary contract/mapping/durations/evidence context |
| One-shot | Raw prompt, complete mapping/evidence/catalog cần thiết, V3 contract; chỉ khi preflight đạt |
| Test Scanner/Finalizer | Synthetic text/JSON ping nhỏ, không media thật; không tuyên bố text ping đã kiểm chứng Vision |

Không gửi original video/video URI/base64 video, whole audio, season folder, arbitrary full frame sequence, VoiceStudio credentials hoặc absolute local paths không cần thiết. VoiceStudio là kênh riêng chỉ nhận narration/voice options/auth của nó; không dùng chung credential object Gateway.

Raw prompt được giữ nguyên ký tự/line breaks trong message payload; serialization JSON escape không đổi nội dung sau decode. Prompt đặt trong boundary có cấu trúc; transcript/evidence là dữ liệu không đáng tin, không được coi chỉ thị hệ thống. Model không được yêu cầu app truy cập URL/path tùy ý.

## 21. Payload measurement, lỗi và retry

Mọi Finalizer request log: `phase`, `request_bytes`, `episode_count`, `evidence_count`, `full_evidence_count`, `image_count`, `output_id`, `retry_count`; bổ sung request ID, dependency hash, duration, HTTP status và completion finish_reason khi có. Đo serialized body thực, gồm ảnh base64 nếu có. Không log API key, headers auth, VoiceStudio secrets hoặc dump body mặc định. Raw response diagnostics chỉ local, được redaction và giới hạn lưu trữ.

### Error taxonomy

- `GatewayConnectionError`, `GatewayTimeoutError`, `UpstreamTimeoutError` (chỉ khi có chứng cứ upstream; không đoán mọi timeout).
- `GatewayRateLimitError` (429), `GatewayServerError` (5xx).
- `PayloadContextError`, `CatalogContextCapacityError`, `OutputCapacityError`.
- `MalformedApiResponseError`, `MalformedModelJsonError`.
- `SourcePreparationError`, `TranscriptError`, `OcrError`, `SttError`, `ModelDownloadError`.
- `ScannerValidationError`, `InvalidEvidenceRequestError`, `VisionRequestError`, `EvidenceBudgetExceededError`.
- `SeasonPlannerError`, `OutputWriterError`, `FinalJsonTechnicalValidationError`, `RepairExhaustedError`.
- Giữ `SourceChangedError`, cancellation và render/VoiceStudio/publication errors V3.

Mỗi lỗi lưu phase/output/request/category/retryability/root cause; wrapper không làm mất HTTP code hoặc validator issues.

### Retry

- Connection reset, recoverable timeouts, 408/429/5xx: tối đa 3 transport retries mặc định, exponential backoff+jitter, tôn trọng Retry-After với finite deadline, hủy được.
- 401/403, sai endpoint/model, malformed contract: không blind retry.
- Context/payload rejection: không gửi lại body y hệt; one-shot chuyển staged; staged kiểm tra packing/capacity hoặc dừng có checkpoint.
- Unsupported optional response_format có thể capability fallback có log; không âm thầm bỏ reasoning user yêu cầu rồi cache như cùng cấu hình.
- Malformed model JSON/technical defects: bounded phase repair, tách transport retry. Không cascade nhân retry không giới hạn.
- Hủy không retry; failure không biến thành empty success.

## 22. AI Gateway settings migration

Giữ trải nghiệm V2: endpoint/API key; Scanner model/reasoning/Vision/parallelism/chunk length; Finalizer model/reasoning; Test Scanner và Test Finalizer riêng. Model ID free text; backend không gắn tên Codex/Gemini/Prime/Sub/nhà cung cấp. Fresh install model IDs trống cho đến cấu hình; không prefill vendor model.

Migration đọc legacy `gateway_sub_model`/reasoning thành Scanner, `gateway_prime_model`/reasoning thành Finalizer, giữ literal model người dùng đã chọn kể cả tên `sub` hoặc `prime`; đây là migrated data, không hardcoded identity. Nếu V4 fields có sẵn thì ưu tiên chúng. Không tự điền `prime` khi thiếu Finalizer; hiển thị chưa cấu hình. Version settings migration idempotent.

Secrets V3 đọc bằng DPAPI entropy cũ rồi lưu an toàn dưới V4, không sửa/xóa V3. Không plaintext export hoặc fallback. Lỗi DPAPI chỉ rõ cần nhập lại credential, không ghi token vào diagnostics.

## 23. Giữ VoiceStudio, Audio Mix, renderer/GPU

- VoiceStudio V3 là authoritative: local/remote/auto, presets/instructions, voice language/style/model, WAV validation, cancellation; Tailscale đi qua remote HTTPS URL như hiện hữu, không dựng tunnel mới.
- Giữ UI settings thực: remote URL mặc định trong `AppSettings` đang trống dù adapter có fallback URL. Không coi một địa chỉ Tailscale cụ thể là dịch vụ được đảm bảo truy cập.
- Audio defaults: original/commentary 0 dB, auto duck OFF; khi bật áp dụng mức cấu hình mặc định -12 dB cho narration overlap; original dialogue không duck; loudness -14 LUFS/true peak -1 dBTP.
- Giữ DAR/SAR/rotation/even dimensions, auto canvas, fps/audio normalization, original-dialogue policy, SRT generation/burn, GPU detection NVENC/AMF/QSV và CPU fallback theo code hiện có.
- Giữ source integrity, renderer không sửa Final JSON/narration/clip để ép render thành công.
- Voice/render fail không tự gọi analysis. Narration fit lỗi thực được báo riêng; retry cùng JSON là 0 AI.
- Bổ sung publication bundle hash cho video và SRT, không chỉ video tồn tại, và destination-aware resume.

## 24. Output Directory resolver

Hàm `resolve_output_directory(selection, manual_path, persisted_choice)` dùng:

1. Manual path không rỗng: dùng đúng đích người dùng chọn; không tự nối `Outputs_*`.
2. Không manual: working folder = folder được chọn; với single file = `file.parent`.
3. Automatic target = `working_folder.parent / ("Outputs_" + working_folder.name)`.
4. `mkdir(parents=True, exist_ok=True)` khi chuẩn bị publication; lỗi quyền/target là file phải báo rõ, không silently fallback sang nơi khác.

Ví dụ folder `D:\Yellowstone (2018)\S03` hoặc file `D:\Yellowstone (2018)\S03\Yellowstone.S03E01.mkv` đều ra `D:\Yellowstone (2018)\Outputs_S03`.

Persist `working_folder`, `output_mode: auto|manual`, `resolved_output_dir`; không suy folder từ project_name, video stem hoặc tập đầu khi user chọn folder. Existing resume giữ lựa chọn project, explicit override mới thắng. Drive root/UNC share root không có sibling thông thường: phát lỗi yêu cầu chọn output cụ thể, không sáng tạo tên folder hoặc ghi ra ngoài share.

Chỉ final MP4/publication artifacts/narration SRT/original SRT trong output. Evidence/cache/JSON checkpoint/frames/model/temp processing ở managed root.

### Publication và collision

V3 hiện tạo `.tmp_<pid>` ngay trong đích. Yêu cầu mới cấm internal temporary files tại output: chuyển staging sang managed publication staging ngoài thư mục đích. Nếu khác volume, staging managed trên cùng volume với output rồi atomic rename; không âm thầm fallback copy non-atomic. Nếu không tạo được staging an toàn trên volume đích, báo PublicationStagingError. Dọn staging hỏng theo ownership manifest; không xóa file người dùng.

Giữ guard không đè bất kỳ source, kể cả source không dùng. Directory đã tồn tại được reuse nhưng không mặc nhiên cho phép ghi đè file không thuộc project. Artifact manifest quyết định owned file; collision file lạ báo lỗi. Khi đổi đích, không skip dựa file ở đích cũ; copy validated bundle hoặc render lại theo policy, luôn 0 AI.

## 25. Packaging, self-check và updater

- Windows portable one-dir như V3; EXE/package marker/namespace V4.
- Bundle FFmpeg/FFprobe; không dựa system PATH/Python cài sẵn.
- Pin OCR/STT packages và native dependencies tương thích Windows; model revision/checksum rõ. Verify imports/runtime từ frozen executable, không chỉ developer Python.
- Models/cache ở managed writable directories, không Program Files hoặc Output Directory. First-use model download có progress/cancel; offline thiếu model báo cụ thể.
- Self-check: version/schema/bundled binaries/OCR runtime/STT runtime/model directory/writeability; phân biệt models absent và runtime broken. Không cần gọi paid AI để selfcheck.
- Updater giữ security archive/rollback; asset tên/marker/repository metadata V4 riêng. Nếu chưa có release repository thật thì updater báo chưa cấu hình, không giả URL hoặc nhận package V3.
- Clean-PATH selfcheck là một gate; clean Windows machine/VM không Python/FFmpeg là gate bổ sung mạnh hơn, không đánh đồng hai bằng chứng.
- Bản phát hành tương lai trong `release/`, README tiếng Việt và checksums/report; chưa build hoặc phát hành trong task lập kế hoạch này.

## 26. End-to-end V4

```text
Select File / Folder
  -> V3 direct-child discovery + natural order
  -> stable E01...En + source fingerprints
  -> local probe/audio/subtitle/OCR/STT
  -> normalized timestamped transcript
  -> factual Scanner chunks qua 9Router
  -> validated full episode evidence + stable IDs
  -> selective visual evidence khi cần
  -> Full Evidence Store
  -> complete compact Season Evidence Catalog
  -> AI Season Planner
  -> exact evidence fetch / controlled additional Vision
  -> locked Season Editorial Plan
  -> independent Output Writers
  -> per-output technical validation / repair
  -> deterministic V3-schema Final JSON merge
  -> persist Final JSON
  -> V3 VoiceStudio / Audio Mix / GPU-FFmpeg renderer
  -> manual output hoặc sibling Outputs_<working-folder-name>
  -> final publication bundle + verified hashes
```

Small safe project có thể dùng one-shot ở Finalizer; mọi invariant dữ liệu/bảo mật/resume vẫn giữ.

## 27. Unit, integration và regression plan

### Source preparation

SRT/ASS/SSA/VTT; embedded text; PGS/VobSub thật và synthetic; crop/OCR quality; optional Vision; local STT; selected audio index; commentary/descriptive; forced-only; wrong show/episode sidecar; UTF-8/Unicode paths; empty/malformed cues; canceled download; partial models; timestamp offset/overlap; sidecar same size/mtime nhưng content đổi; VobSub idx/sub dependency.

### Scanner/evidence/catalog

Không Recap Prompt trong Scanner body; không editorial policy imports; no truncation với long cue; bounded concurrency/payload; strict timestamps/IDs; parallel completion order không đổi ID; restart/visual append giữ IDs; revision isolation; all observations retrievable; range fetch đầy đủ; invented IDs reject; no fuzzy substitution; complete catalog mọi episode/evidence; secondary-character/subplot fixtures vẫn có; pack/unpack equality; capacity failure không bỏ entry.

### Planner/writer/repair/merge

Cross-episode fixture; 0/1/multiple outputs; no fixed quota; complete catalog input; prompt exact roundtrip; evidence follow-up completeness; Vision enrichment refresh before lock; lock không còn pending required requests; từng writer độc lập; chỉ output lỗi được repair; valid siblings byte-identical; duplicate title resolution theo plan order; merge deterministic và schema 3.0; không nhét provenance extra fields vào renderer JSON.

### Resume/invalidation/crash

Counters cho từng phase: unchanged restart/final reuse/render retry/voice-render change = 0 AI; prompt change Planner+writers only; Scanner change không rerun STT; one sidecar change chỉ Scanner affected episodes trước season replan; writer fail không Planner rerun; crash sau raw-save, trước manifest, giữa publication; corrupt artifact/hash; imported JSON render-only; source mutation fail strict; endpoint/key/parallelism không làm invalidation sai; output path change không skip nhầm.

### Vision/transport/security

Vision off không ảnh ở mọi phase; default budget vượt được bằng explicit follow-up; hard cap/no-progress survives restart; PTS thật; request range validation; no blind full episode extraction; images actual format, bytes/dimensions cap; production requests không video MIME/data URI/video-extension URI/source video bytes/whole audio; redaction credentials; malicious path/evidence instructions không được thực thi.

### Output Directory — tám nhóm bắt buộc

1. Folder không manual.
2. Single file không manual, dùng parent folder name.
3. Manual override.
4. Auto directory creation.
5. Existing directory safe reuse, file lạ không overwrite.
6. Basename có spaces/Unicode và đúng ví dụ `S03`.
7. Không internal cache/temp/checkpoint ở output, kể cả crash.
8. Collision/hash/resume V3 tiếp tục đúng, thêm đổi destination và thiếu SRT.

Bổ sung root/UNC/permission/read-only/target-is-file/cross-volume staging.

### Regression/build

Giữ mọi regression V3 ngoài kỳ vọng transport/zero-output/default-path được chủ động thay. Port relevant tests V2, không port skipped legacy editorial tests. Chạy targeted suite mỗi phase; full suite tại integration/release; format/lint/type checks theo tooling dự án, không tự công bố check chưa có. Synthetic 10–20 episodes đo peak RAM/worker counts, không coi synthetic là production acceptance.

## 28. Nghiệm thu thật bắt buộc

Điều kiện cần khi triển khai: video người dùng có quyền sử dụng, Gateway credentials/model cấu hình thật, VoiceStudio hoạt động, tài nguyên máy/disk và mạng. Thiếu một điều kiện thì báo blocked acceptance, không báo production-ready.

### A. Một tập TV full-length

Chạy source prep -> Scanner -> evidence -> Finalizer -> Final JSON -> VoiceStudio -> Audio Mix -> render -> output. Ghi source hashes/duration/streams, actual chosen track, transcript method, phase request counts/sizes, peak RAM, wall time, output hashes. FFprobe xác nhận duration/codec; nghe/xem spot checks narration/dialogue/SRT và timestamps. Test auto output và manual output bằng publish/resume, không gọi lại AI không cần thiết.

### B. Một season thật nhiều tập đầy đủ

Chạy staged architecture toàn bộ tập, không vài clip ngắn thay season. Catalog completeness exact; whole-season Planner nhận tất cả episode mapping; evidence fetch hoạt động; visual thật khi cần và controlled targeted request để xác minh đường Vision nếu Planner không tự yêu cầu. Writers/repairs/merge/voice/render tất cả outputs plan yêu cầu.

Gây lỗi kiểm soát ở một output chưa complete; restart phải giữ previous outputs và locked plan. Gây render failure; retry = 0 AI. Reuse matching Final JSON = 0 AI. Thử prompt change reuse Scanner. Kiểm chứng không raw-video/audio upload bằng request instrumentation allowlist + byte/type/size logs, không chỉ grep code.

Đo bounded RAM với cùng concurrency ở episode đầu và cuối season; không tăng tỷ lệ với tổng raw media. Ghi benchmark ceiling theo máy/reference profile trước run, không bịa con số RAM đạt trước đo. Verify source mapping/time clips, cross-episode story khi prompt/test case yêu cầu; nội dung AI không được app chỉnh cho đẹp kết quả.

Remote VoiceStudio/Tailscale, GPU và updater live cần bằng chứng riêng tương ứng capability; chưa kiểm tra máy từ xa hoặc release thật phải ghi “chưa kiểm chứng”, không suy từ mocks. Các thiếu sót bắt buộc chặn tuyên bố production-ready.

## 29. Trình tự triển khai sau phê duyệt

Mỗi phase: implement -> targeted checks -> fix -> checkpoint/commit khi được phép -> report. Không bắt đầu phase nào trong task hiện tại.

| Phase | Công việc | Gate |
|---|---|---|
| 1 | Tạo repo V4 độc lập từ V3 commit đã khóa, namespace/branding, baseline tests | Không đụng repo cha/V2/V3; preserved tests đạt |
| 2 | Xóa video transport; Gateway text/JSON/image, lỗi/measurement/cancel; settings backend skeleton | Negative transport safety + Gateway regressions |
| 3 | Local source prep/subtitle/OCR/STT/model manager | Format/fallback/audio/RAM/cancel tests |
| 4 | Scanner factual, stable IDs, store và atomic dependencies | No-policy/no-truncate/timestamp/cache tests |
| 5 | Catalog completeness/lossless packing/capacity preflight | Exact coverage + roundtrip |
| 6 | Planner/fetch/plan validation/checkpoints | Whole-season input + IDs/protocol/resume |
| 7 | Selective Vision + budgets + catalog refresh + plan lock | Images-only/PTS/soft-hard/no-loop tests |
| 8 | Output Writers và per-output persistence | Independent work/resume/raw prompt |
| 9 | Per-output validation/repair/merge, zero-output, one-shot routing | V3 schema + failed-only repair + deterministic merge |
| 10 | Gateway UI theo V2, secure settings migration, progress states | UI responsiveness + two tests + secrets |
| 11 | Integrate preserved VoiceStudio/Audio Mix/render/GPU | Existing regressions + 0-AI render retries |
| 12 | Output resolver, publication staging/ownership/destination hash | 8 output tests + cross-volume/crash |
| 13 | Portable build/selfcheck/updater V4 | Frozen runtime/clean-PATH/archive validation |
| 14 | Full regression/unit/integration, visual UI inspection | Deterministic suites green + unresolved defects closed |
| 15 | Real full-length episode acceptance | Recorded real E2E evidence |
| 16 | Real whole-season acceptance + recovery + release report | All mandatory production gates passed |

Dependencies/resume không chờ cuối mới thêm: triển khai cùng artifact owner từ Phase 3 onward. Recheck remote drift trước Phase 1; không tự đổi baseline nếu HEAD mới xuất hiện, đánh giá delta trước.

## 30. Tiêu chuẩn hoàn tất và điểm dừng

Kế hoạch đã chốt kiến trúc và điểm tích hợp vào code thật. Không có V4 implementation, executable hay live V4 acceptance trong lần làm việc này.

Production-ready chỉ khi: code/tests/build đạt; full episode và season thật đạt; zero-video-upload và resume/0-AI invariants được đo; output path đúng; package mở trên Windows mục tiêu; báo cáo ghi đúng capability đã/ chưa kiểm chứng.

Bước tiếp theo duy nhất sau tài liệu này: chờ người dùng phê duyệt kế hoạch. Không tự bắt đầu Phase 1.
