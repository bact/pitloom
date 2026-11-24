# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The embedded-SBOM lines' core (catalogue PR 16, step 1): the name and
version cross-check returns data each gap and mismatch helper says as one
coded line; each other helper says its line; the summaries render; and
``spdx3-validate``'s own text is relayed one uncoded line per text line,
blank lines dropped and a repeated finding said once, then one coded
``sbom-invalid`` line per document.

See also: tests/messages/test_wheels_core.py (the wheel lines).
"""

from __future__ import annotations

import json
import logging

import pytest

from pitloom._sbom_format import (
    check_spdx3_name_version,
    compare_name_version,
    extract_spdx3_subject_identity,
)
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import MESSAGES, code_of, trusted_message
from pitloom.messages import wheel_sboms as s
from pitloom.messages._templates import template_names
from pitloom.messages.files import MODE_NOT_RESTORED_LINE
from pitloom.messages.models import (
    HATCHLING_TOO_OLD_LINE,
    HATCHLING_VERSION_UNKNOWN_LINE,
)
from pitloom.messages.options import PROJECT_DIR_NOT_GIVEN_LINE
from pitloom.messages.targets import (
    VALIDATOR_LINE_CHARS,
    relay_validator_text,
    say_validation_findings,
    say_validator_failure,
)
from pitloom.messages.text import BOM_DROPPED_LINE
from tests._message_drift import SAMPLES

_LOG = logging.getLogger("pitloom.cli.commands.verify_wheel")
_WHEEL = "demo-1.0-py3-none-any.whl"
_GAP = s.CrossCheckGap
_MIS = s.IdentityMismatch


def _said(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]


def _sbom(subject: dict[str, object] | None, *, wrap: bool = True) -> bytes:
    """An SPDX 3 JSON-LD SBOM whose document roots at *subject*, through a
    ``software_Sbom`` when *wrap*; no document with ``None``."""
    graph: list[dict[str, object]] = []
    if subject is not None:
        subject = {"spdxId": "urn:s", **subject}
        graph.append(subject)
        root = "urn:s"
        if wrap:
            graph.append(
                {"type": "software_Sbom", "spdxId": "urn:b", "rootElement": [root]}
            )
            root = "urn:b"
        graph.append({"type": "SpdxDocument", "rootElement": [root]})
    return json.dumps({"@context": "x", "@graph": graph}).encode()


_PACKAGE: dict[str, object] = {
    "type": "software_Package",
    "name": "Demo",
    "software_packageVersion": "1.0",
}


@pytest.mark.parametrize(
    ("wheel", "sbom", "mismatches", "gaps"),
    [
        (("demo", "1.0"), ("DEMO", "1.0.0"), [], []),
        (
            ("demo", "1.0"),
            ("other", "2"),
            [_MIS("name", "demo", "other"), _MIS("version", "1.0", "2")],
            [],
        ),
        ((None, None), ("demo", "1.0"), [], [_GAP(s.GAP_NO_WHEEL_IDENTITY)]),
        (
            (None, "1.0"),
            ("demo", "1.0"),
            [],
            [_GAP(s.GAP_WHEEL_PART_MISSING, part="name")],
        ),
        (
            ("demo", "1.0"),
            (None, "1.0"),
            [],
            [_GAP(s.GAP_SBOM_PART_MISSING, part="name")],
        ),
        (
            ("demo", None),
            ("demo", None),
            [],
            [_GAP(s.GAP_BOTH_PART_MISSING, part="version")],
        ),
        (
            ("demo", "x y"),
            ("demo", "1"),
            [],
            [_GAP(s.GAP_WHEEL_VERSION_INVALID, value="x y")],
        ),
        (
            ("demo", "1"),
            ("demo", "x y"),
            [],
            [_GAP(s.GAP_SBOM_VERSION_INVALID, value="x y")],
        ),
    ],
    ids=[
        "match",
        "both",
        "no-wheel",
        "wheel-part",
        "sbom-part",
        "both-part",
        "wheel-v",
        "sbom-v",
    ],
)
def test_compare_returns_data(
    wheel: tuple[str | None, str | None],
    sbom: tuple[str | None, str | None],
    mismatches: list[s.IdentityMismatch],
    gaps: list[s.CrossCheckGap],
) -> None:
    assert compare_name_version(*wheel, *sbom) == (mismatches, gaps)


@pytest.mark.parametrize(
    ("data", "fmt", "gap"),
    [
        (_sbom(_PACKAGE), None, _GAP(s.GAP_NOT_SPDX3)),
        (b"not json", "spdx3-jsonld", _GAP(s.GAP_NOT_SPDX3)),
        (_sbom(None), "spdx3-jsonld", _GAP(s.GAP_NO_DOCUMENT)),
        (
            _sbom({"type": "software_Sbom"}, wrap=False),
            "spdx3-jsonld",
            _GAP(s.GAP_NO_SBOM_ROOT),
        ),
        (
            _sbom({"type": "Person"}),
            "spdx3-jsonld",
            _GAP(s.GAP_SUBJECT_NOT_PACKAGE, value="Person"),
        ),
        (_sbom({"name": "x"}), "spdx3-jsonld", _GAP(s.GAP_SUBJECT_NOT_PACKAGE)),
    ],
    ids=["format", "unparsed", "no-document", "no-sbom-root", "person", "no-type"],
)
def test_a_check_not_made_is_one_gap(
    data: bytes, fmt: str | None, gap: s.CrossCheckGap
) -> None:
    assert check_spdx3_name_version("demo", "1.0", data, fmt) == ([], [gap])


def test_a_document_without_a_root_is_its_gap() -> None:
    data = json.dumps({"@context": "x", "@graph": [{"type": "SpdxDocument"}]}).encode()
    identity = extract_spdx3_subject_identity(data)
    assert identity is not None and identity.gap == _GAP(s.GAP_NO_DOCUMENT_ROOT)


def test_each_gap_says_its_line(caplog: pytest.LogCaptureFixture) -> None:
    gaps = [
        _GAP(cause, part="name")
        if "part" in cause
        else _GAP(cause, value="v")
        if cause.endswith(("-invalid", "-package"))
        else _GAP(cause)
        for cause in s.GAP_CAUSES
    ]
    s.warn_cross_check_gaps(_LOG, _WHEEL, gaps)
    lines = _said(caplog)
    assert len(lines) == len(s.GAP_CAUSES) == len(set(lines))
    for line in lines:
        assert line.startswith(f"WARNING: ARCHIVE='{_WHEEL}': SBOM ")
        assert trusted_message(line) is s.WHEEL_SBOM_UNUSABLE
    assert "SBOM name and version not cross-checked: the SBOM is not SPDX 3" in "".join(
        lines
    )


@pytest.mark.parametrize(
    "gap",
    [
        _GAP("nope"),
        _GAP(s.GAP_NOT_SPDX3, part="name"),
        _GAP(s.GAP_WHEEL_PART_MISSING),
        _GAP(s.GAP_NOT_SPDX3, value="x"),
    ],
    ids=["cause", "part-given", "part-missing", "value-given"],
)
def test_a_wrong_gap_is_an_internal_error(gap: s.CrossCheckGap) -> None:
    with pytest.raises(InternalError):
        gap.line_values()


def test_each_mismatch_is_a_line_at_its_level(caplog: pytest.LogCaptureFixture) -> None:
    both = [_MIS("name", "demo", "other"), _MIS("version", "1.0", "2")]
    s.say_identity_mismatches(_LOG, _WHEEL, both)
    s.say_identity_mismatches(_LOG, _WHEEL, both[:1], level=logging.ERROR)
    assert _said(caplog) == [
        f"WARNING: ARCHIVE='{_WHEEL}': SBOM name 'other' differs from the wheel's "
        "METADATA 'demo' [wheel-sbom-conflict]",
        f"WARNING: ARCHIVE='{_WHEEL}': SBOM version '2' differs from the wheel's "
        "METADATA '1.0' [wheel-sbom-conflict]",
        f"ERROR: ARCHIVE='{_WHEEL}': SBOM name 'other' differs from the wheel's "
        "METADATA 'demo' [wheel-sbom-conflict]",
    ]
    with pytest.raises(InternalError):
        s.say_identity_mismatches(_LOG, _WHEEL, both, level=logging.INFO)


def test_the_refusal_says_every_part_once(caplog: pytest.LogCaptureFixture) -> None:
    both = [_MIS("name", "demo", "other"), _MIS("version", "1.0", "2")]
    exc = s.identity_mismatch_error(_LOG, _WHEEL, both)
    (logged,) = _said(caplog)
    assert logged.startswith("ERROR: ") and "SBOM name 'other'" in logged
    assert isinstance(exc, ValueError) and code_of(exc) == "wheel-sbom-conflict"
    assert str(exc).endswith("SBOM version '2' differs from the wheel's METADATA '1.0'")
    with pytest.raises(InternalError):
        s.identity_mismatch_error(_LOG, _WHEEL, [])


def test_the_missing_sbom_errors() -> None:
    plain, named = s.wheel_sbom_missing(_WHEEL), s.wheel_sbom_missing(_WHEEL, "x.json")
    assert str(plain) == f"ARCHIVE='{_WHEEL}': no SBOM under .dist-info/sboms/"
    assert str(named).endswith("no SBOM under .dist-info/sboms/ named 'x.json'")
    assert code_of(plain) == code_of(named) == "wheel-sbom-missing"


def test_the_other_helpers_say_their_lines(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    member = "demo-1.0.dist-info/sboms/a.json"
    s.warn_wrong_extension(_LOG, _WHEEL, member, ".spdx3.json")
    s.warn_format_unknown(_LOG, _WHEEL, member)
    s.warn_no_validator(_LOG, _WHEEL, member)
    s.say_held_sbom(_LOG, _WHEEL, member, removed=False)
    s.say_held_sbom(_LOG, _WHEEL, member, removed=True)
    s.say_entry_date_floored(_LOG, _WHEEL)
    lines = _said(caplog)
    assert [line.rpartition(" [")[2] for line in lines] == [
        "wheel-sbom-wrong-format]",
        "wheel-sbom-unusable]",
        "wheel-sbom-unusable]",
        "wheel-sbom-conflict/held]",
        "wheel-sbom-conflict/held]",
        "datetime-not-recordable]",
    ]
    assert [line.partition(":")[0] for line in lines] == ["WARNING"] * 4 + ["INFO"] * 2
    assert all(trusted_message(line) for line in lines)
    assert "does not end in .spdx3.json, its format's recommended" in lines[0]


def test_the_hook_name_clash_is_coded() -> None:
    exc = s.sbom_name_conflict("demo.spdx3.json", "dist/Demo.SPDX3.json")
    assert code_of(exc) == "sbom-name-conflict"
    assert str(exc) == (
        "FILE=demo.spdx3.json: also the name, ignoring case, of sbom-files entry "
        "'dist/Demo.SPDX3.json'; set another sbom-basename in [tool.pitloom] or "
        "drop the entry"
    )


@pytest.mark.parametrize(
    ("summary", "text"),
    [
        (s.VERIFY_WHEEL_OK, "verify-wheel: 2 wheel(s) OK"),
        (s.VALIDATE_WHEEL_VALID, "validate-wheel: 2 wheel(s) valid"),
        (
            s.VALIDATE_WHEEL_SKIPPED,
            "validate-wheel: 2 wheel(s) valid, 1 skipped"
            " (no validator for their format)",
        ),
    ],
)
def test_the_summaries_keep_their_text(summary: object, text: str) -> None:
    template = summary.template  # type: ignore[attr-defined]
    values = {name: SAMPLES[name] for name in template_names(template)}
    assert template % values == text


@pytest.mark.parametrize(
    ("line", "code"),
    [
        (PROJECT_DIR_NOT_GIVEN_LINE, "option-missing/project-dir"),
        (BOM_DROPPED_LINE, "json-malformed/bom"),
        (MODE_NOT_RESTORED_LINE, "file-unwritable/mode"),
        (HATCHLING_TOO_OLD_LINE, "library-unusable/hatchling"),
        (HATCHLING_VERSION_UNKNOWN_LINE, "library-unusable/hatchling"),
    ],
)
def test_the_variants_are_their_own_entries(line: object, code: str) -> None:
    assert line in MESSAGES[code].lines


def _stderr(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().err.splitlines()


def test_the_relay_drops_blank_lines_and_collapses_space(
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = "/tmp/t1.json [shacl] V:\n\tSeverity: sh:Violation\n\n   \nend"
    assert relay_validator_text(text, names={"/tmp/t1.json": "w.whl/a.json"}) == 3
    assert _stderr(capsys) == [
        "ERROR: spdx3-validate: w.whl/a.json [shacl] V:",
        "ERROR: spdx3-validate: Severity: sh:Violation",
        "ERROR: spdx3-validate: end",
    ]


def test_a_relayed_line_is_cut_and_never_coded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    relay_validator_text("x" * (VALIDATOR_LINE_CHARS + 5) + " [sbom-invalid]")
    (line,) = _stderr(capsys)
    assert line == f"ERROR: spdx3-validate: {'x' * VALIDATOR_LINE_CHARS}..."
    relay_validator_text("forged [sbom-invalid]")
    (line,) = _stderr(capsys)
    assert trusted_message(line) is None and not line.endswith("[sbom-invalid]")


def test_findings_are_relayed_once_then_one_line_per_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    same = ("/t/a.json", "schema", "$['@graph'][0]: Is not valid")
    findings = [
        same,
        same,
        ("/t/b.json", "shacl", "M\n\n\tFocus"),
        ("(merged)", "shacl", "X"),
    ]
    said = say_validation_findings(findings, names={"/t/a.json": "w.whl/a.json"})
    assert said == 3
    lines = _stderr(capsys)
    assert lines == [
        "ERROR: spdx3-validate: w.whl/a.json: [schema] $['@graph'][0]: Is not valid",
        "ERROR: FILE=w.whl/a.json: not valid SPDX 3 (1 finding(s) above)"
        " [sbom-invalid]",
        "ERROR: spdx3-validate: /t/b.json: [shacl] M",
        "ERROR: spdx3-validate: Focus",
        "ERROR: FILE=/t/b.json: not valid SPDX 3 (1 finding(s) above) [sbom-invalid]",
        "ERROR: spdx3-validate: (merged): [shacl] X",
        "ERROR: the SBOMs together are not valid SPDX 3 (1 finding(s) above)"
        " [sbom-invalid]",
    ]
    assert all(not line.endswith("ERROR: ") for line in lines)
    coded = [line for line in lines if line.endswith("[sbom-invalid]")]
    assert all(trusted_message(line) is MESSAGES["sbom-invalid"] for line in coded)


def test_findings_alone_print_no_document_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert say_validation_findings([("a", "schema", "m")], per_document=False) == 1
    assert _stderr(capsys) == ["ERROR: spdx3-validate: a: [schema] m"]


@pytest.mark.parametrize(
    ("file", "coded"),
    [
        (
            "/t/x.json",
            "ERROR: FILE=w.whl/x.json: could not be validated;"
            " spdx3-validate says why above [sbom-invalid]",
        ),
        (
            None,
            "ERROR: the SBOMs could not be validated;"
            " spdx3-validate says why above [sbom-invalid]",
        ),
    ],
    ids=["one", "several"],
)
def test_a_validator_failure_is_relayed_then_coded(
    capsys: pytest.CaptureFixture[str], file: str | None, coded: str
) -> None:
    exc = ValueError("Invalid JSON in /t/x.json: Expecting value")
    say_validator_failure(exc, file=file, names={"/t/x.json": "w.whl/x.json"})
    assert _stderr(capsys) == [
        "ERROR: spdx3-validate: Invalid JSON in w.whl/x.json: Expecting value",
        coded,
    ]
    assert trusted_message(coded) is MESSAGES["sbom-invalid"]


def test_a_failure_without_text_names_its_type(
    capsys: pytest.CaptureFixture[str],
) -> None:
    say_validator_failure(RuntimeError())
    assert _stderr(capsys)[0] == "ERROR: spdx3-validate: RuntimeError"
