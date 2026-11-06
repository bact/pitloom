# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What Pitloom relies on in LicenseID 0.7's public API: a failure here
is an upgrade to read before anything else.

A LicenseID without its packaged SPDX License List would leave every
declared value as written, silently in the SBOM, so the first test is that
the list is there.

See also: :mod:`pitloom.extract._license` and
:mod:`pitloom.extract._licenseid_relay` (the callers).
"""

from __future__ import annotations

import ast
from importlib.metadata import version
from pathlib import Path

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


def test_an_operand_has_the_keys_pitloom_reads() -> None:
    (operand,) = resolve("GPL-2.0", source="packaged")["operands"]
    assert (operand["text"], operand["expression"], operand["category"]) == (
        "GPL-2.0",
        "GPL-2.0",
        "assumed_only",
    )
    assert operand["candidates"] == ["GPL-2.0-only", "GPL-2.0-or-later"]


_SRC = Path(__file__).resolve().parent.parent / "src"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


def test_licenseid_is_the_only_reader_of_a_licence_expression() -> None:
    """No module of Pitloom parses an expression itself: ``py-spdx-license``
    is ``licenseid``'s dependency, not Pitloom's."""
    importers = sorted(
        str(path.relative_to(_SRC))
        for path in _SRC.rglob("*.py")
        if "py_spdx_license" in _imported_roots(path)
    )
    assert not importers
