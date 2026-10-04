# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel named ``x.WHL`` on every surface that takes a wheel path.

``pip`` and ``packaging`` accept only ``.whl``, so each surface refuses
``x.WHL`` with the same ``not a .whl file`` message, writes nothing and
leaves the file as it was: ``loom wheel``, ``loom generate``,
``loom wheel --embed``, ``loom embed-wheel``, ``loom verify-wheel``,
``loom validate-wheel``, and the library's ``generate_wheel_sbom()``,
``generate()``, ``read_wheel()``, ``embed_wheel_sbom()`` and
``find_embedded_sbom()``.

See also: tests/core/test_wheel_dist_info.py (the selector).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate, generate_wheel_sbom
from pitloom.core.wheel_dist_info import (
    WheelRefused,
    is_wheel_path,
    looks_like_wheel_path,
)
from pitloom.embed import embed_wheel_sbom, find_embedded_sbom
from pitloom.extract.wheel import read_wheel

_NAME = "demo-1.0-py3-none-any"

_CLI: dict[str, list[str]] = {
    "wheel": ["wheel", "{w}"],
    "generate": ["generate", "{w}", "-o", "out.spdx3.json"],
    "wheel-embed": ["wheel", "{w}", "--embed"],
    "embed-wheel": ["embed-wheel", "{w}"],
    "verify-wheel": ["verify-wheel", "{w}"],
    "validate-wheel": ["validate-wheel", "{w}"],
}

_LIB: dict[str, Callable[[Path], object]] = {
    "generate_wheel_sbom": lambda w: generate_wheel_sbom(w, offline=True),
    "generate": lambda w: generate(w, offline=True),
    "read_wheel": read_wheel,
    "embed_wheel_sbom": embed_wheel_sbom,
    "find_embedded_sbom": find_embedded_sbom,
}


def _wheel(directory: Path, suffix: str) -> Path:
    directory.mkdir(exist_ok=True)
    path = directory / f"{_NAME}.{suffix}"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", "Name: demo\nVersion: 1.0\n")
        zf.writestr("demo/__init__.py", "")
    return path


def _argv(command: str, wheel: Path) -> list[str]:
    return ["loom", *(a.format(w=wheel) for a in _CLI[command])]


@pytest.mark.parametrize("command", sorted(_CLI))
def test_cli_refuses_an_uppercase_extension_alike(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    wheel = _wheel(tmp_path / "up", "WHL")
    before = wheel.read_bytes()
    monkeypatch.setattr(sys, "argv", _argv(command, wheel))

    assert __main__.main() == 1

    lines = capsys.readouterr().err.splitlines()
    assert lines == [f"ERROR: not a .whl file: {wheel.resolve()}"]
    assert wheel.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["up"]


@pytest.mark.parametrize("command", ["wheel", "embed-wheel", "verify-wheel"])
def test_cli_lowercase_control_is_not_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """Guards the test above against passing for the wrong reason."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", _argv(command, _wheel(tmp_path / "lo", "whl")))
    __main__.main()
    assert "not a .whl file" not in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(_LIB))
def test_library_refuses_an_uppercase_extension(tmp_path: Path, name: str) -> None:
    wheel = _wheel(tmp_path / "up", "WHL")
    before = wheel.read_bytes()

    with pytest.raises(WheelRefused, match="not a .whl file"):
        _LIB[name](wheel)

    assert wheel.read_bytes() == before
    assert [p.name for p in wheel.parent.iterdir()] == [wheel.name]


@pytest.mark.parametrize(
    ("name", "strict", "routed"),
    [
        ("a.whl", True, True),
        ("dir.WHL/a.whl", True, True),
        ("a.WHL", False, True),
        ("a.Whl", False, True),
        ("a.whl.zip", False, False),
        ("dir.whl/a.txt", False, False),
    ],
)
def test_wheel_name_helpers(name: str, strict: bool, routed: bool) -> None:
    assert is_wheel_path(name) is strict
    assert is_wheel_path(Path(name)) is strict
    assert looks_like_wheel_path(name) is routed


def test_cli_glob_skips_an_uppercase_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A glob keeps ``.whl`` files only, whatever the file system's case."""
    wheel = _wheel(tmp_path / "up", "WHL")
    monkeypatch.chdir(wheel.parent)
    monkeypatch.setattr(sys, "argv", ["loom", "verify-wheel", "*"])

    assert __main__.main() == 1
    assert capsys.readouterr().err == "ERROR: no wheel files matched: *\n"


def test_cli_refused_name_stops_the_whole_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One ``x.WHL`` among the paths refuses before any wheel is touched."""
    good = _wheel(tmp_path / "lo", "whl")
    bad = _wheel(tmp_path / "up", "WHL")
    before = good.read_bytes()
    monkeypatch.setattr(sys, "argv", ["loom", "embed-wheel", str(good), str(bad)])

    assert __main__.main() == 1
    assert good.read_bytes() == before
