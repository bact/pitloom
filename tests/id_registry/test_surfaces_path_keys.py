# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: every surface that looks a ``software_File`` up gives it the
one id its path key holds, in either order (registry first or surface
first), and a harvest leaves one key per file.

See also: _surfaces_path_keys_shared.py (the project and runners),
test_keys_files.py (``keys.file_lookup_key``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.assemble.spdx3._document_file_hits import file_keys
from pitloom.core.document import DocumentModel
from pitloom.core.project import FilesOrigin, ProjectFile, ProjectMetadata
from pitloom.id_registry import FILE_TYPE, IdRegistry
from tests.id_registry._surfaces_path_keys_shared import (
    FILES,
    KEYS,
    REGISTRY,
    SURFACES,
    allow_build,
    file_ids,
    held_files,
    id_generate,
    src_project,
)
from tests.id_registry.surfaces_base import _run_cli

pytestmark = pytest.mark.usefixtures("fixed_epoch")

_PROJECT = FilesOrigin()
_SDIST = FilesOrigin(archive=True, sdist=True)
_WHEEL = FilesOrigin(archive=True)

_HARVESTING = [name for name, surface in SURFACES.items() if surface.harvests]


def _ids(
    surface: str, project: Path, registry: Path, mp: pytest.MonkeyPatch
) -> dict[str, str]:
    """Each key of :data:`KEYS` -> the id *surface* gives its file."""
    run = SURFACES[surface]
    scratch = project.parent / f"run-{surface}"
    scratch.mkdir()
    ids = file_ids(run.run(project, registry, scratch, mp))
    return {key: ids[run.name(key)] for key in KEYS}


@pytest.mark.parametrize("surface", list(SURFACES))
def test_surface_reuses_generated_ids(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    id_generate(monkeypatch, project, registry)
    held = held_files(registry)
    assert set(held) == set(KEYS)  # non-vacuous: the path keys

    assert _ids(surface, project, registry, monkeypatch) == held
    assert held_files(registry) == held  # no key added, none moved


@pytest.mark.parametrize("surface", _HARVESTING)
def test_surface_first_then_id_generate(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A surface harvesting into an empty registry, then ``id generate``:
    one key per file, the path key, holding the surface's ids."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    first = _ids(surface, project, registry, monkeypatch)

    id_generate(monkeypatch, project, registry)

    assert held_files(registry) == first


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("wheel", "lib-project"),
        ("lib-project", "wheel"),
        ("wheel", "sdist"),
        ("sdist", "wheel"),
        ("allow-build", "wheel"),
        ("wheel", "hook"),
        ("wheel", "embed-wheel-project"),
    ],
)
def test_two_surfaces_share_ids(
    first: str, second: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two surfaces of different key shapes, starting empty: the second
    reuses the first's ids, and one key per file is left."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    ids = _ids(first, project, registry, monkeypatch)

    assert _ids(second, project, registry, monkeypatch) == ids
    assert sorted(held_files(registry).values()) == sorted(ids.values())


#: Every surface that names the project directory (embed-wheel's is in
#: test_surfaces_path_keys_embed.py, with its model).
_MONOREPO = [
    "cli-project",
    "lib-project",
    "hook",
    "allow-build",
    "cli-sdist-project",
    "lib-sdist-project",
    "cli-generate-sdist-project",
    "cli-wheel-project",
    "lib-wheel-project",
    "lib-generate-wheel-project",
]


@pytest.mark.parametrize("surface", _MONOREPO)
def test_monorepo_project_reuses_prefixed_ids(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registry rooted above the project keys its files with the
    project's path from that root."""
    repo = tmp_path / "repo"
    project = src_project(repo / "pkgs" / "demo", registry=f"../../{REGISTRY}")
    registry = IdRegistry.new("demo", project_root=repo)
    registry.generate([project / "src"], project)
    registry.save(repo / REGISTRY)
    held = held_files(repo / REGISTRY)
    assert set(held) == {f"pkgs/demo/{key}" for key in KEYS}

    ids = _ids(surface, project, repo / REGISTRY, monkeypatch)

    assert {f"pkgs/demo/{key}": spdx_id for key, spdx_id in ids.items()} == held
    assert held_files(repo / REGISTRY) == held


@pytest.mark.parametrize(
    ("registry_dir", "physical", "origin", "reason"),
    [
        ("elsewhere", "src/demo/x.py", _PROJECT, "the project is outside the"),
        ("proj", "../../x.py", _PROJECT, "their path is outside the registry's"),
        ("proj", "<tmp>/x.py", _PROJECT, "their path is outside the registry's"),
        (".", "<tmp>/shared/x.py", _PROJECT, None),
        ("proj", "src/demo/x.py", _PROJECT, None),
        ("proj", "../x.py", _SDIST, "leads outside the archive's project"),
        # An archive's --project-dir outside the root: every member.
        ("elsewhere", "src/demo/x.py", _SDIST, "the project is outside the"),
        ("elsewhere", "demo/x.py", _WHEEL, "the project is outside the"),
        ("proj", "demo/x.py", _WHEEL, None),
        # A project outside the root, its files absolute below it: path keys.
        ("root", "<tmp>/root/x.py", _PROJECT, None),
    ],
    ids=[
        "outside-root",
        "no-join",
        "absolute-out",
        "absolute-in",
        "in-root",
        "sdist",
        "sdist-outside-root",
        "wheel-outside-root",
        "wheel-in-root",
        "project-outside-files-in",
    ],
)
def test_fallback_keys_info_once_per_document(
    registry_dir: str,
    physical: str,
    origin: FilesOrigin,
    reason: str | None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Files given no path key get one ``INFO:`` per document, with their
    count and the reason; none when every file has a path key, a file
    outside the project (absolute) but below the root included."""
    project = tmp_path / "proj"
    project.mkdir()
    registry = IdRegistry.new("demo", project_root=tmp_path / registry_dir)
    physical = physical.replace("<tmp>", tmp_path.as_posix())
    files = [ProjectFile(f"{physical}{n}", f"demo/x{n}.py") for n in range(3)]
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", files=files),
        files_origin=origin._replace(project_dir=project),
    )

    with caplog.at_level(logging.INFO, logger="pitloom.id_registry"):
        keys = file_keys(doc, registry)

    infos = [r.getMessage() for r in caplog.records if "path as read" in r.message]
    if reason is None:
        assert not infos
        assert all(lookup.path for lookup in keys.values())  # non-vacuous
    else:
        (message,) = infos
        assert message.startswith("ID registry: 3 file(s) keyed by their path")
        assert reason in message


def test_loom_dataset_file_after_a_wheel_reuses_its_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loom dataset's file typed by its ``src/`` path hits the wheel's
    installed-path key through the layout alias."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    wheel = _ids("wheel", project, registry, monkeypatch)
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    out = tmp_path / "loom.json"

    with loom.run(out, id_registry=IdRegistry.load(registry)):
        loom.add_input_dataset("src/demo/x.py")

    assert file_ids(out.read_text(encoding="utf-8")) == {
        "src/demo/x.py": wheel["src/demo/x.py"]
    }


#: A built ``.data`` member: no layout alias, keyed below the prefix too.
_DATA = "demo-1.0.0.data/scripts/run"


@pytest.mark.parametrize("flat", [False, True], ids=["src", "flat"])
@pytest.mark.parametrize("generate_first", [True, False], ids=["generate", "build"])
def test_monorepo_allow_build_keys_below_the_project(
    flat: bool,
    generate_first: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Built files of a project below the registry's root are keyed below
    its prefix: ``id generate`` and ``--allow-build`` share one id per
    file in either order, and one key set (the project paths) is left."""
    repo = tmp_path / "repo"
    project = src_project(repo / "pkgs" / "demo", f"../../{REGISTRY}", flat=flat)
    path = repo / REGISTRY
    top = "" if flat else "src/"
    keys = {f"pkgs/demo/{top}{name}": name for name in FILES}

    def generate() -> None:
        registry = IdRegistry.load(path)
        registry.generate([project / (top or "demo")], project)
        registry.save()

    def build() -> dict[str, str]:
        extra = {_DATA: b"#!run\n"}
        return file_ids(allow_build(project, path, monkeypatch, extra=extra))

    IdRegistry.new("demo", project_root=repo).save(path)
    if generate_first:
        generate()
    built = build()
    if not generate_first:
        generate()

    assert held_files(path) == {key: built[name] for key, name in keys.items()}
    assert build() == built
    data_key = (FILE_TYPE, f"pkgs/demo/{_DATA}")
    assert IdRegistry.load(path).elements[data_key].spdx_id == built[_DATA]


_FORCE_INCLUDE = (
    '\n[tool.hatch.build.targets.wheel.force-include]\n"../shared/s.py" = "demo/s.py"\n'
)


@pytest.mark.parametrize("surface", ["cli-project", "lib-project"])
@pytest.mark.parametrize("inside", [True, False], ids=["in-root", "out-of-root"])
def test_force_included_file_outside_the_project_keys_from_the_root(
    surface: str,
    inside: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A force-included ``../shared/s.py`` is keyed by its path from the
    registry's root, so it reuses the id ``id generate`` gave it; outside
    the root it keeps its installed path, with one ``INFO:`` saying so."""
    project = src_project(tmp_path / "proj")
    with (project / "pyproject.toml").open("a", encoding="utf-8") as manifest:
        manifest.write(_FORCE_INCLUDE)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "s.py").write_bytes(b"s = 1\n")
    root = tmp_path if inside else project
    registry = root / REGISTRY
    paths = [project / "src", *([tmp_path / "shared"] if inside else [])]
    argv = ["id", "generate", *map(str, paths), "--project-dir", str(root)]
    assert _run_cli(monkeypatch, [*argv, "-o", str(registry)]) == 0
    held = IdRegistry.load(registry).elements.get((FILE_TYPE, "shared/s.py"))
    assert (held is not None) is inside

    with caplog.at_level(logging.INFO, logger="pitloom.id_registry"):
        ids = _ids_of(surface, project, registry, monkeypatch)

    infos = [r.getMessage() for r in caplog.records if "path as read" in r.message]
    if held is not None:
        assert ids["demo/s.py"] == held.spdx_id
        assert not infos
    else:
        assert infos == [
            "ID registry: 1 file(s) keyed by their path as read: "
            "their path is outside the registry's root"
        ]


def _ids_of(
    surface: str, project: Path, registry: Path, mp: pytest.MonkeyPatch
) -> dict[str, str]:
    scratch = project.parent / f"run-{surface}"
    scratch.mkdir()
    return file_ids(SURFACES[surface].run(project, registry, scratch, mp))
