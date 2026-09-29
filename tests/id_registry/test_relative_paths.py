# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Relative ``id-registry`` path resolution, per declaration route.

:class:`~tests.id_registry.surfaces_base.Declare` and the ``SURFACES``
runners in :mod:`tests.id_registry.surfaces_shared` are built around
already-absolute paths -- every test here instead runs from a current
directory distinct from every candidate base directory (the project
directory, an explicit config file's own directory, and cwd itself), so a
surface resolving a relative path against the *wrong* base is caught
rather than accidentally passing because two candidate bases coincide.

Base directory per declaration route (verified against the resolving
code, not just its docstrings -- see ``CLAUDE.md``'s "A docstring or
comment describing 'how surface X does Y' is a claim, not a fact."):

- ``--id-registry``/``id_registry=`` (a flag/kwarg): the *generic* CLI
  cascade (``pitloom.cli.options_config.run_options``) makes a relative
  flag absolute against cwd before it ever reaches the library, so every
  CLI surface built on it resolves relative to cwd regardless of target
  kind. A bare library kwarg (no CLI involved) is resolved by
  ``pitloom.id_registry.resolve.resolve_registry`` itself, against the
  project directory for a directory project target, else cwd (a file
  target -- sdist/wheel/model/env/standalone -- or no project at all).
  ``pitloom id generate``/``pitloom id import`` resolve a relative
  ``-o``/``--id-registry`` the same way -- against cwd -- via their own
  :func:`pitloom.cli.id._resolve_id_registry_target` (``id import``'s
  project directory *is* cwd already, so this is only observable for
  ``id generate`` with a ``--project-dir`` different from cwd); a
  relative PATH argument to ``id generate`` resolves against cwd too.
  They are tested separately, in :mod:`tests.id_registry.
  test_relative_paths_id_commands`, rather than folded into the generic
  CLI loop, since ``--project-dir`` gives them an extra base directory
  the loop doesn't model.
- The project's own ``[tool.pitloom] id-registry`` (``own_key``): stays
  relative through ``pitloom.core._config_parse._read_id_registry``, and
  is resolved by whichever ``resolve_registry()`` call site the surface
  uses -- always the project directory when a project target is a
  directory.
- An explicit ``--config``/``pitloom_config=`` file's own key
  (``config_key``): ``pitloom.core.config_cascade.load_config_file``
  makes it absolute against that config file's own directory before the
  ``PitloomConfig`` is even returned, so it is resolved by the time any
  ``resolve_registry()`` call sees it -- the base directory a surface
  would otherwise use for a flag/own_key never comes into play.

See also: :mod:`tests.id_registry.surfaces_base` (``Declare``, relaxed to
accept a relative path for this module), :mod:`tests.id_registry.
test_surfaces` (the absolute-path declaration/failure/completeness
tests this module complements), :mod:`tests.id_registry.
test_relative_paths_id_commands` (`pitloom id generate`/`pitloom id
import`'s own cwd-based resolution, split out here).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.config_cascade import load_config_file
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from pitloom.loom import run as loom_run
from tests.id_registry.surfaces_base import Declare, demo_project, demo_wheel
from tests.id_registry.surfaces_shared import CLI_SURFACES, SUPPORTED_MODES, SURFACES

#: CLI surfaces resolved by the generic ``run_options()`` cascade -- every
#: ``cli-*`` surface offering ``flag`` except the two ``pitloom id``
#: subcommands, which have their own resolution (see module docstring).
_GENERIC_CLI_FLAG_SURFACES: tuple[str, ...] = tuple(
    sorted(
        name
        for name in CLI_SURFACES
        if "flag" in SUPPORTED_MODES[name]
        and name not in ("cli-id-generate", "cli-id-import")
    )
)


def _relative_registry(name: str, directory: Path) -> tuple[Path, Path]:
    """Save a fresh registry at ``directory / name``; return
    ``(relative_declare_value, absolute_expected_path)``."""
    absolute = (directory / name).resolve()
    IdRegistry.new("relative", path=absolute).save()
    return Path(name), absolute


# --- CLI flag: the generic cascade resolves against cwd -----------------


@pytest.mark.parametrize(
    "surface",
    _GENERIC_CLI_FLAG_SURFACES,
    ids=_GENERIC_CLI_FLAG_SURFACES,
)
def test_cli_flag_relative_resolves_against_cwd(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_spy: list[Path],
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    relative, expected = _relative_registry("rel.json", cwd)
    # A same-named file elsewhere: if the surface resolved against the
    # wrong base it would silently load this one instead of failing.
    IdRegistry.new("decoy", path=other / "rel.json").save()

    monkeypatch.chdir(cwd)
    declare = Declare(flag=relative)
    result = SURFACES[surface](tmp_path, monkeypatch, declare)

    assert result == 0, f"{surface} exited {result}"
    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected], f"{surface}: loaded {loaded}, expected {[expected]}"


# `pitloom id generate`/`pitloom id import`'s own cwd-based resolution
# (flag, PATH arguments, the M-e end-to-end workflow) moved to
# tests.id_registry.test_relative_paths_id_commands -- this file's size.

# --- own_key: the project's own key resolves against the project dir ----


@pytest.mark.parametrize(
    "surface",
    ["cli-project", "cli-generate", "lib-generate", "lib-generate_project_sbom"],
)
def test_own_key_relative_resolves_against_project_dir(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_spy: list[Path],
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    # demo_project() is called by the runner itself (with the own_key
    # TOML this Declare produces); pre-declare where its "proj" directory
    # will land so the expected/decoy paths can be built ahead of it.
    project_dir = tmp_path / "proj"
    other = tmp_path / "elsewhere"
    other.mkdir()
    relative, expected = _relative_registry("rel.json", project_dir)
    IdRegistry.new("decoy", path=other / "rel.json").save()
    IdRegistry.new("decoy", path=cwd / "rel.json").save()

    declare = Declare(own_key=relative)
    result = SURFACES[surface](tmp_path, monkeypatch, declare)

    if surface in CLI_SURFACES:
        assert result == 0, f"{surface} exited {result}"
    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected], f"{surface}: loaded {loaded}"


def test_hook_own_key_relative_resolves_against_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    project_dir = tmp_path / "proj"
    relative, expected = _relative_registry("rel.json", project_dir)
    IdRegistry.new("decoy", path=cwd / "rel.json").save()

    declare = Declare(own_key=relative)
    SURFACES["hook"](tmp_path, monkeypatch, declare)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


# --- config_key: resolves against the explicit config file's directory --


def test_cli_config_key_relative_resolves_against_config_file_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    project = demo_project(tmp_path / "proj-root")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    cfg_dir = tmp_path / "cfgdir"
    cfg_dir.mkdir()
    expected = (cfg_dir / "rel.json").resolve()
    IdRegistry.new("relative", path=expected).save()
    IdRegistry.new("decoy", path=cwd / "rel.json").save()
    IdRegistry.new("decoy", path=project / "rel.json").save()
    config_path = cfg_dir / "explicit-config.toml"
    config_path.write_text(
        '[tool.pitloom]\nid-registry = "rel.json"\n', encoding="utf-8"
    )

    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "project",
            str(project),
            "-o",
            str(tmp_path / "out.spdx3.json"),
            "--config",
            str(config_path),
        ],
    )
    assert __main__.main() == 0
    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


def test_library_config_key_relative_resolves_against_config_file_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    project = demo_project(tmp_path / "proj-root")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    cfg_dir = tmp_path / "cfgdir"
    cfg_dir.mkdir()
    expected = (cfg_dir / "rel.json").resolve()
    IdRegistry.new("relative", path=expected).save()
    IdRegistry.new("decoy", path=cwd / "rel.json").save()
    IdRegistry.new("decoy", path=project / "rel.json").save()
    config_path = cfg_dir / "explicit-config.toml"
    config_path.write_text(
        '[tool.pitloom]\nid-registry = "rel.json"\n', encoding="utf-8"
    )

    monkeypatch.chdir(cwd)
    cfg = load_config_file(config_path)
    generate_project_sbom(project, creation_metadata=None, pitloom_config=cfg)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


# --- library kwarg: project target (dir) -> project dir; else -> cwd ----


def test_library_kwarg_relative_project_dir_target_resolves_to_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    """Kills the ``_generators.py`` mutant replacing ``Path.cwd() if
    target_path.is_file() else target_path`` with ``Path.cwd()``: a
    directory project target must resolve a relative ``id_registry=``
    against the project directory, not cwd."""
    project = demo_project(tmp_path / "proj-root")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative, expected = _relative_registry("rel.json", project)
    IdRegistry.new("decoy", path=cwd / "rel.json").save()

    monkeypatch.chdir(cwd)
    generate_project_sbom(project, creation_metadata=None, id_registry=relative)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


def test_library_kwarg_relative_file_target_resolves_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    """A *file* project target (sdist archive) resolves relative to cwd,
    same as any project-less target -- the counterpart of the directory
    case above, and together they cover both branches the mutant in the
    docstring above collapses into one."""
    # pylint: disable=import-outside-toplevel
    from tests.assemble.conftest import _make_sdist

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    sdist = _make_sdist(
        src_dir,
        'requires-python = ">=3.10"\n',
        members={"demo/__init__.py": b"__version__ = '1.0.0'\n"},
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative, expected = _relative_registry("rel.json", cwd)
    IdRegistry.new("decoy", path=sdist.parent / "rel.json").save()

    monkeypatch.chdir(cwd)
    generate_project_sbom(sdist, creation_metadata=None, id_registry=relative)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


def test_library_kwarg_relative_non_project_target_resolves_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    wheel = demo_wheel(tmp_path / "wheel-src")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative, expected = _relative_registry("rel.json", cwd)

    monkeypatch.chdir(cwd)
    generate_wheel_sbom(wheel, id_registry=relative)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


def test_library_kwarg_relative_embed_wheel_sbom_without_project_resolves_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    """Kills the ``embed.py`` mutant replacing the standalone (no
    ``project_dir``) base directory with anything other than
    ``Path.cwd()``."""
    wheel = demo_wheel(tmp_path / "wheel-src")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative, expected = _relative_registry("rel.json", cwd)

    monkeypatch.chdir(cwd)
    embed_wheel_sbom(wheel, project_dir=None, id_registry=relative)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


def test_library_kwarg_relative_embed_wheel_sbom_with_project_resolves_to_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    """Counterpart of the standalone case above: with ``project_dir``
    given, ``embed.py``'s other resolve_registry() call site must use
    that project directory, not cwd."""
    project = demo_project(tmp_path / "proj-root")
    wheel = demo_wheel(tmp_path / "wheel-src")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative, expected = _relative_registry("rel.json", project)
    IdRegistry.new("decoy", path=cwd / "rel.json").save()

    monkeypatch.chdir(cwd)
    embed_wheel_sbom(wheel, project_dir=project, id_registry=relative)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]


def test_loom_run_kwarg_relative_resolves_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative, expected = _relative_registry("rel.json", cwd)

    monkeypatch.chdir(cwd)
    with loom_run(tmp_path / "frag.spdx3.json", id_registry=relative):
        pass

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [expected]
