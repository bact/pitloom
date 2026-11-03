# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What Pitloom relies on in ``licenseid`` 0.7's public API: a failure here
is an upgrade to read before anything else.

A ``licenseid`` without its packaged SPDX License List would leave every
declared value as written, silently in the SBOM, so the first test is that
the list is there.

See also: :mod:`pitloom.extract._license` and
:mod:`pitloom.extract._licenseid_relay` (the callers).
"""

from __future__ import annotations

from importlib.metadata import version

import pytest
from licenseid import Detection, LicenseIdWarning, resolve

_KEYS = {
    "schema",
    "input",
    "expression",
    "category",
    "trust",
    "steps",
    "expansions",
    "candidates",
    "operands",
    "resolver",
    "components",
    "lists",
    "reason",
}


def test_the_packaged_list_reads_a_declared_value() -> None:
    found = resolve("Apache2", source="packaged")
    assert (found["expression"], found["schema"]) == ("Apache-2.0", 2)
    assert set(found) == _KEYS
    assert [entry["source"] for entry in found["lists"]] == ["packaged"]
    assert found["resolver"]["version"] == version("licenseid")


@pytest.mark.parametrize("value", ["MIT", "Acme-Terms", ""])
def test_a_reason_is_given_exactly_when_there_is_no_expression(value: str) -> None:
    found = resolve(value, source="packaged")
    assert (found["reason"] is None) is (found["expression"] is not None)


def test_a_value_that_is_no_text_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        resolve(None, source="packaged")  # type: ignore[arg-type]


def test_a_warning_carries_its_parts() -> None:
    warning = LicenseIdWarning("database", "build v2 outdated", None, "run x")
    assert isinstance(warning, UserWarning)
    assert (warning.subject, warning.condition, warning.detail, warning.action) == (
        "database",
        "build v2 outdated",
        None,
        "run x",
    )
    assert str(warning) == "database: build v2 outdated; run x"


def test_a_detection_has_the_keys_pitloom_reads() -> None:
    assert {"expression", "score", "similarity", "coverage"} <= set(
        Detection.__annotations__
    )
