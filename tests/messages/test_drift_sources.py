# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on the source: every catalogued message is used, every place
that says a catalogued family's text goes through the catalogue, the evidence
reasons are catalogued or pending, and each pattern reads back as its entry.

See also: tests/messages/test_drift_records.py (run time) and
tests/messages/test_drift_quotes.py (docs and skills).
"""

from __future__ import annotations

import ast
import itertools

import pytest

from pitloom.core.evidence import REASON_CODES
from pitloom.messages import MESSAGES, trusted_message
from tests._message_drift import (
    cores,
    families_said_by,
    family_names,
    referenced_names,
    source_modules,
    string_constants,
)

#: Evidence reasons with no catalogued message yet. Shrink only: a reason
#: moves to the catalogue (its code equals the reason), never back.
PENDING = frozenset(
    {"over-cap", "timeout", "network-failed", "file-unreadable", "dir-unlistable"}
)

#: Modules that hold a catalogued family's text but say nothing: module path
#: under ``src/pitloom``, with why. Shrink only.
_NOT_EMITTERS = {
    # The reason NotAModel carries; emitters interpolate it.
    "extract/ai_model/reader.py",
}

_LOG_METHODS = frozenset({"warning", "info", "error", "critical", "exception", "log"})


def test_every_reason_is_catalogued_or_pending() -> None:
    codes = frozenset(MESSAGES)
    assert REASON_CODES <= codes | PENDING
    assert not codes & PENDING, "a catalogued reason leaves PENDING"
    assert PENDING <= REASON_CODES, "a retired reason leaves PENDING"


def test_every_family_is_exported_by_name() -> None:
    names = family_names()
    assert {m.family for m in MESSAGES.values()} == set(names)
    assert sum(len(n) for n in names.values()) == len(MESSAGES)


def test_every_catalogued_message_is_used_outside_the_catalogue() -> None:
    names = {n for found in family_names().values() for n in found}
    used: set[str] = set()
    for _, tree in source_modules():
        used |= referenced_names(tree) & names
    assert used == names, f"unused: {sorted(names - used)}"


def test_a_module_saying_a_family_text_uses_the_catalogue() -> None:
    """A string holding a pattern's wording sits in a module that refers to
    an entry of that family (the emit helper, its extra or its exception)."""
    names = family_names()
    found = []
    for path, tree in source_modules():
        said = families_said_by(string_constants(tree))
        if said and path not in _NOT_EMITTERS:
            used = referenced_names(tree)
            found += [
                f"{path}: {family}"
                for family in sorted(said)
                if not used & set(names[family])
            ]
    assert not found


def _says(node: ast.Call, family_cores: set[str]) -> bool:
    texts = [c for arg in node.args for c in string_constants(arg)]
    return any(
        piece in core or core in piece
        for text in texts
        for piece in cores(text)
        for core in family_cores
    )


def test_every_call_saying_a_family_text_carries_its_code() -> None:
    """A log call (above ``DEBUG``) whose own strings hold a family's
    wording passes ``extra=``; a raise does it as a ``CodedValueError``."""
    said = {
        c
        for entry in MESSAGES.values()
        for pattern in entry.patterns
        for c in cores(pattern)
    }
    bare = []
    for path, tree in source_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in _LOG_METHODS and _says(node, said):
                if not any(kw.arg == "extra" for kw in node.keywords):
                    bare.append(f"{path}:{node.lineno}: {name}")
            elif name in {"print_error"} and _says(node, said):
                if not any(kw.arg == "code" for kw in node.keywords):
                    bare.append(f"{path}:{node.lineno}: {name}")
    assert not bare


@pytest.mark.parametrize("entry", sorted(MESSAGES), ids=str)
def test_each_pattern_reads_back_as_its_entry(entry: str) -> None:
    """Every pattern, at every level of its entry, with a value for each
    ``%s``, is trusted as that entry; no pattern ends in a code."""
    message = MESSAGES[entry]
    for pattern, level in itertools.product(message.patterns, sorted(message.levels)):
        line = f"{level}: {pattern.replace('%s', 'v')} [{message.code}]"
        assert trusted_message(line) is message, line
        assert not pattern.rstrip().endswith("]")
    assert message.advice.startswith("Tell the user")


def test_no_two_entries_share_a_pattern() -> None:
    patterns = [p for m in MESSAGES.values() for p in m.patterns]
    assert len(patterns) == len(set(patterns))
