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
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from pitloom.messages import code_of, trusted_message
from tests._unreadable import POSIX_NON_ROOT
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform


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
    def _open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if os.path.abspath(file) == os.path.abspath(target):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), file)
        return builtins.open(file, *args, **kwargs)

    monkeypatch.setattr(pitloom.core.given_file, "open", _open, raising=False)


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
    if given == "not-utf8":
        sbom.write_bytes(b'{"@graph": "\xff"}')
    elif given != "missing":
        sbom.write_bytes(b'{"@context": "x", "@graph": []}')
    if given == "denied":
        _deny_open(sbom, monkeypatch)
    if given == "chmod":
        sbom.chmod(0)
    try:
        assert _SURFACES[surface](sbom, wheel, monkeypatch, capsys) == code
    finally:
        if sbom.exists():
            sbom.chmod(0o600)
    assert wheel.read_bytes() == before
    assert not (tmp_path / "ids.json").exists()
