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

import pytest

from pitloom.core.file_names import (
    default_sbom_basename,
    is_plain_file_name,
    sbom_base_name,
    sbom_file_name,
)
from tests.warning_helpers import logged_warnings

_LABEL = "sbom-basename"


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
def test_sbom_base_name_strips_once_and_warns_once(
    value: str, expected: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """A stripped value is announced by exactly one ``WARNING``, naming the
    label and both values; an unchanged value is returned as given, quietly."""
    assert sbom_base_name(value, _LABEL) == (value if expected is None else expected)
    # Read twice, as a config is: still one line.
    sbom_base_name(value, _LABEL)
    warnings = logged_warnings(caplog)
    if expected is None:
        assert not warnings
        return
    assert len(warnings) == 1
    assert _LABEL in warnings[0]
    assert repr(value) in warnings[0]
    assert repr(expected) in warnings[0]


@pytest.mark.parametrize(
    "value",
    [".spdx3.json", ".SPDX3.JSON", "  .spdx3.json", "..spdx3.json", "...spdx3.json"],
)
def test_sbom_base_name_refuses_only_the_extension(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing is left to name the file: an error, not a warning."""
    with pytest.raises(ValueError, match="sbom-basename must be a file name"):
        sbom_base_name(value, _LABEL)
    assert not logged_warnings(caplog)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("x", "x.spdx3.json"), ("x.SPDX3.json", "x.spdx3.json")],
)
def test_sbom_file_name_adds_the_extension_once(value: str, expected: str) -> None:
    assert sbom_file_name(value, _LABEL) == expected


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
    assert sbom_base_name(value, _LABEL) == expected
    assert len(logged_warnings(caplog)) == 1
