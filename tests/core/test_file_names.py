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

from pitloom.core.file_names import sbom_base_name, sbom_file_name
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
