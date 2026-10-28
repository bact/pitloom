# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project that declares a licence, built with no licenseid database, says
so once at ``INFO:`` on every surface (library, CLI, Hatchling hook) and
writes no ``WARNING:``.

See also: :mod:`tests.assemble.test_license_database_missing` (the policy).
"""

from __future__ import annotations

import functools
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from licenseid import AggregatedLicenseMatcher

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.extract import _license
from tests.extract.conftest import make_hook

_PYPROJECT = (
    '[project]\nname = "demo"\nversion = "1.0.0"\nlicense = "Apache-2.0"\n'
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
)
_INFO = "licenseid database not found -- license text detection skipped"


def _library(project: Path) -> None:
    generate_project_sbom(project, output_path=project / "out.spdx3.json")


def _cli(project: Path) -> None:
    sys.argv = ["loom", "project", str(project), "-o", str(project / "out.spdx3.json")]
    assert __main__.main() == 0


def _hook(project: Path) -> None:
    build_data: dict[str, Any] = {}
    hook = make_hook(str(project), {})
    hook.initialize("standard", build_data)
    hook.finalize("standard", build_data, "")


@pytest.mark.parametrize("surface", [_library, _cli, _hook], ids=lambda f: f.__name__)
def test_a_declared_licence_and_no_database_is_info_on_every_surface(
    surface: Callable[[Path], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (project / "LICENSE").write_text("Apache License\n" * 20, encoding="utf-8")
    (project / "demo").mkdir()
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", sys.argv)
    monkeypatch.setattr(
        _license,
        "AggregatedLicenseMatcher",
        functools.partial(AggregatedLicenseMatcher, db_path=str(tmp_path / "none.db")),
    )

    with caplog.at_level(logging.INFO):
        surface(project)

    assert [r.levelno for r in caplog.records if _INFO in r.getMessage()] == [
        logging.INFO
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
