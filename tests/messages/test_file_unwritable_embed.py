# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An embed whose write the system refuses: the new wheel (its directory
read-only) or the ``-o`` copy of the SBOM (its directory read-only or
missing) is ``file-unwritable`` for the file written, as given, on every
surface that embeds (``embed-wheel``, ``wheel --embed``, the library); never
``could not read`` or ``input-not-found`` for the input wheel.

See also: tests/messages/test_file_unreadable_wheel.py (a wheel the system
will not let Pitloom read).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pitloom import __main__, _embed_wheel
from pitloom.assemble import embed_sbom_in_wheel, embed_wheel_sbom
from pitloom.messages import CodedOSError, code_of, trusted_message
from pitloom.messages.targets import input_not_found
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_WHEEL = "demo-1.0.0-py3-none-any.whl"
_CODE = "file-unwritable"
_SBOM = '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"}'
_READ_ONLY_DIRS = os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0


def _run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str
) -> tuple[int, list[str]]:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    status = __main__.main()
    err = capsys.readouterr().err.splitlines()
    return status, [line for line in err if not line.startswith("INFO: ")]


def _assert_unwritable(err: list[str], command: str, file: str) -> None:
    (line,) = err
    assert line.startswith(
        f"ERROR: loom {command}: FILE={file}: could not write for the SBOM; "
    )
    assert line.endswith(f" [{_CODE}]")
    assert "could not read" not in line and "input-not-found" not in line
    trusted = trusted_message(line)
    assert trusted is not None and trusted.code == _CODE


@pytest.mark.parametrize("command", [["embed-wheel"], ["wheel", "--embed"]])
def test_an_sbom_copy_into_a_missing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    monkeypatch.chdir(tmp_path)
    target = os.path.join("nodir", "out.json")
    status, err = _run(monkeypatch, capsys, *command, str(wheel), "-o", target)
    assert status == 1
    _assert_unwritable(err, command[0], target)
    assert not (tmp_path / "nodir").exists()


@pytest.mark.skipif(not _READ_ONLY_DIRS, reason="needs POSIX modes, not root")
@pytest.mark.parametrize("command", [["embed-wheel"], ["wheel", "--embed"]])
def test_an_sbom_copy_into_a_read_only_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ro").mkdir()
    (tmp_path / "ro").chmod(0o555)
    target = os.path.join("ro", "out.json")
    try:
        status, err = _run(monkeypatch, capsys, *command, str(wheel), "-o", target)
    finally:
        (tmp_path / "ro").chmod(0o755)
    assert status == 1
    _assert_unwritable(err, command[0], target)
    assert err[0].endswith("; Permission denied [file-unwritable]")


@pytest.mark.skipif(not _READ_ONLY_DIRS, reason="needs POSIX modes, not root")
@pytest.mark.parametrize("command", [["embed-wheel"], ["wheel", "--embed"]])
def test_a_wheel_in_a_read_only_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    """The new wheel is written beside the old: a read-only directory
    refuses it, said for the wheel by its file name; the wheel is as it was."""
    wheel = _make_dummy_wheel(tmp_path / "ro", "demo", "1.0.0")
    before = wheel.read_bytes()
    wheel.parent.chmod(0o555)
    try:
        status, err = _run(monkeypatch, capsys, *command, str(wheel))
    finally:
        wheel.parent.chmod(0o755)
    assert status == 1
    _assert_unwritable(err, command[0], _WHEEL)
    assert wheel.read_bytes() == before
    assert sorted(p.name for p in wheel.parent.iterdir()) == [_WHEEL]


def test_the_library_raises_a_coded_os_error_for_the_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``embed_sbom_in_wheel``: an ``OSError`` as before, now coded, naming
    the wheel by file name, not the system's text (which quotes the path)."""
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")

    def refuse(*_: object) -> None:
        raise PermissionError(13, "Permission denied", str(tmp_path / "x.tmp"))

    monkeypatch.setattr("os.replace", refuse)
    with pytest.raises(OSError) as caught:
        embed_sbom_in_wheel(wheel, _SBOM)
    assert isinstance(caught.value, CodedOSError)
    assert str(caught.value) == (
        f"FILE={_WHEEL}: could not write for the SBOM; Permission denied"
    )
    assert code_of(caught.value) == _CODE
    assert str(tmp_path) not in str(caught.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == [_WHEEL]


def test_the_library_raises_a_coded_os_error_for_the_copy(tmp_path: Path) -> None:
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    target = tmp_path / "nodir" / "out.json"
    with pytest.raises(OSError) as caught:
        embed_wheel_sbom(wheel, output_path=target)
    assert code_of(caught.value) == _CODE
    assert str(caught.value).startswith(
        f"FILE={target}: could not write for the SBOM; "
    )


def test_a_coded_error_in_the_write_keeps_its_own_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal of ours raised while the new wheel is written (a member
    that cannot be read) is not said again as a refused write."""
    wheel = _make_dummy_wheel(tmp_path, "demo", "1.0.0")
    coded = input_not_found("wheel file", "elsewhere.whl")

    def refuse(*_: object, **__: object) -> Path:
        raise coded

    monkeypatch.setattr(_embed_wheel, "_rewrite_wheel_archive", refuse)
    with pytest.raises(FileNotFoundError) as caught:
        embed_sbom_in_wheel(wheel, _SBOM)
    assert caught.value is coded


def test_no_copy_asked_writes_nothing(tmp_path: Path) -> None:
    before = sorted(tmp_path.iterdir())
    _embed_wheel.write_sbom_copy(_SBOM, None)
    assert sorted(tmp_path.iterdir()) == before
