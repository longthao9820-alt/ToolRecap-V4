# ToolRecap V4 — Implementation & Verification Report (Phase 3 Source Preparation Pipeline)

**Date**: 2026-09-22  
**Contract**: `phase3-docs-acceptance rev1 objective4`
**Project**: ToolRecap V4  
**Target Platform**: Windows 10/11 x64 Portable  
**Version**: v4.0.0  
**Phase**: Phase 3 — Source Preparation Pipeline & Deterministic Subtitle/Audio Processing
**Status**: Phase 3 COMPLETED (Source Preparation Pipeline Validated).

---

## 1. Executive Summary & Scope

This report documents the completion and verification of **Phase 3** of the ToolRecap V4 migration plan (`TOOLRECAP_V4_MIGRATION_PLAN.md`), following the baseline establishment (Phase 1) and safe provider-neutral gateway integration (Phase 2).

### Cumulative Progression:
- **Phase 1 (Baseline Validated)**: Established independent V4 workspace with 215/215 tests passing, schema 3.0 immutable, Windows DPAPI secret persistence preserved.
- **Phase 2 (Safe Gateway & Transport Boundary)**: Completely eliminated whole-video transport APIs (`StreamingChatPayload`, `submit_chat_analysis`, `validate_model_video_capability`, `DEFAULT_MAX_FILE_SIZE_BYTES`, `SUPPORTED_VIDEO_EXTENSIONS`), added strict still-image and text/JSON transport with decompression bomb protections, provider-neutral model availability validation, and early-fail workflow before AI invocation.
- **Phase 3 (Source Preparation Pipeline)**: Built complete local episode discovery, stream probing, audio selection, multi-tiered dialogue extraction, bitmap OCR, audio energy gating, STT transcription orchestration, content-addressable caching, and atomic persistence.

### Exact Scope Executed in Phase 3:
1. **Core Analysis Data Models (`toolrecap_v4.analysis.models`)**:
   - `TranscriptCue`: Immutable dataclass with strict millisecond boundaries (`start_ms < end_ms`), non-negative timing, confidence score, and bidirectional dictionary serialization.
   - `Transcript`: Immutable episode transcript sequence with source provenance, language tagging, dropped cues accounting, and diagnostics collection.
   - `AudioSelection`: Disambiguates container `global_index` (used for FFmpeg `-map 0:<idx>`) from `audio_ordinal` (audio stream index), selecting best dialogue tracks while filtering commentary/descriptive audio.
   - `PreparedEpisode`: Complete normalized container holding probed video/audio/subtitle stream descriptors, selected audio stream, canvas dimensions, duration, transcript, and dependency signatures.

2. **Dependency Tracking & Content-Addressable Caching (`toolrecap_v4.analysis.dependencies`, `cache.py`)**:
   - SHA-256 file content hashing (`hash_file_content`) replacing volatile mtime/size heuristics.
   - VobSub paired indexing validation (`.idx` and `.sub` simultaneous existence and pair hashing).
   - Component-level versioning: `PIPELINE_VERSION`, `SUBTITLE_PARSER_VERSION`, `NORMALIZATION_VERSION`, `PGS_DECODER_VERSION`, `VOBSUB_DECODER_VERSION`.
   - `AnalysisCacheManager`: Temp-file staging with atomic rename, checksum and size validation, collision-resistant naming, and cooperative cancellation support.

3. **Multi-Tiered Subtitle Pipeline (`toolrecap_v4.analysis.source_prep.subtitles`)**:
   - Priority 1: Sidecar English text (`.srt`, `.vtt`, `.ass`) with HTML/formatting tag stripping and timestamp normalization.
   - Priority 2: Embedded English text tracks discovered via FFprobe and demuxed via FFmpeg.
   - Priority 3: Bitmap subtitle extraction (PGS `.sup` and VobSub `.sub`/`.idx`) with local RapidOCR ONNX through `OcrAdapter`.
   - OCR Quality Gate: Rejection of empty lines, repetitive looping characters, low-confidence cues, and non-alphanumeric noise; full multilingual Unicode support.

4. **Audio & Speech-to-Text Pipeline (`toolrecap_v4.analysis.source_prep.audio`, `stt.py`)**:
   - Stream probing and deterministic audio track selection.
   - Bounded energy measurement (`measure_audio_signal_bounded`) using chunked PCM frame reads (`readframes(chunk_frames)`) without loading full audio files into RAM.
   - STT orchestration via `faster-whisper`: Audio window segmentation, overlap cue deduplication, explicit status mapping (`ready`, `no_audio`, `silent`, `failed`), and atomic cache promotion.
   - Model management: Download validation, SHA-256 checksum verification, and atomic promotion.

5. **Integrated Workflow & Persistence (`toolrecap_v4.workflow`, `persistence.py`)**:
   - Pre-preparation source integrity verification (`verify_source_integrity`) to prevent work on corrupted or mutated source files.
   - Sequential episode preparation in natural order (`E01`...`En`).
   - Progress callbacks (`on_source_preparation_progress`, `on_episode_prepared`).
   - Atomic persistence of prepared episodes (`%LOCALAPPDATA%\ToolRecapV4\prepared\<project_id>\<episode_id>.json`) and project manifest (`manifest.json`).
   - Clean state reconciliation: Interrupted analysis with prepared manifest transitions safely to `ProjectStatus.PREPARED`.
   - Controlled boundary stop: When no Final JSON exists, workflow halts cleanly at `ProjectStatus.PREPARED` raising `AnalysisPipelineUnavailableError` (Scanner is unavailable).
   - Zero-AI / Zero-Prep bypass: Existing or imported Final JSON bypasses source preparation and AI Gateway entirely, executing direct render.

---

## 2. Invariants & Truth Boundaries

| Invariant / Requirement | Status | Truthful Evidence & Verification |
|---|---|---|
| **Whole-video transport** | `REMOVED` | 0 occurrences of deleted APIs across codebase; zero video payload transport. |
| **Still-Image Gateway** | `VERIFIED` | JPEG/PNG strict magic-byte validation, re-encoding, size and dimension bounds. |
| **Subtitle Extraction Order** | `ENFORCED` | Sidecar English text -> Embedded text -> Bitmap OCR -> Audio STT. Higher priority always wins. |
| **Cache Invalidation** | `CONTENT-ADDRESSABLE` | SHA-256 of file content, parser versions, and model manifests. Modification of sidecar content invalidates cache immediately. |
| **Memory Boundedness** | `ENFORCED` | Audio energy reads 4096-frame chunks; no full WAV in memory. Image OCR operates on bounded subtitle crops, never full video frames. |
| **Stream Indexing Integrity** | `ENFORCED` | `AudioSelection` maintains separate `global_index` and `audio_ordinal`. Error raised if map spec requested on missing audio. |
| **Editorial Independence** | `CLEAN` | No editorial policy classes, cue-capping heuristics, or arbitrary time clamping injected into analysis/preparation. |
| **Controlled Workflow Boundary**| `VERIFIED` | Halts at `ProjectStatus.PREPARED` before Scanner; raises explicit `AnalysisPipelineUnavailableError`. |
| **Zero-AI Render Bypass** | `PRESERVED` | Projects with Final JSON execute render with exactly 0 source prep and 0 Gateway calls. |
| **DPAPI Entropy** | `PRESERVED` | `OPTIONAL_ENTROPY = b"ToolRecapV3_DPAPI_SecretStorage_v1"` retained intact. |
| **Schema Version** | `PRESERVED` | Schema 3.0 (`recap_v3_schema.json`) immutable. |
| **Storage Isolation** | `PRESERVED` | All working state, prepared artifacts, and cache strictly under `%LOCALAPPDATA%\ToolRecapV4\`. |

---

## 3. Verification & Testing Evidence

All validation suites executed and passed cleanly:

- **Bytecode Compilation**:
  - Command: `python -m compileall toolrecap_v4 tests main.py build_portable.py repackage.py`
  - Result: 100% clean compilation across all modules and tests, 0 syntax or compilation errors.
- **Module Import Verification**:
  - Command: `pkgutil.walk_packages` across `toolrecap_v4`
  - Result: All 49 submodules cleanly imported without error.
- **Full Pytest Suite**:
  - Command: `pytest --basetemp="C:\Users\Long\AppData\Local\Temp\kilo\pytest_v4_phase3_run"`
   - Phase 2 baseline: **237 passed**.
   - Pre-closure Phase 3 suite: **330 passed**, tăng ròng **93 tests** so với Phase 2 baseline **237 passed**.
   - Final closure suite sau 1 SSA + 5 Vision OCR regression tests: **336 passed in 43.45s**, 0 failures, 0 errors, 0 skipped.
- **Test Suite Breakdown (336 tests total)**:
  - `tests/test_analysis_core_subtitles.py`: 19 passed (models, cue bounds, stream indexing, cache hashing, sidecar discovery).
  - `tests/test_analysis_ocr_stt.py`: 44 passed (OCR quality gate, crop validation, Vision OCR safety, model management, STT windowing, energy gating).
  - `tests/test_source_preparation_pipeline.py`: 28 passed (pipeline orchestration, real SSA path, fallback hierarchy, inventory hashing, semantic invalidation).
  - `tests/test_workflow_source_prep.py`: 7 passed (workflow integration, sequential prep, PREPARED status, resume, cancellation).
  - `tests/test_persistence.py`: 8 passed (atomic roundtrips, secret exclusion, prepared episode/manifest persistence).
  - `tests/test_workflow.py`: 17 passed (import zero-AI, resume, retry, publication collision, state reconciliation).
  - `tests/test_gateway.py`: 33 passed (provider-neutral transport, image validation, error classification, retry caps).
  - `tests/test_validator.py`: 49 passed (schema version 3.0, Windows path sanitization, duration clamping).
  - `tests/test_media.py`: 25 passed (FFprobe/FFmpeg runner, audio selector, GPU encoder detection).
  - `tests/test_renderer.py`: 17 passed (ducking, loudnorm, multisource render, subtitle burn).
  - `tests/test_updater.py`: 14 passed (semver, checksums, path traversal, active guard).
  - `tests/test_discovery.py`: 11 passed (natural ordering, extension filtering, source mapping).
  - `tests/test_voice_studio.py`: 9 passed (presets, local/remote routing, WAV validation).
  - `tests/test_ui_views.py`: 12 passed (settings dialog, dual model configuration, format helpers).
  - `tests/test_ui_responsive.py`: 6 passed (heartbeat, cancellation responsiveness).
  - `tests/test_ui_notifications.py`: 5 passed (toast notification, visual receipts).
  - `tests/test_ui_worker.py`: 5 passed (worker thread dispatch, secret redaction, 0-AI render).
  - `tests/test_schema.py`: 5 passed (JSON schema validation).
  - `tests/test_secrets.py`: 5 passed (DPAPI encryption/decryption roundtrips).
  - `tests/test_cancellation.py`: 5 passed (cooperative cancellation token).
  - `tests/test_preflight_regressions.py`: 4 passed (dialog regressions, prompt whitespace preservation).
  - `tests/test_subtitles.py`: 5 passed (SRT formatting, time parsing, escaping).
  - `tests/test_settings.py`: 2 passed (settings defaults and persistence).

---

## 4. Explicit Limitations & Boundaries (Phase 4+ Scope)

- **Multimodal Scanner**: NOT implemented. Scanning video scenes with multimodal AI prompts is Phase 4 scope. Workflow stops at `ProjectStatus.PREPARED`.
- **Season Catalog & Season Planner**: NOT implemented. Cross-episode cataloging, global arc planning, and writer dispatch belong to Phase 4/5.
- **Output Writers & Output Directory Resolver**: NOT implemented. Final JSON generation currently only accepts imported/pre-existing schemas.
- **Executable Packaging**: Portable binary packaging via `build_portable.py` / PyInstaller was not run; no `dist/ToolRecapV4.exe` exists in this phase.
- **AI Model Execution in Tests**: Unit and integration tests used mock/synthetic adapters and injected runners. Live GPU transcription and online model downloading were not invoked during testing.
- **No Git Mutations**: Working tree preserved; no branches, commits, or pushes created.
