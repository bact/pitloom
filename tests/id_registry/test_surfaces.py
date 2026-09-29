# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Cross-surface ID registry declaration/failure/completeness tests.

The registry is an *input*: each surface here is checked for what it does
with a declared registry (resolved, or a hard failure), never for
producing byte-identical SBOMs against another surface -- see
:mod:`tests.id_registry.test_surfaces_same_ids` for the "same ids, per
element" invariant that replaces a whole-document comparison.

See also: :mod:`tests.id_registry.surfaces_shared` (the ``SURFACES``
registry and ``Declare`` this module drives),
:mod:`tests.id_registry.test_surfaces_failures` (the same
declared-bad-registry/undeclared-registry invariants, swept across
every surface and every declaration mode -- this module keeps only one
representative case per invariant, plus the completeness guards),
:mod:`tests.id_registry.test_session` (claim semantics, out of scope
here).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import argparse
import inspect
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

import pitloom
from pitloom import __main__, loom
from pitloom.assemble import generate_project_sbom
from pitloom.cli.parser import _build_parser
from pitloom.core.inert_options import INERT
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from tests.extract.conftest import make_hook
from tests.id_registry.surfaces_shared import (
    CLI_SURFACES,
    EXCLUDED,
    SUPPORTED_MODES,
    SURFACES,
    Declare,
    demo_project,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ``load_spy`` moved to tests/id_registry/conftest.py so every module in
# this package can use it (see tests.id_registry.test_relative_paths).


# --- Resolution: declared registries are loaded, undeclared ones are not ---


def _surface_mode_params() -> Iterator[tuple[str, str]]:
    for name, modes in SUPPORTED_MODES.items():
        for mode in modes:
            yield (name, mode)


@pytest.mark.parametrize(
    ("surface", "mode"),
    list(_surface_mode_params()),
    ids=[f"{s}-{m}" for s, m in _surface_mode_params()],
)
def test_declared_registry_is_loaded_exactly_once(
    surface: str,
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    load_spy: list[Path],
) -> None:
    registry_path = (tmp_path / "registry.json").resolve()
    IdRegistry.new("declared", path=registry_path).save()
    declare = Declare(**{mode: registry_path})

    result = SURFACES[surface](tmp_path, monkeypatch, declare)

    if surface in CLI_SURFACES:
        assert result == 0, f"{surface}/{mode} exited {result}"
    loaded = [p.resolve() for p in load_spy]
    assert loaded == [registry_path], f"{surface}/{mode}: loaded {loaded}"


def test_flag_wins_over_project_own_key(tmp_path: Path, load_spy: list[Path]) -> None:
    """A ``--id-registry``/``id_registry=`` given alongside the project's
    own ``[tool.pitloom] id-registry`` key uses only the flag -- the
    project's own key is never even loaded."""
    flag_registry = (tmp_path / "flag.json").resolve()
    key_registry = (tmp_path / "own-key.json").resolve()
    IdRegistry.new("flag", path=flag_registry).save()
    IdRegistry.new("own-key", path=key_registry).save()

    toml = f"\n[tool.pitloom]\nid-registry = {json.dumps(key_registry.as_posix())}\n"
    project = demo_project(tmp_path, toml)

    generate_project_sbom(project, creation_metadata=None, id_registry=flag_registry)

    loaded = [p.resolve() for p in load_spy]
    assert loaded == [flag_registry], f"expected only the flag's path, got {loaded}"


# --- Failure: a declared-but-bad registry is a hard failure everywhere ---


@pytest.mark.parametrize("content", [None, "{"], ids=["missing", "malformed-json"])
def test_library_and_loom_declared_bad_registry_raises(
    content: str | None, tmp_path: Path
) -> None:
    registry_path = tmp_path / "bad.json"
    if content is not None:
        registry_path.write_text(content, encoding="utf-8")
    project = demo_project(tmp_path)
    output_path = tmp_path / "out.spdx3.json"

    with pytest.raises(ValueError, match=r"^ID registry file "):
        generate_project_sbom(
            project,
            creation_metadata=None,
            output_path=output_path,
            id_registry=registry_path,
        )
    assert not output_path.exists()

    frag_path = tmp_path / "frag.spdx3.json"
    with pytest.raises(ValueError, match=r"^ID registry file "):
        with loom.run(frag_path, id_registry=registry_path):
            pass
    assert not frag_path.exists()


@pytest.mark.parametrize("content", [None, "{"], ids=["missing", "malformed-json"])
def test_hook_declared_bad_registry_raises_one_error_no_sbom_files(
    content: str | None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry_path = tmp_path / "bad.json"
    if content is not None:
        registry_path.write_text(content, encoding="utf-8")
    toml = f"\n[tool.pitloom]\nid-registry = {json.dumps(registry_path.as_posix())}\n"
    project = demo_project(tmp_path, toml)

    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match=r"^ID registry file "):
            hook.initialize("standard", build_data)

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1, caplog.records
    assert "sbom_files" not in build_data


def test_id_generate_creates_missing_declared_registry_and_logs_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`pitloom id generate` treats a missing declared file as "create it",
    not a failure -- and, since it did not come from the project's own
    config, logs the config hint."""
    project = demo_project(tmp_path)
    registry_path = tmp_path / "fresh.json"
    assert not registry_path.exists()

    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "id",
            "generate",
            str(project / "demo"),
            "--project-dir",
            str(project),
            "-o",
            str(registry_path),
        ],
    )
    with caplog.at_level(logging.INFO):
        assert __main__.main() == 0

    assert registry_path.is_file()
    hints = [
        r
        for r in caplog.records
        if "to use this registry, add to [tool.pitloom]" in r.message
    ]
    assert len(hints) == 1, caplog.records


# --- Completeness guard: every id_registry-accepting surface is covered ---


def _walk_id_registry_subcommands() -> set[str]:
    """Every ``<subcommand>``/``<subcommand> <sub-subcommand>`` path in the
    real argparse tree that offers ``--id-registry``."""
    # pylint: disable=protected-access
    parser = _build_parser()
    actions = parser._actions
    (top_subparsers,) = [
        a for a in actions if isinstance(a, argparse._SubParsersAction)
    ]
    found: set[str] = set()
    for name, sub in top_subparsers.choices.items():
        sub_actions = sub._actions
        if any("--id-registry" in a.option_strings for a in sub_actions):
            found.add(name)
        nested = [a for a in sub_actions if isinstance(a, argparse._SubParsersAction)]
        for nested_action in nested:
            for sub_name, sub_sub in nested_action.choices.items():
                if any("--id-registry" in a.option_strings for a in sub_sub._actions):
                    found.add(f"{name} {sub_name}")
    return found


#: Argparse subcommand path -> the SURFACES entries that exercise it.
_SUBCOMMAND_SURFACES: dict[str, tuple[str, ...]] = {
    "generate": ("cli-generate",),
    "project": ("cli-project", "cli-project-sdist"),
    "wheel": ("cli-wheel", "cli-wheel-embed"),
    "embed-wheel": ("cli-embed-wheel-project", "cli-embed-wheel-standalone"),
    "model": ("cli-model",),
    "enrich": ("cli-enrich-standalone", "cli-enrich-project"),
    "env": ("cli-env",),
    "id generate": ("cli-id-generate",),
    "id import": ("cli-id-import",),
}


def test_every_id_registry_cli_subcommand_is_covered() -> None:
    found = _walk_id_registry_subcommands()
    assert found == set(_SUBCOMMAND_SURFACES), found
    for path, surfaces in _SUBCOMMAND_SURFACES.items():
        for surface in surfaces:
            assert surface in SURFACES, f"{path}: missing runner {surface}"


def _library_id_registry_callables() -> dict[str, Any]:
    names = set(pitloom.__all__) | {"embed_wheel_sbom", "Run"}
    callables: dict[str, Any] = {}
    for name in names:
        func = getattr(pitloom, name, None) or {
            "embed_wheel_sbom": embed_wheel_sbom,
            "Run": loom.Run,
        }.get(name)
        if func is None or not callable(func):
            continue
        params = inspect.signature(func).parameters
        if "id_registry" in params:
            callables[name] = func
    return callables


def test_every_public_id_registry_callable_is_covered() -> None:
    callables = _library_id_registry_callables()
    assert "generate" in callables
    assert "generate_project_sbom" in callables
    assert "generate_wheel_sbom" in callables
    assert "generate_env_sbom" in callables
    assert "generate_model_sbom" in callables
    assert "enrich_model" in callables
    assert "embed_wheel_sbom" in callables
    assert "Run" in callables

    covered = {
        "generate": "lib-generate",
        "generate_project_sbom": "lib-generate_project_sbom",
        "generate_wheel_sbom": "lib-generate_wheel_sbom",
        "generate_env_sbom": "lib-generate_env_sbom",
        "generate_model_sbom": "lib-generate_model_sbom",
        "enrich_model": "lib-enrich_model",
        "embed_wheel_sbom": "lib-embed_wheel_sbom",
        "Run": "loom-run",
    }
    for name in callables:
        assert name in covered, f"{name}: no SURFACES entry mapped"
        assert covered[name] in SURFACES

    assert "hook" in SURFACES
    assert "loom-run" in SURFACES


def test_inert_id_registry_rows_are_all_excluded_with_reasons() -> None:
    """Every ``INERT`` row that declares ``id_registry`` has no effect is
    accounted for in :data:`tests.id_registry.surfaces_shared.EXCLUDED`
    (never silently missing from both ``SURFACES`` and ``EXCLUDED``)."""
    inert_kinds = {kind for kind, row in INERT.items() if "id_registry" in row}
    assert inert_kinds == {"hf", "embed_sbom"}
    assert EXCLUDED["model-hf"] == INERT["hf"]["id_registry"]
    assert EXCLUDED["embed-wheel --sbom"] == INERT["embed_sbom"]["id_registry"]
    assert "project-sdist own key" in EXCLUDED


def test_action_yml_declares_id_registry_inputs() -> None:
    action_yml = _REPO_ROOT / "action.yml"
    data = yaml.safe_load(action_yml.read_text(encoding="utf-8"))
    inputs = data.get("inputs")
    assert isinstance(inputs, dict), inputs
    assert "id-registry" in inputs
    assert "update-id-registry" in inputs
