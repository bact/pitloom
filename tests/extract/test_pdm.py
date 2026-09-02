# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PDM-backend-backed dynamic-version resolution
(:mod:`pitloom.extract._pdm`).

See also: tests/extract/test_pyproject.py for the ``read_pyproject()``
integration path this feeds into; tests/core/models_wheel/
test_models_wheel_pdm.py for the sibling wheel-discovery module.
"""

import logging
import subprocess
from pathlib import Path

import pytest

from pitloom.extract._pdm import resolve_pdm_dynamic_version
from pitloom.extract._pyproject import read_pyproject

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
PDM_FIXTURE = FIXTURES / "sampleproject-pdm"


def test_resolve_pdm_dynamic_version_from_file() -> None:
    data = {
        "tool": {
            "pdm": {
                "version": {
                    "source": "file",
                    "path": "src/sampleproject_pdm/__init__.py",
                }
            }
        }
    }
    version, source = resolve_pdm_dynamic_version(PDM_FIXTURE, data, ["version"])

    assert version == "0.1.0"
    assert source == "Source: pyproject.toml | Method: pdm_dynamic_version(file)"


def test_resolve_pdm_dynamic_version_not_requested() -> None:
    """``"version"`` absent from *dynamic_fields* short-circuits before
    any ``[tool.pdm.version]`` lookup."""
    version, source = resolve_pdm_dynamic_version(PDM_FIXTURE, {}, [])
    assert version is None
    assert source is None


def test_resolve_pdm_dynamic_version_no_config() -> None:
    version, source = resolve_pdm_dynamic_version(PDM_FIXTURE, {}, ["version"])
    assert version is None
    assert source is None


def test_resolve_pdm_dynamic_version_scm_with_write_to(tmp_path: Path) -> None:
    """Regression: ``source = "scm"`` combined with ``write_to`` (a
    common, documented PDM idiom for auto-embedding a ``_version.py``)
    must still resolve the version correctly -- previously failed with
    ``AttributeError: 'Builder' object has no attribute 'target'``
    because the plain ``Builder`` base class never sets ``target``,
    which ``resolve_version_from_scm()``'s write path reads. Also
    verifies no file is written to disk: this is a metadata *read*, so
    ``write_to`` must never actually create the file it names."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["pdm-backend"]\n'
        'build-backend = "pdm.backend"\n\n'
        '[project]\nname = "pkg"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )
    (project_dir / "pkg").mkdir()
    (project_dir / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "test"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "-m", "init"],
        ["git", "tag", "v1.0.0"],
    ):
        subprocess.run(cmd, cwd=project_dir, check=True)

    data = {
        "tool": {
            "pdm": {
                "version": {"source": "scm", "write_to": "pkg/_version.py"},
            }
        }
    }
    version, source = resolve_pdm_dynamic_version(project_dir, data, ["version"])

    assert version == "1.0.0"
    assert source == "Source: pyproject.toml | Method: pdm_dynamic_version(scm)"
    assert not (project_dir / ".pdm-build").exists()
    assert not (project_dir / "pkg" / "_version.py").exists()


def test_resolve_pdm_dynamic_version_call_source_unresolved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``source = "call"`` would execute project code merely to read a
    version -- deliberately left unresolved, with a ``WARNING:``, not
    silently skipped."""
    data = {
        "tool": {"pdm": {"version": {"source": "call", "getter": "pkg:get_version"}}}
    }

    with caplog.at_level(logging.WARNING):
        version, source = resolve_pdm_dynamic_version(PDM_FIXTURE, data, ["version"])

    assert version is None
    assert source is None
    assert "not resolvable without executing project code" in caplog.text


def test_read_pyproject_resolves_pdm_dynamic_version() -> None:
    """End-to-end: ``read_pyproject()`` on a real PDM fixture resolves
    the dynamic version via ``[tool.pdm.version]``."""
    metadata, _config = read_pyproject(PDM_FIXTURE / "pyproject.toml")

    assert metadata.version == "0.1.0"
    assert metadata.provenance["version"] == (
        "Source: pyproject.toml | Method: pdm_dynamic_version(file)"
    )
