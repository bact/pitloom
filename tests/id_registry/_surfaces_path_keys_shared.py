# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One ``src/``-layout project, holding an AI model, and a runner per
surface that looks its files up in a Loom ID registry, for the path-key
drift guard.

See also: test_surfaces_path_keys.py (the guard),
test_surfaces_path_keys_models.py (its model), surfaces_shared.py (the
registry-declaration runners, a flat project).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom.assemble import generate, generate_project_sbom, generate_wheel_sbom
from pitloom.core.build_options import BuildOptions
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.build_and_read_shared import install_fake_build
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string
from tests.extract.conftest import make_hook, staged_sbom
from tests.id_registry.surfaces_base import DEMO_INIT_CONTENT, _run_cli

REGISTRY = "loom-id-registry.json"
#: The project's model: a GGUF file whose own name is not its stem.
MODEL = "demo/m.gguf"
MODEL_NAME = "own-name"
MODEL_BYTES = gguf_file(0, 1, kv(b"general.name", STRING, string(MODEL_NAME)))
#: The installed path of each project file -> its bytes (``__init__.py`` as
#: ``_make_dummy_wheel`` writes it).
FILES = {
    "demo/__init__.py": DEMO_INIT_CONTENT,
    "demo/x.py": b"x = 1\n",
    MODEL: MODEL_BYTES,
}
#: Each file's key: its path from the project root.
KEYS = {f"src/{name}": name for name in FILES}

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
requires-python = ">=3.10"

[tool.hatch.build.targets.wheel]
packages = ["src/demo"]

[tool.pitloom]
id-registry = "{registry}"
"""


def src_project(
    directory: Path, registry: str = REGISTRY, *, flat: bool = False
) -> Path:
    """The demo project in *directory*, declaring *registry* (relative);
    with *flat*, its package at the top, not below ``src/``."""
    top = directory if flat else directory / "src"
    for name, data in FILES.items():
        path = top / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    text = _PYPROJECT.format(registry=registry)
    if flat:
        text = text.replace('packages = ["src/demo"]', 'packages = ["demo"]')
    (directory / "pyproject.toml").write_bytes(text.encode("utf-8"))
    return directory


def id_generate(mp: pytest.MonkeyPatch, project: Path, registry: Path) -> None:
    argv = ["id", "generate", str(project / "src"), "--project-dir", str(project)]
    assert _run_cli(mp, [*argv, "-o", str(registry)]) == 0


def file_ids(sbom: str) -> dict[str, str]:
    """The id of each non-directory ``software_File`` by name."""
    return {
        node["name"]: node["spdxId"]
        for node in json.loads(sbom)["@graph"]
        if node["type"] == "software_File"
        and node.get("software_fileKind") != "directory"
    }


def held_files(registry: Path) -> dict[str, str]:
    """Each held ``software_File`` key with the content of a file of
    :data:`FILES` -> its id."""
    shas = {hashlib.sha256(data).hexdigest() for data in FILES.values()}
    return {
        name: entry.spdx_id
        for (type_name, name), entry in IdRegistry.load(registry).elements.items()
        if type_name == FILE_TYPE and entry.sha256 in shas
    }


def model_ids(sbom: str) -> list[str]:
    """The id of each ``ai_AIPackage``."""
    return [
        node["spdxId"]
        for node in json.loads(sbom)["@graph"]
        if node["type"] == "ai_AIPackage"
    ]


def held_models(registry: Path) -> dict[str, str]:
    """Each held ``ai_AIPackage`` key -> its id."""
    return {
        name: entry.spdx_id
        for (type_name, name), entry in IdRegistry.load(registry).elements.items()
        if type_name == AI_PACKAGE_TYPE
    }


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        (name,) = [n for n in zf.namelist() if "/sboms/" in n]
        return zf.read(name).decode("utf-8")


def wheel_of(directory: Path) -> Path:
    """The demo project's wheel, built in *directory*."""
    extra = {name: data for name, data in FILES.items() if name != "demo/__init__.py"}
    return _make_dummy_wheel(directory / "dist", "demo", "1.0.0", extra_members=extra)


#: A runner given *project*, *registry*, scratch dir and monkeypatch.
Runner = Callable[[Path, Path, Path, pytest.MonkeyPatch], str]


class Run(NamedTuple):
    """A surface: *run(project, registry, scratch, monkeypatch)* -> the SBOM;
    *name(key)*, the SBOM name of the file keyed *key*; whether it
    *harvests* into the registry."""

    run: Runner
    name: Callable[[str], str]
    harvests: bool


def _cli_project(project: Path, reg: Path, tmp: Path, mp: pytest.MonkeyPatch) -> str:
    out = tmp / "cli.spdx3.json"
    argv = ["project", str(project), "--id-registry", str(reg), "-o", str(out)]
    assert _run_cli(mp, argv) == 0
    return out.read_text(encoding="utf-8")


def _lib_project(project: Path, reg: Path, _tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(project, creation_metadata=None, id_registry=reg)


def allow_build(
    project: Path,
    reg: Path,
    mp: pytest.MonkeyPatch,
    *,
    extra: dict[str, bytes] | None = None,
) -> str:
    """A backend with no static file list: the build's files (:data:`FILES`
    and *extra*, by installed path) are read."""
    manifest = project / "pyproject.toml"
    text = manifest.read_text(encoding="utf-8").replace(
        'requires = ["hatchling"]\nbuild-backend = "hatchling.build"',
        'requires = ["uv_build"]\nbuild-backend = "uv_build"',
    )
    manifest.write_bytes(text.encode("utf-8"))
    install_fake_build(mp).entries = {**FILES, **(extra or {})}
    return generate_project_sbom(
        project,
        creation_metadata=None,
        id_registry=reg,
        build_options=BuildOptions(allow=True),
    )


def _allow_build(project: Path, reg: Path, _tmp: Path, mp: pytest.MonkeyPatch) -> str:
    return allow_build(project, reg, mp)


def sdist_of(directory: Path) -> Path:
    """The demo project's sdist, built in *directory*."""
    members: dict[str, bytes | None] = {f"src/{n}": d for n, d in FILES.items()}
    return _make_sdist(directory, members=members)


def _cli(command: str, archive: Callable[[Path], Path], with_project: bool) -> Runner:
    """``loom <command> <archive>``, with ``--project-dir`` when
    *with_project*."""

    def run(project: Path, reg: Path, tmp: Path, mp: pytest.MonkeyPatch) -> str:
        out = tmp / f"{command}.spdx3.json"
        argv = [command, str(archive(tmp)), "--id-registry", str(reg), "-o", str(out)]
        if with_project:
            argv += ["--project-dir", str(project)]
        assert _run_cli(mp, argv) == 0
        return out.read_text(encoding="utf-8")

    return run


def _lib(function: Callable[..., str], archive: Callable[[Path], Path]) -> Runner:
    """The library *function* on an archive, with ``project_dir=``."""

    def run(project: Path, reg: Path, tmp: Path, _mp: pytest.MonkeyPatch) -> str:
        return function(archive(tmp), id_registry=reg, project_dir=project)

    return run


def _lib_wheel(_project: Path, reg: Path, tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_wheel_sbom(wheel_of(tmp), id_registry=reg)


def _embed(with_project: bool) -> Runner:
    def run(project: Path, reg: Path, tmp: Path, _mp: pytest.MonkeyPatch) -> str:
        wheel = wheel_of(tmp)
        directory = project if with_project else None
        embed_wheel_sbom(wheel, project_dir=directory, id_registry=reg)
        return _embedded(wheel)

    return run


def _hook(project: Path, _reg: Path, _tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    """The project's own ``[tool.pitloom] id-registry``: the hook's only
    route."""
    hook = make_hook(str(project), {})
    data: dict[str, Any] = {}
    hook.initialize("standard", data)
    staged = staged_sbom(data)
    assert staged is not None
    sbom = staged.read_text(encoding="utf-8")
    hook.finalize("standard", data, "")
    return sbom


def _installed(key: str) -> str:
    return KEYS[key]


def _in_sdist(key: str) -> str:
    return f"demo-1.0.0/{key}"


SURFACES: dict[str, Run] = {
    "cli-project": Run(_cli_project, _installed, True),
    "lib-project": Run(_lib_project, _installed, True),
    "allow-build": Run(_allow_build, _installed, True),
    "sdist": Run(_cli("project", sdist_of, False), _in_sdist, True),
    "wheel": Run(_lib_wheel, _installed, True),
    # An archive with --project-dir / project_dir= (P5b).
    "cli-sdist-project": Run(_cli("project", sdist_of, True), _in_sdist, True),
    "lib-sdist-project": Run(_lib(generate_project_sbom, sdist_of), _in_sdist, True),
    "cli-generate-sdist-project": Run(
        _cli("generate", sdist_of, True), _in_sdist, True
    ),
    "cli-wheel-project": Run(_cli("wheel", wheel_of, True), _installed, True),
    "lib-wheel-project": Run(_lib(generate_wheel_sbom, wheel_of), _installed, True),
    "lib-generate-wheel-project": Run(_lib(generate, wheel_of), _installed, True),
    "embed-wheel": Run(_embed(False), _installed, False),
    "embed-wheel-project": Run(_embed(True), _installed, False),
    "hook": Run(_hook, _installed, False),
}
