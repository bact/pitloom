# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The wheel lines under attacker text, through the real commands: a wheel
is untrusted input, so a member name, an SBOM's declared name, a
``METADATA`` value, ``--sbom-filename``, the wheel's own file name and the
text of ``spdx3-validate`` may each hold a line break with a forged
``WARNING:`` and a forged code, an escape sequence, a URL credential, 64
KiB, both quotes or a NUL. A command prints ONE line per record, masked,
quoted and escaped, with the code of its own entry and no forged one (a
member name is cut at 500 characters plus ``...``; the line is still
trusted); relayed validator text is one tagged line per line of the
validator's.

See also: tests/messages/test_wheels_core_hostile.py (the writers),
tests/messages/test_wheels_core_worst_case.py (every line at its longest)
and tests/messages/test_wheels_surfaces.py (the same lines, plain names).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pitloom.messages import LONGEST_LINE, MESSAGES, trusted_message
from pitloom.messages._field_writers import NAME_CHARACTERS, NAME_CUT_MARK
from tests._raw_archive import write_raw_tar
from tests._wheel_fixtures import (
    DIST_INFO,
    WHEEL_FILE,
    Run,
    make_wheel,
    metadata,
    patch_member_name,
    run_cli,
    spdx3_sbom,
    write_wheel,
)

pytestmark = pytest.mark.platform  # member names, escapes and a NUL, stderr lines

_FORGED = "a\nWARNING: x [wheel-invalid]\r"
#: A hostile name by kind. 64 KiB is cut at 65,000: a ZIP header holds a name
#: of at most 65,535 bytes.
_NAMES = {
    "forged": _FORGED,
    "escape": "\x1b[31mred ",
    "credential": "https://u:pw@h/m.py",
    "long": "x" * 65_000,
    "quotes": 'it\'s "q"',
}
_TAGS = ("ERROR: ", "WARNING: ", "INFO: ")


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.chdir(tmp_path)


def _one_safe_line(line: str, code: str, *, cut: bool = False) -> None:
    """*line* is one tagged line that keeps its own *code*: nothing raw (a
    line break, an escape, a NUL, a URL credential), cut when *cut*."""
    assert line.startswith(_TAGS) and not line.partition(": ")[2].startswith(_TAGS)
    assert not any(c in line for c in "\r\x00\x1b "), line[:200]
    assert ":pw@" not in line and len(line) < LONGEST_LINE
    if cut:
        # The cut is of the whole name, a directory or prefix of it included.
        assert "x" * (NAME_CHARACTERS - 40) + NAME_CUT_MARK + "'" in line
        assert "x" * (NAME_CHARACTERS + 1) not in line
    assert trusted_message(line) is MESSAGES[code]
    assert trusted_message(line.removesuffix(f"[{code}]") + "[over-cap]") is None


def _only(done: Run, code: str, *, cut: bool = False) -> str:
    """The one stderr line of *done*, safe and carrying *code*."""
    (line,) = done.err
    _one_safe_line(line, code, cut=cut)
    assert not any(ln.startswith("WARNING: x") for ln in done.err)  # no forged line
    return line


# -- member names ---------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["unsafe", "normalised"])
@pytest.mark.parametrize("name", _NAMES.values(), ids=list(_NAMES))
@pytest.mark.parametrize("command", ["wheel", "embed-wheel"])
def test_a_member_line_prints_one_safe_line_for_a_hostile_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    name: str,
    kind: str,
) -> None:
    raw = f"/{name}" if kind == "unsafe" else f"d\\{name}"
    wheel = write_wheel(
        tmp_path / WHEEL_FILE, {f"{DIST_INFO}/METADATA": metadata(), raw: b"x"}
    )
    extra = ["-o", tmp_path / "o.json"] if command == "wheel" else []
    done = run_cli(monkeypatch, capsys, command, wheel, *extra)
    assert done.status == 0
    code = "archive-member-unsafe" if kind == "unsafe" else "archive-member-invalid"
    line = _only(done, code, cut=name == _NAMES["long"])
    assert line.startswith(f"WARNING: ARCHIVE='{WHEEL_FILE}' ENTRY='")


@pytest.mark.parametrize("name", _NAMES.values(), ids=list(_NAMES))
def test_a_duplicate_name_is_one_safe_error_naming_the_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    members = {
        f"{DIST_INFO}/METADATA": metadata(),
        f"d/{name}": b"1",
        f"d\\{name}": b"2",
    }
    wheel = write_wheel(tmp_path / WHEEL_FILE, members)
    done = run_cli(monkeypatch, capsys, "verify-wheel", wheel)
    assert done.status == 1
    line = _only(done, "wheel-invalid", cut=name == _NAMES["long"])
    assert line.endswith("duplicate member name; wheel refused [wheel-invalid]")


def test_a_nul_in_a_member_name_is_escaped_and_refuses_the_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path)
    patch_member_name(wheel, "demo/__init__.py", b"demo/__\x00nit__.py")
    done = run_cli(monkeypatch, capsys, "embed-wheel", wheel)
    assert done.status == 1
    assert "ENTRY='demo/__\\x00nit__.py': NUL in member name" in _only(
        done, "wheel-invalid"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="a file name cannot hold these")
def test_a_wheel_file_name_with_a_break_and_an_escape_is_one_quoted_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / f"demo{_FORGED}\x1b[31m-1.0-py3-none-any.whl"
    path.write_bytes(b"not a zip")
    done = run_cli(monkeypatch, capsys, "verify-wheel", path)
    assert done.status == 1
    line = _only(done, "wheel-unreadable")
    assert "ARCHIVE='demo" in line and "\\n" in line and str(tmp_path) not in line


@pytest.mark.parametrize("command", ["project", "generate"])
def test_an_sdist_with_shared_hostile_paths_is_one_safe_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    pyproject = b'[project]\nname = "d"\nversion = "1.0.0"\n'
    sdist = write_raw_tar(
        tmp_path / "d-1.0.0.tar.gz",
        {
            "d-1.0.0/PKG-INFO": metadata("d", "1.0.0"),
            "d-1.0.0/pyproject.toml": pyproject,
            f"d-1.0.0/{_FORGED}.py": b"1",
            f"{_FORGED}.py": b"2",
        },
    )
    done = run_cli(monkeypatch, capsys, command, sdist, "-o", tmp_path / "o.json")
    assert done.status == 0
    line = _only(done, "archive-member-conflict")
    assert (
        "members share a project path ('a\\nWARNING: x [wheel-invalid]\\r.py')" in line
    )


# -- SBOM names, declared values, the file name asked for ---------------------------


def test_a_hostile_sbom_filename_asked_for_is_one_safe_quoted_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path)
    for name in (_FORGED + "\x1b[31m https://u:pw@h/m.py", "x" * 65_000):
        done = run_cli(
            monkeypatch, capsys, "verify-wheel", wheel, "--sbom-filename", name
        )
        assert done.status == 1 and len(done.out) == 1
        _only(done, "wheel-sbom-missing", cut=name.startswith("xxx"))


@pytest.mark.parametrize(
    "name",
    [n for k, n in _NAMES.items() if k not in ("credential",)],
    ids=lambda n: n[:6],
)
def test_a_hostile_member_name_under_sboms_is_one_safe_line_in_each_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    cut = name == _NAMES["long"]
    wrong = make_wheel(tmp_path / "w", sboms={f"{name}.txt": spdx3_sbom()})
    done = run_cli(monkeypatch, capsys, "verify-wheel", wrong)
    assert done.status == 0
    (said, summary) = done.err
    _one_safe_line(said, "wheel-sbom-wrong-format", cut=cut)
    assert summary == "INFO: verify-wheel: 1 wheel(s) OK"
    several = make_wheel(
        tmp_path / "s",
        sboms={f"{name}.spdx3.json": spdx3_sbom(), "b.spdx3.json": b"{}"},
    )
    done = run_cli(monkeypatch, capsys, "verify-wheel", several)
    assert done.status == 1
    _only(done, "wheel-sbom-ambiguous", cut=cut)


@pytest.mark.parametrize("fail", [False, True], ids=["warning", "error"])
@pytest.mark.parametrize(
    "value",
    ["n" * 10_000_000, _FORGED + "\x1b[31m https://u:pw@h/m.py"],
    ids=["10mb", "forged"],
)
def test_a_declared_name_in_a_mismatch_is_one_cut_masked_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
    fail: bool,
) -> None:
    sbom = make_wheel(tmp_path / "s", sboms={"s.spdx3.json": spdx3_sbom(name=value)})
    meta = write_wheel(
        tmp_path / "m" / WHEEL_FILE,
        {
            f"{DIST_INFO}/METADATA": metadata(name="N" * 10_000_000),
            f"{DIST_INFO}/sboms/s.spdx3.json": spdx3_sbom(),
        },
    )
    for wheel in (sbom, meta):
        args = ["--fail-on-mismatch"] if fail else []
        done = run_cli(monkeypatch, capsys, "verify-wheel", wheel, *args)
        lines = [ln for ln in done.err if not ln.startswith("INFO: ")]
        (line,) = lines
        _one_safe_line(line, "wheel-sbom-conflict")
        assert line.startswith(("ERROR: loom verify-wheel: " if fail else "WARNING: "))
        assert len(line) < 1_000  # a value is shown as an excerpt, never whole
        assert done.status == (1 if fail else 0)


# -- the validator's text ----------------------------------------------------------------


@pytest.mark.parametrize(
    "tail",
    [_FORGED + "\x1b[31m https://u:pw@h/m.py", "x" * 100_000],
    ids=["forged", "long"],
)
def test_a_validator_finding_with_a_forged_code_or_a_break_stays_relayed_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    offline_spdx3_validate: None,
    tail: str,
) -> None:
    context = "https://spdx.org/rdf/9.9.9/spdx-context.jsonld" + tail
    sbom = json.dumps({"@context": context, "@graph": []}).encode()
    wheel = make_wheel(tmp_path, sboms={"s.spdx3.json": sbom})
    done = run_cli(monkeypatch, capsys, "validate-wheel", wheel)
    assert done.status == 1
    *relayed, verdict = done.err
    assert relayed
    for line in relayed:
        assert line.startswith("ERROR: loom validate-wheel: spdx3-validate: ")
        assert not any(c in line for c in "\r\x00\x1b") and ":pw@" not in line
        assert trusted_message(line) is None  # a finding is never a coded line
        assert len(line) < 2_000  # cut: 64 KiB of attacker text is not relayed
        assert "[wheel-invalid]" not in line  # a bracket in a finding is escaped
    assert not any(ln.startswith(("WARNING: x", "WARNING: loom")) for ln in done.err)
    _one_safe_line(verdict, "sbom-invalid")
    assert verdict.endswith(
        "could not be validated; spdx3-validate says why above [sbom-invalid]"
    )
    assert done.codes == ["sbom-invalid"]  # no forged code was trusted
