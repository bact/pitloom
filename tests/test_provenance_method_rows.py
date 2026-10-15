# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift-guard: every provenance ``Method`` tag in the source has a docs row.

The ``docs/metadata-provenance*.md`` pages list the ``method`` values in one
table. A new ``Method: <name>`` literal in ``src/pitloom`` without a row there
goes unnoticed, so this scans the source for the literals and checks the
table, wherever among those pages it is.

See also: :mod:`tests.test_docs_links` for the other docs drift-guards.
"""

from __future__ import annotations

import re

from tests._docs_scan import REPO_ROOT

_DOCS = sorted((REPO_ROOT / "docs").glob("metadata-provenance*.md"))
_HEADING = "## What the `method`"
_METHOD_RE = re.compile(r"Method: ([a-z][a-z_]*)")
_ROW_RE = re.compile(r"^\| `([a-z_]+)`", re.M)
#: Tags the scan cannot see because the name is not next to the ``Method:``
#: text: ``deps_originator.py`` sets ``parsed_author_list`` in a variable, and
#: ``extract/lock/cascade.py`` passes ``pinned_requirements`` as a bare string.
_DYNAMIC = {"parsed_author_list", "pinned_requirements"}


def _source_methods() -> set[str]:
    found = set(_DYNAMIC)
    for path in (REPO_ROOT / "src" / "pitloom").rglob("*.py"):
        found.update(_METHOD_RE.findall(path.read_text(encoding="utf-8")))
    return found


def _documented_methods() -> set[str]:
    """The rows of the method table, read from every provenance page."""
    texts = [path.read_text(encoding="utf-8") for path in _DOCS]
    sections = [text.split(_HEADING, 1)[1] for text in texts if _HEADING in text]
    assert len(sections) == 1, f"{len(sections)} method tables in {_DOCS}"
    return set(_ROW_RE.findall(sections[0].split("\n## ", 1)[0]))


def test_every_method_tag_has_a_docs_row() -> None:
    """A ``Method:`` literal in ``src/`` is documented in the method table."""
    documented = _documented_methods()
    methods = _source_methods()
    assert "resolved_lockfile" in methods  # the scan found something
    assert not methods - documented
