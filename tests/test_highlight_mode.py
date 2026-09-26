from pathlib import Path
import json

import pytest

from toolrecap_v4.gateway import GatewayResult
from toolrecap_v4.highlight.models import build_highlight_project
from toolrecap_v4.highlight.renderer import render_highlight
from toolrecap_v4.highlight.service import HighlightPlanner
from toolrecap_v4.highlight.subtitles import highlight_srt
from toolrecap_v4.media import (
    AudioStreamInfo, CommandResult, find_binary, probe_media, run_command,
    select_audio_for_source,
)
from toolrecap_v4.media import EncoderStatus
from toolrecap_v4.settings import AppSettings
from toolrecap_v4.analysis.models import AudioSelection, PreparedEpisode, Transcript, TranscriptCue
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


def test_direct_renderer_maps_only_selected_english_audio_and_publishes_mp4_srt(tmp_path: Path):
    source = tmp_path / "e01.mp4"; source.write_bytes(b"source")
    ffmpeg = tmp_path / "ffmpeg.exe"; ffmpeg.write_bytes(b"binary")
    project = build_highlight_project(project_id="p", prompt="x", dependency_revision="r", candidates=[candidate()], sources=SOURCES)
    commands = []
    def runner(args, **kwargs):
        commands.append(args); Path(args[-1]).write_bytes(b"rendered-original-audio")
        return CommandResult(0, "", "")
    result = render_highlight(
        project.outputs[0], sources={"e01.mp4": source},
        publication_dir=tmp_path / "publication", ffmpeg_path=ffmpeg,
        command_runner=runner, settings=AppSettings(use_gpu=False),
        source_audio_index=2, source_audio_language="eng",
    )
    assert result.video_path.is_file() and result.subtitle_path.is_file()
    command = commands[0]
    assert "0:2" in command and "0:a?" not in command
    assert command[command.index("-metadata:s:a:0") + 1] == "language=eng"
    assert "atempo" not in " ".join(command).lower()
    assert sorted(p.suffix for p in result.video_path.parent.iterdir()) == [".mp4", ".srt"]


def test_real_highlight_output_contains_only_english_from_multilingual_source(tmp_path: Path):
    ffmpeg = find_binary("ffmpeg")
    source = tmp_path / "multilingual.mp4"
    create = [
        str(ffmpeg), "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
        "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-metadata:s:a:0", "language=ukr", "-metadata:s:a:0", "title=Ukrainian Dub",
        "-metadata:s:a:1", "language=eng", "-metadata:s:a:1", "title=English Original",
        "-disposition:a:0", "default", "-disposition:a:1", "0", str(source),
    ]
    assert run_command(create, timeout=30).exit_code == 0
    source_probe = probe_media(source)
    selection = select_audio_for_source(source_probe)
    assert selection.selected_index == 2

    project = build_highlight_project(
        project_id="p", prompt="x", dependency_revision="r",
        candidates=[candidate(start_ms=0, end_ms=800, subtitle_cues=[])], sources=SOURCES,
    )
    result = render_highlight(
        project.outputs[0], sources={"e01.mp4": source}, publication_dir=tmp_path / "out",
        settings=AppSettings(use_gpu=False), source_audio_index=selection.selected_index,
        source_audio_language=selection.selected_stream.language,
    )

    output_probe = probe_media(result.video_path)
    assert len(output_probe.audio_streams) == 1
    assert output_probe.audio_streams[0].language == "eng"


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
        source_codec="hevc", source_pixel_format="yuv420p10le",
        source_audio_index=3, source_audio_language="eng",
    )
    args = commands[0]
    assert "hevc_cuvid" in args and "h264_nvenc" in args
    assert "scale_cuda=format=nv12" in args
    assert not any(args[index:index + 2] == ["-c:v", "copy"] for index in range(len(args) - 1))
    assert args[args.index("-ss") + 1] == "10.000"
    assert args[args.index("-t") + 1] == "10.000"
    assert "0:3" in args and "0:a?" not in args


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
    english_audio = AudioStreamInfo(
        2, "aac", 2, 48000, language="eng", title="English Original",
        disposition={"default": 0},
    )
    prepared = PreparedEpisode(
        "E01", "src_001", source, 60_000, 1920, 1080, source_fingerprint=fingerprint.sha256,
        audio_streams=(
            AudioStreamInfo(1, "aac", 2, 48000, language="ukr", title="Ukrainian Dub", disposition={"default": 1}),
            english_audio,
        ),
        audio_selection=AudioSelection(english_audio, global_index=2, audio_ordinal=1),
        selected_audio=english_audio, audio_ordinal=1,
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
    monkeypatch.setattr("toolrecap_v4.highlight.service.render_highlight", lambda *a, **k: (renders.append(k) or fake_render(*a, **k)))
    planner = Planner()
    workflow = HighlightWorkflow(persistence=persistence, gateway_client=FakeGateway(), planner=planner)
    first = workflow.run("highlight-project", settings=settings)
    second = workflow.run("highlight-project", settings=settings)
    assert first["project_mode"] == second["project_mode"] == "HIGHLIGHT"
    assert planner.calls == 1 and len(renders) == 1
    assert renders[0]["source_audio_index"] == 2
    assert renders[0]["source_audio_language"] == "eng"
    assert second["outputs"]["hl_001"]["audio_selection_version"] == "highlight-audio-selection-v1"
