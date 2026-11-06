# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project that declares a licence, built with no LicenseID database, says
so once at ``INFO:`` on every surface (library, CLI, Hatchling hook) and
writes no ``WARNING:``.

See also: :mod:`tests.assemble.test_license_database_missing` (the policy).
"""

from __future__ import annotations

import functools
import logging
import sys
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from licenseid import LicenseDetector, LicenseIdWarning

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.extract import _license_text_match
from pitloom.logging_config import configure_logging
from tests.extract.conftest import make_hook

_PYPROJECT = (
    '[project]\nname = "demo"\nversion = "1.0.0"\nlicense = "Apache-2.0"\n'
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
)
_INFO = "licenseid database not found: "


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
        _license_text_match,
        "LicenseDetector",
        functools.partial(LicenseDetector, db_path=str(tmp_path / "none.db")),
    )

    with caplog.at_level(logging.INFO):
        surface(project)

    assert [r.levelno for r in caplog.records if _INFO in r.getMessage()] == [
        logging.INFO
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def _write_project(project: Path, licence: str) -> None:
    """A project whose ``project.license`` is the TOML value *licence*."""
    project.mkdir()
    (project / "pyproject.toml").write_text(
        _PYPROJECT.replace('"Apache-2.0"', licence), encoding="utf-8"
    )
    (project / "LICENSE").write_text("Apache License\n" * 20, encoding="utf-8")
    (project / "demo").mkdir()
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")


@pytest.mark.parametrize("surface", [_library, _cli, _hook], ids=lambda f: f.__name__)
def test_a_respelt_licence_is_read_with_no_database_on_every_surface(
    surface: Callable[[Path], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``Apache2`` is read as ``Apache-2.0`` from the packaged SPDX License
    List, as in an isolated build, which has no database (a table: Hatchling
    refuses the string)."""
    project = tmp_path / "proj"
    _write_project(project, '{ text = "Apache2" }')
    monkeypatch.setattr(sys, "argv", sys.argv)
    monkeypatch.setattr(
        _license_text_match,
        "LicenseDetector",
        functools.partial(LicenseDetector, db_path=str(tmp_path / "none.db")),
    )

    with caplog.at_level(logging.INFO):
        surface(project)

    read = [r for r in caplog.records if "LICENSE='Apache2': read as" in r.message]
    assert [r.message.rpartition(": ")[2] for r in read] == [
        "read as Apache-2.0 (separator, version_spelling)"
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# pylint: disable-next=too-few-public-methods
class _OutdatedDetector:
    """A detector on a database an older LicenseID built: it warns as
    LicenseID 0.7 does, through :mod:`warnings`, and detects nothing."""

    def __init__(self) -> None:
        warnings.warn(
            LicenseIdWarning(
                "database", "build v2 outdated", "current v3", "run 'licenseid update'"
            ),
            stacklevel=2,
        )

    def detect(self, text: str) -> list[object]:
        del text
        return []


@pytest.mark.parametrize("surface", [_library, _cli, _hook], ids=lambda f: f.__name__)
def test_a_licenseid_warning_is_one_tagged_line_on_every_surface(
    surface: Callable[[Path], None],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Relayed, not printed in Python's format, nor raised under the suite's
    ``filterwarnings = ["error"]``; said once though asked again."""
    project = tmp_path / "proj"
    _write_project(project, '"Apache-2.0"')
    monkeypatch.setattr(sys, "argv", sys.argv)
    monkeypatch.setattr(_license_text_match, "LicenseDetector", _OutdatedDetector)

    configure_logging()
    surface(project)
    _license_text_match.detect_license_from_text("Apache License\n" * 20)

    err = capsys.readouterr().err.splitlines()
    assert [line for line in err if "licenseid" in line and "outdated" in line] == [
        "WARNING: licenseid: database: build v2 outdated: current v3;"
        " run 'licenseid update'"
    ]
    assert not [line for line in err if "LicenseIdWarning" in line]
