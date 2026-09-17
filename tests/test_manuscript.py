from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "scripts" / "32_validate_manuscript.py"
    spec = importlib.util.spec_from_file_location("validate_manuscript", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manuscript_matches_committed_results() -> None:
    validator = load_validator()
    summary = validator.validate(ROOT / "manuscript" / "manuscript.md")
    assert summary["figures"] == 5
    assert summary["headline_checks"] == 34
    assert summary["word_count"] > 3_000
