# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Flit-core-backed dynamic-metadata resolution
(:mod:`pitloom.extract._flit`).

See also: tests/extract/test_pyproject.py for the ``read_pyproject()``
integration path this feeds into; tests/core/models_wheel/
test_models_wheel_flit.py for the sibling wheel-discovery module.
"""

import logging
from pathlib import Path

import pytest

from pitloom.extract._flit import resolve_flit_dynamic_metadata
from pitloom.extract._pyproject import read_pyproject

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
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
