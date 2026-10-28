# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The validation findings ``fragment validate`` and ``validate-wheel`` print
are the same on every run, and name the document as the user knows it.

See also: tests/cli/test_cli_fragment.py, tests/assemble/test_validate_wheel_cli.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pitloom.cli.commands import utils

# pylint: disable=protected-access


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Value 'x' not in list ['b', 'a', 'c']",
            "Value 'x' not in list ['a', 'b', 'c']",
        ),
        (
            "not in list ['<i/b>', '<i/a>'] and more",
            "not in list ['<i/a>', '<i/b>'] and more",
        ),
        ("not in list [] untouched", "not in list [] untouched"),
        ("no list here [b, a]", "no list here [b, a]"),
    ],
    ids=["sorted", "iris", "empty", "no-marker"],
)
def test_the_values_of_a_not_in_list_finding_are_sorted(
    message: str, expected: str
) -> None:
    assert utils._stable_message(message) == expected


class _Result:  # pylint: disable=too-few-public-methods
    """A failed validation result whose findings come in a run-dependent order."""

    def __init__(self, errors: list[SimpleNamespace]) -> None:
        self.errors = errors

    def __bool__(self) -> bool:
        return False


def _finding(source: str, message: str) -> SimpleNamespace:
    return SimpleNamespace(source=source, kind="shacl", message=message)


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0)])
def test_findings_are_printed_in_a_fixed_order_under_the_shown_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    order: tuple[int, ...],
) -> None:
    findings = [
        _finding("/tmp/x.spdx3.json", "b\nsecond line"),
        _finding("/tmp/x.spdx3.json", "a not in list ['z', 'y']"),
        _finding("/tmp/x.spdx3.json", "c"),
    ]
    fake = SimpleNamespace(
        validate=lambda *_a, **_k: _Result([findings[i] for i in order]),
        SpdxValidateError=ValueError,
    )
    monkeypatch.setattr(utils, "_import_spdx3_validate", lambda: fake)
    code = utils._validate_spdx3_documents(
        ["/tmp/x.spdx3.json"],
        check_merged=False,
        names={"/tmp/x.spdx3.json": "w.whl/m.spdx3.json"},
    )
    assert code == 1
    assert capsys.readouterr().err.splitlines() == [
        "ERROR: w.whl/m.spdx3.json: [shacl] a not in list ['y', 'z']",
        "ERROR: w.whl/m.spdx3.json: [shacl] b",
        "ERROR: second line",
        "ERROR: w.whl/m.spdx3.json: [shacl] c",
    ]
