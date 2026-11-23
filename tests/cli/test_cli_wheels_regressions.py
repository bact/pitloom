# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regressions of the wheel commands found while cataloguing their lines,
each a test that failed before the fix: ``embed-wheel``, ``verify-wheel`` and
``validate-wheel`` warned that a wheel's identity was unknown just before
refusing it (P1); ``validate-wheel`` printed each finding twice and an empty
``ERROR:`` line (P2); an SBOM in a format Pitloom does not recognise printed
``format None`` (P3); ``--sbom-basename ../x`` was refused only after the SBOM
was generated (P4); a member left out was said to be ``skipped`` (P5); the
file-mode warning named the file a symlink led to, not the file given (P7);
and ``embed-wheel --sbom`` and ``loom id import`` did not say, with a code,
that they dropped a byte order mark.

See also: tests/messages/test_wheels_surfaces.py and
tests/messages/test_wheels_surfaces_sboms.py (every line on every surface).
"""

from __future__ import annotations

import codecs
import logging
import re
import zipfile
from pathlib import Path
from typing import Any, NoReturn

import pytest

from pitloom.core._models_wheel_build_and_read import (  # pylint: disable=protected-access
    _extract_wheel_to_included_files,
)
from pitloom.embed import embed_wheel_sbom
from pitloom.messages import code_of
from tests._loom_child import coded_lines, run_loom
from tests._symlink import CAN_SYMLINK
from tests._wheel_fixtures import (
    DIST_INFO,
    WHEEL_FILE,
    make_wheel,
    metadata,
    run_cli,
    spdx3_sbom,
    write_wheel,
)
from tests.id_registry.shared import _write_sample_sbom

pytestmark = pytest.mark.platform  # child processes, files, stderr bytes

#: A wheel Pitloom cannot name the package of: no ``.dist-info``, two of them.
_NO_OWN = {
    "none": {"demo/a.py": b""},
    "several": {f"{DIST_INFO}/METADATA": metadata(), "Demo-1.0.dist-info/M": b""},
}


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.chdir(tmp_path)  # no pyproject.toml here: no project-dir note


def _lines(stderr: bytes) -> list[str]:
    """The lines of a child's *stderr*, whatever its line ends."""
    return stderr.decode("utf-8").splitlines()


# -- P1: a wheel with no single own .dist-info ------------------------------------------


@pytest.mark.parametrize("shape", sorted(_NO_OWN))
def test_p1_a_command_that_refuses_the_wheel_does_not_also_warn_it_is_unknown(
    tmp_path: Path, shape: str
) -> None:
    wheel = write_wheel(tmp_path / WHEEL_FILE, _NO_OWN[shape])
    for command in ("embed-wheel", "verify-wheel", "validate-wheel"):
        done = run_loom([command, str(wheel)], tmp_path)
        lines = _lines(done.stderr)
        assert done.returncode == 1, (command, lines)
        assert len(lines) == 1 and lines[0].startswith("ERROR: "), (command, lines)
        assert "identity unknown" not in lines[0]
    # ``wheel`` only names the package, so there the identity is a WARNING.
    out = tmp_path / "o.json"
    done = run_loom(["wheel", str(wheel), "-o", str(out)], tmp_path)
    (line,) = _lines(done.stderr)
    assert done.returncode == 0 and out.is_file()
    assert line.startswith("WARNING: ") and "; identity unknown [" in line


# -- P2 and P3: the validator's text, and a format Pitloom does not know ---------------


@pytest.mark.usefixtures("offline_spdx3_validate")
def test_p2_each_finding_is_printed_once_and_no_error_line_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path, sboms={"s.spdx3.json": spdx3_sbom()})
    done = run_cli(monkeypatch, capsys, "validate-wheel", wheel)
    assert done.status == 1
    frame = "ERROR: loom validate-wheel:"
    assert all(
        ln.startswith(frame) and ln.removeprefix(frame).strip() for ln in done.err
    )
    findings = [ln for ln in done.err if re.search(r": \[(schema|shacl)\] ", ln)]
    assert findings and len(findings) == len(set(findings))  # none twice
    count = re.search(r"\((\d+) finding\(s\) above\)", done.err[-1])
    assert count is not None and int(count.group(1)) == len(findings)


@pytest.mark.usefixtures("offline_spdx3_validate")
@pytest.mark.parametrize("command", ["verify-wheel", "validate-wheel"])
def test_p3_an_unrecognised_format_never_prints_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    wheel = make_wheel(tmp_path / "w", sboms={"s.spdx3.json": b'{"x": 1}'})
    done = run_cli(monkeypatch, capsys, command, wheel)
    assert done.status == 0 and done.err
    assert not any("None" in ln for ln in done.err)
    given = tmp_path / "given.json"
    given.write_bytes(b'{"x": 1}')
    embedded = run_cli(
        monkeypatch,
        capsys,
        "embed-wheel",
        make_wheel(tmp_path / "e"),
        "--sbom",
        given,
        "--verify",
        "--validate",
    )
    assert not any("None" in ln for ln in embedded.err)


# -- P4: --sbom-basename is checked before anything is generated -----------------------


def _forbid_work(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every place an embed generates an SBOM or runs a build now raises; the
    names that were reached."""
    reached: list[str] = []

    def forbid(name: str) -> Any:
        def work(*_: object, **__: object) -> NoReturn:
            reached.append(name)
            raise AssertionError(f"{name} ran")

        return work

    monkeypatch.setattr("pitloom.embed._generate_embed_sbom_json", forbid("generate"))
    monkeypatch.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel",
        forbid("build"),
    )
    return reached


@pytest.mark.parametrize("basename", ["../x", "a/b"])
@pytest.mark.parametrize("extra", [[], ["--allow-build"]], ids=["analyzed", "build"])
def test_p4_a_basename_that_is_a_path_is_refused_before_any_sbom_or_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    basename: str,
    extra: list[str],
) -> None:
    wheel = make_wheel(tmp_path / "w")
    before = wheel.read_bytes()
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n', encoding="utf-8"
    )
    args = ["--project-dir", project, *extra] if extra else []
    reached = _forbid_work(monkeypatch)
    done = run_cli(
        monkeypatch, capsys, "embed-wheel", wheel, "--sbom-basename", basename, *args
    )
    assert done.status == 1 and not reached and wheel.read_bytes() == before
    assert done.codes == ["option-invalid"]
    assert done.err[-1].startswith("ERROR: loom embed-wheel: --sbom-basename: ")


def test_p4_the_library_refuses_a_path_basename_before_generating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = make_wheel(tmp_path)
    reached = _forbid_work(monkeypatch)
    with pytest.raises(ValueError) as raised:
        embed_wheel_sbom(wheel, sbom_basename="../x")
    assert code_of(raised.value) == "option-invalid" and not reached


@pytest.mark.parametrize(
    ("basename", "arcname"),
    [
        ("x", "x.spdx3.json"),
        ("x.spdx3.json", "x.spdx3.json"),
        ("X.SPDX3.JSON", "X.spdx3.json"),
    ],
    ids=["bare", "suffixed", "upper-suffixed"],
)
def test_p4_a_plain_basename_is_still_accepted_in_each_spelling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    basename: str,
    arcname: str,
) -> None:
    wheel = make_wheel(tmp_path / "w")
    done = run_cli(
        monkeypatch, capsys, "embed-wheel", wheel, "--sbom-basename", basename
    )
    assert done.status == 0, done.err
    with zipfile.ZipFile(wheel) as zf:
        assert f"{DIST_INFO}/sboms/{arcname}" in zf.namelist()


# -- P5: a member left out is "not listed" (a read) or "not copied" (a build) -----------


def _unsafe_wheel(tmp_path: Path) -> Path:
    members = {f"{DIST_INFO}/METADATA": metadata(), "../evil.py": b"x", "pkg/a.py": b""}
    return write_wheel(tmp_path / WHEEL_FILE, members)


def test_p5_a_read_says_not_listed_never_skipped(tmp_path: Path) -> None:
    done = run_loom(["wheel", str(_unsafe_wheel(tmp_path)), "-o", "o.json"], tmp_path)
    (line,) = _lines(done.stderr)
    assert line.endswith("no safe install location; not listed [archive-member-unsafe]")
    assert "skipped" not in line and "Build" not in line
    assert list(coded_lines(done.stderr).values()) == ["archive-member-unsafe"]


def test_p5_a_build_says_not_copied_behind_its_frame(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    with caplog.at_level(logging.WARNING):
        _extract_wheel_to_included_files(_unsafe_wheel(tmp_path), out)
    (record,) = caplog.records
    assert record.getMessage() == (
        f"Build: ARCHIVE='{WHEEL_FILE}' ENTRY='../evil.py': no safe install "
        "location; not copied"
    )


# -- P7: the file mode of a wheel reached through a link ----------------------------------


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symbolic link")
def test_p7_the_file_mode_warning_names_the_file_as_given_not_its_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real = make_wheel(tmp_path / "real", name="target")
    link = tmp_path / "link" / WHEEL_FILE
    link.parent.mkdir()
    link.symlink_to(real)

    def refuse(*_: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr("pitloom._embed_wheel.os.chmod", refuse)
    done = run_cli(monkeypatch, capsys, "embed-wheel", link)
    assert done.status == 0
    (line,) = [ln for ln in done.err if ln.endswith("[file-unwritable/mode]")]
    assert line.startswith(f"WARNING: FILE={WHEEL_FILE}: file mode not restored; ")
    assert "target" not in line and str(tmp_path) not in line


# -- the byte order mark: said with a code by embed-wheel and by loom id import --------


def test_a_byte_order_mark_is_said_with_its_code_by_embed_wheel_and_id_import(
    tmp_path: Path,
) -> None:
    sbom = tmp_path / "bom.json"
    sbom.write_bytes(codecs.BOM_UTF8 + spdx3_sbom())
    embedded = run_loom(
        ["embed-wheel", str(make_wheel(tmp_path / "w")), "--sbom", str(sbom)], tmp_path
    )
    assert embedded.returncode == 0, embedded.stderr
    sample = tmp_path / "sample.spdx3.json"
    _write_sample_sbom(sample)
    sample.write_bytes(codecs.BOM_UTF8 + sample.read_bytes())
    imported = run_loom(["id", "import", str(sample), "-o", "reg.json"], tmp_path)
    assert imported.returncode == 0, imported.stderr
    for done, name in ((embedded, "bom.json"), (imported, "sample.spdx3.json")):
        said = [
            ln
            for ln in coded_lines(done.stderr).items()
            if ln[1] == "json-malformed/bom"
        ]
        ((line, _),) = said
        assert line.startswith("WARNING: FILE=") and name in line
        assert "byte order mark" in line and line.endswith("[json-malformed/bom]")
