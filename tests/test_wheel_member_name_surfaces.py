# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Non-conforming wheel member names: every wheel surface agrees.

``loom wheel``, ``loom wheel --embed``, ``loom embed-wheel``, the library's
``generate_wheel_sbom()`` and ``embed_wheel_sbom()`` all read the wheel
through ``read_wheel()``. Each must name the files by their install
location and print exactly one ``WARNING:`` per non-conforming or unsafe
member.

See also: tests/extract/test_wheel_member_names.py (``read_wheel``),
tests/core/test_wheel_member_names.py (the normaliser).
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.embed import embed_wheel_sbom
from tests._raw_wheel import METADATA, write_raw_wheel
from tests.assemble.embed_surfaces_shared import run_cli
from tests.warning_helpers import stderr_warnings

_DIST_INFO = "demo-1.0.0.dist-info"
_MEMBERS = {
    f"{_DIST_INFO}/METADATA": METADATA,
    f"{_DIST_INFO}/RECORD": b"",
    "demo/__init__.py": b"",
    "demo\\mod.py": b"mod = 1\n",
    "./demo/b.py": b"b = 1\n",
    "../evil.py": b"evil = 1\n",
}
_EXPECTED = {
    f"{_DIST_INFO}/METADATA",
    f"{_DIST_INFO}/RECORD",
    "demo/__init__.py",
    "demo/mod.py",
    "demo/b.py",
}
_RAW_WARNED = ("'demo\\\\mod.py'", "'./demo/b.py'", "'../evil.py'")


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _cli_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    output = wheel.with_suffix(".spdx3.json")
    run_cli(["wheel", str(wheel), "--offline", "-o", str(output)], mp)
    return output.read_text(encoding="utf-8")


def _cli_wheel_embed(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    run_cli(["wheel", str(wheel), "--embed", "--offline"], mp)
    return _embedded(wheel)


def _cli_embed_wheel(wheel: Path, mp: pytest.MonkeyPatch) -> str:
    run_cli(["embed-wheel", str(wheel)], mp)
    return _embedded(wheel)


def _lib_generate_wheel_sbom(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_wheel_sbom(wheel, offline=True)


def _lib_embed_wheel_sbom(wheel: Path, _mp: pytest.MonkeyPatch) -> str:
    return _embedded(embed_wheel_sbom(wheel)[0])


_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "cli-wheel": _cli_wheel,
    "cli-wheel-embed": _cli_wheel_embed,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-generate_wheel_sbom": _lib_generate_wheel_sbom,
    "lib-embed_wheel_sbom": _lib_embed_wheel_sbom,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_wheel_member_names_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    # No [tool.pitloom] to borrow from the current directory.
    monkeypatch.chdir(tmp_path)
    wheel = write_raw_wheel(tmp_path / "demo-1.0.0-py3-none-any.whl", _MEMBERS)

    sbom = _SURFACES[surface](wheel, monkeypatch)

    files = {
        e["name"]
        for e in json.loads(sbom)["@graph"]
        if e["type"] == "software_File" and e["software_fileKind"].endswith("file")
    }
    assert files == _EXPECTED
    member_warnings = [
        w for w in stderr_warnings(capsys.readouterr().err) if "wheel entry" in w
    ]
    assert len(member_warnings) == len(_RAW_WARNED), member_warnings
    for raw in _RAW_WARNED:
        assert sum(raw in w for w in member_warnings) == 1, (raw, member_warnings)
