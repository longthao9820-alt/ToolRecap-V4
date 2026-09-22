from __future__ import annotations

import json

import pytest

from catalog_test_helpers import populated_store
from toolrecap_v4.analysis.finalizer.catalog import CatalogBuilder
from toolrecap_v4.analysis.finalizer.planner import (
    PLANNER_DRAFT_VERSION,
    PLANNER_PROTOCOL_VERSION,
    build_initial_planner_prompt,
    parse_planner_json,
    planner_dependency_signature,
    validate_planner_action,
)
from toolrecap_v4.analysis.finalizer.packing import unpack_catalog
from toolrecap_v4.errors import PlannerResponseError, PlannerValidationError


@pytest.fixture
def catalog(tmp_path):
    store, revision, episodes, _ = populated_store(tmp_path)
    return CatalogBuilder().build(
        project_id="project-1", evidence_revision=revision,
        ordered_episodes=episodes, evidence_store=store,
    )


def draft_response(catalog, round_id="round-001", output_count=1):
    outputs = []
    for index in range(output_count):
        outputs.append({
            "draft_ref": f"draft_output_{index + 1:03d}",
            "working_title": f"Working {index}",
            "editorial_thesis": "A secondary character changes the season.",
            "story_arc": "Connect events across non-consecutive episodes.",
            "episode_ids": ["E01", "E02"],
            "evidence_ids": ["E01-EV-002"],
            "supporting_evidence_ids": ["E01-EV-001"],
            "connections": ["The later episode changes the earlier context."],
            "visual_requests": [{
                "episode_id": "E02", "start_ms": 1000, "end_ms": 2000,
                "purpose": "Verify visually observable action",
            }],
            "uncertainty": [],
        })
    return {
        "protocol_version": PLANNER_PROTOCOL_VERSION, "action": "PLANNER_DRAFT",
        "project_id": "project-1", "catalog_hash": catalog.catalog_hash,
        "evidence_revision": catalog.evidence_revision, "round_id": round_id,
        "draft": {
            "draft_version": PLANNER_DRAFT_VERSION,
            "editorial_rationale": "The complete season supports these concepts.",
            "proposed_output_count": len(outputs), "proposed_outputs": outputs,
            "uncertainty": [],
        },
    }


def test_initial_prompt_preserves_raw_prompt_and_complete_catalog(catalog):
    raw = 'Keep  unusual  spacing.\nUnicode: Việt Nam 🙂\n"Quoted instruction"'
    encoded = build_initial_planner_prompt(
        project_id="project-1", round_id="round-001",
        raw_recap_prompt=raw, catalog=catalog,
    )
    payload = json.loads(encoded)
    assert payload["raw_recap_prompt"] == raw
    assert payload["catalog_identity"]["catalog_item_count"] == len(catalog.items)
    packed = payload["catalog_transport"]["complete_packed_catalog"]
    assert packed["item_count"] == len(catalog.items)
    assert packed["episode_count"] == len(catalog.ordered_episodes)
    transported = unpack_catalog(packed)
    assert [item.evidence_id for item in transported.items] == [item.evidence_id for item in catalog.items]
    assert payload["ordered_episodes"][0]["duration_ms"] == 100_000
    assert "C:/media" not in encoded and "C:\\media" not in encoded
    for forbidden in ("video data", "VoiceStudio", "Candidate Discovery", "Season Connection"):
        assert forbidden not in encoded


def test_request_action_strictly_validates_ids_and_ranges(catalog):
    valid = {
        "protocol_version": PLANNER_PROTOCOL_VERSION, "action": "REQUEST_EVIDENCE",
        "project_id": "project-1", "catalog_hash": catalog.catalog_hash,
        "evidence_revision": catalog.evidence_revision, "round_id": "round-001",
        "requests": [
            {"request_id": "req-1", "type": "evidence_ids", "evidence_ids": ["E01-EV-001"]},
            {"request_id": "req-2", "type": "episode_range", "episode_id": "E01", "start_ms": 0, "end_ms": 5000},
        ],
    }
    action = validate_planner_action(valid, project_id="project-1", round_id="round-001", catalog=catalog)
    assert len(action.requests) == 2
    invalid = json.loads(json.dumps(valid))
    invalid["requests"][0]["evidence_ids"] = ["E99-EV-999"]
    with pytest.raises(PlannerValidationError):
        validate_planner_action(invalid, project_id="project-1", round_id="round-001", catalog=catalog)
    invalid = json.loads(json.dumps(valid))
    invalid["requests"][1]["start_ms"] = True
    with pytest.raises(PlannerValidationError):
        validate_planner_action(invalid, project_id="project-1", round_id="round-001", catalog=catalog)


@pytest.mark.parametrize("count", [0, 1, 6])
def test_draft_output_count_is_ai_decided_and_cross_episode_allowed(catalog, count):
    action = validate_planner_action(
        draft_response(catalog, output_count=count),
        project_id="project-1", round_id="round-001", catalog=catalog,
    )
    assert action.draft.proposed_output_count == count
    if count:
        assert action.draft.proposed_outputs[0].episode_ids == ("E01", "E02")
        assert action.draft.proposed_outputs[0].visual_requests[0].purpose
        assert not action.draft.proposed_outputs[0].draft_ref.startswith("out_")


def test_draft_rejects_canonical_ids_invalid_visual_and_missing_fields(catalog):
    value = draft_response(catalog)
    value["draft"]["proposed_outputs"][0]["draft_ref"] = "out_001"
    with pytest.raises(PlannerValidationError):
        validate_planner_action(value, project_id="project-1", round_id="round-001", catalog=catalog)
    value = draft_response(catalog)
    value["draft"]["proposed_outputs"][0]["evidence_ids"] = ["E01-EV-001", "E01-EV-001"]
    with pytest.raises(PlannerValidationError):
        validate_planner_action(value, project_id="project-1", round_id="round-001", catalog=catalog)
    value = draft_response(catalog)
    value["draft"]["proposed_outputs"][0]["visual_requests"][0]["end_ms"] = 200_000
    with pytest.raises(PlannerValidationError):
        validate_planner_action(value, project_id="project-1", round_id="round-001", catalog=catalog)
    value = draft_response(catalog)
    value["draft"].pop("editorial_rationale")
    with pytest.raises(PlannerValidationError):
        validate_planner_action(value, project_id="project-1", round_id="round-001", catalog=catalog)


def test_parser_rejects_malformed_and_duplicate_keys():
    with pytest.raises(PlannerResponseError):
        parse_planner_json("{bad", project_id="project-1", round_id="round-001")
    with pytest.raises(PlannerResponseError):
        parse_planner_json('{"action":"A","action":"B"}', project_id="project-1", round_id="round-001")


@pytest.mark.parametrize("field,value", [
    ("protocol_version", "wrong"),
    ("action", "FREE_FORM"),
    ("catalog_hash", "wrong"),
    ("evidence_revision", "stale"),
    ("round_id", "round-999"),
])
def test_wrong_protocol_identity_and_action_are_rejected(catalog, field, value):
    response = draft_response(catalog)
    response[field] = value
    with pytest.raises(PlannerValidationError):
        validate_planner_action(response, project_id="project-1", round_id="round-001", catalog=catalog)


def test_planner_dependencies_include_only_semantic_inputs(catalog):
    first = planner_dependency_signature(
        project_id="project-1", raw_recap_prompt="raw prompt", catalog=catalog,
        model="route-id", reasoning="high",
    )
    changed_prompt = planner_dependency_signature(
        project_id="project-1", raw_recap_prompt="raw prompt changed", catalog=catalog,
        model="route-id", reasoning="high",
    )
    changed_model = planner_dependency_signature(
        project_id="project-1", raw_recap_prompt="raw prompt", catalog=catalog,
        model="another-route", reasoning="high",
    )
    assert first != changed_prompt != changed_model
    text = json.dumps(first).lower()
    for irrelevant in ("voice", "audio_mix", "renderer", "gpu", "output_dir", "parallelism"):
        assert irrelevant not in text
