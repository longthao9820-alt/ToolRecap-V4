"""Checkpointed Highlight analysis and publication workflow."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from toolrecap_v4.analysis.cache import AnalysisCacheManager
from toolrecap_v4.analysis.evidence_store import EvidenceStore
from toolrecap_v4.analysis.scanner import ScannerChunkPolicy, ScannerConfig, ScannerService
from toolrecap_v4.analysis.source_prep.pipeline import SourcePreparationPipeline
from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.gateway import GatewayClient
from toolrecap_v4.media import probe_media
from toolrecap_v4.output_paths import derive_working_folder, ensure_publication_root, resolve_publication_root
from toolrecap_v4.persistence import ProjectPersistence, atomic_write_json
from toolrecap_v4.settings import AppSettings, SettingsManager
from toolrecap_v4.workflow import ProjectStatus, resolve_sources, verify_source_integrity
from .models import HighlightProject, build_highlight_project, highlight_dependency_digest
from .renderer import render_highlight

HIGHLIGHT_PLAN_VERSION = "highlight-plan-v1"
HIGHLIGHT_SYSTEM_PROMPT = """You select worthwhile, naturally continuous original scenes for Highlight Mode.
The editorial prompt controls what to find, but this protocol controls the response.
Return only JSON: {"candidates":[{"title":str,"episode_id":str,"source_id":str,
"source_file":str,"start_ms":int,"end_ms":int,"evidence_ids":[str]}]}.
There is no quota. Include every worthwhile scene, including secondary, recurring, and guest-character moments.
Every candidate must stay inside one episode. Never invent dialogue or timestamps."""


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _parse_response(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"candidates"} or not isinstance(value["candidates"], list):
        raise ValueError("Highlight response must contain exactly one candidates array")
    return [dict(item) for item in value["candidates"] if isinstance(item, dict)]


class HighlightPlanner:
    """Episode-first selection followed by a complete-season coverage review."""

    def __init__(self, gateway: GatewayClient, model: str, reasoning: str = "") -> None:
        self.gateway, self.model, self.reasoning = gateway, model, reasoning

    def _request(self, prompt: str, phase: str, token: CancellationToken | None) -> list[dict[str, Any]]:
        result = self.gateway.submit_text_chat(
            prompt=prompt, system_prompt=HIGHLIGHT_SYSTEM_PROMPT, model=self.model,
            reasoning_effort=self.reasoning or None, stream=True, expect_json=False,
            cancellation_token=token, phase=phase,
        )
        return _parse_response(result.raw_response)

    def plan(
        self, *, editorial_prompt: str, sources: Sequence[Mapping[str, Any]],
        evidence_by_episode: Mapping[str, Sequence[Mapping[str, Any]]],
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict[str, Any]]:
        episode_candidates: list[dict[str, Any]] = []
        for source in sources:
            if cancellation_token:
                cancellation_token.check_cancelled()
            episode_id = str(source["episode_id"])
            payload = {
                "pass": "EPISODE_HIGHLIGHT_ANALYSIS", "editorial_prompt": editorial_prompt,
                "source": dict(source), "factual_evidence": list(evidence_by_episode.get(episode_id, ())),
            }
            found = self._request(json.dumps(payload, ensure_ascii=False), "highlight_episode", cancellation_token)
            if any(str(item.get("episode_id")) != episode_id for item in found):
                raise ValueError("Episode Highlight Analysis returned a different episode identity")
            episode_candidates.extend(found)
        if len(sources) == 1:
            return episode_candidates
        coverage = {
            "pass": "COMPLETE_SEASON_COVERAGE_REVIEW", "editorial_prompt": editorial_prompt,
            "sources": [dict(item) for item in sources], "episode_candidates": episode_candidates,
            "instruction": ("Review exhaustive season coverage for overlooked secondary/recurring/guest characters, "
                            "subplots, relationships, setup/payoff, conflicts, and callbacks. Return the complete final "
                            "candidate list. Each output must remain one continuous sequence from one episode."),
        }
        return self._request(json.dumps(coverage, ensure_ascii=False), "highlight_season_coverage", cancellation_token)


class HighlightWorkflow:
    """Distinct Highlight path reusing Source Preparation, Scanner, and Evidence."""

    def __init__(
        self, *, persistence: ProjectPersistence, gateway_client: GatewayClient,
        settings_manager: SettingsManager | None = None,
        source_pipeline: SourcePreparationPipeline | None = None,
        planner: HighlightPlanner | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.persistence = persistence
        self.gateway = gateway_client
        self.settings_manager = settings_manager or SettingsManager(persistence=persistence)
        self.source_pipeline = source_pipeline or SourcePreparationPipeline(
            cache_manager=AnalysisCacheManager(persistence.root / "cache" / "analysis")
        )
        self.planner = planner
        self.progress_callback = progress_callback

    def _emit(self, stage: str, text: str, completed: int | None = None, total: int | None = None) -> None:
        if self.progress_callback:
            self.progress_callback({
                "state": "RUNNING", "active": True, "stage": stage, "stage_label": stage,
                "pipeline_mode": "HIGHLIGHT",
                "activity_text": text, "completed": completed, "total": total,
                "percent": (completed * 100.0 / total if completed is not None and total else None),
            })

    def create_project(
        self, *, project_id: str, project_name: str, source_input: Any, prompt: str,
        settings: AppSettings, output_dir: str | Path | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        fps = resolve_sources(source_input, cancellation_token)
        working = derive_working_folder(source_input)
        publication = resolve_publication_root(manual_output_dir=str(output_dir or settings.output_dir or ""), working_folder=working)
        sources = []
        for index, fp in enumerate(fps, 1):
            duration_ms = int(round(probe_media(fp.path, cancellation_token=cancellation_token).duration * 1000))
            sources.append({
                "episode_id": f"E{index:02d}", "source_id": f"src_{index:03d}",
                "source_file": fp.basename, "duration_ms": duration_ms, "fingerprint": fp.to_dict(),
            })
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "schema_version": "4.0", "project_id": project_id, "project_name": project_name,
            "project_mode": "HIGHLIGHT", "status": ProjectStatus.CREATED.value,
            "prompt": prompt, "output_dir": str(publication), "manual_output_dir": str(output_dir or settings.output_dir or ""),
            "working_folder": str(working), "sources": sources,
            "source_fingerprints": {item["source_file"]: item["fingerprint"] for item in sources},
            "settings_snapshot": settings.to_dict(), "outputs": {}, "timestamps": {"created_at": now, "updated_at": now},
        }
        self.persistence.save_project(state)
        return state

    def run(
        self, project_id: str, *, settings: AppSettings | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        state = self.persistence.load_project(project_id)
        if state.get("project_mode") != "HIGHLIGHT":
            raise ValueError("Refusing to interpret a Recap project as Highlight")
        cfg = settings or AppSettings.from_dict(state["settings_snapshot"])
        verify_source_integrity(state["source_fingerprints"], cancellation_token)
        prepared = []
        total = len(state["sources"])
        for index, source in enumerate(state["sources"], 1):
            self._emit("Preparing Sources", f"Preparing {source['episode_id']}", index - 1, total)
            cached = self.persistence.load_prepared_episode(project_id, source["episode_id"]) if self.persistence.has_prepared_episode(project_id, source["episode_id"]) else None
            if cached:
                from toolrecap_v4.analysis.models import PreparedEpisode
                episode = PreparedEpisode.from_dict(cached)
            else:
                episode = self.source_pipeline.prepare_episode(
                    source["fingerprint"]["path"], source["episode_id"], source["source_id"],
                    source_fingerprint=source["fingerprint"].get("sha256"), cancellation_token=cancellation_token,
                )
                self.persistence.save_prepared_episode(project_id, source["episode_id"], episode.to_dict())
            prepared.append(episode)
        scanner = ScannerService(
            self.gateway, self.persistence.root,
            ScannerConfig(cfg.scanner_model, cfg.scanner_reasoning, cfg.scanner_parallelism,
                          ScannerChunkPolicy(cfg.scanner_chunk_duration_ms, cfg.scanner_max_request_bytes),
                          cfg.scanner_repair_attempts),
            progress_callback=lambda payload: self._emit("Scanning Evidence", payload.get("activity_text", "Scanning"), payload.get("completed"), payload.get("total")),
        )
        scan = scanner.scan_project(project_id, prepared, cancellation_token=cancellation_token)
        self.persistence.save_checkpoint(project_id, "evidence", {
            "status": "completed", "evidence_revision": scan.evidence_revision,
            "episode_count": len(prepared), "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        state["status"] = ProjectStatus.EVIDENCE_READY.value
        self.persistence.save_project(state)
        store = EvidenceStore(self.persistence.root, project_id)
        evidence_by_episode = {
            episode.episode_id: [item.to_dict() for item in store.get_episode(episode.episode_id, scan.evidence_revision).items]
            for episode in prepared
        }
        dep = highlight_dependency_digest(HIGHLIGHT_PLAN_VERSION, state["prompt"], scan.evidence_revision, state["sources"], cfg.finalizer_model)
        checkpoint_path = self.persistence._checkpoint_path(project_id, "highlight_final")
        project: HighlightProject | None = None
        if checkpoint_path.is_file():
            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if saved.get("dependency_revision") == dep and saved.get("status") == "COMPLETE":
                candidates = saved["candidates"]
                project = build_highlight_project(project_id=project_id, prompt=state["prompt"], dependency_revision=dep, candidates=candidates, sources=state["sources"])
        if project is None:
            planner = self.planner or HighlightPlanner(self.gateway, cfg.finalizer_model or cfg.planner_model, cfg.finalizer_reasoning or cfg.planner_reasoning)
            self._emit("Building Highlight Coverage", "Analyzing episodes and complete-season coverage")
            candidates = planner.plan(editorial_prompt=state["prompt"], sources=state["sources"], evidence_by_episode=evidence_by_episode, cancellation_token=cancellation_token)
            transcripts = {episode.episode_id: episode.transcript for episode in prepared}
            for candidate in candidates:
                transcript = transcripts.get(str(candidate.get("episode_id")))
                start, end = int(candidate.get("start_ms", -1)), int(candidate.get("end_ms", -1))
                candidate["subtitle_cues"] = [
                    {"start_ms": cue.start_ms, "end_ms": cue.end_ms, "text": cue.text, "verified": True}
                    for cue in (transcript.cues if transcript else ()) if cue.start_ms >= start and cue.end_ms <= end and cue.text.strip()
                ]
            project = build_highlight_project(project_id=project_id, prompt=state["prompt"], dependency_revision=dep, candidates=candidates, sources=state["sources"])
            atomic_write_json(checkpoint_path, {"status": "COMPLETE", "dependency_revision": dep, "candidates": [item.to_dict() for item in project.outputs]})
        publication = ensure_publication_root(state["output_dir"])
        state["highlight_json"] = project.to_dict()
        state["status"] = ProjectStatus.RENDERING.value
        self.persistence.save_project(state)
        source_paths = {item["source_file"]: item["fingerprint"]["path"] for item in state["sources"]}
        for index, output in enumerate(project.outputs, 1):
            self._emit("Rendering Highlights", output.output_id, index - 1, len(project.outputs))
            existing = state["outputs"].get(output.output_id, {})
            video_path = Path(existing.get("video_path", ""))
            subtitle_path = Path(existing.get("subtitle_path", ""))
            if (
                existing.get("status") == "completed" and video_path.is_file() and subtitle_path.is_file()
                and _file_sha(video_path) == existing.get("video_sha256")
                and _file_sha(subtitle_path) == existing.get("subtitle_sha256")
            ):
                continue
            result = render_highlight(output, sources=source_paths, publication_dir=publication, cancellation_token=cancellation_token)
            state["outputs"][output.output_id] = {
                "status": "completed", "video_path": str(result.video_path), "subtitle_path": str(result.subtitle_path),
                "video_sha256": result.video_sha256, "subtitle_sha256": result.subtitle_sha256,
            }
            self.persistence.save_project(state)
        state["status"] = ProjectStatus.COMPLETED.value
        state["timestamps"]["updated_at"] = state["timestamps"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.persistence.save_project(state)
        self._emit("Publishing", "Highlight publication complete", len(project.outputs), len(project.outputs))
        return state
