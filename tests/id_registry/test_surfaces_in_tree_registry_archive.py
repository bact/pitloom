# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Loom ID registry declared in the project's package tree is left out of
the archive copies (wheel and sdist) built from that project, with one
``WARNING:`` per run; a root that is the registry's own directory keeps
its copy.

See also: test_surfaces_in_tree_registry.py (the walking surfaces and
in-tree settling).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
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
from tests.id_registry._surfaces_in_tree_registry_shared import (
    _in_tree_registry,
    _left_out_warnings,
)
from tests.id_registry.surfaces_base import _own_key_toml, _run_cli
from tests.id_registry.surfaces_shared import Declare, demo_project

pytestmark = pytest.mark.usefixtures("fixed_epoch")


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
