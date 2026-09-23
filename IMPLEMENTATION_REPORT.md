# ToolRecap V4 — Implementation & Verification Report (Phase 14 Synthetic Integration)

**Date**: 2026-09-23
**Contract**: Phase 14 — Full Regression + Synthetic End-to-End Integration Acceptance
**Project**: ToolRecap V4  
**Target Platform**: Windows 10/11 x64 Portable  
**Version**: v4.0.0  
**Phase**: Phase 14 — Full Regression, Synthetic Episode/Season E2E, Restart and Failure Injection
**Status**: Phase 14 IMPLEMENTED with deterministic synthetic episode/season acceptance. Real episode/season E2E remains later scope.

---

## 1. Executive Summary & Scope

This report documents implementation and verification through **Phase 14 — Full Regression + Synthetic End-to-End Integration Acceptance** of the ToolRecap V4 migration plan (`TOOLRECAP_V4_MIGRATION_PLAN.md`). Synthetic source media now runs through the production workflow to published, FFprobe-validated video using deterministic fake AI and VoiceStudio responses. `FINAL_JSON_READY` remains the zero-AI downstream boundary.

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
- **Phase 12 (Publication Resolver)**: Added one authoritative manual/automatic publication-root resolver, automatic sibling `Outputs_<working-folder-name>`, delayed root creation, internal-artifact isolation, destination-aware checkpoints and unowned-target collision protection.
- **Phase 13 (Portable Packaging & Updater)**: Added centralized relocation-safe resource lookup, one-folder PyInstaller packaging with actual FFmpeg/OCR/STT runtime collection, structured zero-AI self-check, package content validation, safe updater staging/checksum/traversal/active-workflow guards, rollback validation, and real Windows portable smoke acceptance.
- **Phase 14 (Synthetic Integration)**: Exercised real source preparation, Scanner/Evidence, Catalog, Planner/evidence fetch, selective Vision, locked Season Plan, independent Writers, targeted repair, canonical Final JSON, fake VoiceStudio narration cache, FFmpeg Audio Mix/render, and publication. Added disk-backed restart, semantic invalidation, zero-AI reuse, technical failure, and cross-project isolation tests. Fixed silent-audio loudnorm and owned-output retry defects found by those tests.

### Exact Scope Executed in Phase 14

1. FFmpeg-generated video/audio/subtitle fixtures drive one-episode and three-episode production workflows. The season includes a complete zero-Evidence episode, a secondary event, and an E01+E03 cross-episode output.
2. A deterministic fake Gateway implements the actual Scanner, Planner, Evidence fetch, selective still-image Vision, final Planner, Writer and repair JSON contracts. Production parsers, validators, stores and orchestration remain active.
3. The real renderer produces decodable videos with human titles; actual source files, LocalAppData artifacts, Final JSON, narration cache and publication remain separated.
4. Restart tests recreate workflows from disk at PREPARED, EVIDENCE_READY, CATALOG_READY, PLANNER_DRAFT_READY, SEASON_PLAN_READY, WRITER_DRAFTS_READY and FINAL_JSON_READY without repeating valid prior AI calls.
5. Invalidation tests cover sidecar content hashes, Scanner model/reasoning/parallelism, Vision model and frame reuse, Planner model, Voice, Audio Mix, render quality and publication destination.
6. Failure tests cover repair exhaustion, zero-output truth, Voice/render retry, blocked publication root, unowned collision, source mutation, corrupt output and narration cache, cancellation after Final JSON, and partial multi-output resume.
7. A silent but valid WAV exposed an FFmpeg loudness-pass failure; the renderer now uses `anull` for non-finite loudness measurements. A failed rerender exposed lost checkpoint ownership; the workflow now retains an already-owned destination path through failure, enabling a safe retry.

### Exact Scope Executed in Phase 13

1. One-folder `ToolRecapV4.exe` packaging keeps Python/source checkout out of the target runtime and bundles the schema, FFmpeg/FFprobe and required OCR/STT runtime modules without user models.
2. Runtime resource and media lookup use application/package roots rather than the process current working directory; schema 3.0 loads after relocation.
3. `--selfcheck` is callable from source and frozen runtime, emits structured PASS/WARN/FAIL checks, returns nonzero only for fatal required-runtime failures, performs zero AI/project/render/update work, and redacts credentials.
4. Self-check covers application state, schema, FFmpeg/FFprobe, encoder fallback, OCR/STT imports and optional model availability, settings, Gateway configuration state, VoiceStudio configuration, Phase 12 resolver, and updater runtime.
5. Package validation rejects missing runtime layout, schema/resource mismatches, invalid versions, user state, tests and Git metadata.
6. Updater staging validates semantic version, checksum, archive name, safe extraction and package resources before apply; active workflow state blocks staging/apply.
7. Update helper validates staged content, separates install/state/publication roots, preserves unknown/user files, rolls back failed handshakes, and cleans staged/backup artifacts.
8. Real acceptance built `dist/ToolRecapV4`, ran clean-PATH self-check from the build path, relocated it under spaces/Unicode, ran from a different CWD, and validated the release ZIP.

### Exact Scope Executed in Phase 12

1. Manual publication root wins exactly; blank means automatic sibling output based on selected working folder.
2. Folder input uses the selected folder; single-file and same-folder file lists use their parent. Multiple source parents require manual output.
3. Root/nameless automatic paths, relative manual paths, path-as-file, unavailable shares/drives and mkdir failures raise `OutputDirectoryError` without fallback.
4. Generated/imported Final JSON use the same downstream resolver; automatic paths are never persisted into the manual setting.
5. Destination is created only at publication/downstream entry, not while Settings/source browsing/analysis runs.
6. Managed Final JSON, narration cache and all analysis artifacts remain outside publication root; renderer temp work remains under managed render-work, and neighbor publication staging files are removed on success, cancellation, or failure.
7. Existing title naming, filename validation, source collision, fingerprint and output SHA checks remain. Unowned existing publication files are rejected rather than overwritten.
8. Output-directory changes keep Final JSON/AI/narration valid; the current renderer rerenders at the new destination using cached narration.
9. No real production episode or season E2E work is included.

### Exact Scope Executed in Phase 11

1. Phase 9-generated canonical Final JSON now continues into the existing downstream path instead of stopping at `FINAL_JSON_READY`.
2. Imported and generated Final JSON are both revalidated at the common downstream boundary and treated identically by Voice/Render.
3. Managed per-segment narration cache keys exact Final JSON narration plus VoiceStudio mode/endpoints/voice/model/language/style; WAV content/hash/duration are validated before reuse.
4. Audio Mix and renderer remain the existing deterministic implementation: source levels, commentary level, optional ducking, two-pass loudness normalization, subtitle behavior, multi-source clips and file-based FFmpeg processing.
5. Existing encoder detection and configured GPU/CPU fallback behavior remain intact.
6. Output fingerprinting excludes AI settings but includes voice, mix, renderer, source and canonical output content dependencies.
7. Existing output checkpoint reuse still requires matching fingerprint, file presence and output SHA; file existence alone is insufficient.
8. Voice/render failures preserve canonical Final JSON and completed sibling outputs; retry performs zero AI and reuses valid narration artifacts.
9. Phase 10 did not add an Output Directory Resolver; Phase 12 now implements it. Packaging and real live episode/season E2E remain excluded.

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
9. At the Phase 9 boundary workflow reached `FINAL_JSON_READY`; Phase 11 connected that checkpoint to VoiceStudio/Audio Mix/render, and Phase 12 now centralizes its publication destination.

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
| **Controlled Workflow Boundary**| `VERIFIED` | Fully configured analysis reaches `ProjectStatus.FINAL_JSON_READY`, the zero-AI boundary, then continues through VoiceStudio/Audio Mix/render and publishes through the Phase 12 resolver. |
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
| **Storage Isolation** | `PRESERVED` | Internal working state, prepared artifacts, Final JSON, narration, and caches remain under `%LOCALAPPDATA%\ToolRecapV4\`; only intended user-facing render outputs are published to the resolved destination. |

---

## 3. Verification & Testing Evidence

All validation suites executed and passed cleanly:

- **Bytecode Compilation**:
  - Command: `python -m compileall toolrecap_v4 tests main.py build_portable.py repackage.py`
  - Result: 100% clean compilation across all modules and tests, 0 syntax or compilation errors.
- **Module Import Verification**:
  - Command: `pkgutil.walk_packages` across `toolrecap_v4`
  - Result: All 76 current submodules cleanly imported without error after Phase 13.
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
- Phase 12 final closure full suite: **571 passed in 62.14s**, 0 failures, 0 errors, 0 skipped. The count increased from 569 only because closure added one three-output destination-resume test and one failed-publication staging-cleanup test.
- Phase 12 resolver-focused suite: **10 passed in 1.08s**, plus generated/imported workflow and Phase 11 downstream regression coverage.
- Phase 12 closure regressions: Phase 11 downstream **32 passed**; VoiceStudio **9 passed**; renderer **18 passed**; media **25 passed**; Phase 10 settings **46 passed**; Phase 9 **25 passed**; Phase 8 **20 passed**; Phase 7 **28 passed**; Phase 6 **35 passed**; Phase 5 **33 passed**; Phase 4 Scanner/Evidence **44 passed**; Phase 3 source preparation **106 passed**; Phase 2 Gateway **33 passed**.
- A first Phase 9 subset invocation used pytest's deeply nested default Windows temp path and hit path-length `ENOENT` errors. The required short Windows-safe `--basetemp` rerun passed all **25** tests; no product code was changed for that environment-only result.
- Phase 13 focused packaging/self-check tests: **22 passed**; updater tests: **15 passed**. Closure coverage includes the wired UI activity guard, Windows archive traversal variants, interrupted download cleanup, semantic version outcomes, unchanged project artifacts during self-check, and rejection of missing Python runtime files.
- Phase 13 final full suite: **594 passed in 57.49s**, 0 failures, 0 errors, 0 skipped. The increase from the Phase 13 implementation's 582 is 12 targeted closure tests.
- Phase 13 regression matrix: Phase 12 **10 passed**; Phase 11 downstream **32 passed**; Phase 10 settings **49 passed**; Phase 9 **25 passed**; Phase 8 **20 passed**; Phase 7 **28 passed**; Phase 6 **35 passed**; Phase 5 **33 passed**; Phase 4 Scanner/Evidence **44 passed**; Phase 3 source preparation **106 passed**; Phase 2 Gateway **33 passed**; VoiceStudio **9 passed**; renderer **18 passed**; media **25 passed**.
- Phase 13 compilation passed and module import verification passed for **76** submodules; `git diff --check` passed.
- Real Windows packaging acceptance passed after the closure fix: one-folder build at `dist/ToolRecapV4`, frozen self-check from the build folder, Unicode/space relocation, different-CWD execution, ZIP extraction validation, and package content audit. Frozen self-check returned **0 / WARN** in all three launch contexts; required schema, FFmpeg, FFprobe, OCR, STT, settings, output resolver, and updater checks were **PASS**. Warnings identified optional OCR/STT model absence and incomplete Gateway configuration. Distribution size: **644,959,153 bytes (615.08 MiB)** across 1,973 files; compressed ZIP: **255,557,903 bytes**. Release SHA-256: `16ed06aecc288797f29dce5764bc858633d37513a26ab2a375a4dbfd04d828b7`.
- Package runtime includes Python 3.12, schema 3.0, FFmpeg/FFprobe, Pillow, ONNX Runtime/RapidOCR, faster-whisper/CTranslate2, tkinter, and updater code. User settings, DPAPI secrets, projects, models, output media, tests, pytest and Git metadata are absent. Managed state remains `%LOCALAPPDATA%\ToolRecapV4\`; the install directory is read-only runtime content for normal operation.
- Updater acceptance uses semantic versions, published archive SHA-256, bounded safe extraction and package resource validation; it is checksum-based, without a release-signature claim. The Settings dialog now passes workflow activity to staging/apply guards. A separate helper waits for process exit, copies the frozen runtime outside the install directory, applies validated files, runs a startup handshake, and restores backed-up install files on failure. Synthetic valid/invalid cases and preservation of settings, DPAPI placeholder, project, Final JSON, narration, and publication markers passed.
- Phase 14 final full suite: **618 passed in 114.52s**, 0 failures, 0 errors, 0 skipped, using a short Windows-safe pytest basetemp. Phase 14 focused integration: **24 passed**. The increase from Phase 13's 594 is exactly those 24 tests.
- Phase 14 regression matrix: Phase 13 **22 passed**, updater **15**, Phase 12 **10**, Phase 11 **32**, Phase 10 **49**, Phase 9 **25**, Phase 8 **20**, Phase 7 **28**, Phase 6 **35**, Phase 5 **33**, Phase 4 **44**, Phase 3 **106**, Phase 2 Gateway **33**, VoiceStudio **9**, renderer **18**, media **25**, workflow **25**, UI **28**, schema **5**, secrets **5**, cancellation **5**.
- Synthetic single episode: production source prep, Scanner, complete Catalog, two Planner rounds with exact Evidence fetch, selected still-image Vision, locked Plan, Writer, canonical Final JSON, fake WAV, real Audio Mix/FFmpeg renderer, and sibling publication completed. AI calls: Scanner 1, Planner 2, Vision 1, final refinement 1, Writer 1, repair 0.
- Synthetic season: E01/E02/E03, with E02 complete and zero Evidence; three outputs include E01+E03 clips, a secondary event, and targeted repair of `out_002`. All three published MP4s were FFprobe-readable. AI calls: Scanner 3, Planner 2, Vision 1, final refinement 1, Writer 3, repair 1. No whole video/audio bytes went to the fake Gateway.
- Disk-backed restarts from PREPARED, EVIDENCE_READY, CATALOG_READY, PLANNER_DRAFT_READY, SEASON_PLAN_READY, WRITER_DRAFTS_READY and FINAL_JSON_READY passed. Final JSON import and completed-Final-JSON retry used zero AI. Voice, mix, render and destination changes respected their cache/invalidation boundaries; changing AI settings after Final JSON did not restart analysis.
- Technical acceptance covered repair exhaustion, zero-output plans, cancellation after Final JSON, corrupt output/WAV recovery, sidecar content mutation with unchanged mtime, Scanner model/reasoning/parallelism, Vision model with reusable frames, Planner model, source integrity, Voice/render failures, blocked publication root, unowned collision, partial multi-output resume, and cross-project isolation. Existing stage tests additionally cover raw-response crash recovery, malformed responses, capacity bounds, Gateway error classification, long-cue splitting, and asynchronous ordering.
- A real silent-WAV render failure led to an `anull` fallback for non-finite loudness measurements. A failed rerender losing ownership of a prior valid file led to preserving an already-owned output path in rendering/failure checkpoints. Both defects have integration regressions.
- Phase 14 production changes required rebuilding the Windows one-folder package. The rebuilt EXE passed clean-PATH, relocated Unicode/space, and different-CWD self-check acceptance. Package size: **644,959,153 bytes (615.08 MiB)**; release SHA-256: `16ed06aecc288797f29dce5764bc858633d37513a26ab2a375a4dbfd04d828b7`. Package audit found no tests, Git metadata or user state.
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

### Phase 14 integration modules

- `tests/test_phase14_workflow_e2e.py`: FFmpeg-generated source variants, one-episode and three-episode workflows, exact protocol fake Gateway, selective Vision, targeted repair, Final JSON determinism, real render/FFprobe and publication inspection.
- `tests/test_phase14_resume.py`: disk-backed checkpoint restarts, zero-Vision completion, downstream settings matrix, partial output resume, source mutation, cancellation, corrupt cache recovery, and cross-project isolation.
- `tests/test_phase14_invalidation.py`: sidecar content hash, Scanner model/reasoning/parallelism, Vision model/frame reuse and Planner model invalidation.
- `tests/test_phase14_failures.py`: imported Final JSON bypass, repair exhaustion, zero-output behavior, Voice/render retry, publication failure and unowned collision.

---

## 4. Explicit Limitations & Boundaries (Phase 15+ Scope)

- **General scene Vision boundary**: Selective Planner-requested still-image Vision is implemented in Phase 7. Full-episode/season scans, video upload and arbitrary sampling remain prohibited.
- **Writer validation/repair and Final JSON**: IMPLEMENTED in Phase 9.
- **AI Gateway settings UI and secure migration**: IMPLEMENTED in Phase 10.
- **Voice/Audio Mix/render verification**: IMPLEMENTED in Phase 11 using deterministic mocks/synthetic media; no real production episode/season acceptance is claimed.
- **Output Directory Resolver**: IMPLEMENTED in Phase 12.
- **Portable packaging/self-check/updater acceptance**: IMPLEMENTED and verified in Phase 13.
- **Real episode E2E**: NOT started; no real production episode acceptance is claimed.
- **Real season E2E**: NOT started; no real production season acceptance is claimed.
- **Output Writers**: IMPLEMENTED in Phase 8 as independent response-capture jobs.
- **Executable Packaging**: One-folder `dist/ToolRecapV4/ToolRecapV4.exe` and `release/ToolRecapV4-v4.0.0-windows-portable.zip` were built and verified. Generated artifacts remain ignored by Git.
- **AI Model Execution in Tests**: Unit and integration tests used mock/synthetic adapters and injected runners. Live GPU transcription and online model downloading were not invoked during testing.
- **External services and hardware**: 9Router and VoiceStudio remain external and were not called by self-check. OCR/STT models remain managed downloads. NVIDIA hardware/driver is not bundled; CPU libx264 fallback was verified. Live release-server update, fresh target-machine/VM acceptance, real single-episode E2E, and real season E2E remain unverified.
- **Git state**: Phase 1–13 history is preserved through `c2016ed7120b2e739cd14cc6bcafb24f5aaeecaa` (`docs: finalize Phase 13 closure report`). Phase 14 implementation/fix is `11d5b798c74f93f93fc85d4b3415eb4553bb8f52` (`fix: close full workflow integration gaps`). No remote or push is configured.
- **Phase 14**: Synthetic integration acceptance completed. The package was rebuilt after the renderer/workflow fixes. Real single-episode and real season E2E acceptance were not performed; Phases 15 and 16 have not started. No production-ready claim is made.
