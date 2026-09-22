# ToolRecap V4 — Báo Cáo Nghiệm Thu Phase 3 (Source Preparation Pipeline)

**Ngày**: 2026-09-22  
**Hợp đồng**: `phase3-docs-acceptance rev1 objective4`  
**Nền tảng mục tiêu**: Windows 10/11 x64 Portable  
**Phiên bản ứng dụng**: `4.0.0`  
**Trạng thái**: NGHIỆM THU HOÀN TẤT (PHASE 3 SOURCE PREPARATION ACCEPTED; SSA/Vision OCR closure verified)

---

## 1. Tóm tắt thực hiện (Executive Summary)

Phase 3 triển khai toàn diện và hoàn tất hệ thống **Chuẩn bị nguồn cục bộ (Source Preparation Pipeline)** cho ToolRecap V4, thiết lập nền tảng trích xuất hội thoại đa tầng, bóc tách luồng âm thanh/video chuẩn xác, nhận diện tiếng nói STT cục bộ, quản lý bộ nhớ đệm theo băm nội dung thực tế (content-addressable hashing) và tích hợp điều phối workflow có kiểm soát an toàn trước ranh giới Phase 4 (Scanner).

### Các kết quả then chốt:
1. **Kiến trúc mô-đun phân tích mới (`toolrecap_v4/analysis/`)**:
   - 19 tệp mã nguồn Python mới được tổ chức chặt chẽ thành các gói `toolrecap_v4.analysis` và `toolrecap_v4.analysis.source_prep`.
   - Các cấu trúc dữ liệu bất biến: `TranscriptCue`, `Transcript`, `AudioSelection`, `PreparedEpisode`.
2. **Quy trình trích xuất phụ đề đa tầng với thứ tự ưu tiên nghiêm ngặt**:
   - Ưu tiên 1: Phụ đề rời tiếng Anh (Sidecar text: `.srt`, `.vtt`, `.ass`) qua bộ phân tích bóc tách sạch thẻ định dạng.
   - Ưu tiên 2: Phụ đề nhúng tiếng Anh (Embedded text: SRT, ASS, VTT, MOV_TEXT).
   - Ưu tiên 3: Phụ đề ảnh bitmap bằng OCR cục bộ (Bitmap OCR: PGS `.sup` và VobSub `.sub`/`.idx` với `OcrAdapter` hỗ trợ ONNX runtime và cổng kiểm soát chất lượng chống rác/lặp ký tự).
   - Ưu tiên 4: Nhận diện giọng nói STT (`faster-whisper` trên luồng âm thanh chọn lọc, phân cửa sổ có đo tín hiệu năng lượng, chống trùng lặp biên).
3. **Phân biệt rành mạch luồng âm thanh**:
   - `AudioSelection` lưu trữ tách biệt cả chỉ số luồng trong container (`global_index`) phục vụ FFmpeg mapping (`-map 0:<idx>`) và thứ tự luồng âm thanh (`audio_ordinal`).
   - Lọc bỏ tự động các luồng bình luận/thuyết minh khi có luồng đối thoại chuẩn.
4. **Đọc âm thanh và ảnh có giới hạn bộ nhớ (Memory Boundedness)**:
   - Đo năng lượng âm thanh qua các khối khung PCM 4096 mẫu (`readframes(chunk_frames)`), tuyệt đối không đọc toàn bộ tệp WAV vào RAM.
   - OCR chỉ xử lý các ảnh cắt phụ đề (crop), từ chối nhận toàn khung hình video để bảo vệ bộ nhớ và tốc độ xử lý.
5. **Bộ nhớ đệm và lưu tạo tác an toàn (Content-Addressable Caching & Persistence)**:
   - Băm SHA-256 nội dung tệp thực tế (`hash_file_content`), băm phiên bản parser/decoder và manifest mô hình. Thay đổi nội dung tệp sidecar sẽ làm mất hiệu lực cache ngay lập tức.
   - Lưu trữ tạo tác chuẩn bị nguyên tử trong `%LOCALAPPDATA%\ToolRecapV4\prepared\<mã_dự_án>\<tập>.json` và `manifest.json`.
6. **Tích hợp Workflow an toàn & điểm dừng có kiểm soát**:
   - Kiểm tra toàn vẹn nguồn tệp trước khi bắt đầu xử lý (`verify_source_integrity`).
   - Khi đã có Final JSON hợp lệ hoặc import: bỏ qua hoàn toàn source prep và Gateway, thực hiện chính xác 0 lượt gọi AI.
   - Khi chưa có Final JSON: chạy chuẩn bị nguồn tuần tự cho từng tập (`E01`, `E02`, ...), lưu tạo tác và chuyển trạng thái sang `ProjectStatus.PREPARED`, sau đó dừng có kiểm soát trước Scanner với ngoại lệ rõ ràng `AnalysisPipelineUnavailableError`.
7. **Bộ kiểm thử toàn diện**:
   - Phase 2 baseline: **237 bài đạt**.
   - Phase 3 trước closure: **330 bài đạt**, tăng ròng **93 bài** so với Phase 2 (không thay đổi tests chỉ để khớp số học).
   - Phase 3 final closure: **336 bài đạt** sau khi thêm đúng 1 regression SSA và 5 regression Vision OCR bắt buộc.
   - Biên dịch bytecode 100% thành công (0 lỗi).
   - Import toàn bộ 49 submodule thành công (0 lỗi).
   - Không xuất hiện bất kỳ API truyền video cũ nào hay logic phán đoán kịch bản (editorial policy) nào trong mã nguồn phân tích.
   - **SSA closure:** `.ssa` sidecar được discovery, chọn English Full, parse bằng ASS/SSA parser và chạy qua `SubtitlePipeline`; test dùng cú pháp SSA `ScriptType: v4.00`, `V4 Styles`, `Marked` dialogue.
   - **Vision OCR closure:** local OCR fail + Vision bật chỉ gửi cropped subtitle still qua Phase 2 `submit_image_chat`; Vision tắt/local OCR đạt thì 0 image Gateway calls; gateway failure và full-frame/oversize đều bị chặn hoặc trả fallback/error.


---

## 2. Danh mục chính xác các tệp đã sửa đổi và tạo mới

### 2.1 Tệp cấu hình & mã nguồn hiện hữu được cập nhật (6 tệp)
1. `pyproject.toml`: Khai báo nhóm phụ thuộc `source-prep` (`faster-whisper>=1.0.0`, `huggingface-hub>=0.20.0`, `rapidocr-onnxruntime>=1.3.0`, `onnxruntime>=1.16.0`).
2. `tests/conftest.py`: Cấu hình `PYTEST_DEBUG_TEMPROOT` trỏ vào thư mục tạm chuẩn Windows để tránh lỗi dọn symlink.
3. `tests/test_persistence.py`: Bổ sung kiểm thử `test_prepared_artifacts_persistence_roundtrip` xác thực lưu và đọc nguyên tử `PreparedEpisode` và `manifest.json`.
4. `tests/test_workflow.py`: Cập nhật fixture video có phụ đề sidecar, cập nhật assertions trạng thái sang `PREPARED`, bổ sung case phục hồi trạng thái bị gián đoạn.
5. `toolrecap_v4/persistence.py`: Bổ sung thư mục `prepared` và 7 phương thức API: `save_prepared_episode`, `load_prepared_episode`, `has_prepared_episode`, `list_prepared_episodes`, `save_prepared_manifest`, `load_prepared_manifest`, `has_prepared_manifest`.
6. `toolrecap_v4/workflow.py`: Bổ sung trạng thái `ProjectStatus.PREPARED`, callbacks `on_source_preparation_progress` và `on_episode_prepared`, kiểm tra tính toàn vẹn nguồn trước khi chuẩn bị, vòng lặp chuẩn bị nguồn tuần tự theo thứ tự tự nhiên `E01..En`, và điểm dừng có kiểm soát ném lỗi `AnalysisPipelineUnavailableError` trước Scanner.

### 2.2 Tệp mã nguồn mới thuộc gói `toolrecap_v4/analysis/` (19 tệp)
7. `toolrecap_v4/analysis/__init__.py`: Xuất các lớp và hàm dùng chung của hệ thống phân tích.
8. `toolrecap_v4/analysis/models.py`: Các dataclass cốt lõi (`TranscriptCue`, `Transcript`, `AudioSelection`, `PreparedEpisode`).
9. `toolrecap_v4/analysis/dependencies.py`: Hằng số phiên bản chuẩn hóa, các hàm băm SHA-256 nội dung và kiểm tra chữ ký phụ thuộc.
10. `toolrecap_v4/analysis/cache.py`: Trình quản lý bộ nhớ đệm phân tích nguyên tử `AnalysisCacheManager`.
11. `toolrecap_v4/analysis/source_prep/__init__.py`: Gói chuẩn bị nguồn cấp tập phim.
12. `toolrecap_v4/analysis/source_prep/probe.py`: Bóc tách thông tin luồng video/audio/phụ đề qua FFprobe (`probe_episode_source`, `EpisodeProbeResult`).
13. `toolrecap_v4/analysis/source_prep/audio.py`: Chọn luồng âm thanh tối ưu (`select_episode_audio_stream`) và đo năng lượng âm thanh dạng khối (`measure_audio_signal_bounded`).
14. `toolrecap_v4/analysis/source_prep/transcript.py`: Xây dựng và kiểm tra tính hợp lệ của kịch bản hội thoại (`build_transcript`).
15. `toolrecap_v4/analysis/source_prep/stt.py`: Bộ điều phối nhận dạng tiếng nói STT (`SttModelManager`, `transcribe_episode_stt`, `SttResult`, `SttStatus`).
16. `toolrecap_v4/analysis/source_prep/pipeline.py`: Bộ điều phối tổng thể chuẩn bị nguồn tập phim (`SourcePreparationPipeline`, `compute_pipeline_cache_key`).
17. `toolrecap_v4/analysis/source_prep/subtitles/__init__.py`: Gói phụ đề.
18. `toolrecap_v4/analysis/source_prep/subtitles/models.py`: Các mô hình luồng và track phụ đề (`SubtitleTrack`, `SubtitleStreamInfo`, `SubtitleCueItem`).
19. `toolrecap_v4/analysis/source_prep/subtitles/discovery.py`: Khám phá phụ đề rời và nhúng, thuật toán chọn track tiếng Anh tối ưu.
20. `toolrecap_v4/analysis/source_prep/subtitles/parsers.py`: Trình phân tích cú pháp phụ đề văn bản SRT, WebVTT, ASS (`SubRipParser`, `WebVttParser`, `AssParser`).
21. `toolrecap_v4/analysis/source_prep/subtitles/ocr.py`: Bộ điều hợp OCR hình ảnh và cổng kiểm soát chất lượng (`OcrAdapter`, `OcrQualityGate`, `OcrModelManager`).
22. `toolrecap_v4/analysis/source_prep/subtitles/pgs.py`: Trình giải mã phụ đề bitmap PGS Blu-ray (`.sup`).
23. `toolrecap_v4/analysis/source_prep/subtitles/vobsub.py`: Trình giải mã phụ đề bitmap VobSub DVD (`.sub` + `.idx`).
24. `toolrecap_v4/analysis/source_prep/subtitles/cache.py`: Bộ nhớ đệm phụ đề content-addressable (`SubtitleCacheManager`).
25. `toolrecap_v4/analysis/source_prep/subtitles/pipeline.py`: Đường ống trích xuất và xử lý phụ đề cấp tập phim (`SubtitlePipeline`).

### 2.3 Bộ kiểm thử mới trong `tests/` (4 tệp)
26. `tests/test_analysis_core_subtitles.py`: 19 bài kiểm thử đơn vị cho models, cue bounds, stream indexing, cache hashing, sidecar discovery, PGS/VobSub parsing.
27. `tests/test_analysis_ocr_stt.py`: 44 bài kiểm thử đơn vị cho OCR quality gate, crop validation, 5 trường hợp Vision OCR safety, model management, STT windowing, energy gating, device policies.
28. `tests/test_source_preparation_pipeline.py`: 28 bài kiểm thử tích hợp cho đường ống chuẩn bị nguồn, cú pháp/path SSA thật, thứ bậc fallback, bộ nhớ đệm và invalidation.
29. `tests/test_workflow_source_prep.py`: 7 bài kiểm thử tích hợp workflow với chuẩn bị nguồn tuần tự, trạng thái `PREPARED`, hủy bỏ và phục hồi.

### 2.4 Tài liệu cập nhật & báo cáo (3 tệp)
30. `README.md`: Cập nhật tiếng Việt chính xác trạng thái Phase 3, cách thức hoạt động, ranh giới Phase 4 và cấu trúc thư mục lưu trữ.
31. `IMPLEMENTATION_REPORT.md`: Báo cáo kỹ thuật tổng hợp tiến độ đến Phase 3.
32. `PHASE3_REPORT.md`: Báo cáo nghiệm thu chi tiết này.

---

## 3. Kiến trúc kỹ thuật và hợp đồng API (Technical Architecture & APIs)

### 3.1 Mô hình dữ liệu cốt lõi (`toolrecap_v4/analysis/models.py`)

#### `TranscriptCue`
- Dataclass bất biến (`frozen=True`) đại diện cho một câu thoại với mốc thời gian tính bằng mili-giây.
- Thuộc tính: `cue_id: str`, `start_ms: int`, `end_ms: int`, `text: str`, `confidence: float | None`.
- Bất biến kiểm chứng:
  - `start_ms` và `end_ms` bắt buộc là số nguyên (từ chối kiểu `bool` hoặc `float`).
  - `end_ms > start_ms` (ném `ValueError` nếu thời gian kết thúc nhỏ hơn hoặc bằng thời gian bắt đầu).
  - Hỗ trợ chuyển đổi hai chiều `to_dict()` và `from_dict()`.

#### `Transcript`
- Dataclass bất biến (`frozen=True`) đại diện cho chuỗi hội thoại hoàn chỉnh của một tập phim.
- Thuộc tính: `episode_id: str`, `source_type: str`, `source_format: str`, `cues: tuple[TranscriptCue, ...]`, `has_speech: bool`, `language: str`, `provenance_hash: str`, `dropped_cues_count: int`, `diagnostics: tuple[str, ...]`.
- Bất biến kiểm chứng:
  - `cue_count`: Số lượng câu thoại hợp lệ.
  - `duration_ms`: Khoảng thời gian từ câu đầu tiên đến câu cuối cùng.

#### `AudioSelection`
- Dataclass bất biến (`frozen=True`) lưu trữ kết quả chọn luồng âm thanh tối ưu.
- Thuộc tính: `selected_stream: AudioStreamInfo | None`, `global_index: int`, `audio_ordinal: int`, `warning: str | None`, `reason: str`.
- Bất biến kiểm chứng:
  - `global_index`: Chỉ số định danh luồng trong container (dùng cho FFmpeg `-map 0:<global_index>`).
  - `audio_ordinal`: Thứ tự riêng của luồng âm thanh trong số các luồng âm thanh (0-based).
  - `ffmpeg_map_spec()`: Trả về chuỗi `"0:<global_index>"` hoặc ném `ValueError` nếu không có luồng âm thanh.

#### `PreparedEpisode`
- Dataclass bất biến (`frozen=True`) đại diện cho tập phim đã được thăm dò đầy đủ thông số kỹ thuật và tạo tác hội thoại.
- Thuộc tính: `episode_id: str`, `source_id: str`, `source_path: Path`, `duration_ms: int`, `canvas_width: int`, `canvas_height: int`, `source_basename: str`, `source_fingerprint: str`, `video_streams: tuple`, `audio_streams: tuple`, `subtitle_streams: tuple`, `audio_selection: AudioSelection | None`, `transcript: Transcript`, `transcript_method: str`, `artifact_hash: str`, `dependency_signature: dict`, `status: str`.
- Bất biến kiểm chứng:
  - Nếu tệp không có âm thanh: `audio_info = None` (tuyệt đối không tạo stream âm thanh giả).
  - Khả năng chuyển đổi hai chiều `to_dict()` và `from_dict()` bảo toàn 100% dữ liệu.

### 3.2 Quy trình chuẩn bị nguồn (`SourcePreparationPipeline`)

- Lớp: `toolrecap_v4.analysis.source_prep.pipeline.SourcePreparationPipeline`
- Phương thức chính:
  ```python
  def prepare_episode(
      self,
      source_path: Path | str,
      episode_id: str,
      source_id: str | None = None,
      source_fingerprint: str | None = None,
      force_refresh: bool = False,
      on_progress: Callable[[str, float, str], None] | None = None,
      cancellation_token: CancellationToken | None = None,
  ) -> PreparedEpisode
  ```
- Thứ bậc Fallback:
  1. Sidecar text (English): SRT -> VTT -> ASS (kiểm tra tính hợp lệ và băm nội dung).
  2. Embedded text (English): Quét các track phụ đề nhúng qua FFprobe và bóc tách qua FFmpeg.
  3. Bitmap OCR: Giải mã PGS (`.sup`) hoặc VobSub (`.sub`/`.idx`), nhận dạng qua `OcrAdapter` với cổng lọc chất lượng.
  4. Audio STT: Nhận dạng qua `faster-whisper` trên luồng âm thanh được `AudioSelection` chỉ định.
- Hành vi bộ nhớ đệm:
  - Khóa cache được tính bằng `compute_pipeline_cache_key` bao gồm băm nội dung nguồn, băm kho tài nguyên, định danh track được chọn, băm mục tiêu và phiên bản các bộ giải mã.
  - Khi phát hiện một tệp sidecar mới xuất hiện trong thư mục nguồn, khóa cache thay đổi và tự động vô hiệu hóa kết quả STT cũ để sử dụng phụ đề mới có chất lượng cao hơn.
  - Hủy bỏ (cancellation) giữa chừng lập tức dọn dẹp các tệp tạm và không bao giờ thăng cấp (promote) dữ liệu chưa hoàn chỉnh vào cache.

### 3.3 Đọc khung âm thanh có giới hạn (`measure_audio_signal_bounded`)

- Vị trí: `toolrecap_v4/analysis/source_prep/audio.py`
- Hàm: `measure_audio_signal_bounded(wav_path, min_rms_threshold=0.01, chunk_ms=100, cancellation_token=None)`
- Cơ chế: Đọc tệp WAV theo từng khối khung PCM 4096 mẫu (`wf.readframes(chunk_frames)`), tính toán RMS cục bộ và kiểm tra ngưỡng hoạt động.
- Invariant: Không nạp toàn bộ mảng mẫu WAV vào bộ nhớ RAM; kiểm tra cờ hủy bỏ ở mỗi vòng lặp; xử lý an toàn lỗi EOF hoặc tệp WAV dị thường.

### 3.4 Cổng chất lượng OCR (`OcrQualityGate`)

- Vị trí: `toolrecap_v4/analysis/source_prep/subtitles/ocr.py`
- Lớp: `OcrQualityGate`
- Quy tắc loại trừ rác:
  - Xóa bỏ thẻ HTML/ASS/formatting.
  - Từ chối chuỗi rỗng hoặc chỉ chứa khoảng trắng.
  - Từ chối chuỗi có độ tin cậy thấp hơn ngưỡng `min_confidence` (mặc định 0.50).
  - Từ chối chuỗi không chứa ký tự chữ cái hoặc số (chỉ toàn ký tự đặc biệt).
  - Từ chối chuỗi lặp lại ký tự đơn hoặc cặp ký tự liên tục quá ngưỡng cho phép (tránh vòng lặp ảo của mô hình OCR).
  - Hỗ trợ đầy đủ Unicode đa ngôn ngữ (tiếng Việt, CJK, tiếng Anh, v.v.).

### 3.5 Mở rộng lớp lưu trữ (`ProjectPersistence`)

- Thư mục lưu trữ: `%LOCALAPPDATA%\ToolRecapV4\prepared\<project_id>\`
- Các phương thức mới:
  - `save_prepared_episode(project_id, episode_id, prepared_data) -> Path`
  - `load_prepared_episode(project_id, episode_id) -> Dict[str, Any]`
  - `has_prepared_episode(project_id, episode_id) -> bool`
  - `list_prepared_episodes(project_id) -> List[Dict[str, Any]]`
  - `save_prepared_manifest(project_id, manifest_data) -> Path`
  - `load_prepared_manifest(project_id) -> Dict[str, Any]`
  - `has_prepared_manifest(project_id) -> bool`
- Bất biến bảo mật: Ngăn chặn tuyệt đối việc lưu trữ khóa API hoặc thông tin nhạy cảm trong các tệp JSON tạo tác chuẩn bị thông qua kiểm tra `contains_secrets`.

---

## 4. Bằng chứng kiểm thử thực tế (Verification Evidence)

### 4.1 Biên dịch Bytecode (`compileall`)
```
Command: python -m compileall toolrecap_v4 tests main.py build_portable.py repackage.py
Result: Listing and compiling all files... Clean compilation, 0 errors.
```

### 4.2 Nạp gói động (`walk_packages`)
```
Command: python -c "import pkgutil, importlib, toolrecap_v4; mods = [m.name for m in pkgutil.walk_packages(toolrecap_v4.__path__, toolrecap_v4.__name__ + '.')]; print(f'Total submodules: {len(mods)}'); [importlib.import_module(m) for m in mods]; print('Import all OK')"
Output:
Total submodules: 49
Import all OK
```

### 4.3 Kết quả kiểm thử toàn diện (`pytest`)
```
Command: pytest --basetemp="C:\Users\Long\AppData\Local\Temp\kilo\pytest_v4_phase3_run"
Result:
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Long\Desktop\ToolRecap_V4
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.2, asyncio-1.4.0
collected 336 items

tests\test_analysis_core_subtitles.py ...................                [  5%]
tests\test_analysis_ocr_stt.py ............................................ [ 18%]
tests\test_cancellation.py .....                                         [ 19%]
tests\test_discovery.py ...........                                      [ 22%]
tests\test_gateway.py .................................                  [ 32%]
tests\test_media.py .........................                            [ 40%]
tests\test_persistence.py ........                                       [ 42%]
tests\test_preflight_regressions.py ....                                 [ 43%]
tests\test_renderer.py .................                                 [ 48%]
tests\test_schema.py .....                                               [ 50%]
tests\test_secrets.py .....                                              [ 51%]
tests\test_settings.py ..                                                [ 52%]
tests\test_source_preparation_pipeline.py ............................   [ 61%]
tests\test_subtitles.py .....                                            [ 62%]
tests\test_ui_notifications.py .....                                     [ 63%]
tests\test_ui_responsive.py ......                                       [ 65%]
tests\test_ui_views.py ............                                      [ 69%]
tests\test_ui_worker.py .....                                            [ 70%]
tests\test_updater.py ..............                                     [ 74%]
tests\test_validator.py ................................................ [ 89%]
..                                                                       [ 90%]
tests\test_voice_studio.py .........                                     [ 92%]
tests\test_workflow.py .................                                 [ 97%]
tests\test_workflow_source_prep.py .......                               [100%]

============================ 336 passed in 43.45s =============================
```

### 4.4 Kiểm tra Grep rà soát Transport cũ và Chính sách biên tập
- Tìm kiếm API video đã xóa (`StreamingChatPayload|submit_chat_analysis|validate_model_video_capability`): **0 kết quả** trong `toolrecap_v4`.
- Tìm kiếm logic chính sách biên tập cũ (`EditorialPolicy|cap_single_cue_text`): **0 kết quả** trong `toolrecap_v4`.
- Kiểm tra cơ chế đọc WAV: Phương thức `measure_audio_signal_bounded` tại `audio.py:224` sử dụng `wf.readframes(chunk_frames)` lặp theo khối nhỏ, không đọc toàn bộ tệp vào RAM.
- Kiểm tra băm sidecar: `cache.py` sử dụng hàm `hash_file_content` đọc tệp nhị phân tính SHA-256 thực tế, không dựa vào mtime/size.

---

## 5. Ranh giới trung thực & Giới hạn kỹ thuật (Boundaries & Limitations)

1. **Chưa triển khai Scanner đa phương thái (Phase 4)**: Quy trình quét video theo từng chunk và trích xuất đặc trưng hình ảnh/ngữ nghĩa bằng mô hình Vision AI chưa được xây dựng. Khi chạy dự án chưa có Final JSON, ứng dụng hoàn tất chuẩn bị nguồn, đổi trạng thái sang `PREPARED` và ném ngoại lệ dừng có kiểm soát `AnalysisPipelineUnavailableError`.
2. **Chưa triển khai Season Catalog & Season Planner**: Việc tổng hợp danh mục toàn mùa và lập kế hoạch recap tổng thể chưa được kích hoạt.
3. **Chưa triển khai Output Writers & Output Directory Resolver**: Việc sinh kịch bản JSON mới từ kế hoạch chưa có; hiện tại chỉ chấp nhận Final JSON đã có hoặc được import từ ngoài.
4. **Không có bản dựng nhị phân (Executable)**: Chưa chạy `build_portable.py` / PyInstaller; thư mục `dist/` và `release/` chưa có tệp thực thi `ToolRecapV4.exe`.
5. **Không gọi API AI bên ngoài hoặc tải model trực tiếp trong kiểm thử**: Tất cả 336 bài kiểm thử sử dụng adapter giả lập (mocked adapters), kiểm tra thuật toán, cấu trúc dữ liệu và xử lý ngoại lệ cục bộ mà không phụ thuộc mạng internet hay phần cứng GPU bắt buộc.
6. **Git**: Phase 3 có checkpoint chính `71a7693`; closure SSA/Vision OCR được checkpoint bằng corrective commit riêng. Không cấu hình remote hoặc push.
