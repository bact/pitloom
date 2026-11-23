# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The wheel families (``wheel-unreadable``, ``wheel-invalid``,
``wheel-unusable``, ``dist-info-*``, ``archive-member-*``) on every command
that reads a wheel: ``verify-wheel``, ``validate-wheel``, ``embed-wheel``,
``wheel`` and ``generate``, through ``__main__.main()``. Each says the
level, the subject (the wheel's file name only, never a directory; the
member as ``ENTRY=``), the code and the exit status that the plan gives it;
the wheel is left as it was on a refusal, and a wheel that is only unusual
for the one command that needs the directory is a ``WARNING:`` where a
command only names the package.

See also: tests/messages/test_wheels_surfaces_sboms.py (the embedded-SBOM
lines), tests/messages/test_wheels_surfaces_library.py (the library, the
hook and the build route) and tests/messages/test_wheels_core.py (the
helpers).
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from tests._raw_archive import write_raw_tar
from tests._wheel_damage import bad_crc
from tests._wheel_fixtures import (
    DIST_INFO,
    WHEEL_FILE,
    make_wheel,
    metadata,
    patch_member_name,
    run_cli,
    write_wheel,
)

pytestmark = pytest.mark.platform  # ZIP archives, member names, stderr lines

_REFUSED = "; wheel refused"
_ARCHIVE = f"ARCHIVE='{WHEEL_FILE}'"


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.chdir(tmp_path)  # no pyproject.toml here: no project-dir note


def _unreadable(directory: Path) -> Path:
    path = directory / WHEEL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a zip")
    return path


def _nul(directory: Path) -> Path:
    wheel = make_wheel(directory)
    patch_member_name(wheel, "demo/__init__.py", b"demo/__\x00nit__.py")
    return wheel


def _duplicate(directory: Path) -> Path:
    members = {f"{DIST_INFO}/METADATA": metadata(), "d/M": b"1", "d\\M": b"2"}
    return write_wheel(directory / WHEEL_FILE, members)


def _no_dist_info(directory: Path) -> Path:
    return write_wheel(directory / WHEEL_FILE, {"demo/a.py": b""})


def _ambiguous(directory: Path) -> Path:
    members = {f"{DIST_INFO}/METADATA": metadata(), "Demo-1.0.dist-info/M": b""}
    return write_wheel(directory / WHEEL_FILE, members)


#: A refusal by its cause: how to build the wheel, the text after the archive
#: (the member as ``ENTRY=``), the code.
_REFUSALS: dict[str, tuple[Callable[[Path], Path], str, str]] = {
    "unreadable": (
        _unreadable,
        ": could not open as a ZIP archive (zipfile.BadZipFile)",
        "wheel-unreadable",
    ),
    "nul": (
        _nul,
        " ENTRY='demo/__\\x00nit__.py': NUL in member name",
        "wheel-invalid",
    ),
    "duplicate": (_duplicate, " ENTRY='d/M': duplicate member name", "wheel-invalid"),
    "no-dist-info": (
        _no_dist_info,
        ": no top-level .dist-info directory",
        "dist-info-missing",
    ),
    "ambiguous": (
        _ambiguous,
        ": several top-level .dist-info directories match the file name",
        "dist-info-ambiguous",
    ),
}
#: What each command prints on standard output for a wheel it refused.
_STATUS = [f"WHEEL={WHEEL_FILE} STATUS=failed"]
_ERROR_COMMANDS = {
    "verify-wheel": _STATUS,
    "validate-wheel": _STATUS,
    "embed-wheel": [],
}


@pytest.mark.parametrize("cause", sorted(_REFUSALS))
@pytest.mark.parametrize("command", sorted(_ERROR_COMMANDS))
def test_a_command_that_needs_the_wheel_refuses_it_with_one_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    cause: str,
) -> None:
    build, tail, code = _REFUSALS[cause]
    wheel = build(tmp_path)
    before = wheel.read_bytes()
    done = run_cli(monkeypatch, capsys, command, wheel)
    assert done.status == 1
    assert done.err == [f"ERROR: loom {command}: {_ARCHIVE}{tail}{_REFUSED} [{code}]"]
    assert done.codes == [code]
    assert done.out == _ERROR_COMMANDS[command]
    assert wheel.read_bytes() == before  # a refusal leaves the wheel as it was


@pytest.mark.parametrize("cause", ["unreadable", "nul", "duplicate"])
@pytest.mark.parametrize("command", ["wheel", "generate"])
def test_wheel_and_generate_refuse_a_wheel_whose_content_is_bad(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    cause: str,
) -> None:
    build, tail, code = _REFUSALS[cause]
    out = tmp_path / "out.spdx3.json"
    done = run_cli(monkeypatch, capsys, command, build(tmp_path), "-o", out)
    assert done.status == 1 and not out.exists()
    assert done.err == [f"ERROR: loom {command}: {_ARCHIVE}{tail}{_REFUSED} [{code}]"]


@pytest.mark.parametrize("cause", ["no-dist-info", "ambiguous"])
@pytest.mark.parametrize("command", ["wheel", "generate"])
def test_wheel_and_generate_only_warn_when_the_identity_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    cause: str,
) -> None:
    build, tail, code = _REFUSALS[cause]
    out = tmp_path / "out.spdx3.json"
    done = run_cli(monkeypatch, capsys, command, build(tmp_path), "-o", out)
    assert done.status == 0 and out.is_file()
    assert done.err == [f"WARNING: {_ARCHIVE}{tail}; identity unknown [{code}]"]


# -- the .dist-info the file name does not name, METADATA that is not there ------


def _renamed(directory: Path) -> Path:
    members = {"bar-2.0.dist-info/METADATA": metadata("bar", "2.0"), "bar/a.py": b""}
    return write_wheel(directory / "foo-1.0-py3-none-any.whl", members)


def _no_metadata(directory: Path) -> Path:
    return write_wheel(directory / WHEEL_FILE, {f"{DIST_INFO}/RECORD": b""})


@pytest.mark.parametrize("command", ["wheel", "generate"])
def test_a_file_name_that_names_no_dist_info_uses_the_only_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    out = tmp_path / "out.spdx3.json"
    done = run_cli(monkeypatch, capsys, command, _renamed(tmp_path), "-o", out)
    assert done.status == 0 and out.is_file()
    assert done.err == [
        "WARNING: ARCHIVE='foo-1.0-py3-none-any.whl': the file name names no "
        "top-level .dist-info; using 'bar-2.0.dist-info/' [dist-info-conflict]"
    ]


@pytest.mark.parametrize("command", ["wheel", "embed-wheel"])
def test_a_wheel_without_metadata_says_so_and_goes_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    extra = ["-o", tmp_path / "out.spdx3.json"] if command == "wheel" else []
    done = run_cli(monkeypatch, capsys, command, _no_metadata(tmp_path), *extra)
    assert done.status == 0
    assert done.err == [
        f"WARNING: {_ARCHIVE} ENTRY='{DIST_INFO}/METADATA': not in the wheel; "
        "identity unknown [dist-info-missing]"
    ]


def test_embed_wheel_warns_where_the_name_only_names_the_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    done = run_cli(monkeypatch, capsys, "embed-wheel", _renamed(tmp_path))
    assert done.status == 0
    assert done.codes == ["dist-info-conflict"] and done.err[0].startswith("WARNING: ")


# -- unusable: a signature, a name that is not one ----------------------------------


def _signed(directory: Path) -> Path:
    return make_wheel(directory, extra={f"{DIST_INFO}/RECORD.jws": b"{}"})


def _non_conforming(directory: Path) -> Path:
    members = {f"{DIST_INFO}\\METADATA": metadata(), f"{DIST_INFO}/WHEEL": b"x"}
    return write_wheel(directory / WHEEL_FILE, members)


def test_a_signed_wheel_is_refused_and_a_flag_says_the_signature_goes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _signed(tmp_path)
    before = wheel.read_bytes()
    entry = f"ENTRY='{DIST_INFO}/RECORD.jws'"
    refused = run_cli(monkeypatch, capsys, "embed-wheel", wheel)
    assert refused.status == 1 and wheel.read_bytes() == before
    assert refused.err == [
        f"ERROR: loom embed-wheel: {_ARCHIVE} {entry}: signs the RECORD the embed "
        "rewrites; --allow-signed-wheel removes it (re-sign the wheel after)"
        f"{_REFUSED} [wheel-unusable/signed]"
    ]
    allowed = run_cli(monkeypatch, capsys, "embed-wheel", wheel, "--allow-signed-wheel")
    assert allowed.status == 0
    assert allowed.err == [
        f"INFO: {_ARCHIVE} {entry}: signature removed; re-sign the wheel "
        "[wheel-unusable/signed]"
    ]
    assert f"{DIST_INFO}/RECORD.jws" not in zipfile.ZipFile(wheel).namelist()


def test_a_batch_says_the_signature_of_the_wheel_that_had_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plain = make_wheel(tmp_path, name="one")
    signed = make_wheel(
        tmp_path, name="two", extra={"two-1.0.dist-info/RECORD.p7s": b"{}"}
    )
    done = run_cli(
        monkeypatch, capsys, "embed-wheel", plain, signed, "--allow-signed-wheel"
    )
    assert done.status == 0
    assert [e for e in done.err if "[wheel-unusable/signed]" in e] == [
        "INFO: ARCHIVE='two-1.0-py3-none-any.whl' "
        "ENTRY='two-1.0.dist-info/RECORD.p7s': signature removed; re-sign the "
        "wheel [wheel-unusable/signed]"
    ]
    assert len(done.out) == 2  # one WHEEL= line each


def test_a_dist_info_member_under_a_non_conforming_name_stops_the_embed_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _non_conforming(tmp_path)
    before = wheel.read_bytes()
    entry = f"ENTRY='{DIST_INFO}\\METADATA'"
    embed = run_cli(monkeypatch, capsys, "embed-wheel", wheel)
    assert embed.status == 1 and wheel.read_bytes() == before
    assert embed.err == [
        f"ERROR: loom embed-wheel: {_ARCHIVE} {entry}: .dist-info member under a "
        f"non-conforming name{_REFUSED} [wheel-unusable]"
    ]
    reader = run_cli(monkeypatch, capsys, "wheel", wheel, "-o", tmp_path / "o.json")
    assert reader.status == 0  # reading it only lists the member under its fix
    assert reader.codes == ["archive-member-invalid"]


def test_a_member_that_cannot_be_read_is_a_refusal_naming_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = make_wheel(tmp_path)
    bad_crc(wheel, f"{DIST_INFO}/METADATA")
    done = run_cli(monkeypatch, capsys, "embed-wheel", wheel)
    assert done.status == 1
    assert done.err == [
        f"ERROR: loom embed-wheel: {_ARCHIVE} ENTRY='{DIST_INFO}/METADATA': could "
        f"not read (zipfile.BadZipFile){_REFUSED} [wheel-unreadable]"
    ]


# -- archive members: the same lines on a wheel and on an sdist ---------------------

_MEMBERS = {
    f"{DIST_INFO}/METADATA": metadata(),
    "demo\\a.py": b"x",
    "../evil.py": b"y",
    "demo/dir": b"",
    "demo/dir/f.py": b"z",
    "/abs.py": b"",
}
_MEMBER_LINES = [
    f"WARNING: {_ARCHIVE} ENTRY='demo\\a.py': non-conforming name; listed as "
    "'demo/a.py' [archive-member-invalid]",
    f"WARNING: {_ARCHIVE} ENTRY='../evil.py': no safe install location; not "
    "listed [archive-member-unsafe]",
    f"WARNING: {_ARCHIVE} ENTRY='demo/dir': also a directory of other entries; "
    "not listed [archive-member-conflict]",
    f"WARNING: {_ARCHIVE} ENTRY='/abs.py': no safe install location; not "
    "listed [archive-member-unsafe]",
]


@pytest.mark.parametrize("command", ["wheel", "embed-wheel"])
def test_a_member_pitloom_leaves_out_is_said_once_as_not_listed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    wheel = write_wheel(tmp_path / WHEEL_FILE, _MEMBERS)
    extra = ["-o", tmp_path / "o.json"] if command == "wheel" else []
    done = run_cli(monkeypatch, capsys, command, wheel, *extra)
    assert done.status == 0
    assert done.err == _MEMBER_LINES  # each member once, no "Build: " frame
    assert not any("skipped" in line for line in done.err)


def test_an_sdist_whose_members_share_a_project_path_says_which(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sdist = write_raw_tar(
        tmp_path / "demo-1.0.0.tar.gz",
        {
            "demo-1.0.0/PKG-INFO": metadata("demo", "1.0.0"),
            "demo-1.0.0/pyproject.toml": b'[project]\nname = "demo"\nversion = "1.0.0"\n',
            "demo-1.0.0/x.py": b"1",
            "x.py": b"2",
            "demo-1.0.0/y.py": b"1",
            "y.py": b"1",
        },
    )
    expected = (
        "WARNING: ARCHIVE='demo-1.0.0.tar.gz': members share a project path "
        "('x.py', 'y.py'); they would share one ID registry key "
        "[archive-member-conflict]"
    )
    for command in ("project", "generate"):
        out = tmp_path / f"{command}.json"
        done = run_cli(monkeypatch, capsys, command, sdist, "-o", out)
        assert (done.status, done.err) == (0, [expected])
