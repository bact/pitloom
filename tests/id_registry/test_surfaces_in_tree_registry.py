# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Loom ID registry declared inside the project's package tree is left
out of the file set and the Merkle root on every surface that walks the
project, with one ``WARNING:`` per run; its SBOM and its own bytes settle.

See also: :mod:`tests.id_registry.surfaces_shared` (the runners driven
here), tests/core/models_wheel/test_models_wheel_exclude_path.py (the
discovery function), tests/id_registry/test_registry_generate.py (``id
generate``).

See also: test_surfaces_in_tree_registry_archive.py (archive copies of
the registry and the registry-as-root cases).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import (
    generate_project_sbom,
)
from pitloom.id_registry import IdRegistry
from tests.assemble.conftest import _make_dummy_wheel
from tests.conftest import FIXTURES_DIR
from tests.id_registry._surfaces_in_tree_registry_shared import (
    _in_tree_registry,
    _left_out_warnings,
)
from tests.id_registry.surfaces_base import _run_cli
from tests.id_registry.surfaces_shared import SURFACES, Declare, demo_project

pytestmark = pytest.mark.usefixtures("fixed_epoch")

_HAS_BUILD = all(importlib.util.find_spec(name) for name in ("build", "hatchling"))

#: The surfaces that walk the project's files, declared by ``[tool.pitloom]``
#: (a wheel or an environment target has no project walk of its own).
WALKING_SURFACES = (
    "cli-project",
    "cli-generate",
    "lib-generate",
    "lib-generate_project_sbom",
    "cli-enrich-project",
    "cli-embed-wheel-project",
    "lib-embed_wheel_sbom",
    "hook",
)


@pytest.mark.parametrize("surface", WALKING_SURFACES)
def test_surface_leaves_the_declared_registry_out_once(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = _in_tree_registry(tmp_path)
    declare = Declare(own_key=registry)

    with caplog.at_level(logging.WARNING):
        outcome = SURFACES[surface](tmp_path, monkeypatch, declare)

    assert outcome in (None, 0)
    warnings = _left_out_warnings(caplog)
    assert len(warnings) == 1, caplog.records
    assert warnings[0].startswith(f"ID registry: {registry} ")
    out = tmp_path / "out.spdx3.json"
    if out.exists():
        assert "reg.json" not in out.read_text(encoding="utf-8")


def test_registry_outside_the_tree_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry = tmp_path / "elsewhere" / "reg.json"
    registry.parent.mkdir()
    IdRegistry.new("demo").save(registry)
    project = demo_project(tmp_path)

    with caplog.at_level(logging.WARNING):
        generate_project_sbom(project, id_registry=registry, creation_metadata=None)

    assert not _left_out_warnings(caplog)


def _run_library(project: Path, registry: Path, out: Path) -> None:
    generate_project_sbom(
        project, output_path=out, id_registry=registry, creation_metadata=None
    )


def _run_cli_project(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Path, Path, Path], None]:
    def run(project: Path, registry: Path, out: Path) -> None:
        argv = ["project", str(project), "-o", str(out)]
        assert _run_cli(monkeypatch, [*argv, "--id-registry", str(registry)]) == 0

    return run


@pytest.mark.parametrize("route", ["library", "cli"])
def test_in_tree_registry_settles(
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Run 2 and run 3 give byte-identical SBOMs and registries: the
    registry the previous run rewrote is not part of the Merkle root."""
    registry = _in_tree_registry(tmp_path)
    project = demo_project(tmp_path)
    run = _run_library if route == "library" else _run_cli_project(monkeypatch)
    sboms: list[bytes] = []
    registries: list[bytes] = []

    for number in (1, 2, 3):
        out = tmp_path / f"out{number}.spdx3.json"
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            run(project, registry, out)
        assert len(_left_out_warnings(caplog)) == 1
        sboms.append(out.read_bytes())
        registries.append(registry.read_bytes())

    # Not vacuous: run 1 filled the registry, and the SBOM names the package
    # file but not the registry.
    assert json.loads(registries[0])["elements"]["software_File"]
    assert b"demo/__init__.py" in sboms[0]
    assert b"demo/reg.json" not in sboms[0]
    assert sboms[1] == sboms[2]
    assert registries[1] == registries[2]


def _in_tree_backend_project(tmp_path: Path) -> Path:
    """The sample Hatchling project behind an in-tree PEP 517 backend
    (``backend-path = ["."]``, no build hook): a ``--no-build-isolation``
    build needs neither the network nor a static discovery module, so
    ``--allow-build`` discovers its files by build-and-read."""
    project = tmp_path / "proj"
    shutil.copytree(FIXTURES_DIR / "projects" / "sampleproject-hatchling", project)
    toml = project / "pyproject.toml"
    text = toml.read_text(encoding="utf-8")
    text = text.replace(
        'build-backend = "hatchling.build"',
        'build-backend = "mybackend"\nbackend-path = ["."]',
    ).replace("[tool.hatch.build.hooks.pitloom]\nenabled = true\n", "")
    toml.write_text(text, encoding="utf-8")
    (project / "mybackend.py").write_text(
        "from hatchling.build import *  # noqa: F403\n", encoding="utf-8"
    )
    return project


_BUILD_FLAGS = ["--allow-build", "--no-build-isolation"]


@pytest.mark.skipif(not _HAS_BUILD, reason="needs build and hatchling")
def test_in_tree_registry_settles_under_build_and_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``--allow-build`` reads the built wheel's copies, outside the
    project: the registry is still left out, once per run, and settles --
    for ``project`` and ``embed-wheel`` alike."""
    project = _in_tree_backend_project(tmp_path)
    registry = project / "src" / "sampleproject_hatchling" / "reg.json"
    monkeypatch.chdir(project)
    assert _run_cli(monkeypatch, ["id", "generate", "src", "-o", str(registry)]) == 0
    flags = [*_BUILD_FLAGS, "--id-registry", str(registry)]
    sboms: list[bytes] = []
    registries: list[bytes] = []
    for number in (1, 2, 3):
        out = tmp_path / f"ab{number}.json"
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            assert _run_cli(monkeypatch, ["project", ".", *flags, "-o", str(out)]) == 0
        assert len(_left_out_warnings(caplog)) == 1, caplog.records
        sboms.append(out.read_bytes())
        registries.append(registry.read_bytes())

    assert b"sampleproject_hatchling/__init__.py" in sboms[0]  # not vacuous
    assert b"reg.json" not in sboms[0]
    assert sboms[1] == sboms[2]
    assert registries[1] == registries[2]

    wheel = _make_dummy_wheel(tmp_path / "dist", "sampleproject_hatchling", "0.1.0")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        argv = ["embed-wheel", str(wheel), "--project-dir", ".", *flags]
        assert _run_cli(monkeypatch, argv) == 0
    assert len(_left_out_warnings(caplog)) == 1, caplog.records


def test_id_generate_indexes_a_project_below_an_ignored_name_without_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``id generate`` under ``<tmp>/build/``: the project is indexed, and
    the declared registry (any file name) is not, on the second run."""
    project = demo_project(tmp_path / "build")
    registry = project / "demo" / "my-ids.json"
    argv = ["id", "generate", str(project / "demo")]
    argv += ["--project-dir", str(project), "-o", str(registry)]

    for _ in (1, 2):
        assert _run_cli(monkeypatch, argv) == 0

    files = json.loads(registry.read_text(encoding="utf-8"))["elements"][
        "software_File"
    ]
    assert set(files) == {"demo/__init__.py"}
