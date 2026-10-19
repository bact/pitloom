# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Flit-core-backed dynamic-metadata resolution
(:mod:`pitloom.extract.project.flit`).

See also: tests/extract/project/test_pyproject.py for the ``read_pyproject()``
integration path this feeds into; tests/core/models_wheel/
test_models_wheel_flit.py for the sibling wheel-discovery module.
"""

import logging
from pathlib import Path

import pytest

from pitloom.extract.project.flit import resolve_flit_dynamic_metadata
from pitloom.extract.project.pyproject import read_pyproject

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "projects"
FLIT_FIXTURE = FIXTURES / "sampleproject-flit"


def test_resolve_flit_dynamic_metadata_version_and_description() -> None:
    result = resolve_flit_dynamic_metadata(
        FLIT_FIXTURE / "pyproject.toml", ["version", "description"]
    )
    assert result == {
        "version": "0.1.0",
        "description": (
            "A minimal sample project used for testing Flit metadata and "
            "wheel file discovery."
        ),
    }


def test_resolve_flit_dynamic_metadata_only_requested_fields() -> None:
    """Only fields in *dynamic_fields* are resolved -- ``version`` alone
    doesn't also pull in ``description``."""
    result = resolve_flit_dynamic_metadata(FLIT_FIXTURE / "pyproject.toml", ["version"])
    assert set(result) == {"version"}


def test_resolve_flit_dynamic_metadata_empty_when_nothing_requested() -> None:
    result = resolve_flit_dynamic_metadata(FLIT_FIXTURE / "pyproject.toml", [])
    assert not result


def test_resolve_flit_dynamic_metadata_warns_on_missing_module(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n\n'
        '[project]\nname = "nonexistent_pkg"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = resolve_flit_dynamic_metadata(pyproject, ["version"])

    assert not result
    assert "Flit dynamic metadata resolution failed" in caplog.text


def test_resolve_flit_dynamic_metadata_quiet_suppresses_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """quiet=True suppresses this resolver's own WARNING: for a caller re-reading
    the same file (e.g. resolve_project_with_lockfile()'s peek-then-reread)."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n\n'
        '[project]\nname = "nonexistent_pkg"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = resolve_flit_dynamic_metadata(pyproject, ["version"], quiet=True)

    assert not result
    assert "Flit dynamic metadata resolution failed" not in caplog.text


def test_resolve_flit_dynamic_metadata_never_executes_project_code(
    tmp_path: Path,
) -> None:
    """A ``dynamic = ["version"]`` whose ``__version__`` is a function call (not
    an AST-resolvable literal) is never resolved by importing the target
    module. flit-core falls back to import here; this resolver stops at the
    AST-only scan and leaves ``version`` unresolved, as
    ``pitloom.core._models_wheel_flit`` does."""
    pkg_dir = tmp_path / "evilpkg"
    pkg_dir.mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n\n'
        '[project]\nname = "evilpkg"\n'
        'dynamic = ["version", "description"]\n',
        encoding="utf-8",
    )
    marker = tmp_path / "imported.marker"
    (pkg_dir / "__init__.py").write_text(
        '"""docstring."""\n'
        "from pathlib import Path\n\n"
        "def _compute():\n"
        f'    Path(r"{marker}").write_text("imported")\n'
        '    return "9.9.9"\n\n'
        "__version__ = _compute()\n",
        encoding="utf-8",
    )

    result = resolve_flit_dynamic_metadata(
        tmp_path / "pyproject.toml", ["version", "description"]
    )

    assert not marker.exists(), "resolver imported (executed) the project's module"
    assert "version" not in result


def test_read_pyproject_resolves_flit_dynamic_fields() -> None:
    """End-to-end: ``read_pyproject()`` on a real Flit fixture resolves
    both dynamic fields and tags their provenance distinctly from a
    plain declared ``[project]`` field."""
    metadata, _config = read_pyproject(FLIT_FIXTURE / "pyproject.toml")

    assert metadata.version == "0.1.0"
    assert metadata.description == (
        "A minimal sample project used for testing Flit metadata and "
        "wheel file discovery."
    )
    assert metadata.provenance["version"] == (
        "Source: pyproject.toml | Method: flit_dynamic_metadata"
    )
    assert metadata.provenance["description"] == (
        "Source: pyproject.toml | Method: flit_dynamic_metadata"
    )


def test_resolve_flit_dynamic_metadata_reads_a_pep_263_module(tmp_path: Path) -> None:
    """The confinement check reads the module as bytes and honours a PEP 263
    declaration (``latin-1``), as flit-core does, keeping its version and
    description."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend = "flit_core.buildapi"\n'
        '[project]\nname = "m"\ndynamic = ["version", "description"]\n',
        encoding="utf-8",
    )
    (tmp_path / "m.py").write_bytes(
        b'# -*- coding: latin-1 -*-\n"""Caf\xe9 module."""\n__version__ = "1.2"\n'
    )
    result = resolve_flit_dynamic_metadata(
        tmp_path / "pyproject.toml", ["version", "description"]
    )
    assert result == {"version": "1.2", "description": "Caf\u00e9 module."}
