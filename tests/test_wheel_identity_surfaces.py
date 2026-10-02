# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel's identity, and a wheel with an unreadable member, on every
surface that reads a wheel: ``loom wheel``, ``loom generate``,
``loom wheel --embed``, ``loom embed-wheel``, ``generate_wheel_sbom()`` and
``embed_wheel_sbom()``.

Each takes the name and version from the wheel's own top-level
``.dist-info``; each refuses a wheel with an unreadable member with one
``ERROR:`` line (the library: one ``ValueError``), writes nothing and leaves
the wheel as it was.

See also: tests/extract/test_wheel_identity.py (``read_wheel``),
tests/core/test_wheel_dist_info.py (the selector).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom
from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from tests._wheel_damage import damaged_wheel
from tests.build_and_read_shared import FakeBuildState, install_fake_build

_WHEEL = "demo-1.0-py3-none-any.whl"
_REAL = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n"
_EVIL = "Metadata-Version: 2.1\nName: evil\nVersion: 9.9\n"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``[tool.pitloom]`` to borrow from the current directory; a fixed
    creation time."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _hijack_wheel(tmp_path: Path) -> Path:
    path = tmp_path / _WHEEL
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("demo-1.0.dist-info/METADATA", _REAL)
        zf.writestr("demo/_vendor/zipp-3.23.0.dist-info/METADATA", _EVIL)
        zf.writestr("evil-9.9.dist-info/METADATA", _EVIL)
        zf.writestr("demo/__init__.py", "")
    return path


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _cli(argv: list[str], mp: pytest.MonkeyPatch) -> int:
    mp.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _cli_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    output = wheel.parent / "out.spdx3.json"
    assert _cli(["wheel", str(wheel), "--offline", "-o", str(output)], mp) == 0
    return output.read_text(encoding="utf-8")


def _cli_generate(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    output = wheel.parent / "out.spdx3.json"
    assert _cli(["generate", str(wheel), "--offline", "-o", str(output)], mp) == 0
    return output.read_text(encoding="utf-8")


def _cli_wheel_embed(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    assert _cli(["wheel", str(wheel), "--embed", "--offline"], mp) == 0
    return _embedded(wheel)


def _cli_embed_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    assert _cli(["embed-wheel", str(wheel)], mp) == 0
    return _embedded(wheel)


def _lib_generate(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_wheel_sbom(wheel, offline=True)


def _lib_embed(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return _embedded(embed_wheel_sbom(wheel)[0])


_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "cli-wheel": _cli_wheel,
    "cli-generate": _cli_generate,
    "cli-wheel-embed": _cli_wheel_embed,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-generate_wheel_sbom": _lib_generate,
    "lib-embed_wheel_sbom": _lib_embed,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_the_identity_is_the_wheels_own_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    wheel = _hijack_wheel(tmp_path)

    sbom = _SURFACES[surface](wheel, monkeypatch)

    packages = [
        (e["name"], e["software_packageVersion"])
        for e in json.loads(sbom)["@graph"]
        if e["type"] == "software_Package"
    ]
    assert packages == [("demo", "1.0")]
    assert "WARNING:" not in capsys.readouterr().err


def _cli_argv(surface: str, wheel: Path) -> list[str]:
    return {
        "cli-wheel": ["wheel", str(wheel), "--offline", "-o", "out.spdx3.json"],
        "cli-generate": ["generate", str(wheel), "--offline", "-o", "out.spdx3.json"],
        "cli-wheel-embed": ["wheel", str(wheel), "--embed", "--offline"],
        "cli-embed-wheel": ["embed-wheel", str(wheel)],
    }[surface]


def _refusal(surface: str, wheel: Path, mp: pytest.MonkeyPatch) -> None:
    """Run *surface* on *wheel*; it must refuse."""
    if surface.startswith("lib-"):
        with pytest.raises(ValueError, match="ENTRY="):
            _SURFACES[surface](wheel, mp)
    else:
        assert _cli(_cli_argv(surface, wheel), mp) == 1


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_an_unreadable_member_refuses_the_wheel_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    wheel = damaged_wheel(tmp_path, "deflate")
    before = wheel.read_bytes()

    _refusal(surface, wheel, monkeypatch)

    err = capsys.readouterr().err
    if not surface.startswith("lib-"):
        errors = [line for line in err.splitlines() if line.startswith("ERROR:")]
        assert len(errors) == 1, err
        assert f"ENTRY={'demo/bad.py'!r}" in errors[0]
        assert "Traceback" not in err
    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.spdx3.json"))
    assert not list(tmp_path.glob("*.tmp"))


def test_a_damaged_wheel_in_an_embed_batch_fails_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The existing per-wheel contract: the others are still processed and
    the exit code is non-zero."""
    bad = damaged_wheel(tmp_path, "deflate")
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    good = _hijack_wheel(good_dir)

    code = _cli(["embed-wheel", str(bad), str(good)], monkeypatch)

    assert code == 1
    assert _embedded(good)
    err = capsys.readouterr().err
    assert len([x for x in err.splitlines() if x.startswith("ERROR:")]) == 1


def test_a_build_and_read_extraction_keeps_its_own_fallback_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``--allow-build`` reads its just-built wheel itself, not through
    ``read_wheel()``: an unreadable member is the documented discovery
    failure (``None`` and one ``WARNING:``), never a crash."""
    state: FakeBuildState = install_fake_build(monkeypatch)
    state.entries = {"pkg/__init__.py": b"x = 1\n"}

    with mock.patch.object(zipfile.ZipFile, "open", side_effect=zlib.error("bad")):
        assert build_and_read_wheel(tmp_path, timeout=60) is None

    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


@pytest.mark.parametrize("kind", ["deflate", "encrypted", "name"])
def test_the_embed_rewrite_refuses_an_unreadable_member_too(
    tmp_path: Path, kind: str
) -> None:
    """``embed_sbom_in_wheel()`` takes the SBOM as given, so it reaches the
    archive rewrite without ``read_wheel()``: the same error, the wheel as it
    was and no temporary file left."""
    wheel = damaged_wheel(tmp_path, kind)
    before = wheel.read_bytes()

    with pytest.raises(ValueError, match="could not read"):
        embed_sbom_in_wheel(wheel, b'{"x": 1}')

    assert wheel.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
