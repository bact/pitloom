# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every line of the wheel and embedded-SBOM entries (catalogue PR 16) at
its longest still keeps its code: each name at NAME_CHARACTERS, each list
at SHOWN_NAMES names, each declared value at its excerpt, every character
the one that escapes longest, and the line stays under LONGEST_LINE, so
:func:`pitloom.messages.trusted_message` trusts it.

See also: tests/messages/test_wheels_core_hostile.py (one hostile value
per writer).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import pytest

from pitloom.messages import LONGEST_LINE, MESSAGES, trusted_message
from pitloom.messages import wheel_sboms as s
from pitloom.messages._field_writers import NAME_CHARACTERS, NAME_CUT_MARK
from pitloom.messages._types import Line
from pitloom.messages.files import BOM_DROPPED_LINE, MODE_NOT_RESTORED_LINE
from pitloom.messages.targets import (
    DOCUMENT_INVALID_LINE,
    MERGED_INVALID_LINE,
    NONE_VALIDATED_LINE,
    NOT_VALIDATED_LINE,
    say_validation_findings,
    say_validator_failure,
)
from pitloom.messages.wheels import SHOWN_NAMES

pytestmark = pytest.mark.platform  # escapes of names, as a path is shown

#: The code point whose escape is the longest (``\\U0001000c``, ten
#: characters for one).
_WIDE = "\U0001000c"
_LOG = logging.getLogger("pitloom.core.wheel_dist_info")
#: A name longer than the cap.
_NAME = _WIDE * (4 * NAME_CHARACTERS)
#: A path of the user's own (``FILE=``), uncapped: PATH_MAX characters.
_PATH = _WIDE * 4096

#: The longest value of each field the lines name. ``version`` is the
#: installed Hatchling's, ``option`` and ``extension`` are Pitloom's own:
#: none is attacker text.
_LONGEST: Mapping[str, object] = {
    "archive": _NAME,
    "member": _NAME,
    "later_member": _NAME,
    "install_name": _NAME,
    "sbom_filename": _NAME,
    "members": [_NAME] * (3 * SHOWN_NAMES),
    "project_paths": [_NAME] * (3 * SHOWN_NAMES),
    "exception_type": EOFError(),
    "identity_part": "version",
    "wheel_value": _WIDE * 100_000,
    "sbom_value": _WIDE * 100_000,
    "extension": ".spdx3.json",
    "skipped": 10**30,
    "number": 10**30,
    "minimum_version": "1.29.0",
    "version": "1.29.0rc1",
    "option": "--allow-signed-wheel",
    "file": _PATH,
    "path": _PATH,
    "failure": ValueError(_WIDE * 100_000),
}

#: The new entries; ``sbom-name-conflict`` is said only through its helper,
#: which cuts both its paths (below).
_CODES = (
    "wheel-unreadable",
    "wheel-invalid",
    "wheel-unusable",
    "wheel-unusable/signed",
    "dist-info-missing",
    "dist-info-ambiguous",
    "dist-info-conflict",
    "archive-member-unsafe",
    "archive-member-conflict",
    "archive-member-invalid",
    "wheel-sbom-missing",
    "wheel-sbom-ambiguous",
    "wheel-sbom-wrong-format",
    "wheel-sbom-unusable",
    "wheel-sbom-conflict",
    "wheel-sbom-conflict/held",
    "datetime-not-recordable",
    "library-unusable/hatchling",
    "json-malformed/bom",
    "file-unwritable/mode",
    "option-missing/project-dir",
)
#: The new lines of an older entry.
_ADDED: tuple[tuple[str, Line], ...] = (
    ("json-malformed/bom", BOM_DROPPED_LINE),
    ("file-unwritable/mode", MODE_NOT_RESTORED_LINE),
    ("sbom-invalid", DOCUMENT_INVALID_LINE),
    ("sbom-invalid", MERGED_INVALID_LINE),
    ("sbom-invalid", NOT_VALIDATED_LINE),
    ("sbom-invalid", NONE_VALIDATED_LINE),
)
_LINES = tuple(
    dict.fromkeys(
        [(code, line) for code in _CODES for line in MESSAGES[code].lines]
        + list(_ADDED)
    )
)


def _trusted(code: str, level: str, text: str) -> str:
    """The whole line, after checking it fits and keeps *code*."""
    line = f"{level}: {text} [{code}]"
    assert len(line) <= LONGEST_LINE
    assert trusted_message(line) is MESSAGES[code]
    return line


@pytest.mark.parametrize(
    ("code", "line"), _LINES, ids=[f"{c}-{i}" for i, (c, _) in enumerate(_LINES)]
)
def test_every_line_at_its_longest_keeps_its_code(code: str, line: Line) -> None:
    text = line.render({name: _LONGEST[name] for name in line.fields})
    _trusted(code, line.level, text)
    if line.fields & {"archive", "member", "members", "sbom_filename"}:
        assert NAME_CUT_MARK + "'" in text  # a name was cut


def test_the_longest_line_is_near_the_limit() -> None:
    # Guard against a vacuous pass: the list line is the longest one built.
    longest = max(
        len(line.render({name: _LONGEST[name] for name in line.fields}))
        for _, line in _LINES
    )
    assert longest > LONGEST_LINE * 3 // 4


def test_the_name_clash_error_cuts_both_paths() -> None:
    exc = s.sbom_name_conflict(_PATH, _PATH)
    line = _trusted("sbom-name-conflict", "ERROR", str(exc))
    assert line.count(NAME_CUT_MARK) == 2


def test_the_relay_cuts_the_document_name(capsys: pytest.CaptureFixture[str]) -> None:
    names = {"/t/a.json": _PATH}
    say_validation_findings([("/t/a.json", "schema", "m")], names=names)
    say_validator_failure(OSError("x"), file="/t/a.json", names=names)
    coded = [
        line
        for line in capsys.readouterr().err.splitlines()
        if line.endswith("[sbom-invalid]")
    ]
    assert len(coded) == 2
    for line in coded:
        assert len(line) <= LONGEST_LINE
        assert trusted_message(line) is MESSAGES["sbom-invalid"]
        assert NAME_CUT_MARK in line


def test_a_mismatch_past_the_cut_at_its_longest_keeps_its_code() -> None:
    """Both sides cut alike, each also shown from where they differ."""
    wheel, sbom = _WIDE * 100_000 + "b", _WIDE * 100_000 + "c" + _WIDE * 1000
    mismatch = s.IdentityMismatch("name", wheel, sbom)
    exc = s.identity_mismatch_error(_LOG, _NAME, [mismatch])
    line = _trusted("wheel-sbom-conflict", "ERROR", str(exc))
    assert line.count("(from character 100001: ") == 2
