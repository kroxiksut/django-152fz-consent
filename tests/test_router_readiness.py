from __future__ import annotations

from pathlib import Path


def test_core_has_no_jurisdiction_selection_logic() -> None:
    core_dir = Path("src/django_consent_152fz/core")
    prohibited_tokens = (
        "jurisdiction",
        "gdpr",
        "юрисдик",
    )

    matches: list[tuple[str, str]] = []
    for path in sorted(core_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for token in prohibited_tokens:
            if token in text:
                matches.append((path.as_posix(), token))

    assert matches == []
