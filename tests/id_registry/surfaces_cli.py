# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""CLI-backed runners for :mod:`tests.id_registry.surfaces_shared` -- split
out to keep that module under the project's file-size guidance. Each
runner returns the CLI's process exit code.

Imports from :mod:`tests.id_registry.surfaces_base` rather than
:mod:`tests.id_registry.surfaces_shared` -- that module folds this one's
``CLI_RUNNERS`` into its own ``SURFACES``, so this module importing back
from it would be a cycle.

See also: :mod:`tests.id_registry.surfaces_base` (``Declare``, the demo
project/wheel fixtures, and the CLI-argv/config-file helpers this module
builds on), :mod:`tests.id_registry.surfaces_shared` (the combined
``SURFACES`` registry these runners are folded into).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.id_registry.surfaces_base import (
    DEMO_INIT_CONTENT,
    DEPENDENCY,
    Declare,
    _config_argv,
    _id_registry_argv,
    _own_key_toml,
    _run_cli,
    _stub_pipdeptree,
    demo_project,
    demo_wheel,
)

# --- CLI runners -----------------------------------------------------


def cli_project(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    project = demo_project(tmp_path, _own_key_toml(declare))
    argv = ["project", str(project), "-o", str(tmp_path / "out.spdx3.json")]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_project_sdist(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    # pylint: disable=import-outside-toplevel
    from tests.assemble.conftest import _make_sdist

    sdist = _make_sdist(
        tmp_path,
        f'requires-python = ">=3.10"\ndependencies = ["{DEPENDENCY}==1.0"]\n',
        members={"demo/__init__.py": DEMO_INIT_CONTENT},
    )
    argv = ["project", str(sdist), "-o", str(tmp_path / "out.spdx3.json")]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_generate(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    project = demo_project(tmp_path, _own_key_toml(declare))
    argv = [str(project), "-o", str(tmp_path / "out.spdx3.json")]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, ["generate", *argv])


def cli_wheel(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    wheel = demo_wheel(tmp_path)
    argv = ["wheel", str(wheel), "-o", str(tmp_path / "out.spdx3.json")]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_wheel_embed(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    wheel = demo_wheel(tmp_path)
    argv = ["wheel", str(wheel), "--embed"]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_env(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    _stub_pipdeptree(mp)
    argv = ["env", "-o", str(tmp_path / "out.spdx3.json")]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_model(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    argv = [
        "model",
        str(SAFETENSORS_FIXTURE),
        "-o",
        str(tmp_path / "out.spdx3.json"),
    ]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_enrich_standalone(
    tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare
) -> int:
    argv = [
        "enrich",
        str(SAFETENSORS_FIXTURE),
        "-o",
        str(tmp_path / "out.enrich.spdx3.json"),
    ]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_enrich_project(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    project = demo_project(tmp_path, _own_key_toml(declare))
    argv = [
        "enrich",
        str(SAFETENSORS_FIXTURE),
        "--project-dir",
        str(project),
        "-o",
        str(tmp_path / "out.enrich.spdx3.json"),
    ]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_embed_wheel_project(
    tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare
) -> int:
    project = demo_project(tmp_path, _own_key_toml(declare))
    wheel = demo_wheel(tmp_path)
    argv = ["embed-wheel", str(wheel), "--project-dir", str(project)]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_embed_wheel_standalone(
    tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare
) -> int:
    wheel = demo_wheel(tmp_path)
    argv = ["embed-wheel", str(wheel)]
    argv += _id_registry_argv(declare)
    argv += _config_argv(tmp_path, declare)
    return _run_cli(mp, argv)


def cli_id_generate(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    project = demo_project(tmp_path, _own_key_toml(declare))
    argv = ["id", "generate", str(project / "demo"), "--project-dir", str(project)]
    if declare.flag is not None:
        argv += ["-o", str(declare.flag)]
    return _run_cli(mp, argv)


def cli_id_import(tmp_path: Path, mp: pytest.MonkeyPatch, declare: Declare) -> int:
    # The SBOM to import comes from a *separate*, undeclared project --
    # only "id import"'s own resolution (of `declare`) should touch a
    # registry, not this source SBOM's own generation.
    source_project = demo_project(tmp_path / "source")
    sbom_path = tmp_path / "import-source.spdx3.json"
    sbom_json = generate_project_sbom(source_project, creation_metadata=None)
    sbom_path.write_text(sbom_json, encoding="utf-8")

    cwd_project = demo_project(tmp_path / "cwd", _own_key_toml(declare))
    mp.chdir(cwd_project)
    argv = ["id", "import", str(sbom_path)]
    if declare.flag is not None:
        argv += ["-o", str(declare.flag)]
    return _run_cli(mp, argv)


CLI_RUNNERS: dict[str, Callable[[Path, pytest.MonkeyPatch, Declare], int]] = {
    "cli-project": cli_project,
    "cli-project-sdist": cli_project_sdist,
    "cli-generate": cli_generate,
    "cli-wheel": cli_wheel,
    "cli-wheel-embed": cli_wheel_embed,
    "cli-env": cli_env,
    "cli-model": cli_model,
    "cli-enrich-standalone": cli_enrich_standalone,
    "cli-enrich-project": cli_enrich_project,
    "cli-embed-wheel-project": cli_embed_wheel_project,
    "cli-embed-wheel-standalone": cli_embed_wheel_standalone,
    "cli-id-generate": cli_id_generate,
    "cli-id-import": cli_id_import,
}
