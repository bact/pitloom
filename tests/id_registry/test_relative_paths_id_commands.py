# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Relative path resolution for `pitloom id generate`/`pitloom id
import`'s own ``-o``/``--id-registry`` and PATH arguments -- split out
of :mod:`tests.id_registry.test_relative_paths` (this file's own size)
since these two subcommands share one resolution function
(:func:`pitloom.cli.id._resolve_id_registry_target`) distinct from every
other surface's.

See also: :mod:`tests.id_registry.test_relative_paths` (every other
declaration route's base-directory tests, and the module docstring
there for the full per-route breakdown), :mod:`tests.cli.
test_cli_id_config_errors` (the rest of `pitloom id`'s CLI tests).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pitloom.id_registry import IdRegistry
from tests.id_registry.surfaces_base import Declare, _run_cli, demo_project
from tests.id_registry.surfaces_shared import SURFACES

# --- `pitloom id generate`: same cwd-based rule as every other command --


def test_cli_id_generate_flag_relative_resolves_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    """A relative ``-o``/``--id-registry`` resolves against the current
    directory, exactly like every other command -- even though
    ``--project-dir`` names a *different* directory here."""
    project = demo_project(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    IdRegistry.new("decoy", path=project / "rel.json").save()
    expected = (other / "rel.json").resolve()

    monkeypatch.chdir(other)  # cwd deliberately NOT the project directory
    declare = Declare(flag=Path("rel.json"))
    result = SURFACES["cli-id-generate"](tmp_path, monkeypatch, declare)

    assert result == 0, f"cli-id-generate exited {result}"
    assert expected.is_file(), "id generate should have created it there"
    # `id generate` creates a missing target rather than loading it, so
    # IdRegistry.load never fires for a fresh file -- assert on the
    # created path directly instead of load_spy.
    assert not load_spy


def test_cli_id_generate_relative_path_arg_resolves_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative PATH argument also resolves against the current
    directory, not ``--project-dir`` -- and produces the same registry
    keys (relative to ``--project-dir``) as passing the absolute
    equivalent would."""
    project = demo_project(tmp_path)
    # cwd is the project's own parent, so a relative PATH argument
    # ("proj/demo") contains no ".." components -- deliberately not the
    # project directory itself, so a base-directory mixup is caught.
    monkeypatch.chdir(tmp_path)
    registry_path_relative = tmp_path / "registry-relative.json"
    registry_path_absolute = tmp_path / "registry-absolute.json"

    relative_path_arg = os.path.relpath(project / "demo", tmp_path)
    result = _run_cli(
        monkeypatch,
        [
            "id",
            "generate",
            relative_path_arg,
            "--project-dir",
            str(project),
            "-o",
            str(registry_path_relative),
        ],
    )
    assert result == 0, f"cli-id-generate exited {result}"

    result = _run_cli(
        monkeypatch,
        [
            "id",
            "generate",
            str(project / "demo"),
            "--project-dir",
            str(project),
            "-o",
            str(registry_path_absolute),
        ],
    )
    assert result == 0, f"cli-id-generate exited {result}"

    registry_relative = IdRegistry.load(registry_path_relative)
    registry_absolute = IdRegistry.load(registry_path_absolute)
    assert registry_relative.files.keys() == registry_absolute.files.keys()
    assert "demo/__init__.py" in registry_relative.files


def test_cli_id_generate_then_project_from_same_cwd_reuses_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end-to-end workflow M-e names: `id generate --project-dir proj
    -o reg.json` then `project proj --id-registry reg.json`, both run
    from the same cwd with relative ``-o``/``--id-registry`` values --
    both must resolve to the same file, so the second run reuses the
    first's ids rather than starting a fresh registry.

    Flat (non-``src``-layout) project deliberately: ``physical_path`` ==
    ``distribution_path`` there, so this test isn't also exercising that
    unrelated divergence (see ``CLAUDE.md``'s "physical_path vs
    distribution_path") -- just registry-path resolution and id reuse."""
    demo_project(tmp_path)  # writes tmp_path / "proj"
    monkeypatch.chdir(tmp_path)

    generate_result = _run_cli(
        monkeypatch,
        ["id", "generate", "proj/demo", "--project-dir", "proj", "-o", "reg.json"],
    )
    assert generate_result == 0, f"id generate exited {generate_result}"
    registry_path = tmp_path / "reg.json"
    assert registry_path.is_file()
    expected_id = IdRegistry.load(registry_path).files["demo/__init__.py"].spdx_id

    output_path = tmp_path / "out.spdx3.json"
    project_result = _run_cli(
        monkeypatch,
        ["project", "proj", "-o", str(output_path), "--id-registry", "reg.json"],
    )
    assert project_result == 0, f"project exited {project_result}"

    elements = json.loads(output_path.read_text(encoding="utf-8"))["@graph"]
    reused_id = next(
        (
            node.get("spdxId")
            for node in elements
            if node.get("type") == "software_File"
            and node.get("name") == "demo/__init__.py"
        ),
        None,
    )
    assert reused_id == expected_id
    assert reused_id is not None


def test_cli_id_import_flag_relative_resolves_against_its_own_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``cli_id_import``'s own runner ``chdir``s to a project it writes
    under ``tmp_path/cwd`` before invoking the CLI -- that directory (its
    own resolution's cwd, not any directory this test picks) is the
    expected base. Set an unrelated external cwd first to prove the
    runner's own chdir -- not whatever cwd this test started from --
    determines the base."""
    cwd_project = tmp_path / "cwd" / "proj"
    other = tmp_path / "elsewhere"
    other.mkdir(parents=True)
    monkeypatch.chdir(other)

    declare = Declare(flag=Path("rel.json"))
    result = SURFACES["cli-id-import"](tmp_path, monkeypatch, declare)

    assert result == 0, f"cli-id-import exited {result}"
    expected = (cwd_project / "rel.json").resolve()
    assert expected.is_file()
