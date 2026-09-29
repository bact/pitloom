# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Portability guard: every ``skills/*/SKILL.md`` stays a valid Agent Skill.

The skills have no test suite of their own (see CLAUDE.md's "Usage
surfaces"), and a client that validates strictly (claude.ai and the
Skills API upload, ``skills-ref validate``) rejects a frontmatter key
outside the specification -- Claude Code alone tolerates it. If a case
here fails, fix the ``SKILL.md`` (do not widen the allowlist unless the
Agent Skills specification itself grew).

See also: :mod:`tests.test_build_timeout_examples` (drift guard for the
duration examples in the same files).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = sorted(REPO_ROOT.glob("skills/*/SKILL.md"))
SKILL_DIRS = [path.parent for path in SKILL_FILES]

# Keys the Agent Skills specification allows in the frontmatter.
_ALLOWED_KEYS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME = 64
_MAX_DESCRIPTION = 1024
_MAX_COMPATIBILITY = 500
# The specification: keep the SKILL.md body under 500 lines (a hard limit
# here) and about 5,000 tokens (~20 KB).
_MAX_BODY_LINES = 500
# Byte ratchet on the body, with headroom over today's largest (~20 KB);
# lower it towards 20 KB as detail moves to references/, never raise it.
_MAX_BODY_BYTES = 24 * 1024

_FENCE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.DOTALL | re.MULTILINE)
_SPAN_RE = re.compile(r"`[^`\n]*`")
# A code span that is exactly one skill markdown file name (a nested
# references/ path matches too, so the one-level check sees it).
_MENTION_RE = re.compile(r"^(?:\.\./)?(?:references/(?:[\w-]+/)*)?[\w-]+\.md$")
_LINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_EXTERNAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#)", re.IGNORECASE)

# Files a skill names that belong to the user's project, not to the skill.
_PROJECT_FILES = frozenset({"README.md", "CONTRIBUTING.md"})
# Deliberate sibling-skill mentions: (skill, mention) -> skill that ships it.
_SIBLING_MENTIONS = {("sbom-enrich", "references/id-registry.md"): "sbom-generate"}


def _frontmatter(path: Path) -> dict[str, Any]:
    """Parse the YAML frontmatter block that must start at line 1."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{path}: frontmatter must start at line 1"
    end = next((i for i, line in enumerate(lines[1:], 1) if line == "---"), None)
    assert end is not None, f"{path}: frontmatter is not closed"
    data = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(data, dict), f"{path}: frontmatter is not a mapping"
    return data


def _relative_links(path: Path) -> list[str]:
    """Relative markdown link targets in *path*, outside code."""
    text = _SPAN_RE.sub("", _FENCE_RE.sub("", path.read_text(encoding="utf-8")))
    targets = (m.group(1).split("#", 1)[0] for m in _LINK_RE.finditer(text))
    return [t for t in targets if t and not _EXTERNAL_RE.match(t)]


def _mentions(path: Path) -> list[str]:
    """Skill markdown file names written as a whole code span in *path*."""
    text = _FENCE_RE.sub("", path.read_text(encoding="utf-8"))
    spans = (m.group(0).strip("`") for m in _SPAN_RE.finditer(text))
    return [s for s in spans if _MENTION_RE.match(s) and s not in _PROJECT_FILES]


def _mention_exists(skill_dir: Path, md_file: Path, mention: str) -> bool:
    """A mention resolves beside its file, or from the skill directory."""
    sibling = _SIBLING_MENTIONS.get((skill_dir.name, mention))
    if sibling is not None:
        return (skill_dir.parent / sibling / mention).is_file()
    return any(
        (base / mention).resolve().is_file() for base in (md_file.parent, skill_dir)
    )


def _body(path: Path) -> str:
    """The SKILL.md text after the closing frontmatter delimiter."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    end = next(i for i, line in enumerate(lines[1:], 1) if line.rstrip() == "---")
    return "".join(lines[end + 1 :])


def _skill_markdown(skill_dir: Path) -> list[Path]:
    return [skill_dir / "SKILL.md", *sorted(skill_dir.glob("references/*.md"))]


def test_skills_found() -> None:
    """Guard against a vacuous pass: the glob must find the shipped skills."""
    assert [d.name for d in SKILL_DIRS] == [
        "sbom-enrich",
        "sbom-generate",
        "sbom-validate",
    ]


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda d: d.name)
class TestSkillFrontmatter:
    """Frontmatter rules from the Agent Skills specification."""

    def test_keys_are_specified(self, skill_dir: Path) -> None:
        extra = set(_frontmatter(skill_dir / "SKILL.md")) - _ALLOWED_KEYS
        assert not extra, f"keys outside the specification: {sorted(extra)}"

    def test_name(self, skill_dir: Path) -> None:
        name = _frontmatter(skill_dir / "SKILL.md")["name"]
        assert isinstance(name, str)
        assert _NAME_RE.match(name)
        assert len(name) <= _MAX_NAME
        assert name == skill_dir.name
        assert "anthropic" not in name
        assert "claude" not in name

    def test_description(self, skill_dir: Path) -> None:
        description = _frontmatter(skill_dir / "SKILL.md")["description"]
        assert isinstance(description, str)
        assert description.strip()
        assert len(description) <= _MAX_DESCRIPTION
        assert "<" not in description
        assert ">" not in description

    def test_compatibility(self, skill_dir: Path) -> None:
        data = _frontmatter(skill_dir / "SKILL.md")
        assert "compatibility" in data, "declare what the skill needs to run"
        compatibility = data["compatibility"]
        assert isinstance(compatibility, str)
        assert compatibility.strip()
        assert len(compatibility) <= _MAX_COMPATIBILITY

    def test_body_size(self, skill_dir: Path) -> None:
        body = _body(skill_dir / "SKILL.md")
        assert len(body.splitlines()) <= _MAX_BODY_LINES, "move detail to references/"
        assert len(body.encode("utf-8")) <= _MAX_BODY_BYTES, (
            "move detail to references/"
        )


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda d: d.name)
class TestSkillReferences:
    """Files a skill ships stay reachable and one level deep."""

    def test_relative_links_resolve(self, skill_dir: Path) -> None:
        for md_file in _skill_markdown(skill_dir):
            for target in _relative_links(md_file):
                resolved = (md_file.parent / target).resolve()
                assert resolved.exists(), f"{md_file}: broken link {target}"

    def test_named_files_resolve(self, skill_dir: Path) -> None:
        """Every skill file named in a code span exists (none named: vacuous)."""
        assert _mentions(skill_dir / "SKILL.md"), "guard would pass vacuously"
        for md_file in _skill_markdown(skill_dir):
            for mention in _mentions(md_file):
                assert _mention_exists(skill_dir, md_file, mention), (
                    f"{md_file.name}: `{mention}` does not exist"
                    " (a user-project file? add it to _PROJECT_FILES)"
                )

    def test_references_one_level_deep(self, skill_dir: Path) -> None:
        references = skill_dir / "references"
        assert not [p for p in references.rglob("*") if p.is_dir()]
        skill_md = skill_dir / "SKILL.md"
        for target in [*_relative_links(skill_md), *_mentions(skill_md)]:
            assert len(Path(target).parts) <= 2, f"{target} is nested"

    def test_every_reference_is_named_in_skill_md(self, skill_dir: Path) -> None:
        body = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        for ref in sorted((skill_dir / "references").glob("*.md")):
            assert f"references/{ref.name}" in body, f"{ref.name} is orphaned"
