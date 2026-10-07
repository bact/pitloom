# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift-guard: every link in the user manual still lands.

``mkdocs build --strict`` checks the links between docs pages, but not an
anchor, not a link in the README, and not a link to a file on GitHub
(``https://github.com/bact/pitloom/blob/main/...#anchor``). Moving a section
to another page, as the docs splits do, breaks those silently. Checked here:

* a relative link to a file resolves; one with an ``#anchor`` into a Markdown
  file finds a heading with that slug;
* a GitHub ``blob/main`` link to a Markdown file of this repository does too;
* every page in the ``mkdocs.yml`` nav exists, and every docs page is in it.

See also: :mod:`tests.test_docs_examples` for the code examples.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from urllib.parse import unquote

import pytest
import yaml

from tests._docs_scan import CLI_DOC_FILES, REPO_ROOT, prose, rel, without_fences

_LINK_RE = re.compile(
    r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)|^\[[^\]]+\]:\s*(\S+)", re.M
)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.M)
_BLOB = "https://github.com/bact/pitloom/blob/main/"
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _slug(heading: str) -> str:
    """The anchor MkDocs' ``toc`` extension (and GitHub, for these headings)
    gives a heading: link text kept, code marks and emphasis dropped, ASCII
    letters, digits, ``_`` and ``-`` only, spaces as hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"[`*]", "", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


@cache
def _anchors(path: Path) -> frozenset[str]:
    """Every anchor *path* offers. A repeated heading gets ``_1``, ``_2`` ...
    (MkDocs) or ``-1``, ``-2`` ... (GitHub): both are accepted."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    for match in _HEADING_RE.finditer(without_fences(path)):
        slug = _slug(match.group(1))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.update({slug} if not count else {f"{slug}_{count}", f"{slug}-{count}"})
    return frozenset(found)


def _links(path: Path) -> Iterator[tuple[int, str]]:
    """``(line, target)`` of every link in *path*'s prose."""
    text = prose(path)
    for match in _LINK_RE.finditer(text):
        target = match.group(1) or match.group(2)
        yield text.count("\n", 0, match.start()) + 1, target


def _local_target(source: Path, target: str) -> tuple[Path, str] | None:
    """The file and anchor a link points at in this repository, ``None`` for a
    link elsewhere."""
    if target.startswith(_BLOB):
        path, _, fragment = target[len(_BLOB) :].partition("#")
        return REPO_ROOT / unquote(path), unquote(fragment)
    if _SCHEME_RE.match(target):
        return None
    path, _, fragment = target.partition("#")
    resolved = (source.parent / unquote(path)) if path else source
    return resolved.resolve(), unquote(fragment)


def _link_errors(source: Path) -> list[str]:
    errors: list[str] = []
    for line, target in _links(source):
        local = _local_target(source, target)
        if local is None:
            continue
        path, fragment = local
        where = f"{rel(source)}:{line}: {target}"
        if not path.exists():
            errors.append(f"{where}: no such file")
        elif fragment and path.suffix == ".md" and fragment not in _anchors(path):
            errors.append(f"{where}: no heading with that anchor in {rel(path)}")
    return errors


@pytest.mark.parametrize("path", CLI_DOC_FILES, ids=rel)
def test_links_resolve(path: Path) -> None:
    errors = _link_errors(path)
    assert not errors, "\n".join(errors)


def _nav_files(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _nav_files(value)
    elif isinstance(node, list):
        for item in node:
            yield from _nav_files(item)


def test_nav_and_docs_pages_agree() -> None:
    config = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    in_nav = set(_nav_files(config["nav"]))
    on_disk = {p.name for p in (REPO_ROOT / "docs").glob("*.md")}
    assert in_nav == on_disk


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("Generate an SBOM", "generate-an-sbom"),
        ("Embed an SBOM into a wheel (PEP 770)", "embed-an-sbom-into-a-wheel-pep-770"),
        ("`[tool.pitloom.creation]`", "toolpitloomcreation"),
        (
            "`[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]`",
            "toolpitloomcreator-toolpitloomcreation-tool",
        ),
        ("Explicit config (`pitloom_config=`)", "explicit-config-pitloom_config"),
    ],
)
def test_slug_matches_mkdocs(heading: str, slug: str) -> None:
    """Pin :func:`_slug` to the anchors the docs already link to."""
    assert _slug(heading) == slug


def test_scan_found_links() -> None:
    """Guard against a vacuous pass: a changed link syntax would leave every
    file with nothing to check."""
    assert sum(1 for path in CLI_DOC_FILES for _ in _links(path)) > 200
