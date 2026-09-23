# ToolRecap V4 — Implementation & Verification Report (Phase 11 Downstream Voice & Render)

**Date**: 2026-09-22  
**Contract**: Phase 11 — Connect Final JSON to VoiceStudio, Audio Mix & GPU Render
**Project**: ToolRecap V4  
**Target Platform**: Windows 10/11 x64 Portable  
**Version**: v4.0.0  
**Phase**: Phase 11 — Canonical Final JSON Downstream Execution & Zero-AI Retry
**Status**: Phase 11 IMPLEMENTED with mocked/synthetic verification; real episode/season acceptance remains later.

---

## 1. Executive Summary & Scope

This report documents the implementation and closure verification of **Phase 11** of the ToolRecap V4 migration plan (`TOOLRECAP_V4_MIGRATION_PLAN.md`), connecting canonical Final JSON to the preserved VoiceStudio, Audio Mix, and renderer stack.

### Cumulative Progression:
- **Phase 1 (Baseline Validated)**: Established independent V4 workspace with 215/215 tests passing, schema 3.0 immutable, Windows DPAPI secret persistence preserved.
- **Phase 2 (Safe Gateway & Transport Boundary)**: Completely eliminated whole-video transport APIs (`StreamingChatPayload`, `submit_chat_analysis`, `validate_model_video_capability`, `DEFAULT_MAX_FILE_SIZE_BYTES`, `SUPPORTED_VIDEO_EXTENSIONS`), added strict still-image and text/JSON transport with decompression bomb protections, provider-neutral model availability validation, and early-fail workflow before AI invocation.
- **Phase 3 (Source Preparation Pipeline)**: Built complete local episode discovery, stream probing, audio selection, multi-tiered dialogue extraction, bitmap OCR, audio energy gating, STT transcription orchestration, content-addressable caching, and atomic persistence.
- **Phase 4 (Factual Scanner & Evidence Store)**: Added deterministic cue-aware chunking, lossless long-cue parts, text-only Gateway scanning, strict response validation, bounded per-chunk repair, raw-response recovery, stable application-owned Evidence IDs, dependency-aware evidence revisions, bounded Scanner parallelism, and a hash-verified immutable Full Episode Evidence Store.
- **Phase 5 (Complete Season Evidence Catalog)**: Added one-to-one full-evidence projection, technical completeness ledger, deterministic IDs digest and Catalog hash, exact structural pack/unpack, capacity metrics, atomic persistence/cache, corruption recovery, and `CATALOG_READY` workflow integration with zero AI calls.
- **Phase 6 (Season Planner Draft)**: Added verbatim raw-prompt delivery, complete Catalog transport, provider-neutral Planner configuration, exact ID/range Evidence fetch, strict two-action protocol, bounded repair/rounds, raw-response recovery, atomic session reuse, technically validated draft outputs/visual requests and `PLANNER_DRAFT_READY` workflow integration.
- **Phase 7 (Selective Visual Evidence & Season Plan)**: Added deterministic Planner-requested range IDs, local bounded frame extraction, safe still-image Vision, factual Visual Evidence, empty-visual completion, final Planner refinement, deterministic application-owned output IDs, immutable locked `season_plan.json`, cache reuse and `SEASON_PLAN_READY` workflow integration.
- **Phase 8 (Independent Writers)**: Added deterministic Writer jobs from locked `out_###` entries, authoritative Full/Visual Evidence context, verbatim raw prompt, provider-neutral text-only requests, bounded parallelism, per-output raw checkpoints/cache/resume, best-effort structured extraction and `WRITER_DRAFTS_READY` workflow integration.
- **Phase 9 (Validation/Repair/Merge)**: Added deterministic per-output issue codes, invalid-only bounded repair, repair recovery/provenance, immutable validated outputs, application-owned schema 3.0 mapping, canonical validation, atomic Final JSON checkpoint/reuse and `FINAL_JSON_READY` workflow integration.
- **Phase 10 (Gateway Settings)**: Added provider-neutral Scanner/Vision/Finalizer controls, secure transactional API-key save, legacy stage-preserving migration, unified explicit Finalizer mapping, unsaved-value background diagnostics and settings dependency wiring.
- **Phase 11 (Downstream Integration)**: Connected generated Final JSON to the same imported-JSON VoiceStudio/Audio Mix/render path, added validated narration WAV caching, and verified zero-AI downstream retry/reuse boundaries.

### Exact Scope Executed in Phase 11

1. Phase 9-generated canonical Final JSON now continues into the existing downstream path instead of stopping at `FINAL_JSON_READY`.
2. Imported and generated Final JSON are both revalidated at the common downstream boundary and treated identically by Voice/Render.
3. Managed per-segment narration cache keys exact Final JSON narration plus VoiceStudio mode/endpoints/voice/model/language/style; WAV content/hash/duration are validated before reuse.
4. Audio Mix and renderer remain the existing deterministic implementation: source levels, commentary level, optional ducking, two-pass loudness normalization, subtitle behavior, multi-source clips and file-based FFmpeg processing.
5. Existing encoder detection and configured GPU/CPU fallback behavior remain intact.
6. Output fingerprinting excludes AI settings but includes voice, mix, renderer, source and canonical output content dependencies.
7. Existing output checkpoint reuse still requires matching fingerprint, file presence and output SHA; file existence alone is insufficient.
8. Voice/render failures preserve canonical Final JSON and completed sibling outputs; retry performs zero AI and reuses valid narration artifacts.
9. No Output Directory Resolver, packaging, or real live episode/season E2E work is included.

### Exact Scope Executed in Phase 10

1. Compact AI Gateway pane exposes endpoint, masked API key, Scanner model/reasoning/parallelism/chunk milliseconds, Vision model/reasoning and unified Finalizer model/reasoning.
2. Model inputs are provider-neutral free text; fresh defaults are empty and no capability is inferred from model names.
3. DPAPI entropy and V3 description remain unchanged; normal settings persistence rejects/leaks no secret.
4. UI-independent controller validates form values, performs atomic settings/secret save with rollback, and supports diagnostics from unsaved values.
5. Legacy split Planner/Writer/Prime values are preserved when different; explicit unified Finalizer Save alone updates all intended creative stages.
6. Test Scanner/Finalizer use one bounded model-availability request, no prompt/project/media/artifacts, background thread work and Tk-main-thread result polling.
7. Save is explicit, Cancel does not mutate effective settings, unknown unrelated settings survive persistence, and existing Voice/Audio Mix/render controls remain intact.
8. Phase 3–9 dependency semantics and existing Final JSON zero-AI path are unchanged.

### Exact Scope Executed in Phase 9

1. Parses captured Writer JSON and validates identity, narration, segments, authoritative Evidence/Visual references and evidence-grounded source clips independently per output.
2. Deterministic sorted issue codes distinguish valid and repairable-invalid responses without subjective prose scoring.
3. Only invalid outputs receive bounded provider-neutral repair; valid siblings remain untouched and original responses are never overwritten.
4. Repair prompts carry exact issue codes, raw prompt, locked entry and complete output-specific authoritative context; repair cannot replan or alter output identity/order.
5. Repair raw responses/results/provenance are checkpointed per attempt and recover after crash without repeating paid calls.
6. Local deterministic mapper converts ordered valid outputs to immutable schema 3.0 without AI merge or editorial rewrite.
7. Canonical validator runs before atomic COMPLETE Final JSON publication; corrupt/mismatched artifacts are not cache hits.
8. Zero-output plans stop truthfully without fabricated content; one-shot routing foundation is capacity-explicit and seasons remain staged.
9. At the Phase 9 boundary workflow reached `FINAL_JSON_READY`; Phase 11 now connects that checkpoint to the preserved VoiceStudio/Audio Mix/render stack. UI redesign and Output Directory Resolver remain separate phases.

### Exact Scope Executed in Phase 8

1. Exactly one independent Writer job per locked Season Plan output; zero-output plans make zero Writer calls.
2. Context validates locked plan hash/order, output entry, canonical episodes/sources/ranges, authoritative Evidence Store objects and active Visual Evidence.
3. Every request preserves the raw prompt verbatim and supplies all locked target Evidence/Visual Evidence without ranking, truncation, frames or media.
4. Provider-neutral model/reasoning, actual serialized request-byte preflight, explicit capacity failures and finite worker-pool scheduling.
5. Full raw response is checkpointed before parsing; oversized truncated diagnostics never count as complete production responses.
6. Per-output cache/recovery and independent retries preserve successful sibling outputs across failures/restarts.
7. Best-effort parse state is recorded without semantic repair, corrected content, merge or production Final JSON.
8. Workflow reaches `WRITER_DRAFTS_READY` and stops before Phase 9; no VoiceStudio, Audio Mix, render or publish operation occurs.

### Exact Scope Executed in Phase 6

1. `season-planner-protocol-v1` supporting only `REQUEST_EVIDENCE` and `PLANNER_DRAFT` actions.
2. Verbatim raw Recap Prompt plus complete `season-catalog-packed-v1`, ordered episode mapping, durations and active identities in every Planner round.
3. Exact ID/range retrieval from Full Evidence with Catalog membership, project/revision, source/episode and detail-hash verification; no fuzzy or top-K search.
4. AI-decided proposed output count, ordered draft concepts, cross-episode support, secondary-character/subplot freedom and technically validated Phase 7 visual range requests.
5. Bounded Planner rounds and bounded technical repair; actual serialized request byte preflight with `UNKNOWN`/`FIT`/capacity failure behavior.
6. Atomic Planner session, raw response, round, evidence-fetch and draft checkpoints with restart reuse and raw-response crash recovery.
7. Workflow advances from `CATALOG_READY` through Planner rounds to `PLANNER_DRAFT_READY`, then stops before Phase 7.
8. Explicit exclusions: no frame extraction, general image Gateway, visual Evidence, locked `season_plan.json`, canonical `out_###` IDs, Output Writer, Final JSON, voice or render.

### Exact Scope Executed in Phase 7

1. Validated Planner-requested visual ranges with deterministic `VR-E##-###` identities and canonical source derivation.
2. Bounded local FFmpeg still extraction, deterministic temporal coverage, safe JPEG normalization, independent frame-cache keys and explicit hard-cap failures.
3. Factual still-image Vision over selected frames only, strict request/frame/timestamp/episode/source validation, identity-grounding instructions and preserved uncertainty.
4. Separate deterministic `E##-VIS-###` Visual Evidence layer; immutable Phase 4 textual Evidence remains unchanged.
5. Hash-verified visual revisions, bounded raw response recovery metadata, request-state completeness ledger, zero-visual completion and resume without repeated valid Vision calls.
6. Final Planner refinement with verbatim raw prompt, complete Catalog, Planner Draft, authoritative Full Evidence, complete Visual Evidence and visual completeness.
7. Strict final references/ranges, AI-owned order/count, application-owned sequential `out_###`, deterministic plan hash/revision and atomic immutable `season_plan.json` lock.
8. Workflow reaches `SEASON_PLAN_READY` and stops before Phase 8; no Writer, narration, Final JSON, voice, or render work is implemented.

### Exact Scope Executed in Phase 5

1. Versioned `season-catalog-v1` contract with every ordered episode and one Catalog item for every active Evidence object.
2. Exact preservation of Evidence ID, episode/source identity, integer timestamps, factual observation, category, entities, modality, confidence, uncertainty, visual references and immutable Full Evidence detail hash.
3. Completeness validation for expected/actual episode and Evidence counts, duplicate/missing/unexpected IDs, ordered IDs digest, Evidence revision and per-episode Evidence manifest hashes.
4. Deterministic canonical Catalog hash over semantic content only; no creation time, PID, random UUID, temporary path or downstream settings.
5. `season-catalog-packed-v1` structural encoding with string, source, episode and entity tables plus columnar item rows. Strict unpack validation and exact `unpack(pack(catalog)) == catalog` verification.
6. Capacity preflight measures actual canonical and packed UTF-8 bytes, counts and diagnostic ratio. Unknown capacity remains `UNKNOWN`; explicit profiles report `FIT` or `EXCEEDS_CONFIGURED_LIMIT` without dropping content.
7. Atomic local checkpoint/cache under `projects/<project_id>/catalog/`, including dependency digest, file hashes, COMPLETE manifest and active pointer. Corrupt or partial artifacts are rebuilt from verified Full Evidence.
8. Workflow advances through `EVIDENCE_READY` to `CATALOG_READY`, then stops before Phase 6. Existing/imported Final JSON continues to bypass source prep, Scanner and Catalog.
9. Explicit exclusions: no Season Planner, Planner prompts/Gateway calls, Evidence Fetch protocol, editorial plan, general scene Vision, Output Writer, merge or Final JSON generation.

### Exact Scope Executed in Phase 4

1. `toolrecap_v4.analysis.scanner`: factual-only prompt contract, actual serialized request measurement, deterministic chunk planning, lossless technical cue splitting, strict response schema and bounded repair.
2. Stable IDs: accepted observations are sorted by chunk order, integer bounds, category, normalized content digest and occurrence order before allocation as `E##-EV-###`.
3. Revisions: transcript content/provenance, prepared/source hashes, Scanner model/reasoning, prompt/schema/validation/normalization versions and chunk policy form the semantic signature. Parallelism and downstream creative/render settings are excluded.
4. Cache/resume: each successful raw response is saved locally with a byte cap before validation; complete chunk artifacts require content-hash manifests. A crash after raw receipt can recover and validate that response without another provider call.
5. Full Evidence Store: immutable episode JSON plus atomic manifests under `projects/<project_id>/evidence/<revision>/`; supports `get`, `get_many`, `get_episode`, `query_range`, `verify_revision`, and completeness/count reporting.
6. Workflow: a configured project progresses through source preparation and Scanner to `EVIDENCE_READY`, then stops explicitly before Phase 5. Existing/imported Final JSON still bypasses preparation and Scanner with zero AI calls.
7. Explicit exclusions: no Season Catalog, general scene Vision, planner, story selection/ranking, writer, Final JSON generation, or Phase 5 work.

### Preserved Phase 3 Scope (historical baseline):
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
   - Phase 3 originally stopped at `ProjectStatus.PREPARED`; Phase 4 now continues from that artifact boundary when a Scanner model is configured.
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
| **Controlled Workflow Boundary**| `VERIFIED` | Fully configured nonzero analysis reaches `ProjectStatus.FINAL_JSON_READY` and stops before Phase 10/11; generated Final JSON exists before any downstream voice/render work. |
| **Scanner Editorial Isolation** | `VERIFIED` | Scanner receives no Recap Prompt, application ranking policy, candidate logic, output quota, video, whole audio, or arbitrary local path. |
| **Stable Evidence Identity** | `VERIFIED` | IDs are application-owned, deterministic after sorted validated chunk artifacts, and scoped by project + evidence revision. |
| **Full Evidence Retention** | `VERIFIED` | Range queries return every overlap in deterministic order; no top-K, fuzzy dedupe, story ranking, or character/subplot filtering. |
| **Complete Catalog Coverage** | `VERIFIED` | Every complete episode and every active Evidence ID is represented exactly once; zero-Evidence complete episodes remain explicit. |
| **Lossless Packing** | `VERIFIED` | Strict pack/unpack equality preserves complete canonical Catalog content, including Unicode and long observations. |
| **Zero-AI Catalog** | `VERIFIED` | Catalog build, packing, capacity measurement and cache reuse are entirely local and invoke no Gateway API. |
| **Verbatim Planner Prompt** | `VERIFIED` | Raw Recap Prompt survives JSON transport exactly, including Unicode, newlines, quotes and unusual spacing. |
| **Exact Evidence Fetch** | `VERIFIED` | Only exact IDs/ranges are accepted; Full Evidence detail hashes and complete range overlap results are verified. |
| **No App Editorial Scoring** | `VERIFIED` | Output count/order/story/character/subplot decisions remain AI-owned; no scoring, fixed quota or application reranking exists. |
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
  - Result: All 74 current submodules cleanly imported without error after Phase 11.
- **Full Pytest Suite**:
  - Command: `pytest --basetemp="C:\Users\Long\AppData\Local\Temp\kilo\pytest_v4_phase3_run"`
   - Phase 2 baseline: **237 passed**.
   - Pre-closure Phase 3 suite: **330 passed**, tăng ròng **93 tests** so với Phase 2 baseline **237 passed**.
   - Final closure suite sau 1 SSA + 5 Vision OCR regression tests: **336 passed in 43.45s**, 0 failures, 0 errors, 0 skipped.
- Phase 4 final full suite: **383 passed in 49.42s**, 0 failures, 0 errors, 0 skipped.
- Phase 4 focused coverage: **47 Scanner/Evidence/Workflow/settings tests** across the five new test modules plus two Scanner settings tests in `test_settings.py`.
- Phase 5 final full suite: **416 passed in 50.19s**, 0 failures, 0 errors, 0 skipped.
- Phase 5 focused coverage: **33 Catalog/packing/store tests** plus updated workflow bypass and `CATALOG_READY` integration assertions.
- Phase 6 final full suite: **453 passed in 51.05s**, 0 failures, 0 errors, 0 skipped.
- Phase 6 focused coverage: **35 Planner protocol/fetch/service tests**, two Planner settings tests, and updated workflow boundary/bypass assertions.
- Phase 7 closure full suite: **481 passed in 53.68s**, 0 failures, 0 errors, 0 skipped.
- Phase 7 focused coverage: **28 targeted visual request/frame/Vision/cache/plan-lock tests** plus updated workflow assertions.
- Phase 8 closure full suite: **501 passed in 68.99s**, 0 failures, 0 errors, 0 skipped.
- Phase 8 closure focused coverage: **20 targeted Writer context/integrity/execution/cache/response-boundary tests** plus updated workflow/bypass assertions.
- Phase 9 closure full suite: **526 passed in 67.39s**, 0 failures, 0 errors, 0 skipped.
- Phase 9 focused coverage: **25 validation/repair/mapping/revision/zero-output tests** plus updated workflow/bypass assertions.
- Phase 10 closure full suite: **550 passed in 93.75s**, 0 failures, 0 errors, 0 skipped (short Windows-safe isolated basetemp).
- Phase 10 settings/UI focused suite: **48 passed**, including secure migration, transactional rollback, diagnostics, dependency boundaries and real-Tk interaction tests.
- Phase 11 closure full suite: **560 passed in 59.23s**, 0 failures, 0 errors, 0 skipped.
- Phase 11 downstream-focused suite: **86 passed**, including 10 narration-cache/integration tests plus VoiceStudio, renderer, media and workflow regressions.
- **Preserved Phase 3 Test Suite Breakdown (336-test baseline)**:
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

### Phase 4 test modules

- `tests/test_scanner_chunking.py`: deterministic cue/time/byte planning, exact boundaries, empty/malformed transcripts, long-cue losslessness, controlled source identifiers, and forbidden Scanner context.
- `tests/test_scanner_schema.py`: identity, timestamp type/range, cue reference, required field, enum, confidence, uncertainty, and malformed JSON rejection.
- `tests/test_scanner_service.py`: bounded concurrency, text-only requests, order-independent IDs, independent repair, repair exhaustion, semantic invalidation, cancellation, completed-chunk reuse, and raw-response crash recovery.
- `tests/test_evidence_store.py`: immutable revisions, get/get-many/episode/range, overlap completeness, repeated observation preservation, partial/corrupt/hash-mismatch rejection, and old-revision survival.
- `tests/test_workflow_scanner.py`: source preparation → Scanner → `EVIDENCE_READY` integration and explicit stop before Phase 5.

### Phase 5 test modules

- `tests/test_catalog.py`: complete episode/Evidence coverage, zero-Evidence episodes, deterministic order/hash/bytes, exact detail links, repeated/short/secondary-character/Unicode/long observations, and failed/incomplete episode rejection.
- `tests/test_catalog_packing.py`: exact pack/unpack equality, byte stability, no semantic loss, and rejection of invalid versions, indices, rows, numeric types, duplicate IDs, count/digest/hash corruption.
- `tests/test_catalog_store.py`: canonical/packed byte metrics, capacity states, atomic cancellation behavior, checkpoint reuse, evidence/schema/packing invalidation, corrupt/partial rebuild, and downstream-setting independence.
- `tests/test_workflow_scanner.py`: source prep → Scanner → Evidence → Catalog → `CATALOG_READY`, Catalog reuse after restart, zero extra Gateway calls, and explicit stop before Phase 6.
- `tests/test_workflow_source_prep.py`: imported Final JSON bypass now explicitly asserts Catalog is never invoked.

### Phase 6 test modules

- `tests/test_planner_protocol.py`: verbatim prompt, complete Catalog membership, strict identities/actions, AI-decided output count, cross-episode drafts, draft refs and visual range validation.
- `tests/test_planner_evidence_fetch.py`: exact ID/range retrieval, overlap completeness, deterministic order, invalid/stale/malformed requests and detail-hash failure.
- `tests/test_planner_service.py`: immediate/multi-round drafts, round limits, bounded repair, raw recovery, completed fetch reuse, dependency invalidation, capacity, cancellation and no final lock.
- `tests/test_workflow_scanner.py`: `PLANNER_DRAFT_READY` boundary and raw prompt handoff.
- `tests/test_workflow_source_prep.py`: imported Final JSON bypass explicitly asserts Planner is never invoked.

### Phase 7 test modules

- `tests/test_visual_phase7.py`: selective extraction, factual ambiguity, safe Vision path, zero-visual behavior, stable Visual Evidence/output IDs and locked-plan reuse.
- `tests/test_visual_closure.py`: strict range and Vision identity/type rejection, deterministic request IDs, canonical source mapping, raw response recovery, factual prompt boundary and immutable Phase 4 Evidence.
- `tests/test_season_plan_closure.py`: zero/one/many outputs, AI order preservation, application-owned IDs, identity mismatch rejection, pre-lock absence and semantic plan revision behavior.

---

## 4. Explicit Limitations & Boundaries (Phase 12+ Scope)

- **General scene Vision boundary**: Selective Planner-requested still-image Vision is implemented in Phase 7. Full-episode/season scans, video upload and arbitrary sampling remain prohibited.
- **Writer validation/repair and Final JSON**: IMPLEMENTED in Phase 9.
- **AI Gateway settings UI and secure migration**: IMPLEMENTED in Phase 10.
- **Voice/Audio Mix/render verification**: IMPLEMENTED in Phase 11 using deterministic mocks/synthetic media; no real production episode/season acceptance is claimed.
- **Output Directory Resolver**: NOT implemented; remains Phase 12.
- **Output Writers**: IMPLEMENTED in Phase 8 as independent response-capture jobs.
- **Executable Packaging**: Portable binary packaging via `build_portable.py` / PyInstaller was not run; no `dist/ToolRecapV4.exe` exists in this phase.
- **AI Model Execution in Tests**: Unit and integration tests used mock/synthetic adapters and injected runners. Live GPU transcription and online model downloading were not invoked during testing.
- **Git state**: Phase 1–10 history is preserved. Phase 11 implementation is `b429cabc7560415ace2593686bd79092b0b5350b` (`feat: connect final json to voice and render`) and closure is `b77547a5981eeaf1323666c0ef62f7f24181e4c2` (`fix: close Phase 11 downstream gaps`). No remote or push is configured.
