# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Non-conforming archive member names: every wheel and sdist surface agrees.

``loom wheel``, ``loom wheel --embed``, ``loom embed-wheel``, the library's
``generate_wheel_sbom()`` and ``embed_wheel_sbom()`` read a wheel through
``read_wheel()``; ``loom project``, ``loom generate`` and
``generate_project_sbom()`` read a zip or tar sdist through ``read_sdist()``.
Each must name the files by their install location and print exactly one
``WARNING:`` per non-conforming or unsafe member.

See also: tests/extract/test_wheel_member_names.py (``read_wheel``),
tests/extract/project/test_sdist_member_names.py (``read_sdist``),
tests/core/test_archive_member_names.py (the normaliser).
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.embed import embed_wheel_sbom
from tests._raw_archive import (
    METADATA,
    SDIST_FILES,
    SDIST_MEMBERS,
    SDIST_ROOT,
    SDIST_WARNED,
    write_raw_tar,
    write_raw_zip,
)
from tests._wheel_models import safetensors_bytes
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
    "demo\\m.safetensors": safetensors_bytes(),
}
_EXPECTED = {
    f"{_DIST_INFO}/METADATA",
    f"{_DIST_INFO}/RECORD",
    "demo/__init__.py",
    "demo/mod.py",
    "demo/b.py",
    "demo/m.safetensors",
}
_RAW_WARNED = (
    "'demo\\\\mod.py'",
    "'./demo/b.py'",
    "'../evil.py'",
    "'demo\\\\m.safetensors'",
)


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


def _file_names(sbom: str) -> set[str]:
    return {
        e["name"]
        for e in json.loads(sbom)["@graph"]
        if e["type"] == "software_File" and e["software_fileKind"].endswith("file")
    }


def _assert_warned_once(err: str, raws: tuple[str, ...]) -> None:
    member_warnings = [w for w in stderr_warnings(err) if "ENTRY=" in w]
    assert len(member_warnings) == len(raws), member_warnings
    for raw in raws:
        assert sum(f"ENTRY={raw}:" in w for w in member_warnings) == 1, (
            raw,
            member_warnings,
        )


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
    wheel = write_raw_zip(tmp_path / "demo-1.0.0-py3-none-any.whl", _MEMBERS)

    sbom = _SURFACES[surface](wheel, monkeypatch)

    assert _file_names(sbom) == _EXPECTED
    _assert_warned_once(capsys.readouterr().err, _RAW_WARNED)
    # The scanned model is contained in the File of its install-location name.
    graph = json.loads(sbom)["@graph"]
    names = {e["spdxId"]: e["name"] for e in graph if e["type"] == "software_File"}
    kinds = {e["spdxId"]: e["type"] for e in graph if "spdxId" in e}
    contained = [
        names[target]
        for rel in graph
        if rel["type"] == "Relationship"
        and rel["relationshipType"] == "contains"
        and kinds.get(rel["from"]) == "ai_AIPackage"
        for target in rel["to"]
        if target in names
    ]
    assert contained == ["demo/m.safetensors"]


def _cli_project(sdist: Path, mp: pytest.MonkeyPatch) -> str:
    output = sdist.parent / "out.spdx3.json"
    run_cli(["project", str(sdist), "--offline", "-o", str(output)], mp)
    return output.read_text(encoding="utf-8")


def _cli_generate(sdist: Path, mp: pytest.MonkeyPatch) -> str:
    output = sdist.parent / "out.spdx3.json"
    run_cli(["generate", str(sdist), "--offline", "-o", str(output)], mp)
    return output.read_text(encoding="utf-8")


def _lib_generate_project_sbom(sdist: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(sdist, offline=True)


_SDIST_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "cli-project": _cli_project,
    "cli-generate": _cli_generate,
    "lib-generate_project_sbom": _lib_generate_project_sbom,
}


@pytest.mark.parametrize("kind", ["zip", "tar.gz"])
@pytest.mark.parametrize("surface", sorted(_SDIST_SURFACES))
def test_sdist_member_names_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    kind: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / f"{SDIST_ROOT}.{kind}"
    write = write_raw_zip if kind == "zip" else write_raw_tar
    sdist = write(path, SDIST_MEMBERS)

    sbom = _SDIST_SURFACES[surface](sdist, monkeypatch)

    assert _file_names(sbom) == SDIST_FILES
    _assert_warned_once(capsys.readouterr().err, SDIST_WARNED)
