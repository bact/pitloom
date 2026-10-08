# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift-guard: every provenance ``Method`` tag in the source has a docs row.

``docs/metadata-provenance.md`` lists the ``method`` values in a table. A new
``Method: <name>`` literal in ``src/pitloom`` without a row there goes
unnoticed, so this scans the source for the literals and checks the table.

See also: :mod:`tests.test_docs_links` for the other docs drift-guards.
"""

from __future__ import annotations

import re

from tests._docs_scan import REPO_ROOT

_DOC = REPO_ROOT / "docs" / "metadata-provenance.md"
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


def test_every_method_tag_has_a_docs_row() -> None:
    """A ``Method:`` literal in ``src/`` is documented in the method table."""
    section = _DOC.read_text(encoding="utf-8").split("## What the `method`", 1)[1]
    documented = set(_ROW_RE.findall(section.split("\n## ", 1)[0]))
    methods = _source_methods()
    assert "resolved_lockfile" in methods  # the scan found something
    assert not methods - documented
