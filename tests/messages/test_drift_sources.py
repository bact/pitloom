# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard on the source: every catalogued message is used, every place
that says a catalogued family's text goes through the catalogue, the evidence
reasons are catalogued or pending, each line reads back as its entry, and
each entry's advice fits its actor.

See also: tests/messages/test_drift_records.py (run time) and
tests/messages/test_drift_quotes.py (docs and skills).
"""

from __future__ import annotations

import ast

import pytest

from pitloom.core.evidence import REASON_CODES
from pitloom.messages import FRAMES, MESSAGES, trusted_message
from tests._message_drift import (
    SAMPLES,
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


def _says(node: ast.Call) -> bool:
    """Whether a call's own strings hold a family's line text whole."""
    texts = [c for arg in node.args for c in string_constants(arg)]
    return bool(families_said_by(texts, whole=True))


def test_every_call_saying_a_family_text_carries_its_code() -> None:
    """A log call (above ``DEBUG``) or ``print_error`` whose own strings
    hold a family's text says it through the catalogue instead (``emit``,
    ``CodedValueError``), or at least carries the code; a sibling message
    sharing a tail (``not listed as an AI model``) is not one."""
    bare = []
    for path, tree in source_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _says(node):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            key = {"print_error": "code"}.get(name, "extra")
            if (name in _LOG_METHODS or name == "print_error") and not any(
                kw.arg == key for kw in node.keywords
            ):
                bare.append(f"{path}:{node.lineno}: {name}")
    assert not bare


@pytest.mark.parametrize("entry", sorted(MESSAGES), ids=str)
def test_each_line_reads_back_as_its_entry(entry: str) -> None:
    """Every line, with a sample value for each field, alone and after each
    frame of its level, is trusted as its entry, and at no other level."""
    message = MESSAGES[entry]
    for line in message.lines:
        text = line.render({name: SAMPLES[name] for name in line.fields})
        heads = [
            frame.render({name: SAMPLES[name] for name in frame.fields})
            for frame in FRAMES
            if line.level in frame.levels
        ]
        for head in ["", *heads]:
            printed = f"{line.level}: {head}{text} [{message.code}]"
            assert trusted_message(printed) is message, printed
        for other in {"ERROR", "WARNING", "INFO"} - message.levels:
            assert trusted_message(f"{other}: {text} [{message.code}]") is None


@pytest.mark.parametrize("entry", sorted(MESSAGES), ids=str)
def test_the_advice_fits_its_actor(entry: str) -> None:
    """``user``: an agent relays the advice and does not act on it;
    ``caller``: the program that ran the command may fix it itself."""
    message = MESSAGES[entry]
    relayed = message.advice.startswith("Tell the user")
    if message.actor == "user":
        assert relayed and " Do not " in message.advice, message.advice
    else:
        assert not relayed, message.advice


def test_no_two_entries_share_a_line() -> None:
    lines = [(ln.level, ln.template) for m in MESSAGES.values() for ln in m.lines]
    assert len(lines) == len(set(lines))
