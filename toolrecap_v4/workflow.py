"""Project workflow controller and execution engine for ToolRecap V4.

Invariants:
- Single file supported, folder direct children natural order.
- One project one Gateway submission.
- Raw response persisted including invalid JSON via callback/error field.
- Final validate actual probe durations then save BEFORE voice/render.
- Resume/import NEVER Gateway once Final JSON exists.
- Stop keeps completed outputs final/state.
- Reconcile interrupted ANALYZING/RENDERING to resumable.
- Render-settings fingerprint rerender affected outputs only no AI; source changes fail no substitution.
- Store source fingerprints, prompt hash, Gateway nonsecret identifier, settings snapshot, voice endpoint, timestamps.
- Validate completed output presence/hash before skip.
- Output failure stops queue preserves complete previous outputs.
- No secrets state/log.
- Prevent publication paths colliding ANY project sources including unused.
- Minimal controller no scheduler.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import enum
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.discovery import (
    SUPPORTED_EXTENSIONS,
    SourceFingerprint,
    compute_file_fingerprint,
    discover_sources,
    is_windows_reserved_stem,
    natural_sort_key,
)
from toolrecap_v4.errors import (
    CancelledError,
    DiscoveryError,
    InvalidGatewayResponseError,
    PersistenceError,
    SourceChangedError,
    SourceNotFoundError,
    ValidationError,
    WindowsCollisionError,
    WindowsNameError,
    WindowsReservedNameError,
)
from toolrecap_v4.gateway import GatewayClient, GatewayResult
from toolrecap_v4.media import probe_media
from toolrecap_v4.persistence import ProjectPersistence, get_storage_root
from toolrecap_v4.renderer import (
    RenderError,
    RenderResult,
    SourceCollisionError,
    compute_file_sha256,
    render_output,
)
from toolrecap_v4.settings import AppSettings, SettingsManager
from toolrecap_v4.validator import check_for_secrets, validate_project, validate_windows_name
from toolrecap_v4.voice_studio import VoiceStudioAdapter


class ProjectStatus(str, enum.Enum):
    CREATED = "created"
    NEW = "new"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    JSON_READY = "json_ready"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def normalize(cls, status: Union[str, ProjectStatus]) -> str:
        """Migrate and normalize status between user brief and internal enum names."""
        val = status.value if isinstance(status, ProjectStatus) else str(status)
        if val == cls.NEW.value:
            return cls.CREATED.value
        if val == cls.JSON_READY.value:
            return cls.ANALYZED.value
        return val


class OutputStatus(str, enum.Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowCallbacks:
    """Optional callbacks for tracking workflow progress."""

    on_status_change: Optional[Callable[[str], None]] = None
    on_sub_analysis: Optional[Callable[[str], None]] = None
    on_raw_response: Optional[Callable[[str], None]] = None
    on_final_json: Optional[Callable[[Dict[str, Any]], None]] = None
    on_output_started: Optional[Callable[[str], None]] = None
    on_output_completed: Optional[Callable[[str, Dict[str, Any]], None]] = None
    on_output_failed: Optional[Callable[[str, str], None]] = None
    on_output_skipped: Optional[Callable[[str, Dict[str, Any]], None]] = None
    on_error: Optional[Callable[[Exception, Optional[str]], None]] = None


def resolve_sources(
    source_input: str | Path | Sequence[str | Path],
    cancellation_token: Optional[CancellationToken] = None,
) -> List[SourceFingerprint]:
    """Resolve single file, folder, or list of files into naturally sorted SourceFingerprint list.
    
    Rules:
    - Single file: validated, fingerprinted, returned as 1-element list.
    - Folder: direct children only (non-recursive), natural order, Windows collision check.
    - List/sequence: validated, fingerprinted, naturally sorted, Windows collision check.
    """
    if cancellation_token:
        cancellation_token.check_cancelled()

    if isinstance(source_input, (str, Path)):
        p = Path(source_input).resolve()
        if not p.exists():
            raise DiscoveryError(f"Source path does not exist: {p}")
        if p.is_dir():
            return discover_sources(p, cancellation_token=cancellation_token)
        elif p.is_file():
            ext = p.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                raise DiscoveryError(f"Unsupported media extension '{ext}' for file {p.name}")
            if is_windows_reserved_stem(p.stem):
                raise WindowsReservedNameError(f"Source file uses Windows reserved name: {p.name}")
            validate_windows_name(p.name, "source_file")
            fp = compute_file_fingerprint(p, cancellation_token=cancellation_token)
            return [fp]
        else:
            raise DiscoveryError(f"Source path is neither file nor directory: {p}")

    elif isinstance(source_input, (list, tuple)):
        if not source_input:
            raise DiscoveryError("Source list cannot be empty.")
        fps: List[SourceFingerprint] = []
        casefold_seen: Dict[str, str] = {}
        for item in source_input:
            if cancellation_token:
                cancellation_token.check_cancelled()
            p = Path(item).resolve()
            if not p.is_file():
                raise DiscoveryError(f"Source file does not exist or is not a file: {p}")
            ext = p.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                raise DiscoveryError(f"Unsupported media extension '{ext}' for file {p.name}")
            if is_windows_reserved_stem(p.stem):
                raise WindowsReservedNameError(f"Source file uses Windows reserved name: {p.name}")
            validate_windows_name(p.name, "source_file")
            cf = p.name.casefold()
            if cf in casefold_seen:
                raise WindowsCollisionError(
                    f"Duplicate source basename under casefold: '{p.name}' conflicts with '{casefold_seen[cf]}'"
                )
            casefold_seen[cf] = p.name
            fps.append(compute_file_fingerprint(p, cancellation_token=cancellation_token))

        fps.sort(key=lambda x: natural_sort_key(x.basename))
        return fps
    else:
        raise TypeError(f"Invalid source_input type: {type(source_input).__name__}")


def compute_output_fingerprint(
    output_def: Dict[str, Any],
    source_fingerprints: Dict[str, Any],
    settings: AppSettings,
) -> str:
    """Compute deterministic SHA-256 fingerprint for an output, its sources, and render settings."""
    out_copy = {
        "render_id": output_def.get("render_id"),
        "title": output_def.get("title"),
        "segments": output_def.get("segments", []),
    }

    used_sources: Dict[str, Any] = {}
    for seg in output_def.get("segments", []):
        src_name = seg.get("source_file")
        if src_name and src_name in source_fingerprints:
            s_fp = source_fingerprints[src_name]
            if isinstance(s_fp, dict):
                used_sources[src_name] = {
                    "sha256": s_fp.get("sha256"),
                    "size_bytes": s_fp.get("size_bytes"),
                }
            else:
                used_sources[src_name] = {
                    "sha256": s_fp.sha256,
                    "size_bytes": s_fp.size_bytes,
                }

    render_settings = {
        "original_audio_db": settings.original_audio_db,
        "commentary_audio_db": settings.commentary_audio_db,
        "auto_duck": settings.auto_duck,
        "ducking_amount_db": settings.ducking_amount_db,
        "target_loudness_lufs": settings.target_loudness_lufs,
        "true_peak_db": settings.true_peak_db,
        "use_gpu": settings.use_gpu,
        "quality": settings.quality,
        "video_codec": settings.video_codec,
        "canvas_width": settings.canvas_width,
        "canvas_height": settings.canvas_height,
        "canvas_fps": settings.canvas_fps,
        "canvas_auto": getattr(settings, "canvas_auto", True),
        "burn_subtitles": settings.burn_subtitles,
        "output_format": settings.output_format,
        "voice_id": settings.voice_id,
        "voice_language": settings.voice_language,
        "voice_style": settings.voice_style,
        "voice_model": settings.voice_model,
        "voice_mode": settings.voice_mode,
        "voice_local_url": settings.voice_local_url,
        "voice_remote_url": settings.voice_remote_url,
    }

    payload = {
        "output": out_copy,
        "sources": used_sources,
        "settings": render_settings,
    }

    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_publication_collision(
    outputs: Sequence[Dict[str, Any]],
    output_dir: Path | str,
    all_source_paths: Sequence[Path | str],
) -> None:
    """Ensure publication paths do not collide with ANY project sources (including unused)."""
    out_dir = Path(output_dir).resolve()
    all_sources = {Path(p).resolve() for p in all_source_paths}

    for out in outputs:
        title = out.get("title", "")
        if not title:
            continue
        targets = [
            out_dir / f"{title}.mp4",
            out_dir / f"{title}.narration.srt",
            out_dir / f"{title}.original.srt",
        ]
        for t in targets:
            if t.resolve() in all_sources:
                raise SourceCollisionError(
                    f"Publication target '{t.name}' at '{t.resolve()}' collides with project source file."
                )


def verify_source_integrity(
    source_fingerprints: Dict[str, Any],
    cancellation_token: Optional[CancellationToken] = None,
) -> None:
    """Verify source files exist and have not changed since project creation."""
    for basename, fp_data in source_fingerprints.items():
        if cancellation_token:
            cancellation_token.check_cancelled()
        path_str = fp_data.get("path") if isinstance(fp_data, dict) else fp_data.path
        expected_sha = fp_data.get("sha256") if isinstance(fp_data, dict) else fp_data.sha256
        expected_size = fp_data.get("size_bytes") if isinstance(fp_data, dict) else fp_data.size_bytes

        p = Path(path_str).resolve()
        if not p.is_file():
            raise SourceNotFoundError(
                f"Source file '{basename}' not found at '{p}'. Substitution is strictly prohibited."
            )

        current_fp = compute_file_fingerprint(p, cancellation_token=cancellation_token)
        if current_fp.sha256 != expected_sha or current_fp.size_bytes != expected_size:
            raise SourceChangedError(
                f"Source file '{basename}' has been modified since project creation (expected sha256={expected_sha[:8]}..., "
                f"current sha256={current_fp.sha256[:8]}...). Substitution is strictly prohibited."
            )


def reconcile_project_state(
    project_state: Dict[str, Any],
    persistence: ProjectPersistence,
) -> Dict[str, Any]:
    """Reconcile interrupted ANALYZING/RENDERING states to resumable status."""
    project_id = project_state["project_id"]
    raw_status = project_state.get("status")
    status = ProjectStatus.normalize(raw_status) if raw_status else None

    if status == ProjectStatus.ANALYZING.value:
        if persistence.has_final_json(project_id) or project_state.get("final_json"):
            project_state["status"] = ProjectStatus.ANALYZED.value
        else:
            project_state["status"] = ProjectStatus.CREATED.value
        persistence.save_project(project_state)
    elif status == ProjectStatus.RENDERING.value:
        project_state["status"] = ProjectStatus.ANALYZED.value
        persistence.save_project(project_state)

    return project_state


class ProjectWorkflow:
    """Synchronous worker-friendly controller for ToolRecap V4 projects."""

    def __init__(
        self,
        persistence: Optional[ProjectPersistence] = None,
        gateway_client: Optional[GatewayClient] = None,
        voice_adapter: Optional[VoiceStudioAdapter] = None,
        settings_manager: Optional[SettingsManager] = None,
        storage_root: Optional[Path | str] = None,
    ) -> None:
        self.persistence = persistence or ProjectPersistence(storage_root=storage_root)
        self.settings_manager = settings_manager or SettingsManager(persistence=self.persistence)
        self.gateway_client = gateway_client or GatewayClient()
        self.voice_adapter = voice_adapter

    def create_project(
        self,
        project_id: str,
        project_name: str,
        source_input: str | Path | Sequence[str | Path],
        prompt: str = "",
        output_dir: Optional[Path | str] = None,
        settings: Optional[AppSettings] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Create a new project from sources and persist initial state."""
        validate_windows_name(project_id, "project_id")
        if not re.match(r"^[A-Za-z0-9._-]+$", project_id):
            raise ValidationError(f"project_id '{project_id}' must match pattern ^[A-Za-z0-9._-]+$")
        validate_windows_name(project_name, "project_name")

        cfg = settings or self.settings_manager.load()
        fps = resolve_sources(source_input, cancellation_token=cancellation_token)
        if not fps:
            raise DiscoveryError("No supported source files discovered.")

        if output_dir is not None:
            resolved_output_dir = Path(output_dir).resolve()
        else:
            resolved_output_dir = self.persistence.root / "outputs" / project_id
        resolved_output_dir.mkdir(parents=True, exist_ok=True)

        source_fps_map = {fp.basename: fp.to_dict() for fp in fps}
        effective_prompt = prompt or cfg.prompt
        prompt_hash = hashlib.sha256(effective_prompt.encode("utf-8")).hexdigest() if effective_prompt else ""

        gw_identifier = f"{cfg.gateway_endpoint}::{cfg.gateway_model}"
        voice_endpoint = f"{cfg.voice_mode}::{cfg.voice_local_url}::{cfg.voice_remote_url}"

        now_iso = datetime.now(timezone.utc).isoformat()
        state: Dict[str, Any] = {
            "schema_version": "3.0",
            "project_id": project_id,
            "project_name": project_name,
            "status": ProjectStatus.CREATED.value,
            "output_dir": str(resolved_output_dir),
            "sources": [
                {
                    "source_file": fp.basename,
                    "fingerprint": fp.to_dict(),
                    "duration_ms": int(round(probe_media(fp.path, cancellation_token=cancellation_token).duration * 1000.0)),
                }
                for fp in fps
            ],
            "source_fingerprints": source_fps_map,
            "prompt": effective_prompt,
            "prompt_hash": prompt_hash,
            "gateway_identifier": gw_identifier,
            "settings_snapshot": cfg.to_dict(),
            "voice_endpoint": voice_endpoint,
            "timestamps": {
                "created_at": now_iso,
                "updated_at": now_iso,
            },
            "sub_analysis": None,
            "raw_response": None,
            "final_json": None,
            "outputs": {},
            "error": None,
        }

        check_for_secrets(state)
        self.persistence.save_project(state)
        return state

    def import_project(
        self,
        project_id: str,
        project_name: str,
        source_input: str | Path | Sequence[str | Path],
        final_json: Dict[str, Any],
        output_dir: Optional[Path | str] = None,
        settings: Optional[AppSettings] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Import an existing final project JSON with sources and validate before save."""
        validate_windows_name(project_id, "project_id")
        if not re.match(r"^[A-Za-z0-9._-]+$", project_id):
            raise ValidationError(f"project_id '{project_id}' must match pattern ^[A-Za-z0-9._-]+$")
        validate_windows_name(project_name, "project_name")

        cfg = settings or self.settings_manager.load()
        fps = resolve_sources(source_input, cancellation_token=cancellation_token)
        if not fps:
            raise DiscoveryError("No supported source files discovered.")

        if output_dir is not None:
            resolved_output_dir = Path(output_dir).resolve()
        else:
            resolved_output_dir = self.persistence.root / "outputs" / project_id
        resolved_output_dir.mkdir(parents=True, exist_ok=True)

        source_fps_map = {fp.basename: fp.to_dict() for fp in fps}

        # Probe actual durations for all discovered sources
        source_durations = {
            fp.basename: int(round(probe_media(fp.path, cancellation_token=cancellation_token).duration * 1000.0))
            for fp in fps
        }

        # Validate final_json against actual probed durations
        validate_project(final_json, source_durations=source_durations, cancellation_token=cancellation_token)

        # Check publication collision against ALL project sources including unused
        all_source_paths = [fp.path for fp in fps]
        check_publication_collision(final_json.get("outputs", []), resolved_output_dir, all_source_paths)

        # Save final JSON atomically to disk BEFORE voice/render
        self.persistence.save_final_json(project_id, final_json)

        gw_identifier = f"{cfg.gateway_endpoint}::{cfg.gateway_model}"
        voice_endpoint = f"{cfg.voice_mode}::{cfg.voice_local_url}::{cfg.voice_remote_url}"

        now_iso = datetime.now(timezone.utc).isoformat()
        state: Dict[str, Any] = {
            "schema_version": "3.0",
            "project_id": project_id,
            "project_name": project_name,
            "status": ProjectStatus.ANALYZED.value,
            "output_dir": str(resolved_output_dir),
            "sources": [
                {
                    "source_file": fp.basename,
                    "fingerprint": fp.to_dict(),
                    "duration_ms": source_durations[fp.basename],
                }
                for fp in fps
            ],
            "source_fingerprints": source_fps_map,
            "prompt": "",
            "prompt_hash": "",
            "gateway_identifier": gw_identifier,
            "settings_snapshot": cfg.to_dict(),
            "voice_endpoint": voice_endpoint,
            "timestamps": {
                "created_at": now_iso,
                "updated_at": now_iso,
                "analyzed_at": now_iso,
            },
            "sub_analysis": None,
            "raw_response": None,
            "final_json": final_json,
            "outputs": {},
            "error": None,
        }

        check_for_secrets(state)
        self.persistence.save_project(state)
        return state

    def start_project(
        self,
        project_id: str,
        output_dir: Optional[Path | str] = None,
        settings: Optional[AppSettings] = None,
        cancellation_token: Optional[CancellationToken] = None,
        callbacks: Optional[WorkflowCallbacks] = None,
    ) -> Dict[str, Any]:
        """Start or run project workflow synchronously."""
        return self._execute_workflow(
            project_id=project_id,
            output_dir=output_dir,
            settings=settings,
            cancellation_token=cancellation_token,
            callbacks=callbacks,
        )

    def resume_project(
        self,
        project_id: str,
        output_dir: Optional[Path | str] = None,
        settings: Optional[AppSettings] = None,
        cancellation_token: Optional[CancellationToken] = None,
        callbacks: Optional[WorkflowCallbacks] = None,
    ) -> Dict[str, Any]:
        """Resume project workflow, skipping completed outputs whose fingerprints match."""
        return self._execute_workflow(
            project_id=project_id,
            output_dir=output_dir,
            settings=settings,
            cancellation_token=cancellation_token,
            callbacks=callbacks,
        )

    def retry_project(
        self,
        project_id: str,
        output_dir: Optional[Path | str] = None,
        settings: Optional[AppSettings] = None,
        cancellation_token: Optional[CancellationToken] = None,
        callbacks: Optional[WorkflowCallbacks] = None,
    ) -> Dict[str, Any]:
        """Retry failed outputs or rerender invalidated outputs."""
        return self._execute_workflow(
            project_id=project_id,
            output_dir=output_dir,
            settings=settings,
            cancellation_token=cancellation_token,
            callbacks=callbacks,
        )

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Load and return current project state."""
        validate_windows_name(project_id, "project_id")
        return self.persistence.load_project(project_id)

    def reconcile_state(self, project_id: str) -> Dict[str, Any]:
        """Reconcile interrupted states to resumable status."""
        validate_windows_name(project_id, "project_id")
        state = self.persistence.load_project(project_id)
        return reconcile_project_state(state, self.persistence)

    def _execute_workflow(
        self,
        project_id: str,
        output_dir: Optional[Path | str] = None,
        settings: Optional[AppSettings] = None,
        cancellation_token: Optional[CancellationToken] = None,
        callbacks: Optional[WorkflowCallbacks] = None,
    ) -> Dict[str, Any]:
        """Synchronous execution engine for create/start/resume/retry."""
        validate_windows_name(project_id, "project_id")

        # Step 1: Load state and reconcile interrupted states
        state = self.persistence.load_project(project_id)
        state = reconcile_project_state(state, self.persistence)

        try:
            # Step 2: Source integrity check (source changes fail no substitution)
            verify_source_integrity(state["source_fingerprints"], cancellation_token=cancellation_token)

            # Step 3: Resolve settings and output directory
            cfg = settings or AppSettings.from_dict(state.get("settings_snapshot", {}))
            if output_dir is not None:
                resolved_output_dir = Path(output_dir).resolve()
                resolved_output_dir.mkdir(parents=True, exist_ok=True)
                state["output_dir"] = str(resolved_output_dir)
            else:
                resolved_output_dir = Path(state.get("output_dir", self.persistence.root / "outputs" / project_id)).resolve()
                resolved_output_dir.mkdir(parents=True, exist_ok=True)

            # Step 4: Check if final_json exists (Resume/import NEVER Gateway once Final JSON exists)
            final_json = state.get("final_json")
            if final_json is None and self.persistence.has_final_json(project_id):
                final_json = self.persistence.load_final_json(project_id)
                state["final_json"] = final_json

            if final_json is None:
                # Stage 1: Sub model (whole original videos -> text analysis)
                if cancellation_token:
                    cancellation_token.check_cancelled()

                sub_analysis = state.get("sub_analysis")
                if not sub_analysis and self.persistence.has_sub_analysis(project_id):
                    sub_analysis = self.persistence.load_sub_analysis(project_id)
                    state["sub_analysis"] = sub_analysis

                ordered_sources = [
                    Path(fp["path"]).resolve()
                    for fp in sorted(state["source_fingerprints"].values(), key=lambda x: natural_sort_key(x["basename"]))
                ]
                source_meta = [
                    {
                        "source_file": s["source_file"],
                        "duration_ms": s.get("duration_ms"),
                    }
                    for s in state.get("sources", [])
                ]
                if not source_meta:
                    source_meta = [{"source_file": p.name} for p in ordered_sources]

                if not sub_analysis:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    state["status"] = ProjectStatus.ANALYZING.value
                    state["timestamps"]["analyzing_started_at"] = now_iso
                    state["timestamps"]["updated_at"] = now_iso
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_status_change:
                        callbacks.on_status_change(ProjectStatus.ANALYZING.value)

                    try:
                        sub_result = self.gateway_client.submit_chat_analysis(
                            sources=ordered_sources,
                            prompt=state["prompt"],
                            model=cfg.gateway_sub_model,
                            source_metadata=source_meta,
                            reasoning_effort=cfg.gateway_sub_reasoning or None,
                            expect_json=False,
                            cancellation_token=cancellation_token,
                        )
                        sub_analysis = sub_result.raw_response
                    except CancelledError:
                        raise
                    except InvalidGatewayResponseError as e:
                        raw_sub = getattr(e, "raw_response", None)
                        if raw_sub:
                            self.persistence.save_raw_response(project_id, raw_sub)
                            state["raw_response"] = raw_sub
                        state["status"] = ProjectStatus.FAILED.value
                        state["error"] = str(e)
                        state["timestamps"]["failed_at"] = datetime.now(timezone.utc).isoformat()
                        self.persistence.save_project(state)
                        if callbacks and callbacks.on_error:
                            callbacks.on_error(e, raw_sub)
                        raise
                    except Exception as e:
                        state["status"] = ProjectStatus.FAILED.value
                        state["error"] = str(e)
                        state["timestamps"]["failed_at"] = datetime.now(timezone.utc).isoformat()
                        self.persistence.save_project(state)
                        if callbacks and callbacks.on_error:
                            callbacks.on_error(e, None)
                        raise

                    # PERSIST rawSub checkpoint BEFORE Prime!
                    self.persistence.save_sub_analysis(project_id, sub_analysis)
                    state["sub_analysis"] = sub_analysis
                    now_sub_iso = datetime.now(timezone.utc).isoformat()
                    state["timestamps"]["sub_analyzed_at"] = now_sub_iso
                    state["timestamps"]["updated_at"] = now_sub_iso
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_sub_analysis:
                        callbacks.on_sub_analysis(sub_analysis)

                # Stage 2: Prime model (text analysis + original prompt + schema -> Final JSON)
                if cancellation_token:
                    cancellation_token.check_cancelled()

                from toolrecap_v4.schemas.schema import get_project_schema
                technical_schema = get_project_schema()

                technical_metadata = {
                    "project_id": state["project_id"],
                    "sources": source_meta,
                }

                prime_prompt = (
                    f"Original User Prompt:\n{state['prompt']}\n\n"
                    f"Technical Metadata (Exact Source Files, Durations, Project ID):\n{json.dumps(technical_metadata, indent=2, ensure_ascii=False)}\n\n"
                    f"Video Analysis from Sub Stage:\n{sub_analysis}\n\n"
                    f"Technical Schema:\n{json.dumps(technical_schema, indent=2, ensure_ascii=False)}\n\n"
                    "Generate the final recap JSON matching the schema based on the video analysis and user prompt."
                )

                raw_response = None
                try:
                    prime_result = self.gateway_client.submit_text_chat(
                        prompt=prime_prompt,
                        model=cfg.gateway_prime_model,
                        reasoning_effort=cfg.gateway_prime_reasoning or None,
                        expect_json=True,
                        cancellation_token=cancellation_token,
                    )
                    raw_response = prime_result.raw_response
                    parsed_json = prime_result.parsed_json
                except CancelledError:
                    raise
                except InvalidGatewayResponseError as e:
                    raw_response = getattr(e, "raw_response", None)
                    if raw_response:
                        self.persistence.save_raw_response(project_id, raw_response)
                        state["raw_response"] = raw_response
                    state["status"] = ProjectStatus.FAILED.value
                    state["error"] = str(e)
                    state["timestamps"]["failed_at"] = datetime.now(timezone.utc).isoformat()
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_error:
                        callbacks.on_error(e, raw_response)
                    raise
                except Exception as e:
                    state["status"] = ProjectStatus.FAILED.value
                    state["error"] = str(e)
                    state["timestamps"]["failed_at"] = datetime.now(timezone.utc).isoformat()
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_error:
                        callbacks.on_error(e, None)
                    raise

                # Save raw response immediately!
                self.persistence.save_raw_response(project_id, raw_response)
                state["raw_response"] = raw_response
                if callbacks and callbacks.on_raw_response:
                    callbacks.on_raw_response(raw_response)

                # Validate parsed_json against actual probed source durations
                source_durations = {
                    s["source_file"]: s["duration_ms"]
                    for s in state.get("sources", [])
                }
                try:
                    validate_project(parsed_json, source_durations=source_durations, cancellation_token=cancellation_token)
                except Exception as e:
                    state["status"] = ProjectStatus.FAILED.value
                    state["error"] = f"Validation failed: {e}"
                    state["timestamps"]["failed_at"] = datetime.now(timezone.utc).isoformat()
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_error:
                        callbacks.on_error(e, raw_response)
                    raise

                # SAVE FINAL JSON TO DISK BEFORE ANY VOICE SYNTHESIS OR RENDERING!
                self.persistence.save_final_json(project_id, parsed_json)
                state["final_json"] = parsed_json
                state["status"] = ProjectStatus.ANALYZED.value
                now_iso = datetime.now(timezone.utc).isoformat()
                state["timestamps"]["analyzed_at"] = now_iso
                state["timestamps"]["updated_at"] = now_iso
                self.persistence.save_project(state)
                if callbacks and callbacks.on_final_json:
                    callbacks.on_final_json(parsed_json)
                if callbacks and callbacks.on_status_change:
                    callbacks.on_status_change(ProjectStatus.ANALYZED.value)

                final_json = parsed_json

            # Step 5: Check publication collision against ALL project sources (including unused)
            all_source_paths = [fp["path"] for fp in state["source_fingerprints"].values()]
            check_publication_collision(final_json.get("outputs", []), resolved_output_dir, all_source_paths)

            # Step 6: Render outputs sequentially
            if cancellation_token:
                cancellation_token.check_cancelled()

            state["status"] = ProjectStatus.RENDERING.value
            now_iso = datetime.now(timezone.utc).isoformat()
            state["timestamps"]["rendering_started_at"] = now_iso
            state["timestamps"]["updated_at"] = now_iso
            self.persistence.save_project(state)
            if callbacks and callbacks.on_status_change:
                callbacks.on_status_change(ProjectStatus.RENDERING.value)

            source_paths_mapping = {
                fp["basename"]: fp["path"]
                for fp in state["source_fingerprints"].values()
            }

            outputs_def = final_json.get("outputs", [])
            outputs_state = state.setdefault("outputs", {})

            for out_def in outputs_def:
                if cancellation_token:
                    cancellation_token.check_cancelled()

                render_id = out_def["render_id"]
                title = out_def["title"]

                # Compute current render fingerprint
                cur_fp = compute_output_fingerprint(out_def, state["source_fingerprints"], cfg)

                # Check existing checkpoint
                ckpt = None
                try:
                    ckpt = self.persistence.load_checkpoint(project_id, render_id)
                except Exception:
                    ckpt = outputs_state.get(render_id)

                # Validate completed output presence and hash before skip
                should_skip = False
                if ckpt and ckpt.get("status") in (OutputStatus.COMPLETED.value, OutputStatus.SKIPPED.value):
                    ckpt_fp = ckpt.get("fingerprint")
                    out_path_str = ckpt.get("output_path")
                    expected_hash = ckpt.get("output_file_hash")

                    if ckpt_fp == cur_fp and out_path_str and expected_hash:
                        out_path = Path(out_path_str)
                        if out_path.is_file():
                            actual_hash = compute_file_sha256(out_path)
                            if actual_hash == expected_hash:
                                should_skip = True

                if should_skip:
                    skip_ckpt = {
                        **ckpt,
                        "status": OutputStatus.SKIPPED.value,
                    }
                    self.persistence.save_checkpoint(project_id, render_id, skip_ckpt)
                    outputs_state[render_id] = skip_ckpt
                    state["timestamps"]["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_output_skipped:
                        callbacks.on_output_skipped(render_id, skip_ckpt)
                    continue

                # Render output
                if callbacks and callbacks.on_output_started:
                    callbacks.on_output_started(render_id)

                in_progress_ckpt = {
                    "render_id": render_id,
                    "title": title,
                    "status": OutputStatus.RENDERING.value,
                    "fingerprint": cur_fp,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                self.persistence.save_checkpoint(project_id, render_id, in_progress_ckpt)
                outputs_state[render_id] = in_progress_ckpt
                self.persistence.save_project(state)

                try:
                    render_res = render_output(
                        output_def=out_def,
                        source_paths=source_paths_mapping,
                        output_dir=resolved_output_dir,
                        settings=cfg,
                        voice_adapter=self.voice_adapter,
                        cancellation_token=cancellation_token,
                    )
                except CancelledError:
                    raise
                except Exception as e:
                    # Output failure stops queue preserves complete previous outputs!
                    fail_ckpt = {
                        "render_id": render_id,
                        "title": title,
                        "status": OutputStatus.FAILED.value,
                        "error": str(e),
                        "fingerprint": cur_fp,
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    }
                    self.persistence.save_checkpoint(project_id, render_id, fail_ckpt)
                    outputs_state[render_id] = fail_ckpt
                    state["status"] = ProjectStatus.FAILED.value
                    state["error"] = f"Output '{render_id}' failed: {e}"
                    state["timestamps"]["failed_at"] = datetime.now(timezone.utc).isoformat()
                    self.persistence.save_project(state)
                    if callbacks and callbacks.on_output_failed:
                        callbacks.on_output_failed(render_id, str(e))
                    raise

                # Render succeeded
                out_file_hash = compute_file_sha256(render_res.output_path)
                now_iso = datetime.now(timezone.utc).isoformat()
                completed_ckpt = {
                    "render_id": render_id,
                    "title": title,
                    "status": OutputStatus.COMPLETED.value,
                    "output_path": str(render_res.output_path),
                    "narration_srt_path": str(render_res.narration_srt_path),
                    "original_srt_path": str(render_res.original_srt_path),
                    "duration": render_res.duration,
                    "fingerprint": cur_fp,
                    "output_file_hash": out_file_hash,
                    "completed_at": now_iso,
                    "video_codec": render_res.video_codec,
                    "audio_codec": render_res.audio_codec,
                    "width": render_res.width,
                    "height": render_res.height,
                    "fps": render_res.fps,
                }
                self.persistence.save_checkpoint(project_id, render_id, completed_ckpt)
                outputs_state[render_id] = completed_ckpt
                state["timestamps"]["updated_at"] = now_iso
                self.persistence.save_project(state)
                if callbacks and callbacks.on_output_completed:
                    callbacks.on_output_completed(render_id, completed_ckpt)

            # All outputs complete!
            state["status"] = ProjectStatus.COMPLETED.value
            now_iso = datetime.now(timezone.utc).isoformat()
            state["timestamps"]["completed_at"] = now_iso
            state["timestamps"]["updated_at"] = now_iso
            self.persistence.save_project(state)
            if callbacks and callbacks.on_status_change:
                callbacks.on_status_change(ProjectStatus.COMPLETED.value)

            return state

        except CancelledError:
            state["status"] = ProjectStatus.CANCELLED.value
            now_iso = datetime.now(timezone.utc).isoformat()
            state.setdefault("timestamps", {})["cancelled_at"] = now_iso
            state.setdefault("timestamps", {})["updated_at"] = now_iso
            self.persistence.save_project(state)
            if callbacks and callbacks.on_status_change:
                callbacks.on_status_change(ProjectStatus.CANCELLED.value)
            raise
