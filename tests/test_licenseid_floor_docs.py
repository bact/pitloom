# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every ``licenseid>=`` spelling in the docs, skills and the unreleased
changelog section states the floor that ``pyproject.toml`` declares.

Released changelog sections, ``CHANGELOG-archive.md`` and ``working-docs/``
are history and keep the floor of their time.

See also: :mod:`tests.test_changelog`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# `licenseid>=0.9.2,<0.10` or the spaced "`licenseid` >= 0.9.2": the lower
# bound, and the upper bound when one is written.
_SPELLING = re.compile(
    r"licenseid`?\s*>=\s*([0-9][0-9.]*)(?:\s*,\s*<\s*([0-9][0-9.]*))?"
)


def _unreleased(changelog: str) -> str:
    start = changelog.index("## [Unreleased]")
    end = changelog.find("\n## [", start + 1)
    return changelog[start : end if end != -1 else len(changelog)]


def _texts() -> dict[str, str]:
    """Each checked file (or section) by name."""
    files = [_ROOT / "README.md", _ROOT / "AGENTS.md"]
    files += sorted((_ROOT / "docs").rglob("*.md"))
    files += sorted((_ROOT / "skills").rglob("*.md"))
    texts = {
        str(f.relative_to(_ROOT)): f.read_text(encoding="utf-8")
        for f in files
        if f.is_file()
    }
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    texts["CHANGELOG.md (Unreleased)"] = _unreleased(changelog)
    return texts


def test_documented_licenseid_floor_matches_pyproject() -> None:
    declared = _SPELLING.search((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared is not None and declared.group(2) is not None
    floor, ceiling = declared.groups()
    wrong: list[str] = []
    seen: set[str] = set()
    for name, text in _texts().items():
        for match in _SPELLING.finditer(text):
            seen.add(name)
            lower, upper = match.groups()
            if lower != floor or (upper is not None and upper != ceiling):
                wrong.append(f"{name}: {match.group(0)!r}")
    assert not wrong, f"floor is licenseid>={floor},<{ceiling}: {wrong}"
    # The scan finds the spellings it guards (not a vacuous pass).
    assert {"AGENTS.md", "CHANGELOG.md (Unreleased)"} <= seen
    assert any(name.startswith("skills") for name in seen)
    assert any(name.startswith("docs") for name in seen)


@pytest.mark.parametrize(
    ("text", "bounds"),
    [
        ("`licenseid>=0.9.2,<0.10`", ("0.9.2", "0.10")),
        ("`licenseid` >= 0.9.2;", ("0.9.2", None)),
        ('"licenseid>=0.8.4 , < 0.9"', ("0.8.4", "0.9")),
    ],
    ids=["compact", "spaced", "loose"],
)
def test_spelling_pattern_reads_both_forms(
    text: str, bounds: tuple[str, str | None]
) -> None:
    match = _SPELLING.search(text)
    assert match is not None and match.groups() == bounds
