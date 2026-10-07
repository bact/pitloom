# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The changelog files link each entry to its PR, resolve every link, and
list each section's entries in PR order."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_CHANGELOG = _ROOT / "CHANGELOG.md"
_FILES = ["CHANGELOG.md", "CHANGELOG-archive.md"]
_REF_USE = re.compile(r"\[#(\d+)\](?!:)")
_REF_DEF = re.compile(r"^\[#(\d+)\]:", re.M)
_BULLET = re.compile(r"^- .*?(?=^- |^#|\Z)", re.M | re.S)


def _text(path: Path = _CHANGELOG) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} is not in this checkout")
    return path.read_text(encoding="utf-8")


def _section_pr_keys(text: str) -> dict[str, list[int]]:
    """Lowest PR number of each bullet, per ``## version / ### kind`` section."""
    keys: dict[str, list[int]] = {}
    for version in re.split(r"^(?=## \[)", text, flags=re.M)[1:]:
        for kind in re.split(r"^(?=### )", version, flags=re.M)[1:]:
            heading = f"{version.splitlines()[0]} {kind.splitlines()[0]}"
            keys[heading] = [
                min(int(n) for n in _REF_USE.findall(b))
                for b in _BULLET.findall(kind)
                if _REF_USE.search(b)
            ]
    return keys


def _unreleased_bullets(text: str) -> list[str]:
    """Entries of ``[Unreleased]``, else (right after a release is cut, with
    the heading empty or removed) of the newest released section."""
    _, found_heading, after = text.partition("## [Unreleased]")
    sections = (after if found_heading else text).split("\n## [")
    if not found_heading:
        sections = sections[1:]  # what precedes the first version heading
    return next(
        (found for body in sections[:2] if (found := _BULLET.findall(body))), []
    )


_NEW = "### Fixed\n\n- new ([#3])\n"
_OLD = "### Fixed\n\n- old ([#1])\n"
_RELEASE_STATES = [
    f"# C\n\n## [Unreleased]\n\n{_NEW}\n## [1.0.0]\n\n{_OLD}",
    f"# C\n\n## [Unreleased]\n\n## [1.0.0]\n\n{_NEW}",
    f"# C\n\n## [1.0.0] - 2026-01-01\n\n{_NEW}\n## [0.9.0]\n\n{_OLD}",
]


@pytest.mark.parametrize(
    "text",
    _RELEASE_STATES,
    ids=["unreleased-filled", "unreleased-empty", "unreleased-removed"],
)
def test_unreleased_bullets_in_every_release_state(text: str) -> None:
    """Right after a release is cut the heading may be empty or gone; the
    newest entry is still found, never the older release's."""
    assert [b.split(" (")[0] for b in _unreleased_bullets(text)] == ["- new"]


def test_every_unreleased_entry_links_its_pr() -> None:
    bullets = _unreleased_bullets(_text())
    assert bullets  # not vacuous: the section was found and split
    missing = [b.splitlines()[0] for b in bullets if not _REF_USE.search(b)]
    assert not missing, missing


@pytest.mark.parametrize("name", _FILES)
def test_every_pr_reference_is_defined(name: str) -> None:
    text = _text(_ROOT / name)
    used = set(_REF_USE.findall(text))
    assert used  # not vacuous
    assert not used - set(_REF_DEF.findall(text))


@pytest.mark.parametrize("name", _FILES)
def test_entries_are_sorted_by_lowest_pr(name: str) -> None:
    sections = _section_pr_keys(_text(_ROOT / name))
    assert sections  # not vacuous
    unsorted = [h for h, keys in sections.items() if keys != sorted(keys)]
    assert not unsorted, unsorted


def test_section_pr_keys_uses_lowest_pr_of_each_entry() -> None:
    text = "## [1.0.0]\n\n### Fixed\n\n- a ([#5], [#2])\n- b ([#3])\n"
    assert _section_pr_keys(text) == {"## [1.0.0] ### Fixed": [2, 3]}


@pytest.mark.parametrize(
    ("section", "linked"),
    [
        ("### Fixed\n\n- first ([#1])\n- second\n  wraps ([#2])\n", True),
        ("### Fixed\n\n- first, no link\n- second ([#2])\n", False),
        ("### Added\n\n- a ([#1])\n\n### Fixed\n\n- b, no link\n", False),
    ],
)
def test_bullet_split_sees_each_entry(section: str, linked: bool) -> None:
    """The first entry of a section is its own bullet, not merged into the
    heading (a split that merged it hid an unlinked entry)."""
    text = f"## [Unreleased]\n\n{section}\n## [0.1.0]\n\n- old\n"
    bullets = _unreleased_bullets(text)
    assert all(_REF_USE.search(b) for b in bullets) is linked


def test_empty_unreleased_checks_the_release_just_cut() -> None:
    text = "## [Unreleased]\n\n## [0.2.0]\n\n- new, no link\n## [0.1.0]\n\n- old\n"
    assert _unreleased_bullets(text) == ["- new, no link"]
