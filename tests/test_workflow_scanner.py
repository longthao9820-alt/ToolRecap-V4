from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from toolrecap_v4.analysis.models import PreparedEpisode, Transcript, TranscriptCue
from toolrecap_v4.analysis.scanner import ScannerChunkPolicy, ScannerConfig, ScannerService
from toolrecap_v4.analysis.finalizer import PlannerDraft, PlannerRunResult
from toolrecap_v4.discovery import compute_file_fingerprint
from toolrecap_v4.errors import AnalysisPipelineUnavailableError
from toolrecap_v4.gateway import GatewayResult
from toolrecap_v4.persistence import ProjectPersistence
from toolrecap_v4.settings import AppSettings
from toolrecap_v4.workflow import ProjectStatus, ProjectWorkflow


class Pipeline:
    def __init__(self, episode: PreparedEpisode):
        self.episode = episode
        self.calls = 0

    def prepare_episode(self, **kwargs):
        self.calls += 1
        return self.episode


class Gateway:
    def __init__(self):
        self.calls = []

    def submit_text_chat(self, **kwargs):
        self.calls.append(kwargs)
        request = json.loads(kwargs["prompt"])
        part = request["transcript_parts"][0]
        raw = json.dumps({
            "episode_id": request["episode_id"], "source_id": request["source_id"], "chunk_id": request["chunk_id"],
            "observations": [{
                "start_ms": part["start_ms"], "end_ms": part["end_ms"], "category": "event",
                "observation": "The speaker greets someone.",
                "cue_refs": [{"cue_id": part["cue_id"], "part_index": part["part_index"]}],
                "entities": [], "modality": "subtitle", "confidence": None, "uncertainty": [],
            }],
        })
        return GatewayResult(raw_response=raw, bytes_sent=1234, metadata={"status_code": 200, "duration_ms": 2})


def test_workflow_reaches_catalog_ready_and_stops_before_phase6(tmp_path):
    source = tmp_path / "episode01.mkv"
    source.write_bytes(b"synthetic source")
    fingerprint = compute_file_fingerprint(source)
    prepared = PreparedEpisode(
        episode_id="E01", source_id="src_001", source_path=source, source_basename=source.name,
        source_fingerprint=fingerprint.sha256, duration_ms=10_000, canvas_width=1920, canvas_height=1080,
        transcript=Transcript(
            episode_id="E01", source_type="sidecar", source_format="srt",
            cues=(TranscriptCue("E01-CUE-001", 1000, 3000, "Hello there."),),
            provenance_hash="transcript-hash",
        ), artifact_hash="prepared-hash",
    )
    persistence = ProjectPersistence(storage_root=tmp_path / "storage")
    state = {
        "schema_version": "3.0", "project_id": "project-1", "project_name": "Project",
        "status": ProjectStatus.CREATED.value, "output_dir": str(tmp_path / "out"),
        "sources": [{"source_file": source.name, "fingerprint": fingerprint.to_dict(), "duration_ms": 10_000}],
        "source_fingerprints": {source.name: fingerprint.to_dict()},
        "prompt": "THIS CREATIVE PROMPT MUST NEVER ENTER SCANNER", "prompt_hash": "x",
        "gateway_identifier": "local", "settings_snapshot": AppSettings().to_dict(),
        "voice_endpoint": "", "timestamps": {}, "final_json": None,
        "prepared_episodes": {}, "outputs": {}, "error": None,
    }
    persistence.save_project(state)
    gateway = Gateway()
    scanner = ScannerService(
        gateway, persistence.root,
        ScannerConfig("model-id", chunk_policy=ScannerChunkPolicy(30_000, 5000)),
    )
    workflow = ProjectWorkflow(
        persistence=persistence, gateway_client=gateway,
        source_preparation_pipeline=Pipeline(prepared), scanner_service=scanner,
    )
    with pytest.raises(AnalysisPipelineUnavailableError, match="Phase 6"):
        workflow.start_project("project-1")
    saved = persistence.load_project("project-1")
    assert saved["status"] == ProjectStatus.CATALOG_READY.value
    assert saved["evidence"]["total_evidence_count"] == 1
    assert saved["catalog"]["evidence_count"] == 1
    assert saved["catalog"]["episode_count"] == 1
    assert saved["catalog"]["capacity"]["status"] == "UNKNOWN"
    assert persistence.load_checkpoint("project-1", "evidence")["status"] == "completed"
    assert persistence.load_checkpoint("project-1", "catalog")["status"] == "completed"
    assert all("THIS CREATIVE PROMPT" not in call["prompt"] for call in gateway.calls)
    assert all(call["phase"] == "scanner" and "images" not in call for call in gateway.calls)
    gateway_call_count = len(gateway.calls)
    with pytest.raises(AnalysisPipelineUnavailableError, match="Phase 6"):
        workflow.resume_project("project-1")
    resumed = persistence.load_project("project-1")
    assert resumed["status"] == ProjectStatus.CATALOG_READY.value
    assert resumed["catalog"]["reused"] is True
    assert len(gateway.calls) == gateway_call_count

    class PlannerStub:
        def __init__(self):
            self.calls = []

        def run(self, **kwargs):
            self.calls.append(kwargs)
            draft_path = tmp_path / "storage" / "projects" / "project-1" / "planning" / "stub" / "planner_draft.json"
            return PlannerRunResult(
                project_id="project-1", session_id="planner-stub", dependency_digest="dep",
                draft=PlannerDraft("planner-draft-v1", "Rationale", 0, (), ()),
                round_count=1, request_measurements=(), reused=False, draft_path=draft_path,
            )

    planner = PlannerStub()
    workflow.planner_service = planner
    workflow.visual_service = SimpleNamespace(run=lambda **kwargs: SimpleNamespace(visual_revision="vis-stub", evidence=(), completeness={"complete": True, "failed": 0, "canceled": 0}))
    workflow.season_plan_service = SimpleNamespace(run=lambda **kwargs: SimpleNamespace(plan=SimpleNamespace(plan_hash="plan-hash", outputs=()), path=tmp_path / "season_plan.json", reused=False))
    with pytest.raises(AnalysisPipelineUnavailableError, match="Phase 8"):
        workflow.resume_project("project-1")
    planned = persistence.load_project("project-1")
    assert planned["status"] == ProjectStatus.SEASON_PLAN_READY.value
    assert planned["planner_draft"]["proposed_output_count"] == 0
    assert planned["season_plan"]["plan_hash"] == "plan-hash"
    assert planner.calls[0]["raw_recap_prompt"] == "THIS CREATIVE PROMPT MUST NEVER ENTER SCANNER"
    assert planner.calls[0]["catalog"].catalog_hash == planned["catalog"]["catalog_hash"]
    workflow.writer_service = SimpleNamespace(run=lambda **kwargs: SimpleNamespace(artifacts=(), reused_count=0, requested_count=0))
    with pytest.raises(AnalysisPipelineUnavailableError, match="Phase 9"):
        workflow.resume_project("project-1")
    written = persistence.load_project("project-1")
    assert written["status"] == ProjectStatus.WRITER_DRAFTS_READY.value
    assert written["writer_drafts"]["expected_output_count"] == 0
