# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom._sbom_io`: SBOM text is ``\\n`` and UTF-8 on
every platform, and no other text-mode write exists in ``src/``.

On Windows, text mode turns ``\\n`` into ``\\r\\n``, so the same SBOM had
different bytes there. The bytes are compared raw here -- reading them back
in text mode would translate the ``\\r`` away and hide the bug.

See also: :mod:`tests.test_wall_clock_sources` (the same kind of guard).
"""

from __future__ import annotations

import io
import os
import re
import stat
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from pitloom._sbom_io import (
    open_text_lf,
    replace_text_lf,
    write_sbom_output,
    write_stdout_lf,
    write_text_lf,
)
from pitloom.assemble import generate_project_sbom
from tests.assemble.embed_surfaces_shared import demo_project

_SRC = Path(__file__).resolve().parents[1] / "src" / "pitloom"
#: Multi-line and non-ASCII, as a pretty SBOM with an accented name is.
_TEXT = '{\n  "name": "Caf\u00e9 na\u00efve"\n}\n'
_TEXT_WRITE = re.compile(
    r"\.write_text\(|\b(?:open|fdopen)\([^)]*[\"'][wax]\+?t?[\"']"
    r"|sys\.stdout\.write\("
)
#: File (relative to ``src/pitloom``) -> text-write matches that are not SBOM
#: text, with the reason.
_ALLOWED = {
    "_sbom_io.py": 2,  # the writers themselves
    # ZipFile.open(info, "w") is a binary archive member, not text mode.
    "_embed_wheel.py": 1,
}


def test_write_text_lf_writes_lf_and_utf8(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_text_lf(path, _TEXT)
    assert path.read_bytes() == _TEXT.encode("utf-8")
    assert b"\r" not in path.read_bytes()


def test_open_text_lf_translates_nothing(tmp_path: Path) -> None:
    path = tmp_path / "ids.json"
    with open_text_lf(path) as f:
        f.write("a\nb\n")
    assert path.read_bytes() == b"a\nb\n"


def test_replace_text_lf_new_file_is_like_open(tmp_path: Path) -> None:
    """A new file gets the bytes and the permission bits ``open()`` gives
    one (the umask's, not a private temporary file's ``0o600``)."""
    plain, replaced = tmp_path / "plain.json", tmp_path / "replaced.json"
    write_text_lf(plain, _TEXT)
    replace_text_lf(replaced, _TEXT)
    assert replaced.read_bytes() == _TEXT.encode("utf-8")
    assert stat.S_IMODE(replaced.stat().st_mode) == stat.S_IMODE(plain.stat().st_mode)
    assert sorted(os.listdir(tmp_path)) == ["plain.json", "replaced.json"]


def test_replace_text_lf_keeps_the_symlink_and_the_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing through a symlink replaces the file it names, which keeps
    its permission bits (spied on Windows, where NTFS has only read-only)."""
    real, link = tmp_path / "real.json", tmp_path / "link.json"
    real.write_bytes(b"old\n")
    os.chmod(real, 0o640)
    try:
        link.symlink_to(real)
    except OSError:  # pragma: no cover - Windows without symlink privilege
        pytest.skip("cannot create a symlink here")
    mode = stat.S_IMODE(real.stat().st_mode)
    chmod = Mock(wraps=os.chmod)
    monkeypatch.setattr("pitloom._sbom_io.os.chmod", chmod)

    replace_text_lf(link, _TEXT)

    assert link.is_symlink()
    assert real.read_bytes() == _TEXT.encode("utf-8")
    assert chmod.call_args.args[1] == mode
    if sys.platform != "win32":
        assert stat.S_IMODE(real.stat().st_mode) == 0o640
    assert sorted(os.listdir(tmp_path)) == ["link.json", "real.json"]


#: Whether a read-only file refuses this process (root writes through 0o444).
_READ_ONLY_REFUSES = sys.platform == "win32" or os.geteuid() != 0


@pytest.mark.skipif(not _READ_ONLY_REFUSES, reason="root writes a read-only file")
def test_replace_text_lf_refuses_a_read_only_file(tmp_path: Path) -> None:
    """A read-only target raises, as ``open(path, "w")`` does, on every
    platform: replacing the directory entry would bypass the mode."""
    path = tmp_path / "ids.json"
    path.write_bytes(b"old\n")
    os.chmod(path, 0o444)
    try:
        with pytest.raises(PermissionError):
            replace_text_lf(path, _TEXT)
        assert path.read_bytes() == b"old\n"
    finally:
        os.chmod(path, 0o644)
    assert sorted(os.listdir(tmp_path)) == ["ids.json"]


def test_replace_text_lf_writes_through_its_exclusive_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temporary file is written through the descriptor ``O_EXCL``
    created, never reopened by name, and in binary mode (no CRLF)."""
    opened: list[object] = []
    real_open = open

    def _spy(file: object, *args: object, **kwargs: object) -> object:
        opened.append(file)
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr("builtins.open", _spy)
    replace_text_lf(tmp_path / "out.json", _TEXT)

    assert [type(file) for file in opened] == [int]
    assert (tmp_path / "out.json").read_bytes() == _TEXT.encode("utf-8")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("no-newline", b"no-newline\n"), ("has-newline\n", b"has-newline\n")],
)
def test_stdout_gets_exactly_one_trailing_newline(
    capsysbinary: pytest.CaptureFixture[bytes], text: str, expected: bytes
) -> None:
    write_sbom_output(text, "-")
    assert capsysbinary.readouterr().out == expected


def test_stdout_is_utf8_lf_bytes(capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    """Bytes, not console text: no ``\\r``, and UTF-8 whatever the console's
    code page."""
    write_stdout_lf(_TEXT)
    assert capsysbinary.readouterr().out == _TEXT.encode("utf-8")


def test_stdout_bypasses_the_console_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A console whose code page cannot encode the text (ASCII here) still
    gets UTF-8: the bytes go to its buffer, not through its text layer."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="ascii", newline="\r\n")
    monkeypatch.setattr(sys, "stdout", stream)
    write_stdout_lf(_TEXT)
    assert raw.getvalue() == _TEXT.encode("utf-8")


def test_stdout_without_a_byte_buffer_still_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    write_stdout_lf("x")
    assert stream.getvalue() == "x\n"


def test_no_output_path_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    monkeypatch.chdir(tmp_path)
    write_sbom_output("x", None)
    assert capsysbinary.readouterr().out == b""
    assert not list(tmp_path.iterdir())


def test_a_pretty_project_sbom_file_has_no_carriage_return(tmp_path: Path) -> None:
    """End to end through a generator: the file has newlines (so the check
    is not vacuous) and none of them is ``\\r\\n``."""
    out = tmp_path / "sbom.json"
    generate_project_sbom(demo_project(tmp_path), output_path=out, pretty=True)
    data = out.read_bytes()
    assert data.count(b"\n") > 10
    assert b"\r" not in data


def _text_writes() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(_SRC.rglob("*.py")):
        code = "\n".join(
            line.split("#", 1)[0]
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        found = len(_TEXT_WRITE.findall(code))
        if found:
            counts[path.relative_to(_SRC).as_posix()] = found
    return counts


def test_every_text_write_goes_through_the_shared_writer() -> None:
    """A new ``write_text()``/``open(..., "w")``/``sys.stdout.write()`` in
    ``src/`` fails here: use :mod:`pitloom._sbom_io`, or list it with the
    reason it is not SBOM text."""
    assert _text_writes() == _ALLOWED


def test_the_scan_sees_a_text_write() -> None:
    for code in (
        'p.write_text(s, encoding="utf-8")',
        'open(p, "w", encoding="utf-8")',
        'open(p, "a")',
        'open(p, "w+")',
        'open(p, "x")',
        'os.fdopen(fd, "wt")',
        "sys.stdout.write(s)",
    ):
        assert _TEXT_WRITE.search(code), code
    assert not _TEXT_WRITE.search('open(p, "rb")')
