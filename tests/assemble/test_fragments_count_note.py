# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The parameter count note of a merged ``ai_AIPackage``: derived from the
merged ``parameters`` entry, one copy, the first line of the comment.

See also: :mod:`tests.core.test_model_parameters` (the comment rule) and
:mod:`tests.core.test_fragments_models_datasets` (a whole merge).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _fragments_props as props
from pitloom.core.model_parameters import PARAMETER_COUNT_KEY, PARAMETER_COUNT_NOTE

_NOTE = PARAMETER_COUNT_NOTE
_PROV = "Metadata provenance: name: Source: a | Method: m; version: Source: a"


def _pkg(comment: str | None, count: str | None = None) -> spdx3.ai_AIPackage:
    pkg = spdx3.ai_AIPackage(name="m")
    pkg.spdxId = "urn:m"
    if comment is not None:
        pkg.comment = comment
    if count is not None:
        pkg.ai_hyperparameter = [
            spdx3.DictionaryEntry(key=PARAMETER_COUNT_KEY, value=count)
        ]
    return pkg


def _count(pkg: spdx3.ai_AIPackage) -> list[str]:
    entries = [e for e in pkg.ai_hyperparameter if isinstance(e, spdx3.DictionaryEntry)]
    return [str(e.value) for e in entries if e.key == PARAMETER_COUNT_KEY]


@pytest.mark.parametrize(
    ("base", "fragment", "comment", "count"),
    [
        # A fragment adds the count and its note to a base with none
        (_pkg(_PROV), _pkg(_NOTE, "7"), f"{_NOTE}\n{_PROV}", ["7"]),
        (_pkg(None), _pkg(_NOTE, "7"), _NOTE, ["7"]),
        # Both have it: one note, the base's entry wins
        (
            _pkg(f"{_NOTE}\n{_PROV}", "7"),
            _pkg(f"{_NOTE}\nMetadata provenance: lr: Source: b", "9"),
            f"{_NOTE}\n{_PROV}; Metadata provenance: lr: Source: b",
            ["7"],
        ),
        (_pkg(f"{_NOTE}\n{_PROV}", "7"), _pkg("x", "9"), f"{_NOTE}\n{_PROV}; x", ["7"]),
        # A note with no `parameters` entry anywhere goes
        (_pkg(_PROV), _pkg(_NOTE), _PROV, []),
        (_pkg(None), _pkg(f"x; {_NOTE}; y"), "x; y", []),
        (_pkg(None), _pkg(_NOTE), None, []),
    ],
    ids=[
        "fragment-adds",
        "note-only",
        "both",
        "base-wins",
        "no-entry",
        "no-entry-segment",
        "no-entry-empty",
    ],
)
def test_the_merged_note(
    base: spdx3.ai_AIPackage,
    fragment: spdx3.ai_AIPackage,
    comment: str | None,
    count: list[str],
) -> None:
    props._merge_properties(base, fragment)
    assert base.comment == comment
    assert _count(base) == count
    assert (base.comment or "").count(_NOTE) == (1 if count else 0)


def test_a_re_merge_changes_nothing() -> None:
    base, fragment = _pkg(_PROV), _pkg(f"{_NOTE}\n{_PROV}", "7")
    props._merge_properties(base, fragment)
    once = base.comment
    assert once == f"{_NOTE}\n{_PROV}"
    props._merge_properties(base, fragment)
    assert base.comment == once


def test_only_a_model_package_is_rewritten() -> None:
    base = spdx3.software_Package(name="p", comment="a")
    base.spdxId = "urn:p"
    props._merge_properties(base, spdx3.software_Package(name="p", comment=_NOTE))
    assert base.comment == f"a; {_NOTE}"  # a plain merge, as for any element
