# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Lowest-level shared pieces for :mod:`tests.id_registry.surfaces_shared`
and :mod:`tests.id_registry.surfaces_cli` -- split into its own module so
neither of those two needs to import the other (an import cycle: each
needs names the other module used to define). Nothing here imports either
of them.

See also: :mod:`tests.id_registry.surfaces_shared` (the combined
``SURFACES`` registry and library/hook/loom runners built from this
module's pieces), :mod:`tests.id_registry.surfaces_cli` (the CLI runners
built from this module's pieces).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.core.config_cascade import load_config_file
from tests.assemble.conftest import _make_dummy_wheel

DEPENDENCY = "fakedep"

#: Same bytes ``_make_dummy_wheel`` bakes into its own ``demo/__init__.py``
#: -- see :mod:`tests.id_registry.surfaces_shared`'s module docstring.
DEMO_INIT_CONTENT = b"__version__ = '1.0.0'\n"

_PYPROJECT = f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = ["{DEPENDENCY}==1.0"]
"""


def demo_project(tmp_path: Path, pitloom_toml: str = "") -> Path:
    """Write the demo project under *tmp_path*; return its directory."""
    root = tmp_path / "proj"
    (root / "demo").mkdir(parents=True, exist_ok=True)
    (root / "demo" / "__init__.py").write_bytes(DEMO_INIT_CONTENT)
    (root / "pyproject.toml").write_text(_PYPROJECT + pitloom_toml, encoding="utf-8")
    return root


def demo_wheel(tmp_path: Path) -> Path:
    """Write a minimal wheel for the demo project under *tmp_path*."""
    return _make_dummy_wheel(
        tmp_path / "dist", "demo", "1.0.0", requires_dist=(f"{DEPENDENCY}==1.0",)
    )


@dataclass(frozen=True)
class Declare:
    """How one run points (or doesn't) at an ID registry file.

    Exactly one of *flag*/*own_key*/*config_key* is set, or none
    (:attr:`undeclared`). Each value may be absolute or relative --
    *relative* is exercised by :mod:`tests.id_registry.test_relative_paths`
    (run from a cwd distinct from every candidate base directory, so a
    surface that resolves against the wrong base is caught); every other
    consumer of this module still passes already-absolute paths, which
    keeps their construction of each mode independent of any base
    directory.
    """

    flag: Path | None = None
    own_key: Path | None = None
    config_key: Path | None = None

    def __post_init__(self) -> None:
        declared = [v for v in (self.flag, self.own_key, self.config_key) if v]
        if len(declared) > 1:
            raise ValueError("Declare: at most one of flag/own_key/config_key")

    @property
    def undeclared(self) -> bool:
        return self.flag is None and self.own_key is None and self.config_key is None


UNDECLARED = Declare()


def _own_key_toml(declare: Declare) -> str:
    if declare.own_key is None:
        return ""
    return f"\n[tool.pitloom]\nid-registry = {json.dumps(declare.own_key.as_posix())}\n"


def _write_explicit_config(tmp_path: Path, declare: Declare) -> Path | None:
    if declare.config_key is None:
        return None
    config_path = tmp_path / "explicit-config.toml"
    config_path.write_text(
        f"[tool.pitloom]\nid-registry = {json.dumps(declare.config_key.as_posix())}\n",
        encoding="utf-8",
    )
    return config_path


def _id_registry_argv(declare: Declare) -> list[str]:
    if declare.flag is None:
        return []
    return ["--id-registry", str(declare.flag)]


def _config_argv(tmp_path: Path, declare: Declare) -> list[str]:
    config_path = _write_explicit_config(tmp_path, declare)
    return [] if config_path is None else ["--config", str(config_path)]


def _run_cli(mp: pytest.MonkeyPatch, argv: list[str]) -> int:
    mp.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def _explicit_pitloom_config(tmp_path: Path, declare: Declare) -> Any:
    config_path = _write_explicit_config(tmp_path, declare)
    return None if config_path is None else load_config_file(config_path)


def _stub_pipdeptree(mp: pytest.MonkeyPatch) -> None:
    tree = [
        {
            "package": {
                "key": DEPENDENCY,
                "package_name": DEPENDENCY,
                "installed_version": "1.0",
            }
        }
    ]
    mp.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout=json.dumps(tree), stderr=""
        ),
    )
