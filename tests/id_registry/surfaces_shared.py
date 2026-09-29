# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Runners for every Pitloom surface that accepts a Loom ID registry --
the CLI subcommands offering ``--id-registry``, the public library
functions taking ``id_registry=``, the Hatchling build hook, and
``pitloom.loom.run``.

Each runner takes ``(tmp_path, monkeypatch, declare)`` where *declare* is
a :class:`~tests.id_registry.surfaces_base.Declare` saying how (if at all)
the run should point at a registry file, and executes that surface
against a small demo project. A CLI-backed runner returns the process
exit code (an ``int``); every other runner returns ``None`` on success
and lets its natural failure mode (``ValueError``, an ``ERROR:``/log
record) propagate -- the registry is an *input*, so callers compare
per-surface behaviour, never whole SBOM bytes across surfaces (see the
PR A2 spec, section 6).

``demo/__init__.py`` is written with the exact bytes
:func:`tests.assemble.conftest._make_dummy_wheel` bakes into its own
``demo/__init__.py`` (``__version__ = '1.0.0'``), so the same file --
same path, same hash -- appears on both the project and wheel surfaces;
this lets :mod:`tests.id_registry.test_surfaces_same_ids` assert the same
registry-minted id on both without caring which surface produced it.

See also: :mod:`tests.id_registry.surfaces_base` (``Declare``, the demo
project/wheel fixtures, and the CLI-argv/config-file helpers this module
and :mod:`tests.id_registry.surfaces_cli` both build on -- split out to
avoid an import cycle between this module and that one),
:mod:`tests.id_registry.test_surfaces_failures` (the exhaustive
declared-bad-registry/undeclared-registry sweeps this module's runners
drive), :mod:`tests.id_registry.test_session` (claim semantics),
:mod:`tests.assemble.embed_surfaces_shared` (a sibling shared-surfaces
module for option-cascade tests -- not reused directly here because its
``demo_project()`` writes different ``demo/__init__.py`` bytes).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.assemble import (
    enrich_model,
    generate,
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.embed import embed_wheel_sbom
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.extract.conftest import make_hook
from tests.id_registry.surfaces_base import (
    DEPENDENCY,
    UNDECLARED,
    Declare,
    _explicit_pitloom_config,
    _own_key_toml,
    _stub_pipdeptree,
    demo_project,
    demo_wheel,
)
from tests.id_registry.surfaces_cli import CLI_RUNNERS

__all__ = [
    "CLI_SURFACES",
    "DEPENDENCY",
    "EXCLUDED",
    "LIBRARY_RUNNERS",
    "LIBRARY_RUNNERS_WITH_OUTPUT_PATH",
    "SUPPORTED_MODES",
    "SURFACES",
    "UNDECLARED",
    "Declare",
    "demo_project",
    "demo_wheel",
    "lib_embed_wheel_sbom",
    "run_hook",
]

#: Surface name -> the :class:`Declare` modes it can be run with. A
#: surface with no project of its own has no "own_key" mode (there is no
#: ``[tool.pitloom]`` to put the key in); the Hatchling hook and
#: ``loom.run`` each have only one declaration route of their own.
SUPPORTED_MODES: dict[str, tuple[str, ...]] = {
    "cli-project": ("flag", "own_key", "config_key"),
    "cli-project-sdist": ("flag", "config_key"),
    "cli-generate": ("flag", "own_key", "config_key"),
    "cli-wheel": ("flag", "config_key"),
    "cli-wheel-embed": ("flag", "config_key"),
    "cli-env": ("flag", "config_key"),
    "cli-model": ("flag", "config_key"),
    "cli-enrich-standalone": ("flag", "config_key"),
    "cli-enrich-project": ("flag", "own_key", "config_key"),
    "cli-embed-wheel-project": ("flag", "own_key", "config_key"),
    "cli-embed-wheel-standalone": ("flag", "config_key"),
    "cli-id-generate": ("flag", "own_key"),
    "cli-id-import": ("flag", "own_key"),
    "lib-generate": ("flag", "own_key", "config_key"),
    "lib-generate_project_sbom": ("flag", "own_key", "config_key"),
    "lib-generate_wheel_sbom": ("flag", "config_key"),
    "lib-generate_env_sbom": ("flag", "config_key"),
    "lib-generate_model_sbom": ("flag", "config_key"),
    "lib-enrich_model": ("flag", "config_key"),
    "lib-embed_wheel_sbom": ("flag", "own_key", "config_key"),
    "hook": ("own_key",),
    "loom-run": ("flag",),
}

#: Surfaces backed by the CLI entry point -- their runner returns the
#: process exit code rather than raising on failure.
CLI_SURFACES = frozenset(name for name in SUPPORTED_MODES if name.startswith(("cli-",)))


#: Surfaces excluded from the registry cross-surface invariant, with the
#: reason (taken from the code, not restated by hand -- see
#: ``pitloom.core.inert_options.INERT`` and ``sdist.py``'s own-key drop).
def _excluded_reasons() -> dict[str, str]:
    # pylint: disable=import-outside-toplevel
    from pitloom.core.inert_options import EMBED_SBOM, HF, INERT

    return {
        "model-hf": INERT[HF]["id_registry"],
        "embed-wheel --sbom": INERT[EMBED_SBOM]["id_registry"],
        "project-sdist own key": (
            "dropped: an id-registry names a file inside the archive"
        ),
    }


EXCLUDED: dict[str, str] = _excluded_reasons()


# --- Library runners ---------------------------------------------------


def lib_generate(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    output_path: Path | None = None,
) -> None:
    project = demo_project(tmp_path, _own_key_toml(declare))
    generate(
        project,
        output_path=output_path,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


def lib_generate_project_sbom(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    output_path: Path | None = None,
) -> None:
    project = demo_project(tmp_path, _own_key_toml(declare))
    generate_project_sbom(
        project,
        output_path=output_path,
        creation_metadata=None,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


def lib_generate_wheel_sbom(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    output_path: Path | None = None,
) -> None:
    wheel = demo_wheel(tmp_path)
    generate_wheel_sbom(
        wheel,
        output_path=output_path,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


def lib_generate_env_sbom(
    tmp_path: Path,
    mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    output_path: Path | None = None,
) -> None:
    _stub_pipdeptree(mp)
    generate_env_sbom(
        output_path=output_path,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


def lib_generate_model_sbom(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    output_path: Path | None = None,
) -> None:
    generate_model_sbom(
        SAFETENSORS_FIXTURE,
        output_path=output_path,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


def lib_enrich_model(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    output_path: Path | None = None,
) -> None:
    enrich_model(
        SAFETENSORS_FIXTURE,
        output_path=output_path,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


def lib_embed_wheel_sbom(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    wheel: Path | None = None,
) -> None:
    """*wheel* lets a caller build the wheel itself and keep its own
    path/bytes reference (e.g. to assert it's untouched after a raise) --
    defaults to a throwaway wheel this function builds, as before."""
    project = demo_project(tmp_path, _own_key_toml(declare))
    if wheel is None:
        wheel = demo_wheel(tmp_path)
    embed_wheel_sbom(
        wheel,
        project_dir=project,
        id_registry=declare.flag,
        pitloom_config=_explicit_pitloom_config(tmp_path, declare),
    )


LIBRARY_RUNNERS: dict[str, Callable[[Path, pytest.MonkeyPatch, Declare], None]] = {
    "lib-generate": lib_generate,
    "lib-generate_project_sbom": lib_generate_project_sbom,
    "lib-generate_wheel_sbom": lib_generate_wheel_sbom,
    "lib-generate_env_sbom": lib_generate_env_sbom,
    "lib-generate_model_sbom": lib_generate_model_sbom,
    "lib-enrich_model": lib_enrich_model,
    "lib-embed_wheel_sbom": lib_embed_wheel_sbom,
}

#: The subset of :data:`LIBRARY_RUNNERS` that accepts an ``output_path=``
#: override -- every one except ``lib-embed_wheel_sbom``, which embeds
#: into the wheel it's given rather than writing a separate output file
#: (see :mod:`tests.id_registry.test_surfaces_failures`'s use of this,
#: proving registry resolution happens before any output is written).
#: ``Callable[..., None]`` (not the narrower signature above) so the
#: extra keyword-only parameter type-checks at the call site.
LIBRARY_RUNNERS_WITH_OUTPUT_PATH: dict[str, Callable[..., None]] = {
    name: runner
    for name, runner in LIBRARY_RUNNERS.items()
    if name != "lib-embed_wheel_sbom"
}


# --- Hook and loom.run runners ------------------------------------------


def run_hook(
    tmp_path: Path,
    _mp: pytest.MonkeyPatch,
    declare: Declare,
    *,
    build_data: dict[str, Any] | None = None,
) -> None:
    """Run the Hatchling build hook's ``initialize``/``finalize``. Only
    ``own_key`` applies: the hook reads nothing but the project's own
    ``[tool.pitloom]`` (no ``--config``/flag equivalent).

    *build_data* lets a caller pass its own dict and inspect it after a
    raise (``hook.initialize()`` mutates it in place before failing, so
    the exception propagating out of this function doesn't lose that
    state as long as the caller kept its own reference) -- defaults to a
    throwaway dict when the caller doesn't need to look at it."""
    if declare.flag is not None or declare.config_key is not None:
        raise ValueError("hook: only own_key is a supported Declare mode")
    project = demo_project(tmp_path, _own_key_toml(declare))
    hook = make_hook(str(project), {})
    data: dict[str, Any] = build_data if build_data is not None else {}
    hook.initialize("standard", data)
    hook.finalize("standard", data, "")


def run_loom(tmp_path: Path, _mp: pytest.MonkeyPatch, declare: Declare) -> None:
    """Run one ``pitloom.loom.run`` fragment build. Only ``flag`` applies:
    ``loom.run`` resolves ``id_registry=`` alone, never a config key."""
    if declare.own_key is not None or declare.config_key is not None:
        raise ValueError("loom-run: only flag is a supported Declare mode")
    frag_path = tmp_path / "frag.spdx3.json"
    with loom.run(frag_path, id_registry=declare.flag):
        pass


SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch, Declare], object]] = {
    **CLI_RUNNERS,
    **LIBRARY_RUNNERS,
    "hook": run_hook,
    "loom-run": run_loom,
}
