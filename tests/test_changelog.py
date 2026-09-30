# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``CHANGELOG.md`` links each entry to its PR, and every link resolves."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
_REF_USE = re.compile(r"\[#(\d+)\](?!:)")
_REF_DEF = re.compile(r"^\[#(\d+)\]:", re.M)
_BULLET = re.compile(r"^- .*?(?=^- |^#|\Z)", re.M | re.S)


def _text() -> str:
    if not _CHANGELOG.is_file():
        pytest.skip("CHANGELOG.md is not in this checkout")
    return _CHANGELOG.read_text(encoding="utf-8")


def _unreleased_bullets(text: str) -> list[str]:
    body = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    return _BULLET.findall(body)


def test_every_unreleased_entry_links_its_pr() -> None:
    bullets = _unreleased_bullets(_text())
    assert bullets  # not vacuous: the section was found and split
    missing = [b.splitlines()[0] for b in bullets if not _REF_USE.search(b)]
    assert not missing, missing


def test_every_pr_reference_is_defined() -> None:
    text = _text()
    used = set(_REF_USE.findall(text))
    assert used  # not vacuous
    assert not used - set(_REF_DEF.findall(text))


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
