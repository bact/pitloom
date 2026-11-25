# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every ``licenseid>=`` spelling in the docs, skills, the source (a
docstring or comment) and the unreleased changelog section states the floor
that ``pyproject.toml`` declares, once: every spelling there agrees.

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


def _texts(root: Path) -> dict[str, str]:
    """Each checked file (or section) under *root* by name."""
    files = [root / "README.md", root / "AGENTS.md"]
    files += sorted((root / "docs").rglob("*.md"))
    files += sorted((root / "skills").rglob("*.md"))
    files += sorted((root / "src").rglob("*.py"))
    texts = {
        f.relative_to(root).as_posix(): f.read_text(encoding="utf-8")
        for f in files
        if f.is_file()
    }
    changelog = root / "CHANGELOG.md"
    if changelog.is_file():
        texts["CHANGELOG.md (Unreleased)"] = _unreleased(
            changelog.read_text(encoding="utf-8")
        )
    return texts


def _declared(pyproject: str) -> tuple[str, str]:
    """The one floor and ceiling every spelling in *pyproject* states."""
    bounds = {m.groups() for m in _SPELLING.finditer(pyproject)}
    assert len(bounds) == 1, f"pyproject.toml states several: {sorted(bounds)}"
    (floor, ceiling), *_ = bounds
    assert ceiling is not None
    return floor, ceiling


def _wrong(
    texts: dict[str, str], floor: str, ceiling: str
) -> tuple[list[str], set[str]]:
    """Each spelling of *texts* stating other bounds, and the names that
    hold a spelling."""
    wrong: list[str] = []
    seen: set[str] = set()
    for name, text in texts.items():
        for match in _SPELLING.finditer(text):
            seen.add(name)
            lower, upper = match.groups()
            if lower != floor or (upper is not None and upper != ceiling):
                wrong.append(f"{name}: {match.group(0)!r}")
    return wrong, seen


def test_documented_licenseid_floor_matches_pyproject() -> None:
    floor, ceiling = _declared((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wrong, seen = _wrong(_texts(_ROOT), floor, ceiling)
    assert not wrong, f"floor is licenseid>={floor},<{ceiling}: {wrong}"
    # The scan finds the spellings it guards (not a vacuous pass).
    assert {"AGENTS.md", "CHANGELOG.md (Unreleased)"} <= seen
    assert any(name.startswith("skills") for name in seen)
    assert any(name.startswith("docs") for name in seen)


@pytest.mark.parametrize(
    "pyproject",
    [
        '"licenseid>=0.9.2,<0.10",\n"licenseid>=0.9.1,<0.10",',
        '"licenseid>=0.9.2,<0.10",\n"licenseid>=0.9.2,<0.11",',
    ],
    ids=["floor", "ceiling"],
)
def test_pyproject_spellings_must_agree(pyproject: str) -> None:
    """A second requirement (another dependency group) with other bounds."""
    with pytest.raises(AssertionError, match="states several"):
        _declared(pyproject)
    assert _declared('"licenseid>=0.9.2,<0.10",\n"licenseid>=0.9.2,<0.10"')


def test_a_source_docstring_floor_is_checked(tmp_path: Path) -> None:
    """A floor in a docstring under ``src/`` is read (one stale here)."""
    module = tmp_path / "src" / "pkg" / "m.py"
    module.parent.mkdir(parents=True)
    module.write_text('"""Needs ``licenseid>=0.9.1``."""\n', encoding="utf-8")
    wrong, seen = _wrong(_texts(tmp_path), "0.9.2", "0.10")
    assert seen == {"src/pkg/m.py"}
    assert wrong == ["src/pkg/m.py: 'licenseid>=0.9.1'"]


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
