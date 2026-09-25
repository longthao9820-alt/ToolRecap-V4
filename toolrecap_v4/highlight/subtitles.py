"""Verified original-dialogue SRT creation for Highlight Mode."""
from __future__ import annotations

from .models import HighlightOutput


def _stamp(ms: int) -> str:
    hours, remain = divmod(ms, 3_600_000)
    minutes, remain = divmod(remain, 60_000)
    seconds, millis = divmod(remain, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def highlight_srt(output: HighlightOutput) -> str:
    """Convert verified source-global cue timestamps to highlight-relative SRT."""
    rows: list[str] = []
    for index, cue in enumerate(output.subtitle_cues, 1):
        start = cue.start_ms - output.start_ms
        end = cue.end_ms - output.start_ms
        if start < 0 or end <= start or end > output.end_ms - output.start_ms:
            raise ValueError("Subtitle cue falls outside Highlight bounds")
        rows.extend((str(index), f"{_stamp(start)} --> {_stamp(end)}", cue.text.strip(), ""))
    return "\n".join(rows)
