"""Canonical, versioned Highlight output contract and strict validation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

HIGHLIGHT_SCHEMA_VERSION = "highlight-v1"
GENERIC_TITLES = {"highlight", "highlight 1", "best scene", "episode clip", "scene"}
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class HighlightSubtitleCue:
    start_ms: int
    end_ms: int
    text: str
    verified: bool = True

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HighlightSubtitleCue":
        return cls(int(value["start_ms"]), int(value["end_ms"]), str(value["text"]), bool(value.get("verified", True)))

    def to_dict(self) -> dict[str, Any]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms, "text": self.text, "verified": self.verified}


@dataclass(frozen=True)
class HighlightOutput:
    output_id: str
    title: str
    episode_id: str
    source_id: str
    source_file: str
    start_ms: int
    end_ms: int
    original_audio: bool
    subtitle_cues: tuple[HighlightSubtitleCue, ...]
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id, "title": self.title, "episode_id": self.episode_id,
            "source_id": self.source_id, "source_file": self.source_file,
            "start_ms": self.start_ms, "end_ms": self.end_ms, "original_audio": self.original_audio,
            "subtitle_cues": [cue.to_dict() for cue in self.subtitle_cues],
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class HighlightProject:
    schema_version: str
    project_id: str
    project_mode: str
    prompt_hash: str
    dependency_revision: str
    outputs: tuple[HighlightOutput, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "project_id": self.project_id,
            "project_mode": self.project_mode, "prompt_hash": self.prompt_hash,
            "dependency_revision": self.dependency_revision,
            "outputs": [item.to_dict() for item in self.outputs],
        }


def sanitize_highlight_title(value: str) -> str:
    title = _FORBIDDEN.sub("-", value).strip(" .")
    title = re.sub(r"\s+", " ", title)
    if not title or title.casefold() in GENERIC_TITLES or re.fullmatch(r"scene\s*\d+", title, re.I):
        raise ValueError("Highlight title must be publication-ready and non-generic")
    return title[:120].rstrip(" .")


def _source_map(sources: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for source in sources:
        episode_id = str(source.get("episode_id", ""))
        if not episode_id or episode_id in result:
            raise ValueError("Highlight sources require unique episode_id values")
        result[episode_id] = source
    return result


def build_highlight_project(
    *, project_id: str, prompt: str, dependency_revision: str,
    candidates: Sequence[Mapping[str, Any]], sources: Sequence[Mapping[str, Any]],
) -> HighlightProject:
    """Validate AI-selected order, then assign deterministic app-owned IDs."""
    known = _source_map(sources)
    outputs: list[HighlightOutput] = []
    for index, candidate in enumerate(candidates, 1):
        episode_id = str(candidate.get("episode_id", ""))
        if episode_id not in known:
            raise ValueError(f"Unknown Highlight episode identity: {episode_id}")
        source = known[episode_id]
        source_id = str(candidate.get("source_id", ""))
        source_file = str(candidate.get("source_file", ""))
        if source_id != str(source.get("source_id")) or source_file != str(source.get("source_file")):
            raise ValueError(f"Wrong source identity for Highlight episode {episode_id}")
        start_ms, end_ms = int(candidate.get("start_ms", -1)), int(candidate.get("end_ms", -1))
        duration_ms = int(source.get("duration_ms", 0))
        if start_ms < 0 or end_ms <= start_ms or end_ms > duration_ms:
            raise ValueError(f"Invalid Highlight timestamps for {episode_id}: {start_ms}..{end_ms}")
        cues: list[HighlightSubtitleCue] = []
        for raw in candidate.get("subtitle_cues", []):
            cue = HighlightSubtitleCue.from_dict(raw)
            if not cue.verified or not cue.text.strip():
                raise ValueError("Highlight SRT may contain verified original dialogue only")
            if cue.start_ms < start_ms or cue.end_ms > end_ms or cue.end_ms <= cue.start_ms:
                raise ValueError("Highlight subtitle cue must be source-global and inside the selected scene")
            cues.append(cue)
        outputs.append(HighlightOutput(
            output_id=f"hl_{index:03d}", title=sanitize_highlight_title(str(candidate.get("title", ""))),
            episode_id=episode_id, source_id=source_id, source_file=source_file,
            start_ms=start_ms, end_ms=end_ms, original_audio=True,
            subtitle_cues=tuple(cues), evidence_ids=tuple(str(x) for x in candidate.get("evidence_ids", [])),
        ))
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return HighlightProject(HIGHLIGHT_SCHEMA_VERSION, project_id, "HIGHLIGHT", prompt_hash, dependency_revision, tuple(outputs))


def validate_highlight_project(project: HighlightProject, sources: Sequence[Mapping[str, Any]]) -> None:
    if project.schema_version != HIGHLIGHT_SCHEMA_VERSION or project.project_mode != "HIGHLIGHT":
        raise ValueError("Unsupported Highlight contract or project mode")
    rebuilt = build_highlight_project(
        project_id=project.project_id, prompt="", dependency_revision=project.dependency_revision,
        candidates=[item.to_dict() for item in project.outputs], sources=sources,
    )
    if tuple(item.output_id for item in rebuilt.outputs) != tuple(item.output_id for item in project.outputs):
        raise ValueError("Highlight output IDs must be deterministic and application-owned")


def highlight_dependency_digest(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
