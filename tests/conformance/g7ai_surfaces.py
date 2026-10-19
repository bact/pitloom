# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every Pitloom surface that builds an SBOM from one input, for the
conformance parity tests.

Each runner takes the input and a scratch directory and returns the SBOM text:
the library, the ``loom`` subcommands (through ``__main__.main()``, the
entry point ``loom`` runs) and the Hatchling build hook. The GitHub Action
and the skills run these same ``loom`` commands.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from tests._author_routes import CREATED, hook_sbom
from tests.conformance.g7ai_shared import without_licence_database

Runner = Callable[[Path, Path, pytest.MonkeyPatch], str]


def _cli(mp: pytest.MonkeyPatch, scratch: Path, *argv: str) -> str:
    """Run ``loom *argv -o <file>`` offline; return the file's text."""
    out = scratch / "out.spdx3.json"
    mp.setattr(sys, "argv", ["loom", *argv, "-o", str(out)])
    with without_licence_database():
        code = __main__.main()
    assert code == 0, f"loom {' '.join(argv)} exited {code}"
    return out.read_text(encoding="utf-8")


def _lib(call: Callable[[], str]) -> str:
    with without_licence_database():
        return call()


#: Surface name -> runner, per kind of input.
MODEL_SURFACES: dict[str, Runner] = {
    "library": lambda src, _s, _m: _lib(
        lambda: generate_model_sbom(src, creation_metadata=CREATED)
    ),
    "cli-model": lambda src, s, m: _cli(m, s, "model", str(src)),
    "cli-generate": lambda src, s, m: _cli(m, s, "generate", str(src)),
}
PROJECT_SURFACES: dict[str, Runner] = {
    "library": lambda src, _s, _m: _lib(
        lambda: generate_project_sbom(src, creation_metadata=CREATED, offline=True)
    ),
    "cli-generate": lambda src, s, m: _cli(m, s, "generate", str(src), "--offline"),
    "cli-project": lambda src, s, m: _cli(m, s, "project", str(src), "--offline"),
}


#: The hook runs only for a Hatchling project.
def hook_surface(src: Path, _scratch: Path, _mp: pytest.MonkeyPatch) -> str:
    """The SBOM the build hook stages for the project *src*."""
    return _lib(lambda: hook_sbom(src))


WHEEL_SURFACES: dict[str, Runner] = {
    "library": lambda src, _s, _m: _lib(
        lambda: generate_wheel_sbom(src, creation_metadata=CREATED)
    ),
    "cli-wheel": lambda src, s, m: _cli(m, s, "wheel", str(src)),
    "cli-generate": lambda src, s, m: _cli(m, s, "generate", str(src)),
}
