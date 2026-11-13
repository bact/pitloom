# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.given_file`: one SBOM file the user names
fails with the same code on ``loom id import`` and ``loom embed-wheel
--sbom``, on the command line and in the library.

See also: tests/assemble/test_embed_unusable_sbom.py (every bad content
embed-wheel refuses), tests/id_registry/test_registry_import.py.
"""

from __future__ import annotations

import builtins
import errno
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import pitloom.core.given_file
from pitloom import __main__
from pitloom.core.given_file import read_given_bytes
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from pitloom.messages import code_of, trusted_message
from pitloom.messages.files import SBOM_USE
from tests._unreadable import POSIX_NON_ROOT
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

#: Whether this platform makes a FIFO (POSIX); short-circuited, so the
#: name is never read where it does not exist.
HAS_FIFO = hasattr(os, "mkfifo")
#: An SPDX 3 shaped document, as every surface reads it.
_DOCUMENT = '{"@context": "x", "@graph": []}'


def _cli(argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: Any) -> str:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    (line,) = [
        ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("ERROR:")
    ]
    found = trusted_message(line)
    assert found is not None
    return found.code


def _lib(call: Callable[[], object]) -> str | None:
    with pytest.raises((ValueError, FileNotFoundError)) as raised:
        call()
    return code_of(raised.value)


def _cli_embed(sbom: Path, wheel: Path, mp: pytest.MonkeyPatch, err: Any) -> object:
    return _cli(["embed-wheel", str(wheel), "--sbom", str(sbom)], mp, err)


def _cli_import(sbom: Path, wheel: Path, mp: pytest.MonkeyPatch, err: Any) -> object:
    registry = wheel.parent / "ids.json"
    return _cli(["id", "import", str(sbom), "--id-registry", str(registry)], mp, err)


def _lib_embed(sbom: Path, wheel: Path, _mp: pytest.MonkeyPatch, _err: Any) -> object:
    return _lib(lambda: embed_wheel_sbom(wheel, sbom_path=sbom))


def _lib_import(sbom: Path, _w: Path, _mp: pytest.MonkeyPatch, _err: Any) -> object:
    return _lib(lambda: IdRegistry.new("proj").import_sbom(sbom))


_SURFACES = {
    "cli-embed-wheel": _cli_embed,
    "cli-id-import": _cli_import,
    "lib-embed-wheel": _lib_embed,
    "lib-id-import": _lib_import,
}


def _deny_open(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening *target* raises ``PermissionError``: a file the system will
    not open, or a directory as Windows refuses one."""

    def _open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if os.path.abspath(file) == os.path.abspath(target):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), file)
        return builtins.open(file, *args, **kwargs)

    monkeypatch.setattr(pitloom.core.given_file, "open", _open, raising=False)


def _write(sbom: Path, given: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make *sbom* the case *given* names."""
    contents = {
        "not-utf8": b'{"@graph": "\xff"}',
        "utf16-bom-only": b"\xff\xfe{}",
        "utf16": _DOCUMENT.encode("utf-16"),
        "utf32": _DOCUMENT.encode("utf-32"),
        "not-spdx3": b'{"a": 1}',
    }
    if given in ("directory", "directory-windows"):
        sbom.mkdir()
    elif given == "fifo":
        os.mkfifo(sbom)  # pylint: disable=no-member
    elif given != "missing":
        sbom.write_bytes(contents.get(given, _DOCUMENT.encode("utf-8")))
    if given in ("denied", "directory-windows"):
        _deny_open(sbom, monkeypatch)
    if given == "over-cap":
        monkeypatch.setattr(
            pitloom.core.given_file, "FETCH_MAX_BYTES", len(_DOCUMENT) - 1
        )


@pytest.mark.parametrize(
    ("given", "code"),
    [
        ("not-utf8", "file-unreadable/not-utf8"),
        ("denied", "file-unreadable"),
        pytest.param(
            "chmod",
            "file-unreadable",
            marks=pytest.mark.skipif(
                not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root"
            ),
        ),
        ("missing", "input-not-found"),
        ("utf16-bom-only", "file-unreadable/not-utf8"),
        ("utf16", "file-unreadable/not-utf8"),
        ("utf32", "file-unreadable/not-utf8"),
        ("directory", "input-not-found"),
        ("directory-windows", "input-not-found"),
        pytest.param(
            "fifo",
            "input-not-found",
            marks=pytest.mark.skipif(not HAS_FIFO, reason="needs a FIFO"),
        ),
        ("not-spdx3", "sbom-wrong-format"),
        ("over-cap", "over-cap"),
    ],
)
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_one_sbom_file_gets_one_code_on_every_surface(
    surface: str,
    given: str,
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    wheel = _make_dummy_wheel(tmp_path, "extpkg", "1.0.0")
    before = wheel.read_bytes()
    sbom = tmp_path / "s.spdx3.json"
    _write(sbom, given, monkeypatch)
    if given == "chmod":
        sbom.chmod(0)
    try:
        assert _SURFACES[surface](sbom, wheel, monkeypatch, capsys) == code
    finally:
        if sbom.is_file():
            sbom.chmod(0o600)
    assert wheel.read_bytes() == before
    assert not (tmp_path / "ids.json").exists()


@pytest.mark.parametrize(
    ("size", "refused"), [(20_000, False), (20_001, True)], ids=["at-cap", "over"]
)
def test_a_file_is_read_in_chunks_up_to_the_cap(
    size: int, refused: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file of more than one chunk is read whole when it fits the cap, and
    refused one byte over it, naming the cap."""
    monkeypatch.setattr(pitloom.core.given_file, "FETCH_MAX_BYTES", 20_000)
    given = tmp_path / "s.json"
    given.write_bytes(bytes(range(256)) * (size // 256) + b"x" * (size % 256))
    if not refused:
        assert read_given_bytes(given, kind="SBOM file", use=SBOM_USE) == (
            given.read_bytes()
        )
        return
    with pytest.raises(ValueError, match="larger than the 20000-byte") as raised:
        read_given_bytes(given, kind="SBOM file", use=SBOM_USE)
    assert code_of(raised.value) == "over-cap"
