# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``pitloom.core.file_names.sbom_base_name``: a base name loses one
trailing ``.spdx3.json`` and says so once.

See also: :mod:`tests.test_sbom_basename_surfaces` (every surface that
takes a base name).
"""

from __future__ import annotations

import re

import pytest

from pitloom.core.file_names import (
    CONFIG_BASENAME_PLACE,
    default_sbom_basename,
    is_plain_file_name,
    sbom_base_name,
    sbom_file_name,
)
from pitloom.messages import code_of
from pitloom.messages.config import ConfigPlace, Parameter
from tests.warning_helpers import logged_warnings

# The stage of a base name: read from a file, or given by a caller.
_FILE = CONFIG_BASENAME_PLACE
_PARAM = Parameter("--sbom-basename")
_WHERE = pytest.mark.parametrize("where", [_FILE, _PARAM], ids=["file", "parameter"])


def _label(where: ConfigPlace | Parameter) -> str:
    """How a warning names *where*: the place's text or the parameter's name."""
    return where.text if isinstance(where, ConfigPlace) else where.name


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("x", None),
        ("x.json", None),
        ("x.spdx3", None),
        ("x.spdx3.jsonx", None),
        ("x.spdx3.json", "x"),
        ("x.SPDX3.JSON", "x"),
        ("x.Spdx3.Json", "x"),
        ("x.spdx3.json.spdx3.json", "x.spdx3.json"),
        ("  x.spdx3.json  ", "x"),
        ("x .spdx3.json", "x"),
    ],
)
@_WHERE
def test_sbom_base_name_strips_once_and_warns_once(
    value: str,
    expected: str | None,
    where: ConfigPlace | Parameter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stripped value is announced by exactly one ``WARNING``, naming the
    label and both values; an unchanged value is returned as given, quietly."""
    assert sbom_base_name(value, where) == (value if expected is None else expected)
    # Read twice, as a config is: still one line.
    sbom_base_name(value, where)
    warnings = logged_warnings(caplog)
    if expected is None:
        assert not warnings
        return
    assert len(warnings) == 1
    assert _label(where) in warnings[0]
    assert repr(value) in warnings[0]
    assert repr(expected) in warnings[0]


@pytest.mark.parametrize(
    "value",
    [".spdx3.json", ".SPDX3.JSON", "  .spdx3.json", "..spdx3.json", "...spdx3.json"],
)
@pytest.mark.parametrize(
    ("where", "text", "code"),
    [
        (
            _FILE,
            "[tool.pitloom] sbom-basename: must be a plain file name",
            "config-invalid",
        ),
        (_PARAM, "--sbom-basename: must be a plain file name", "option-invalid"),
    ],
    ids=["file", "parameter"],
)
def test_sbom_base_name_refuses_only_the_extension(
    value: str,
    where: ConfigPlace | Parameter,
    text: str,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing is left to name the file: an error, not a warning; the stage
    (a file or a caller's value) picks the code."""
    with pytest.raises(ValueError, match=re.escape(text)) as exc:
        sbom_base_name(value, where)
    assert code_of(exc.value) == code
    assert not logged_warnings(caplog)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("x", "x.spdx3.json"), ("x.SPDX3.json", "x.spdx3.json")],
)
def test_sbom_file_name_adds_the_extension_once(value: str, expected: str) -> None:
    assert sbom_file_name(value, _FILE) == expected
    assert sbom_file_name(value) == expected  # the default place


@pytest.mark.parametrize(
    ("name", "plain"),
    [
        ("x", True),
        ("x.json", True),
        (" x ", True),
        ("com10", True),
        ("", False),
        ("..", False),
        ("a/b", False),
        ("a\\b", False),
        ("a:b", False),
        ("a\x00b", False),
        ("a\tb", False),
        ("a\nb", False),
        ("a\u202eb", False),
        ("x.", False),
        ("CON", False),
        ("nul.spdx3.json", False),
        ("Com1.txt", False),
        ("lpt9 .x", False),
    ],
)
def test_is_plain_file_name(name: str, plain: bool) -> None:
    """A name that stays a file name on Windows too: no separator, control
    character, trailing dot or device name."""
    assert is_plain_file_name(name) is plain


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [
        ("demo", "1.0", "demo-1.0"),
        ("demo", None, "demo"),
        ("demo", "", "demo"),
        (None, "1.0", "sbom-1.0"),
        (None, None, "sbom"),
        ("../../escaped", "1.0", ".._.._escaped-1.0"),
        ("a/b\\c:d", "1\n2", "a_b_c_d-1_2"),
        ("con", None, "sbom"),
        ("Nul", "", "sbom"),
        ("con", "1.0", "con-1.0"),
    ],
)
def test_default_sbom_basename(
    name: str | None, version: str | None, expected: str
) -> None:
    """Parts are escaped, so a project cannot choose a directory; a name that
    Windows would open as a device falls back to ``sbom``."""
    base = default_sbom_basename(name, version)
    assert base == expected
    assert is_plain_file_name(f"{base}.spdx3.json")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(" x", "x"), ("x ", "x"), ("\tx\t", "x")],
)
def test_sbom_base_name_trims_white_space_and_says_so(
    caplog: pytest.LogCaptureFixture, value: str, expected: str
) -> None:
    assert sbom_base_name(value, _FILE) == expected
    assert len(logged_warnings(caplog)) == 1
