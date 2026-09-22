"""Schema loader and validator access."""

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict

import jsonschema

_SCHEMA_CACHE: Dict[str, Any] | None = None
_VALIDATOR_CACHE: jsonschema.protocols.Validator | None = None


def get_project_schema() -> Dict[str, Any]:
    """Load and return the Recap Project Schema v3 dictionary."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        candidates = [
            Path(__file__).resolve().parent / "recap_v3_schema.json",
        ]
        if getattr(sys, "frozen", False):
            if hasattr(sys, "_MEIPASS"):
                base_mei = Path(sys._MEIPASS)
                candidates.extend([
                    base_mei / "toolrecap_v4" / "schemas" / "recap_v3_schema.json",
                    base_mei / "schemas" / "recap_v3_schema.json",
                    base_mei / "recap_v3_schema.json",
                ])
            exe_parent = Path(sys.executable).resolve().parent
            candidates.extend([
                exe_parent / "schemas" / "recap_v3_schema.json",
                exe_parent / "toolrecap_v4" / "schemas" / "recap_v3_schema.json",
                exe_parent / "recap_v3_schema.json",
            ])
        for p in candidates:
            if p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    _SCHEMA_CACHE = json.load(f)
                break
        if _SCHEMA_CACHE is None:
            with open(candidates[0], "r", encoding="utf-8") as f:
                _SCHEMA_CACHE = json.load(f)
    return _SCHEMA_CACHE


def get_schema_validator() -> jsonschema.protocols.Validator:
    """Get or create the jsonschema Draft 2020-12 validator instance."""
    global _VALIDATOR_CACHE
    if _VALIDATOR_CACHE is None:
        schema = get_project_schema()
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        _VALIDATOR_CACHE = validator_cls(schema)
    return _VALIDATOR_CACHE
