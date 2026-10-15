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
    generate_wheel_sbom,
    project_document_id,
)
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.conftest import FIXTURES_DIR
from tests.id_registry.surfaces_base import _own_key_toml, _run_cli
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
_NEEDLE = "is inside the project's file set; left out of it"


def _in_tree_registry(tmp_path: Path) -> Path:
    """An existing, empty registry in the demo project's package."""
    path = tmp_path / "proj" / "demo" / "reg.json"
    path.parent.mkdir(parents=True)
    IdRegistry.new("demo").save(path)
    return path


def _left_out_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if _NEEDLE in r.getMessage()]


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


def _rooted_registry(tmp_path: Path, root_is_project: bool = True) -> Path:
    """``demo/reg.json`` in the demo project, storing the project as its
    root (or, by default, its own directory)."""
    project = demo_project(tmp_path)
    registry = project / "demo" / "reg.json"
    root = project if root_is_project else None
    IdRegistry.new("demo", project_root=root).save(registry)
    return registry


#: Another file, named by a tail of the registry's path: never left out.
_TAIL_NAMED = {"reg.json": b'{"unrelated": true}\n'}


def _archive(
    directory: Path, copy: bytes | None, sdist: bool = False, tail: bool = True
) -> Path:
    """A wheel (or an sdist) of the demo project carrying *copy* (``None``:
    nothing) where a build puts the in-tree registry, ``demo/reg.json``,
    and (*tail*) a top-level ``reg.json`` of its own."""
    own = _TAIL_NAMED if tail else {}
    if sdist:
        directory.mkdir(exist_ok=True)
        members = {"demo/reg.json": copy, "demo/__init__.py": b"", **own}
        return _make_sdist(directory, members=members)
    extra = {**own, **({} if copy is None else {"demo/reg.json": copy})}
    return _make_dummy_wheel(directory / "dist", "demo", "1.0.0", extra_members=extra)


def _file_names(sbom: str) -> set[str]:
    graph = json.loads(sbom)["@graph"]
    return {e["name"] for e in graph if e["type"] == "software_File"}


#: Runs one route: (archive, registry, output, monkeypatch).
_Route = Callable[[Path, Path, Path, pytest.MonkeyPatch], object]


def _cli(command: str, *extra: str, project: bool = False) -> _Route:
    """``loom COMMAND TARGET EXTRA [--project-dir P] --id-registry R -o OUT``,
    P the registry's project."""

    def run(target: Path, registry: Path, out: Path, mp: pytest.MonkeyPatch) -> int:
        argv = [command, str(target), *extra, "--id-registry", str(registry)]
        if project:
            argv += ["--project-dir", str(registry.parents[1])]
        return _run_cli(mp, [*argv, "-o", str(out)])

    return run


def _lib_embed(project: bool) -> _Route:
    def run(archive: Path, registry: Path, out: Path, _: pytest.MonkeyPatch) -> None:
        directory = registry.parents[1] if project else None
        embed_wheel_sbom(
            archive, project_dir=directory, id_registry=registry, output_path=out
        )

    return run


def _lib(function: Callable[..., object]) -> _Route:
    def run(archive: Path, registry: Path, out: Path, _: pytest.MonkeyPatch) -> None:
        function(archive, id_registry=registry, output_path=out)

    return run


#: Every route that reads a wheel's or an sdist's members, and whether its
#: target is an sdist.
_ARCHIVE_ROUTES: dict[str, tuple[_Route, bool]] = {
    "cli-wheel": (_cli("wheel"), False),
    "cli-wheel-embed": (_cli("wheel", "--embed"), False),
    "cli-generate": (_cli("generate"), False),
    "cli-embed-wheel": (_cli("embed-wheel"), False),
    "cli-embed-wheel-project": (_cli("embed-wheel", project=True), False),
    "lib-generate_wheel_sbom": (_lib(generate_wheel_sbom), False),
    "lib-embed_wheel_sbom": (_lib_embed(False), False),
    "lib-embed_wheel_sbom-project": (_lib_embed(True), False),
    "cli-project-sdist": (_cli("project"), True),
    "lib-generate_project_sbom-sdist": (_lib(generate_project_sbom), True),
}
_STALE_COPY = b'{"an": "older registry"}\n'


@pytest.mark.parametrize("route", _ARCHIVE_ROUTES)
def test_archive_copy_of_the_registry_is_left_out_once(
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The copy a build put in the archive is an older registry (other
    bytes): its path below the stored project root says what it is. The
    SBOM is the one of the same archive without it, Merkle root included,
    from the same registry; a top-level ``reg.json`` stays. One warning
    for the copy; none without it, unless a project walk met the registry."""
    run, sdist = _ARCHIVE_ROUTES[route]
    registry = _rooted_registry(tmp_path)
    before = registry.read_bytes()
    sboms: list[str] = []
    warned: list[list[str]] = []
    for copy in (None, _STALE_COPY):
        registry.write_bytes(before)
        archive = _archive(tmp_path / str(copy is None), copy, sdist)
        out = tmp_path / f"out-{copy is None}.json"
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            assert run(archive, registry, out, monkeypatch) in (None, 0)
        sboms.append(out.read_text(encoding="utf-8"))
        warned.append([w.split(" is ")[0] for w in _left_out_warnings(caplog)])

    names = _file_names(sboms[0])
    assert "demo/__init__.py" in sboms[0]  # not vacuous
    assert ("demo-1.0.0/reg.json" if sdist else "reg.json") in names
    assert sboms[1] == sboms[0]
    one = [f"ID registry: {registry}"]
    assert warned == [one if route.endswith("-project") else [], one]


@pytest.mark.parametrize("route", ["cli-wheel", "cli-project-sdist"])
def test_archive_copy_is_kept_when_the_root_is_the_registry_directory(
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A registry whose root is its own directory cannot tell where the
    archive's tree starts: nothing is left out, silently."""
    run, sdist = _ARCHIVE_ROUTES[route]
    registry = _rooted_registry(tmp_path, root_is_project=False)
    archive = _archive(tmp_path, registry.read_bytes(), sdist, tail=False)
    out = tmp_path / "out.json"

    with caplog.at_level(logging.WARNING):
        assert run(archive, registry, out, monkeypatch) == 0

    assert "demo/reg.json" in out.read_text(encoding="utf-8")
    assert not _left_out_warnings(caplog)


@pytest.mark.parametrize("project", [False, True], ids=["standalone", "project"])
def test_embed_wheel_batch_warns_once(
    project: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two wheels carrying the copy, in one ``embed-wheel`` run (with a
    project, its discovery leaves the registry out too): one warning."""
    registry = _rooted_registry(tmp_path)
    wheels = [str(_archive(tmp_path / n, _STALE_COPY)) for n in ("a", "b")]
    argv = ["embed-wheel", *wheels, "--id-registry", str(registry)]
    if project:
        argv += ["--project-dir", str(registry.parents[1])]

    with caplog.at_level(logging.WARNING):
        assert _run_cli(monkeypatch, argv) == 0

    assert len(_left_out_warnings(caplog)) == 1


def test_in_tree_registry_settles_across_wheel_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``project``, ``wheel``, ``embed-wheel``, ``wheel``, three times, each
    time from a wheel built with the registry as it is then: each step of
    runs 2 and 3 gives byte-identical SBOMs and registries, and run 3
    changes no file or package entry.

    The project and the wheel are two documents, so the registry's
    per-document ``Tool``/``SoftwareAgent`` ids follow whichever ran last
    (a known item: not a lookup type); the two wheel-only steps after them
    update nothing."""
    registry = _rooted_registry(tmp_path)
    project = registry.parents[1]
    runs: list[list[tuple[bytes, bytes, int]]] = []
    for number in (1, 2, 3):
        wheel = _archive(tmp_path / f"run{number}", registry.read_bytes())
        steps = [
            (_cli("project"), project),
            (_cli("wheel"), wheel),
            (_cli("embed-wheel", project=True), wheel),
            (_cli("wheel"), wheel),
        ]
        results: list[tuple[bytes, bytes, int]] = []
        for index, (run, target) in enumerate(steps):
            out = tmp_path / f"{number}-{index}.json"
            caplog.clear()
            with caplog.at_level(logging.INFO):
                assert run(target, registry, out, monkeypatch) == 0
            stale = sum("updated stale" in r.getMessage() for r in caplog.records)
            results.append((out.read_bytes(), registry.read_bytes(), stale))
        runs.append(results)

    def lookup(registry_bytes: bytes) -> str:
        elements = json.loads(registry_bytes)["elements"]
        return json.dumps([elements["software_File"], elements["software_Package"]])

    first = [sbom for sbom, _, _ in runs[0]]
    assert b"demo/__init__.py" in first[1]  # not vacuous
    assert all(b"demo/reg.json" not in sbom for sbom in first)
    assert runs[1] == runs[2]
    assert {lookup(r) for _, r, _ in runs[2]} == {lookup(runs[1][-1][1])}
    assert [stale for _, _, stale in runs[2][2:]] == [0, 0]


def test_project_document_id_matches_the_sbom_with_an_in_tree_registry(
    tmp_path: Path,
) -> None:
    """``loom fragment list`` compares fragments with this id: it must be
    the SBOM's own, so it walks the files without the registry too."""
    registry = _in_tree_registry(tmp_path)
    project = demo_project(tmp_path, _own_key_toml(Declare(own_key=registry)))

    sbom = json.loads(generate_project_sbom(project, creation_metadata=None))
    (document,) = [e for e in sbom["@graph"] if e["type"] == "SpdxDocument"]
    assert project_document_id(project) == document["spdxId"]
