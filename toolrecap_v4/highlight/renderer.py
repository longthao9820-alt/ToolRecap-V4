"""Direct original-audio Highlight renderer."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Mapping

from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.media import CommandResult, find_binary, run_command
from .models import HighlightOutput
from .subtitles import highlight_srt


@dataclass(frozen=True)
class HighlightRenderResult:
    output_id: str
    video_path: Path
    subtitle_path: Path
    video_sha256: str
    subtitle_sha256: str


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def render_highlight(
    output: HighlightOutput, *, sources: Mapping[str, Path | str], publication_dir: Path | str,
    ffmpeg_path: Path | str | None = None,
    command_runner: Callable[..., CommandResult] = run_command,
    cancellation_token: CancellationToken | None = None,
) -> HighlightRenderResult:
    """Publish exactly one MP4 and one relative-timestamp SRT.

    No narration, VoiceStudio, Narration Fit, tempo adjustment, or synthetic
    audio enters this path.  Video and original source audio are trimmed from
    one episode sequence at normal playback rate.
    """
    if not output.original_audio:
        raise ValueError("Highlight outputs must preserve original source audio")
    if output.source_file not in sources:
        raise ValueError(f"Missing Highlight source: {output.source_file}")
    source = Path(sources[output.source_file]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    target_dir = Path(publication_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    video = target_dir / f"{output.title}.mp4"
    subtitle = target_dir / f"{output.title}.srt"
    if source in (video.resolve(), subtitle.resolve()):
        raise ValueError("Highlight publication collides with its source")
    ffmpeg = find_binary("ffmpeg", ffmpeg_path)
    if cancellation_token:
        cancellation_token.check_cancelled()
    with tempfile.TemporaryDirectory(prefix="toolrecap_highlight_", dir=target_dir) as temp_name:
        temp = Path(temp_name)
        staged_video = temp / "highlight.mp4"
        staged_srt = temp / "highlight.srt"
        duration = (output.end_ms - output.start_ms) / 1000.0
        args = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{output.start_ms / 1000.0:.3f}", "-i", str(source),
            "-t", f"{duration:.3f}", "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero",
            str(staged_video),
        ]
        result = command_runner(args, timeout=max(120.0, duration * 4.0), cancellation_token=cancellation_token)
        if result.exit_code != 0 or not staged_video.is_file():
            raise RuntimeError(f"Highlight render failed: {result.stderr[-500:]}")
        staged_srt.write_text(highlight_srt(output), encoding="utf-8", newline="\n")
        if cancellation_token:
            cancellation_token.check_cancelled()
        os.replace(staged_video, video)
        os.replace(staged_srt, subtitle)
    return HighlightRenderResult(output.output_id, video, subtitle, _sha(video), _sha(subtitle))
