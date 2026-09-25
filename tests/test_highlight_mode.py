from pathlib import Path
import json

import pytest

from toolrecap_v4.gateway import GatewayResult
from toolrecap_v4.highlight.models import build_highlight_project
from toolrecap_v4.highlight.renderer import render_highlight
from toolrecap_v4.highlight.service import HighlightPlanner
from toolrecap_v4.highlight.subtitles import highlight_srt
from toolrecap_v4.media import CommandResult
from toolrecap_v4.media import EncoderStatus
from toolrecap_v4.settings import AppSettings
from toolrecap_v4.analysis.models import PreparedEpisode, Transcript, TranscriptCue
from toolrecap_v4.discovery import compute_file_fingerprint
from toolrecap_v4.highlight.renderer import HighlightRenderResult
from toolrecap_v4.highlight.service import HighlightWorkflow
from toolrecap_v4.persistence import ProjectPersistence


SOURCES = [
    {"episode_id": "E01", "source_id": "src_001", "source_file": "e01.mp4", "duration_ms": 60_000},
    {"episode_id": "E02", "source_id": "src_002", "source_file": "e02.mp4", "duration_ms": 70_000},
]


def candidate(**changes):
    value = {
        "title": "Beth challenges the board", "episode_id": "E01", "source_id": "src_001",
        "source_file": "e01.mp4", "start_ms": 10_000, "end_ms": 20_000,
        "evidence_ids": ["E01-EV-001"], "subtitle_cues": [
            {"start_ms": 12_250, "end_ms": 13_500, "text": "You heard me.", "verified": True}
        ],
    }
    value.update(changes)
    return value


def test_contract_app_ids_relative_srt_visual_only_and_no_recap_fields():
    project = build_highlight_project(
        project_id="highlight-season", prompt="exhaustive", dependency_revision="rev",
        candidates=[candidate(), candidate(title="A quiet decision", start_ms=30_000, end_ms=35_000, subtitle_cues=[])],
        sources=SOURCES,
    )
    assert project.project_mode == "HIGHLIGHT"
    assert [item.output_id for item in project.outputs] == ["hl_001", "hl_002"]
    assert "00:00:02,250 --> 00:00:03,500" in highlight_srt(project.outputs[0])
    assert highlight_srt(project.outputs[1]) == ""
    encoded = json.dumps(project.to_dict()).lower()
    assert all(word not in encoded for word in ("narration", "voicestudio", "commentary_reading_speed", "narration_fit"))


@pytest.mark.parametrize("changes", [
    {"start_ms": -1}, {"end_ms": 10_000}, {"end_ms": 60_001},
    {"source_id": "wrong"}, {"episode_id": "E99"},
])
def test_strict_timestamp_and_identity_validation(changes):
    with pytest.raises(ValueError):
        build_highlight_project(
            project_id="p", prompt="x", dependency_revision="r",
            candidates=[candidate(**changes)], sources=SOURCES,
        )


def test_no_cross_episode_montage_and_no_generic_title():
    with pytest.raises(ValueError):
        build_highlight_project(project_id="p", prompt="x", dependency_revision="r", candidates=[candidate(title="Highlight 1")], sources=SOURCES)
    with pytest.raises(ValueError):
        build_highlight_project(
            project_id="p", prompt="x", dependency_revision="r",
            candidates=[candidate(episode_id="E02", source_id="src_001")], sources=SOURCES,
        )


class FakeGateway:
    def __init__(self): self.calls = []
    def submit_text_chat(self, **kwargs):
        self.calls.append(kwargs)
        phase = kwargs["phase"]
        if phase == "highlight_episode":
            payload = json.loads(kwargs["prompt"]); source = payload["source"]
            rows = [{"title": f"A worthwhile {source['episode_id']} guest moment", **source, "start_ms": 1000, "end_ms": 2000, "evidence_ids": []}]
        else:
            payload = json.loads(kwargs["prompt"]); rows = payload["episode_candidates"]
        return GatewayResult(json.dumps({"candidates": rows}))


def test_episode_then_season_coverage_has_no_quota_and_secondary_characters():
    gateway = FakeGateway(); planner = HighlightPlanner(gateway, "model")
    rows = planner.plan(editorial_prompt="include secondary and guest characters", sources=SOURCES, evidence_by_episode={})
    assert len(rows) == 2
    assert [call["phase"] for call in gateway.calls] == ["highlight_episode", "highlight_episode", "highlight_season_coverage"]
    assert all("guest moment" in row["title"] for row in rows)


def test_direct_renderer_preserves_original_audio_and_publishes_mp4_srt(tmp_path: Path):
    source = tmp_path / "e01.mp4"; source.write_bytes(b"source")
    ffmpeg = tmp_path / "ffmpeg.exe"; ffmpeg.write_bytes(b"binary")
    project = build_highlight_project(project_id="p", prompt="x", dependency_revision="r", candidates=[candidate()], sources=SOURCES)
    commands = []
    def runner(args, **kwargs):
        commands.append(args); Path(args[-1]).write_bytes(b"rendered-original-audio")
        return CommandResult(0, "", "")
    result = render_highlight(project.outputs[0], sources={"e01.mp4": source}, publication_dir=tmp_path / "publication", ffmpeg_path=ffmpeg, command_runner=runner, settings=AppSettings(use_gpu=False))
    assert result.video_path.is_file() and result.subtitle_path.is_file()
    command = commands[0]
    assert "0:a?" in command and "atempo" not in " ".join(command).lower()
    assert sorted(p.suffix for p in result.video_path.parent.iterdir()) == [".mp4", ".srt"]


def test_highlight_prompt_is_separate_and_speed_is_irrelevant():
    settings = AppSettings(prompt="recap", highlight_prompt="highlight", commentary_reading_speed=1.30)
    assert settings.prompt == "recap" and settings.highlight_prompt == "highlight"
    project = build_highlight_project(project_id="p", prompt=settings.highlight_prompt, dependency_revision="r", candidates=[candidate()], sources=SOURCES)
    assert "commentary_reading_speed" not in json.dumps(project.to_dict())


def test_highlight_nvidia_command_uses_cuvid_nvenc_no_copy_and_exact_bounds(tmp_path: Path):
    source = tmp_path / "e01.mp4"; source.write_bytes(b"source")
    ffmpeg = tmp_path / "ffmpeg.exe"; ffmpeg.write_bytes(b"binary")
    project = build_highlight_project(
        project_id="p", prompt="x", dependency_revision="r", candidates=[candidate()], sources=SOURCES,
    )
    commands = []
    def runner(args, **_kwargs):
        commands.append(args); Path(args[-1]).write_bytes(b"video")
        return CommandResult(0, "", "")
    render_highlight(
        project.outputs[0], sources={"e01.mp4": source}, publication_dir=tmp_path / "gpu",
        ffmpeg_path=ffmpeg, command_runner=runner, settings=AppSettings(use_gpu=True),
        encoder_status=EncoderStatus(True, "RTX 3060", "h264_nvenc", "NVIDIA NVENC"),
        source_codec="h264",
    )
    args = commands[0]
    assert "h264_cuvid" in args and "h264_nvenc" in args
    assert not any(args[index:index + 2] == ["-c:v", "copy"] for index in range(len(args) - 1))
    assert args[args.index("-ss") + 1] == "10.000"
    assert args[args.index("-t") + 1] == "10.000"
    assert "0:a?" in args


def test_highlight_resume_reuses_plan_and_completed_publication(tmp_path: Path, monkeypatch):
    source = tmp_path / "e01.mp4"; source.write_bytes(b"source-video")
    fingerprint = compute_file_fingerprint(source)
    persistence = ProjectPersistence(tmp_path)
    settings = AppSettings(scanner_model="scanner", finalizer_model="finalizer", highlight_prompt="find scenes")
    state = {
        "project_id": "highlight-project", "project_name": "Season", "project_mode": "HIGHLIGHT",
        "status": "created", "prompt": "find scenes", "output_dir": str(tmp_path / "publication"),
        "sources": [{"episode_id": "E01", "source_id": "src_001", "source_file": source.name,
                     "duration_ms": 60_000, "fingerprint": fingerprint.to_dict()}],
        "source_fingerprints": {source.name: fingerprint.to_dict()}, "settings_snapshot": settings.to_dict(),
        "outputs": {}, "timestamps": {},
    }
    persistence.save_project(state)
    prepared = PreparedEpisode(
        "E01", "src_001", source, 60_000, 1920, 1080, source_fingerprint=fingerprint.sha256,
        transcript=Transcript(episode_id="E01", source_type="sidecar", source_format="srt",
                              cues=(TranscriptCue("c1", 12_250, 13_500, "You heard me."),)),
    )
    persistence.save_prepared_episode("highlight-project", "E01", prepared.to_dict())

    class Scanner:
        def __init__(self, *args, **kwargs): pass
        def scan_project(self, *args, **kwargs): return type("Scan", (), {"evidence_revision": "ev-rev"})()
    class Store:
        def __init__(self, *args, **kwargs): pass
        def get_episode(self, *args, **kwargs): return type("Result", (), {"items": ()})()
    class Planner:
        def __init__(self): self.calls = 0
        def plan(self, **kwargs):
            self.calls += 1
            return [candidate(subtitle_cues=[])]
    renders = []
    def fake_render(output, **kwargs):
        folder = Path(kwargs["publication_dir"]); folder.mkdir(parents=True, exist_ok=True)
        video, subtitle = folder / f"{output.title}.mp4", folder / f"{output.title}.srt"
        video.write_bytes(b"video"); subtitle.write_bytes(b"srt")
        import hashlib
        return HighlightRenderResult(output.output_id, video, subtitle, hashlib.sha256(b"video").hexdigest(), hashlib.sha256(b"srt").hexdigest())
    monkeypatch.setattr("toolrecap_v4.highlight.service.ScannerService", Scanner)
    monkeypatch.setattr("toolrecap_v4.highlight.service.EvidenceStore", Store)
    monkeypatch.setattr("toolrecap_v4.highlight.service.render_highlight", lambda *a, **k: (renders.append(1) or fake_render(*a, **k)))
    planner = Planner()
    workflow = HighlightWorkflow(persistence=persistence, gateway_client=FakeGateway(), planner=planner)
    first = workflow.run("highlight-project", settings=settings)
    second = workflow.run("highlight-project", settings=settings)
    assert first["project_mode"] == second["project_mode"] == "HIGHLIGHT"
    assert planner.calls == 1 and len(renders) == 1
