# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``WARNING`` twins of a project file's ``ERROR`` lines: a reader that
catches a coded error and reads on says its text again as a warning
(:func:`~pitloom.messages._emit.relay_extra` trusts a code only for a line
the entry holds at that level). ``config-malformed``'s three file lines
(TOML, INI, INI interpolation) have a twin; the two lines that name no file
(``--config``'s own INI text) do not. ``file-unreadable`` read ``for the
project metadata`` has both levels.

See also: tests/messages/test_metadata_relays.py (the relays that say them),
tests/messages/test_config.py (the other lines of the family).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.messages import READ_USES, CodedValueError, Line, trusted_message
from pitloom.messages._emit import relay_extra
from pitloom.messages.config import (
    CONFIG_MALFORMED,
    INI_FILE_LINE,
    INI_LINE,
    INTERPOLATION_FILE_LINE,
    INTERPOLATION_LINE,
    TOML_LINE,
)
from pitloom.messages.files import METADATA_USE, file_unreadable_error

pytestmark = pytest.mark.platform

_FILE = Path("proj") / "pyproject.toml"
_FILE_LINES = (TOML_LINE, INI_FILE_LINE, INTERPOLATION_FILE_LINE)
_VALUES = {"file": _FILE, "failure": ValueError("x"), "error": "e"}


def _error(line: Line) -> CodedValueError:
    """The ``ERROR`` of *line*, with the values its template names."""
    values = {k: v for k, v in _VALUES.items() if f"%({k})s" in line.template}
    return CodedValueError(CONFIG_MALFORMED, line=line, **values)


def _levels(template: str) -> set[str]:
    return {ln.level for ln in CONFIG_MALFORMED.lines if ln.template == template}


@pytest.mark.parametrize("line", _FILE_LINES, ids=["toml", "ini", "interpolation"])
def test_a_project_file_line_is_said_as_an_error_and_as_a_warning(line: Line) -> None:
    template = line.template
    assert _levels(template) == {"ERROR", "WARNING"}


@pytest.mark.parametrize("line", [INI_LINE, INTERPOLATION_LINE], ids=["ini", "interp"])
def test_a_line_that_names_no_file_has_no_twin(line: Line) -> None:
    """``--config``'s own text is never caught and read on past."""
    assert _levels(line.template) == {"ERROR"}
    assert relay_extra("config-malformed", "WARNING", str(_error(line))) is None


@pytest.mark.parametrize("line", _FILE_LINES, ids=["toml", "ini", "interpolation"])
def test_a_relayed_file_line_keeps_its_code_only_as_a_warning(line: Line) -> None:
    exc = _error(line)
    assert relay_extra("config-malformed", "WARNING", str(exc)) is not None
    assert trusted_message(f"WARNING: {exc} [config-malformed]") is not None
    assert trusted_message(f"ERROR: {exc} [config-malformed]") is not None


@pytest.mark.parametrize(
    "exc",
    [OSError(13, "denied"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")],
    ids=["unreadable", "not-utf8"],
)
def test_a_metadata_file_that_cannot_be_read_is_an_error_and_a_warning(
    exc: BaseException,
) -> None:
    error = file_unreadable_error(exc, file=_FILE, use=METADATA_USE)
    code = "file-unreadable/not-utf8" if isinstance(exc, UnicodeDecodeError) else None
    assert "for the project metadata" in str(error)
    assert METADATA_USE in READ_USES
    code = code or "file-unreadable"
    assert relay_extra(code, "WARNING", str(error)) is not None
    assert trusted_message(f"ERROR: {error} [{code}]") is not None
