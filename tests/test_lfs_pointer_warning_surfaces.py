# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every surface says a run's Git LFS pointers in one ``WARNING:``, not one
per file: a ``DEBUG`` line names each, a model-named pointer is still listed
in ``files``, and an opening that does not parse keeps its own warning.

See also: tests/test_lfs_pointer_surfaces.py (the flag on each route);
tests/core/test_lfs_pointer.py (the warning helpers).
"""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.embed import embed_wheel_sbom
from tests._lfs import POINTERS, TREE, lfs_pointer_bytes, write_project
from tests._raw_archive import METADATA, write_raw_zip
from tests.assemble.embed_surfaces_shared import run_cli
from tests.extract.conftest import make_hook, staged_sbom
from tests.warning_helpers import stderr_warnings

_CHECKOUT = "content not read"
_SHIPPED = "Git LFS pointer shipped"
_Surface = Callable[[Path, pytest.MonkeyPatch], str]


def _wheel(tmp_path: Path, tree: dict[str, bytes]) -> Path:
    info = "demo-1.0.0.dist-info/"
    members = {**tree, f"{info}METADATA": METADATA, f"{info}RECORD": b""}
    return write_raw_zip(tmp_path / "demo-1.0.0-py3-none-any.whl", members)


def _cli_project(tree: dict[str, bytes], tmp_path: Path, mp: Any) -> str:
    out = tmp_path / "out.spdx3.json"
    run_cli(["project", str(write_project(tmp_path / "p", tree)), "-o", str(out)], mp)
    return out.read_text(encoding="utf-8")


def _lib_project(tree: dict[str, bytes], tmp_path: Path, _mp: Any) -> str:
    return generate_project_sbom(write_project(tmp_path / "p", tree), offline=True)


def _hook(tree: dict[str, bytes], tmp_path: Path, _mp: Any) -> str:
    hook = make_hook(str(write_project(tmp_path / "p", tree)), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        staged = staged_sbom(build_data)
        assert staged is not None
        return staged.read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


def _cli_wheel(tree: dict[str, bytes], tmp_path: Path, mp: Any) -> str:
    out = tmp_path / "out.spdx3.json"
    run_cli(["wheel", str(_wheel(tmp_path, tree)), "--offline", "-o", str(out)], mp)
    return out.read_text(encoding="utf-8")


def _lib_wheel(tree: dict[str, bytes], tmp_path: Path, _mp: Any) -> str:
    return generate_wheel_sbom(_wheel(tmp_path, tree), offline=True)


def _cli_embed(tree: dict[str, bytes], tmp_path: Path, mp: Any) -> str:
    wheel = _wheel(tmp_path, tree)
    run_cli(["embed-wheel", str(wheel)], mp)
    return _embedded(wheel)


def _lib_embed(tree: dict[str, bytes], tmp_path: Path, _mp: Any) -> str:
    return _embedded(embed_wheel_sbom(_wheel(tmp_path, tree))[0])


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


#: Surface -> (runner, the kind of pointer it reports).
_SURFACES: dict[str, tuple[Callable[..., str], str]] = {
    "cli-project": (_cli_project, _CHECKOUT),
    "lib-project": (_lib_project, _CHECKOUT),
    "hook": (_hook, _SHIPPED),
    "cli-wheel": (_cli_wheel, _SHIPPED),
    "lib-wheel": (_lib_wheel, _SHIPPED),
    "cli-embed-wheel": (_cli_embed, _SHIPPED),
    "lib-embed-wheel": (_lib_embed, _SHIPPED),
}
_FIRST = "demo/crlf.dat"
_PLAIN = {k: v for k, v in TREE.items() if k not in POINTERS}


def _run(
    surface: str,
    tree: dict[str, bytes],
    tmp_path: Path,
    mp: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, list[str], str]:
    mp.chdir(tmp_path)
    mp.delenv("PITLOOM_DEBUG", raising=False)
    sbom = _SURFACES[surface][0](tree, tmp_path, mp)
    err = capsys.readouterr().err
    return sbom, stderr_warnings(err), err


@pytest.mark.parametrize("surface", _SURFACES)
def test_one_warning_names_all_the_pointers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    """Five pointers (a model-named one among them): one line with the
    count and the first path, no per-file line, every file still listed."""
    sbom, warnings, err = _run(surface, TREE, tmp_path, monkeypatch, capsys)
    assert len(warnings) == 1, warnings
    assert f"FILE={_FIRST}: " in warnings[0] and "(5 files)" in warnings[0]
    assert _SURFACES[surface][1] in warnings[0]
    assert "not listed as an AI model" not in err
    names = {e.get("name") for e in json.loads(sbom)["@graph"]}
    assert set(TREE) <= names


@pytest.mark.parametrize("surface", ["cli-project", "hook", "cli-wheel"])
def test_a_debug_line_names_each_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    """With ``PITLOOM_DEBUG`` each pointer has its own line, still one
    warning; without it none."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    _SURFACES[surface][0](TREE, tmp_path, monkeypatch)
    err = capsys.readouterr().err
    lines = [
        x
        for x in err.splitlines()
        if x.startswith("DEBUG: ") and "content not read" in x
    ]
    assert len(lines) == len(POINTERS)
    assert len(stderr_warnings(err)) == 1
    assert all(f"FILE={name}:" in err for name in POINTERS)


@pytest.mark.parametrize("surface", _SURFACES)
def test_no_pointer_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    """Including a 1 KiB file that only opens like a pointer."""
    assert "demo/long.dat" in _PLAIN
    _, warnings, err = _run(surface, _PLAIN, tmp_path, monkeypatch, capsys)
    assert not warnings, warnings
    assert "Git LFS" not in err


@pytest.mark.parametrize("surface", ["cli-project", "lib-wheel"])
def test_a_newline_in_a_pointer_path_is_escaped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    if os.name == "nt":
        pytest.skip("a file name cannot hold a newline on Windows")
    tree = {"demo/__init__.py": b"", "demo/a\nb.dat": lfs_pointer_bytes(b"x")}
    _, warnings, err = _run(surface, tree, tmp_path, monkeypatch, capsys)
    assert len(warnings) == 1 and "a\\nb.dat" in warnings[0]
    assert all(x.startswith(("WARNING: ", "INFO: ")) or not x for x in err.splitlines())


@pytest.mark.parametrize("name", ["m.gguf", "m.onnx", "m.bin", "m.model", "m.zip"])
@pytest.mark.parametrize("surface", ["cli-project", "lib-wheel"])
def test_a_model_named_pointer_is_listed_and_said_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    name: str,
) -> None:
    tree = {"demo/__init__.py": b"", f"demo/{name}": lfs_pointer_bytes(b"w" * 5)}
    sbom, warnings, err = _run(surface, tree, tmp_path, monkeypatch, capsys)
    assert len(warnings) == 1 and "not listed" not in err
    assert f"demo/{name}" in {e.get("name") for e in json.loads(sbom)["@graph"]}
    assert not [e for e in json.loads(sbom)["@graph"] if "ai_" in e["type"]]


@pytest.mark.parametrize("surface", ["cli-project", "lib-wheel"])
def test_an_opening_that_does_not_parse_keeps_its_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    """The version line is exact, the rest is not a pointer: a defect, said
    per file; the shape of a model-named pointer, no pointer summary."""
    bad = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\n"
    tree = {"demo/__init__.py": b"", "demo/m.gguf": bad, "demo/m.bin": bad}
    _, warnings, _ = _run(surface, tree, tmp_path, monkeypatch, capsys)
    per_file = [w for w in warnings if "header is a Git LFS pointer" in w]
    assert len(per_file) == 2 and len(warnings) == 2
