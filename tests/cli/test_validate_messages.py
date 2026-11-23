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
        # a value holding a quote or a bracket: still one value
        ("not in list ['b', \"it's\", 'a']", "not in list ['a', 'b', \"it's\"]"),
        ("not in list ['b', 'a]c', 'd']", "not in list ['a]c', 'b', 'd']"),
        ("not in list [1, 'a'] not strings", "not in list [1, 'a'] not strings"),
        ("not in list ['a' unclosed", "not in list ['a' unclosed"),
        ("not in list x", "not in list x"),  # no bracket after the marker
        ("not in list [" + "a]" * 60, "not in list [" + "a]" * 60),  # search bound
    ],
    ids=[
        "sorted",
        "iris",
        "empty",
        "no-marker",
        "quote",
        "bracket",
        "not-strings",
        "unclosed",
        "no-bracket",
        "bound",
    ],
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
        "ERROR: spdx3-validate: w.whl/m.spdx3.json: [shacl] a not in list ['y', 'z']",
        "ERROR: spdx3-validate: w.whl/m.spdx3.json: [shacl] b",
        "ERROR: spdx3-validate: second line",
        "ERROR: spdx3-validate: w.whl/m.spdx3.json: [shacl] c",
        "ERROR: FILE=w.whl/m.spdx3.json: not valid SPDX 3 (3 finding(s) above) "
        "[sbom-invalid]",
    ]


def _fake_validator(result: object) -> SimpleNamespace:
    """A stand-in for ``spdx3_validate`` whose ``validate`` gives *result*, or
    raises it when it is an exception."""

    def validate(*_a: object, **_k: object) -> object:
        if isinstance(result, Exception):
            raise result
        return result

    return SimpleNamespace(validate=validate, SpdxValidateError=ValueError)


def test_a_blank_line_is_dropped_and_a_repeat_said_once(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The empty line of a SHACL finding is not an ``ERROR:`` line, and a
    finding the validator gives twice is said once and counted once."""
    same = _finding("p", "x\n\n  y")
    fake = _fake_validator(_Result([same, same, _finding("p", "z")]))
    monkeypatch.setattr(utils, "_import_spdx3_validate", lambda: fake)
    assert utils._validate_spdx3_documents(["p"], check_merged=False) == 1
    assert capsys.readouterr().err.splitlines() == [
        "ERROR: spdx3-validate: p: [shacl] x",
        "ERROR: spdx3-validate: y",
        "ERROR: spdx3-validate: p: [shacl] z",
        "ERROR: FILE=p: not valid SPDX 3 (2 finding(s) above) [sbom-invalid]",
    ]


@pytest.mark.parametrize(
    ("per_document", "last"),
    [
        (True, "ERROR: FILE=p: not valid SPDX 3 (1 finding(s) above) [sbom-invalid]"),
        (False, "ERROR: spdx3-validate: p: [shacl] c"),
    ],
    ids=["coded-line", "left-to-the-caller"],
)
def test_per_document_gates_the_coded_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    per_document: bool,
    last: str,
) -> None:
    fake = _fake_validator(_Result([_finding("p", "c")]))
    monkeypatch.setattr(utils, "_import_spdx3_validate", lambda: fake)
    code = utils._validate_spdx3_documents(
        ["p"], check_merged=False, per_document=per_document
    )
    assert code == 1
    assert capsys.readouterr().err.splitlines()[-1] == last


@pytest.mark.parametrize(
    ("paths", "per_document", "last"),
    [
        (
            ["a"],
            True,
            "ERROR: FILE=a: could not be validated; spdx3-validate says "
            "why above [sbom-invalid]",
        ),
        (
            ["a", "b"],
            True,
            "ERROR: the SBOMs could not be validated; spdx3-validate "
            "says why above [sbom-invalid]",
        ),
        (["a"], False, "ERROR: spdx3-validate: cannot load"),
    ],
    ids=["one", "several", "left-to-the-caller"],
)
def test_a_document_the_validator_cannot_load_says_why_then_one_coded_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    paths: list[str],
    per_document: bool,
    last: str,
) -> None:
    fake = _fake_validator(ValueError("cannot load"))
    monkeypatch.setattr(utils, "_import_spdx3_validate", lambda: fake)
    code = utils._validate_spdx3_documents(
        paths, check_merged=True, per_document=per_document
    )
    assert code == 1
    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "ERROR: spdx3-validate: cannot load"
    assert lines[-1] == last


def test_the_merged_findings_have_their_own_coded_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _fake_validator(_Result([_finding("(merged)", "m")]))
    monkeypatch.setattr(utils, "_import_spdx3_validate", lambda: fake)
    assert utils._validate_spdx3_documents(["a", "b"], check_merged=True) == 1
    assert capsys.readouterr().err.splitlines()[-1] == (
        "ERROR: the SBOMs together are not valid SPDX 3 (1 finding(s) above) "
        "[sbom-invalid]"
    )
