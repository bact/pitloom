# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The embedded-SBOM families (``wheel-sbom-*``, ``datetime-not-recordable``,
``option-missing/project-dir``, ``file-unwritable/mode``, ``sbom-invalid``
and the relay of ``spdx3-validate``'s text) on ``verify-wheel``,
``validate-wheel`` and ``embed-wheel`` (single wheel, batch, ``--sbom``,
``--verify``, ``--validate``), through ``__main__.main()``: level, subject
(``ARCHIVE=`` the file name, ``ENTRY=`` the member), code and exit status;
a mismatch says one line per differing part; verify stays structural and
validate stays content.

See also: tests/messages/test_wheels_surfaces.py (the wheel lines),
tests/messages/test_wheels_surfaces_library.py (library, hook, build) and
tests/messages/test_wheels_core_sboms.py (the helpers).
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

from pitloom.messages import trusted_message
from tests._wheel_fixtures import (
    DIST_INFO,
    WHEEL_FILE,
    make_wheel,
    run_cli,
    spdx3_sbom,
)

pytestmark = [
    pytest.mark.platform,  # ZIP archives, member names, stderr lines
    pytest.mark.usefixtures("offline_spdx3_validate"),  # no socket for the schema
]

_ARCHIVE = f"ARCHIVE='{WHEEL_FILE}'"
_SBOMS = f"{DIST_INFO}/sboms"
_STATUS = f"WHEEL={WHEEL_FILE} STATUS="


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.chdir(tmp_path)  # no pyproject.toml here: no project-dir note


def _given(tmp_path: Path, content: bytes, name: str = "given.json") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


# -- missing, ambiguous: the caller's mistake, an ERROR on verify and validate -


@pytest.mark.parametrize("command", ["verify-wheel", "validate-wheel"])
@pytest.mark.parametrize(
    ("args", "said"),
    [
        ([], "no SBOM under .dist-info/sboms/"),
        (
            ["--sbom-filename", "x.spdx3.json"],
            "no SBOM under .dist-info/sboms/ named 'x.spdx3.json'",
        ),
    ],
    ids=["none", "named"],
)
def test_no_sbom_is_an_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    args: list[str],
    said: str,
) -> None:
    done = run_cli(monkeypatch, capsys, command, make_wheel(tmp_path), *args)
    assert done.status == 1 and done.out == [f"{_STATUS}failed"]
    assert done.err == [
        f"ERROR: loom {command}: {_ARCHIVE}: {said} [wheel-sbom-missing]"
    ]


@pytest.mark.parametrize("command", ["verify-wheel", "validate-wheel"])
def test_several_sboms_are_ambiguous_unless_one_is_named(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    sboms = {"a.spdx3.json": spdx3_sbom(), "b.spdx3.json": spdx3_sbom()}
    wheel = make_wheel(tmp_path, sboms=sboms)
    done = run_cli(monkeypatch, capsys, command, wheel)
    assert done.status == 1
    assert done.err == [
        f"ERROR: loom {command}: {_ARCHIVE}: 2 SBOMs under .dist-info/sboms/ "
        f"('{_SBOMS}/a.spdx3.json', '{_SBOMS}/b.spdx3.json'); pass "
        "--sbom-filename [wheel-sbom-ambiguous]"
    ]
    named = run_cli(
        monkeypatch, capsys, command, wheel, "--sbom-filename", "a.spdx3.json"
    )
    assert "wheel-sbom-ambiguous" not in named.codes  # valid or not, it is read


# -- wrong format, unusable, conflict ------------------------------------------


def test_verify_says_a_wrong_extension_and_an_unknown_format_as_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wrong = make_wheel(tmp_path / "w", sboms={"x.json": spdx3_sbom()})
    done = run_cli(monkeypatch, capsys, "verify-wheel", wrong)
    assert done.status == 0 and done.out == [f"{_STATUS}ok"]
    assert done.err[:-1] == [
        f"WARNING: {_ARCHIVE} ENTRY='{_SBOMS}/x.json': SBOM does not end in "
        ".spdx3.json, its format's recommended extension [wheel-sbom-wrong-format]"
    ]
    assert done.err[-1] == "INFO: verify-wheel: 1 wheel(s) OK"
    unknown = make_wheel(tmp_path / "u", sboms={"x.spdx3.json": b'{"bomFormat": 1}'})
    done = run_cli(monkeypatch, capsys, "verify-wheel", unknown)
    assert done.status == 0
    assert done.err[:2] == [
        f"WARNING: {_ARCHIVE} ENTRY='{_SBOMS}/x.spdx3.json': SBOM format not "
        "recognised; extension not checked [wheel-sbom-unusable]",
        f"WARNING: {_ARCHIVE}: SBOM name and version not cross-checked: the SBOM is "
        "not SPDX 3 JSON-LD [wheel-sbom-unusable]",
    ]


@pytest.mark.parametrize(
    ("sbom", "why"),
    [
        (
            spdx3_sbom(version=None),
            "SBOM version not cross-checked: the SBOM's subject states none",
        ),
        (
            spdx3_sbom(version="not a version"),
            "SBOM version not cross-checked: the SBOM's version 'not a version' "
            "is not a PEP 440 version",
        ),
    ],
    ids=["no-version", "not-pep-440"],
)
def test_an_identity_that_cannot_be_compared_is_a_warning_even_when_it_must_not_differ(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sbom: bytes,
    why: str,
) -> None:
    wheel = make_wheel(tmp_path, sboms={"s.spdx3.json": sbom})
    done = run_cli(monkeypatch, capsys, "verify-wheel", wheel, "--fail-on-mismatch")
    assert done.status == 0  # "could not check" is not "checked and wrong"
    assert done.err[0] == f"WARNING: {_ARCHIVE}: {why} [wheel-sbom-unusable]"


@pytest.mark.parametrize(
    ("sbom_name", "sbom_version", "parts"),
    [
        ("other", "1.0", ["name 'other' differs from the wheel's METADATA 'demo'"]),
        ("demo", "2.0", ["version '2.0' differs from the wheel's METADATA '1.0'"]),
        (
            "other",
            "2.0",
            [
                "name 'other' differs from the wheel's METADATA 'demo'",
                "version '2.0' differs from the wheel's METADATA '1.0'",
            ],
        ),
    ],
    ids=["name", "version", "both"],
)
def test_a_mismatch_says_one_line_per_differing_part_at_the_level_the_command_gives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sbom_name: str,
    sbom_version: str,
    parts: list[str],
) -> None:
    sbom = spdx3_sbom(sbom_name, sbom_version)
    wheel = make_wheel(tmp_path / "w", sboms={"s.spdx3.json": sbom})
    lines = [f"{_ARCHIVE}: SBOM {part} [wheel-sbom-conflict]" for part in parts]
    verify = run_cli(monkeypatch, capsys, "verify-wheel", wheel)
    assert verify.status == 0
    assert verify.err[: len(parts)] == [f"WARNING: {x}" for x in lines]
    failing = run_cli(monkeypatch, capsys, "verify-wheel", wheel, "--fail-on-mismatch")
    assert failing.status == 1
    assert failing.err == [f"ERROR: loom verify-wheel: {x}" for x in lines]
    # embed-wheel --sbom: refused before anything is written, or a warning.
    target = make_wheel(tmp_path / "t")
    before = target.read_bytes()
    given = _given(tmp_path, sbom)
    refused = run_cli(monkeypatch, capsys, "embed-wheel", target, "--sbom", given)
    assert refused.status == 1 and target.read_bytes() == before
    assert refused.err == [f"ERROR: loom embed-wheel: {x}" for x in lines]
    allowed = run_cli(
        monkeypatch, capsys, "embed-wheel", target, "--sbom", given, "--allow-mismatch"
    )
    assert allowed.status == 0 and allowed.err == [f"WARNING: {x}" for x in lines]


# -- held SBOMs, the ZIP date floor, the project-dir note, the file mode -------


@pytest.mark.parametrize(
    ("types", "line"),
    [
        (
            ["source"],
            "WARNING: {a} ENTRY='{s}/mine.spdx3.json': a Pitloom SBOM, not a build "
            "or analyzed one of this wheel's name and version; kept "
            "[wheel-sbom-conflict/held]",
        ),
        (
            ["build"],
            "INFO: {a} ENTRY='{s}/mine.spdx3.json': an earlier Pitloom SBOM of "
            "this wheel; removed [wheel-sbom-conflict/held]",
        ),
    ],
    ids=["kept", "removed"],
)
def test_another_pitloom_sbom_in_the_wheel_is_said_kept_or_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    types: list[str],
    line: str,
) -> None:
    wheel = make_wheel(
        tmp_path, sboms={"mine.spdx3.json": spdx3_sbom(pitloom_types=types)}
    )
    done = run_cli(monkeypatch, capsys, "embed-wheel", wheel)
    assert done.status == 0
    assert done.err == [line.format(a=_ARCHIVE, s=_SBOMS)]
    kept = f"{_SBOMS}/mine.spdx3.json" in zipfile.ZipFile(wheel).namelist()
    assert kept is (types == ["source"])


def test_an_embed_on_the_zip_date_floor_says_so_once_per_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    one, two = make_wheel(tmp_path, name="one"), make_wheel(tmp_path, name="two")
    done = run_cli(monkeypatch, capsys, "embed-wheel", one, two)
    assert done.status == 0
    assert done.err == [
        f"INFO: ARCHIVE='{n}-1.0-py3-none-any.whl': SBOM entry dated 1980-01-01, "
        "the earliest a ZIP archive can record; the SBOM's created keeps the true "
        "date [datetime-not-recordable]"
        for n in ("one", "two")
    ]
    with zipfile.ZipFile(one) as zf:
        assert zf.getinfo("one-1.0.dist-info/sboms/one-1.0.spdx3.json").date_time == (
            1980,
            1,
            1,
            0,
            0,
            0,
        )


def test_an_embed_is_byte_for_byte_repeatable_on_a_pinned_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    digests = set()
    for run in "ab":
        wheel = make_wheel(tmp_path / run)
        assert run_cli(monkeypatch, capsys, "embed-wheel", wheel).status == 0
        digests.add(hashlib.sha256(wheel.read_bytes()).hexdigest())
    assert len(digests) == 1


def test_the_project_dir_note_is_one_info_when_a_pyproject_is_here(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "other"\nversion = "9"\n', encoding="utf-8"
    )
    wheels = [make_wheel(tmp_path / "w", name=n) for n in ("one", "two")]
    done = run_cli(monkeypatch, capsys, "embed-wheel", *wheels)
    note = [e for e in done.err if e.endswith("[option-missing/project-dir]")]
    assert note == [
        "INFO: --project-dir not given; the SBOM is built from the wheel alone, not "
        "from the project in the current directory [option-missing/project-dir]"
    ]
    quiet = run_cli(monkeypatch, capsys, "embed-wheel", wheels[0], "--project-dir", ".")
    assert "option-missing/project-dir" not in quiet.codes


# -- the validator's text and the summaries ------------------------------------


_BAD_VERSION = {
    "@context": "https://spdx.org/rdf/9.9.9/spdx-context.jsonld",
    "@graph": [],
}


def _sbom_of(document: dict[str, object]) -> bytes:
    return json.dumps(document).encode("utf-8")


def test_validate_relays_each_finding_then_says_the_document_is_not_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path, sboms={"s.spdx3.json": spdx3_sbom()})
    done = run_cli(monkeypatch, capsys, "validate-wheel", wheel)
    shown = f"{WHEEL_FILE}/{_SBOMS}/s.spdx3.json"
    assert done.status == 1 and done.out == [f"{_STATUS}failed"]
    *findings, verdict = done.err
    assert findings  # the validator's own text, line by line
    assert all(
        f.startswith("ERROR: loom validate-wheel: spdx3-validate: ") for f in findings
    )
    assert all(f.split("spdx3-validate:", 1)[1].strip() for f in findings)  # none empty
    assert re.fullmatch(
        rf"ERROR: loom validate-wheel: FILE={re.escape(shown)}: not valid SPDX 3 "
        r"\(\d+ finding\(s\) above\) \[sbom-invalid\]",
        verdict,
    )
    assert done.codes == ["sbom-invalid"]  # a relayed finding carries no code


def test_validate_says_when_the_document_could_not_be_validated_at_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path, sboms={"s.spdx3.json": _sbom_of(_BAD_VERSION)})
    done = run_cli(monkeypatch, capsys, "validate-wheel", wheel)
    shown = f"{WHEEL_FILE}/{_SBOMS}/s.spdx3.json"
    assert done.status == 1
    assert done.err[-1] == (
        f"ERROR: loom validate-wheel: FILE={shown}: could not be validated; "
        "spdx3-validate says why above [sbom-invalid]"
    )
    assert done.err[0].startswith("ERROR: loom validate-wheel: spdx3-validate: ")
    assert len(done.err) == 2


def test_a_given_sbom_that_is_not_valid_is_stopped_before_anything_is_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path / "w")
    before = wheel.read_bytes()
    given = _given(tmp_path, spdx3_sbom(), "given.spdx3.json")
    done = run_cli(
        monkeypatch, capsys, "embed-wheel", wheel, "--sbom", given, "--validate"
    )
    assert done.status == 1 and wheel.read_bytes() == before
    assert done.err[-1].startswith("ERROR: loom embed-wheel: FILE=")
    assert done.err[-1].endswith(
        "SBOM is not valid; no wheel was written [sbom-invalid]"
    )
    assert trusted_message(done.err[-1]) is not None
    assert done.err[0].startswith("ERROR: loom embed-wheel: spdx3-validate: ")


def test_the_summaries_say_valid_skipped_and_nothing_after_a_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    good = make_wheel(tmp_path / "g", name="good")
    assert run_cli(monkeypatch, capsys, "embed-wheel", good).status == 0
    skipped = make_wheel(
        tmp_path / "s", name="skip", sboms={"a.spdx3.json": b'{"x": 1}'}
    )
    bad = make_wheel(tmp_path / "b", name="bad", sboms={"a.spdx3.json": spdx3_sbom()})
    valid = run_cli(monkeypatch, capsys, "validate-wheel", good)
    assert valid.err == ["INFO: validate-wheel: 1 wheel(s) valid"]
    mixed = run_cli(monkeypatch, capsys, "validate-wheel", good, skipped)
    assert mixed.status == 0
    assert mixed.err[-1] == (
        "INFO: validate-wheel: 1 wheel(s) valid, 1 skipped (no validator for "
        "their format)"
    )
    failed = run_cli(monkeypatch, capsys, "validate-wheel", good, bad)
    assert failed.status == 1
    assert not [e for e in failed.err if e.startswith("INFO: ")]
    ok = run_cli(monkeypatch, capsys, "verify-wheel", good, skipped)
    assert ok.err[-1] == "INFO: verify-wheel: 2 wheel(s) OK"
