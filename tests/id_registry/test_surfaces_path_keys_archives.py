# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``--project-dir`` of ``wheel``, ``project <sdist>`` and ``generate`` (the
library's ``project_dir=``): an archive's members are keyed below the
project's prefix, so a registry rooted above the project (a monorepo) gives
them the ids ``id generate`` wrote; and the option's misuses.

See also: _surfaces_path_keys_shared.py (the project and runners),
test_surfaces_path_keys.py (the drift guard over every surface),
test_surfaces_path_keys_embed.py (``embed-wheel --project-dir``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate, generate_project_sbom, generate_wheel_sbom
from pitloom.id_registry import IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.id_registry._surfaces_path_keys_shared import (
    MODEL,
    REGISTRY,
    SURFACES,
    file_ids,
    held_files,
    held_models,
    model_ids,
    sdist_of,
    src_project,
    wheel_of,
)
from tests.id_registry.surfaces_base import _run_cli

pytestmark = pytest.mark.usefixtures("fixed_epoch")

_OUTSIDE_INFO = (
    "file(s) keyed by their path as read: the project is outside the registry's root"
)


def _monorepo(tmp_path: Path) -> tuple[Path, Path]:
    """``pkgs/demo`` below a registry root, ``id generate`` having run over
    it: the project and the registry file."""
    repo = tmp_path / "repo"
    project = src_project(repo / "pkgs" / "demo", registry=f"../../{REGISTRY}")
    registry = IdRegistry.new("demo", project_root=repo)
    registry.generate([project / "src"], project)
    registry.save(repo / REGISTRY)
    return project, repo / REGISTRY


def _run(surface: str, project: Path, registry: Path, mp: pytest.MonkeyPatch) -> str:
    scratch = project.parent / f"run-{surface}"
    scratch.mkdir()
    return SURFACES[surface].run(project, registry, scratch, mp)


@pytest.mark.parametrize(
    "surface", ["cli-wheel-project", "lib-wheel-project", "lib-generate-wheel-project"]
)
def test_monorepo_wheel_model_reuses_its_id(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wheel's model is keyed below the prefix too, through its file."""
    project, registry = _monorepo(tmp_path)
    held = held_models(registry)
    assert list(held) == [f"pkgs/demo/src/{MODEL}"]  # non-vacuous

    assert model_ids(_run(surface, project, registry, monkeypatch)) == list(
        held.values()
    )
    assert held_models(registry) == held


@pytest.mark.parametrize("surface", ["wheel", "sdist"])
def test_monorepo_archive_without_project_dir_misses(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--project-dir`` an archive has no project: its members are
    keyed by their archive paths, miss, and are harvested at the root."""
    project, registry = _monorepo(tmp_path)
    held = held_files(registry)

    ids = file_ids(_run(surface, project, registry, monkeypatch))

    assert not set(ids.values()) & set(held.values())
    added = set(held_files(registry)) - set(held)
    assert added
    assert not any(key.startswith("pkgs/") for key in added)


#: (command, archive builder) for each CLI route with an archive target.
_CLI_ARCHIVES: list[tuple[str, Callable[[Path], Path]]] = [
    ("wheel", wheel_of),
    ("project", sdist_of),
    ("generate", wheel_of),
]
_IDS = ["wheel", "project-sdist", "generate-wheel"]


@pytest.mark.parametrize("missing", [True, False], ids=["missing", "a-file"])
@pytest.mark.parametrize(("command", "archive"), _CLI_ARCHIVES, ids=_IDS)
def test_cli_project_dir_not_a_directory_fails(
    command: str,
    archive: Callable[[Path], Path],
    missing: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, registry = _monorepo(tmp_path)
    target = archive(tmp_path)
    given = tmp_path / "absent" if missing else target
    out = tmp_path / "out.spdx3.json"
    argv = [command, str(target), "--project-dir", str(given)]

    code = _run_cli(
        monkeypatch, [*argv, "--id-registry", str(registry), "-o", str(out)]
    )

    assert code == 1
    (line,) = [x for x in capsys.readouterr().err.splitlines() if "ERROR" in x]
    assert line.startswith("ERROR: ")
    assert line.endswith(f"project directory not found: {given.resolve()}")
    assert not out.exists()


@pytest.mark.parametrize(
    ("function", "archive"),
    [
        (generate_wheel_sbom, wheel_of),
        (generate_project_sbom, sdist_of),
        (generate, wheel_of),
    ],
    ids=["wheel", "sdist", "generate-wheel"],
)
def test_library_project_dir_not_a_directory_raises(
    function: Callable[..., str], archive: Callable[[Path], Path], tmp_path: Path
) -> None:
    _, registry = _monorepo(tmp_path)
    with pytest.raises(FileNotFoundError, match="project directory not found"):
        function(archive(tmp_path), id_registry=registry, project_dir=tmp_path / "x")


@pytest.mark.parametrize(
    ("command", "target"),
    [("wheel", wheel_of), ("project", sdist_of), ("embed-wheel", wheel_of)],
    ids=["wheel", "project-sdist", "embed-wheel"],
)
def test_project_dir_outside_the_root_says_so(
    command: str,
    target: Callable[[Path], Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A project directory outside the registry's root keys every member
    by its archive path, with one ``INFO:`` saying why."""
    _, registry = _monorepo(tmp_path)
    elsewhere = src_project(tmp_path / "elsewhere")
    argv = [command, str(target(tmp_path)), "--project-dir", str(elsewhere)]
    argv += ["--id-registry", str(registry)]
    if command != "embed-wheel":
        argv += ["-o", str(tmp_path / "out.spdx3.json")]

    assert _run_cli(monkeypatch, argv) == 0

    err = capsys.readouterr().err.splitlines()
    (line,) = [x for x in err if _OUTSIDE_INFO in x]
    assert line.startswith("INFO: ID registry: ")


@pytest.mark.parametrize(
    ("command", "target", "reason"),
    [
        ("wheel", "wheel", "without an ID registry"),
        ("project", "sdist", "without an ID registry"),
        ("project", "dir", "for a project directory target"),
        ("generate", "dir", "for a project directory target"),
    ],
    ids=["wheel-no-registry", "sdist-no-registry", "project-dir", "generate-dir"],
)
def test_project_dir_with_no_effect_warns(
    command: str,
    target: str,
    reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No registry to key for (an archive given none), or a directory target
    (itself the project; given a registry): one ``WARNING:``, and the SBOM
    is the one without the option."""
    project, registry = _monorepo(tmp_path)
    paths = {"wheel": wheel_of, "sdist": sdist_of}
    given = paths[target](tmp_path) if target in paths else project
    argv = [command, str(given), "--no-update-id-registry"]
    argv += [] if target in paths else ["--id-registry", str(registry)]
    outputs: list[bytes] = []
    for extra in ([], ["--project-dir", str(project)]):
        out = tmp_path / f"out{len(outputs)}.spdx3.json"
        capsys.readouterr()
        assert _run_cli(monkeypatch, [*argv, *extra, "-o", str(out)]) == 0
        outputs.append(out.read_bytes())

    (line,) = [x for x in capsys.readouterr().err.splitlines() if "WARNING" in x]
    assert line.startswith(f"WARNING: Options: {given.parent}")
    assert f": --project-dir has no effect {reason} (" in line
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("with_project", [True, False], ids=["project-dir", "none"])
@pytest.mark.parametrize("sdist", [False, True], ids=["wheel", "sdist"])
def test_registry_copy_is_taken_below_the_project_dir(
    sdist: bool, with_project: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A copy of the registry in an archive is recognised by its path below
    ``project_dir``, as ``embed-wheel --project-dir`` does; without one,
    below the nearest project holding the registry (here ``sub/``)."""
    project = src_project(tmp_path / "repo" / "pkgs" / "demo")
    (project / "sub").mkdir()
    (project / "sub" / "pyproject.toml").write_bytes(b'[project]\nname = "s"\n')
    registry = project / "sub" / REGISTRY
    IdRegistry.new("demo", project_root=tmp_path / "repo").save(registry)
    member = f"sub/{REGISTRY}"
    given = project if with_project else None
    if sdist:
        archive = _make_sdist(tmp_path, members={member: b"{}\n"})
        sbom = generate_project_sbom(archive, id_registry=registry, project_dir=given)
        member = f"demo-1.0.0/{member}"
    else:
        extra = {member: b"{}\n"}
        archive = _make_dummy_wheel(tmp_path / "dist", "demo", extra_members=extra)
        sbom = generate_wheel_sbom(archive, id_registry=registry, project_dir=given)

    assert set(file_ids(sbom))  # non-vacuous
    assert (member in file_ids(sbom)) is not with_project
    left_out = [r for r in caplog.records if "left out of it" in r.getMessage()]
    assert bool(left_out) is with_project


def test_wheel_verbose_names_the_project_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project, registry = _monorepo(tmp_path)
    argv = ["wheel", str(wheel_of(tmp_path)), "-v", "--project-dir", str(project)]
    argv += ["--id-registry", str(registry), "-o", str(tmp_path / "out.json")]

    assert _run_cli(monkeypatch, argv) == 0

    assert f"INFO: PROJECT_DIR={project}" in capsys.readouterr().err.splitlines()
