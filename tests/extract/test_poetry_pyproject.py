# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for read_pyproject()'s [tool.poetry] fallback/override behaviour,
fixture-based integration coverage, and G2 license fallback/conflict on the
poetry-only path.

See also: test_poetry_parsing.py for low-level [tool.poetry] parsing helpers.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from pitloom.extract._poetry import extract_poetry_metadata
from pitloom.extract._pyproject import read_pyproject

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
POETRY_FIXTURE = FIXTURE_DIR / "projects" / "sampleproject-poetry"


# ---------------------------------------------------------------------------
# read_pyproject -- poetry fallback when [project] absent
# ---------------------------------------------------------------------------


def test_read_pyproject_falls_back_to_poetry() -> None:
    content = """
[build-system]
requires = ["poetry-core>=2.0.0"]
build-backend = "poetry.core.masonry.api"

[tool.poetry]
name = "poetry-only"
version = "2.0.0"
description = "No [project] section"
authors = ["Dev <dev@example.com>"]
license = "Apache-2.0"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        metadata, _ = read_pyproject(Path(d) / "pyproject.toml")
    assert metadata.name == "poetry-only"
    assert metadata.version == "2.0.0"
    assert metadata.description == "No [project] section"
    assert metadata.license_name == "Apache-2.0"
    assert metadata.authors == [{"name": "Dev", "email": "dev@example.com"}]


def test_read_pyproject_poetry_deps_converted() -> None:
    content = """
[tool.poetry]
name = "pkg"
version = "1.0"

[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.28"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        metadata, _ = read_pyproject(Path(d) / "pyproject.toml")
    assert metadata.requires_python == ">=3.10,<4.0.0"
    assert any("requests" in d for d in metadata.dependencies)


# ---------------------------------------------------------------------------
# read_pyproject -- [project] overrides [tool.poetry]
# ---------------------------------------------------------------------------


def test_read_pyproject_project_overrides_poetry() -> None:
    content = """
[project]
name = "project-name"
version = "3.0.0"
description = "From [project]"

[tool.poetry]
name = "poetry-name"
version = "1.0.0"
description = "From [tool.poetry]"
keywords = ["from-poetry"]
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        metadata, _ = read_pyproject(Path(d) / "pyproject.toml")
    # [project] wins on fields it has
    assert metadata.name == "project-name"
    assert metadata.version == "3.0.0"
    assert metadata.description == "From [project]"
    # [tool.poetry] fills gap not covered by [project]
    assert metadata.keywords == ["from-poetry"]


def test_read_pyproject_explicit_empty_keywords_not_filled_from_poetry() -> None:
    """Regression: `[project] keywords = []` is an explicit declaration of
    zero keywords, not an omission -- `[tool.poetry] keywords` must not
    silently fill it back in via `merge_project_metadata()`'s
    empty-container gap-fill (see `_FIELD_PROVENANCE`'s `"keywords"` entry,
    which records this explicit-declaration provenance)."""
    content = """
[project]
name = "project-name"
version = "1.0.0"
keywords = []

[tool.poetry]
name = "project-name"
version = "1.0.0"
keywords = ["from-poetry"]
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        metadata, _ = read_pyproject(Path(d) / "pyproject.toml")

    assert metadata.keywords == []


def test_read_pyproject_poetry_fills_missing_project_fields() -> None:
    content = """
[project]
name = "my-pkg"
version = "1.0.0"

[tool.poetry]
name = "my-pkg"
version = "1.0.0"
license = "MIT"
authors = ["Alice <a@example.com>"]
keywords = ["extra"]
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        metadata, _ = read_pyproject(Path(d) / "pyproject.toml")
    # Poetry fills license and authors that [project] didn't declare
    assert metadata.license_name == "MIT"
    assert metadata.keywords == ["extra"]


# ---------------------------------------------------------------------------
# Fixture-based integration tests (mistral-inference pyproject.toml)
#
# The fixture at tests/fixtures/projects/sampleproject-poetry/ is a copy of
# https://github.com/mistralai/mistral-inference/blob/main/pyproject.toml
# It uses Poetry as build backend with no [project] section.
# ---------------------------------------------------------------------------


def test_fixture_read_poetry_name_and_version() -> None:
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.name == "mistral_inference"
    assert metadata.version == "1.6.0"


def test_fixture_read_poetry_description_empty() -> None:
    # mistral-inference has description = "" -- maps to None after stripping.
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.description is None


def test_fixture_read_poetry_author() -> None:
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.authors == [{"name": "bam4d", "email": "bam4d@mistral.ai"}]


def test_fixture_read_poetry_license_absent() -> None:
    # mistral-inference has no license field in [tool.poetry].
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.license_name is None


def test_fixture_read_poetry_keywords_empty() -> None:
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert not metadata.keywords


def test_fixture_read_poetry_urls_empty() -> None:
    # mistral-inference declares no homepage/repository/documentation.
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert not metadata.urls


def test_fixture_read_poetry_requires_python() -> None:
    # python = "^3.9.10" -> >=3.9.10,<4.0.0
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.requires_python == ">=3.9.10,<4.0.0"


def test_fixture_read_poetry_main_dependencies_only() -> None:
    # Only [tool.poetry.dependencies] (not group deps) end up in SBOM deps.
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    dep_names = {
        d.split(">=")[0].split("==")[0].split("<")[0] for d in metadata.dependencies
    }
    # main deps present
    assert "xformers" in dep_names
    assert "fire" in dep_names
    assert "mistral_common" in dep_names
    assert "safetensors" in dep_names
    assert "pillow" in dep_names
    # dev-group deps NOT present (pytest, ruff, mypy, etc.)
    assert "pytest" not in dep_names
    assert "ruff" not in dep_names
    assert "mypy" not in dep_names


def test_fixture_read_poetry_no_pitloom_section_defaults() -> None:
    # mistral-inference has no [tool.pitloom] -- all defaults apply.
    _, config = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert config.sbom_basename is None
    assert config.pretty is False
    assert not config.creators


def test_read_poetry_multiple_creators_array_of_tables() -> None:
    """Poetry projects also support ``[[tool.pitloom.creator]]``."""
    content = """
[tool.poetry]
name = "poetry-multi-creator"
version = "0.1.0"
description = "Test"
authors = ["Someone <someone@example.com>"]

[[tool.pitloom.creator]]
name = "Acme Corp"
type = "organization"

[[tool.pitloom.creator]]
name = "Alice"
"""
    with tempfile.TemporaryDirectory() as d:
        pyproject_path = Path(d) / "pyproject.toml"
        pyproject_path.write_text(content, encoding="utf-8")
        _, config = read_pyproject(pyproject_path)

    assert [c.name for c in config.creators] == ["Acme Corp", "Alice"]
    assert config.creators[0].type == "organization"


def test_fixture_read_pyproject_falls_back_to_poetry() -> None:
    # No [project] section -> falls back to [tool.poetry].
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.name == "mistral_inference"
    assert metadata.version == "1.6.0"


# ---------------------------------------------------------------------------
# G2: license fallback detection / conflict (poetry-only path)
#
# Regression coverage for the poetry-only extraction path, which previously
# had zero license detection capability beyond reading the declared
# [tool.poetry] license field verbatim -- no fallback directory detection,
# no independent second-opinion scan. See resolve_license_concluded()'s
# docstring in _license.py for why every extractor must call it.
# ---------------------------------------------------------------------------


def test_extract_poetry_metadata_license_fallback_detection() -> None:
    """No [tool.poetry] license declared: falls back to directory
    detection, same baseline every other extractor has."""
    data = {"tool": {"poetry": {"name": "pkg", "version": "1.0.0"}}}
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        metadata = extract_poetry_metadata(data, tmp_path)
    assert metadata.license_name == "MIT"
    assert metadata.license_concluded is None
    assert "LICENSE" in (metadata.provenance.get("license") or "")


def test_extract_poetry_metadata_license_conflict() -> None:
    """Declared MIT + independently-detected Apache-2.0: G2 populates
    license_concluded with the detected value (and its own provenance),
    distinct from the declared license_name."""
    data = {"tool": {"poetry": {"name": "pkg", "version": "1.0.0", "license": "MIT"}}}
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE").write_text("Apache License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            metadata = extract_poetry_metadata(data, tmp_path)
    assert metadata.license_name == "MIT"
    assert metadata.license_concluded == "Apache-2.0"
    assert "LICENSE" in (metadata.provenance.get("license_concluded") or "")


def test_read_pyproject_fallback_license_conflict_end_to_end() -> None:
    """``read_pyproject()``'s fallback-to-``[tool.poetry]`` branch (no
    ``[project]`` section) resolves G2 correctly end-to-end from a real
    file -- not just via a direct :func:`extract_poetry_metadata` call
    with a pre-parsed dict, which is what the other G2 tests in this
    file exercise. Regression guard for the same "different extractor
    path, same bug class" gap ``resolve_license_concluded()``'s
    docstring warns about, applied to the poetry-fallback path."""
    content = """
[tool.poetry]
name = "poetry-pkg"
version = "1.0.0"
license = "MIT"
"""
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "pyproject.toml").write_text(content)
        (tmp_path / "LICENSE").write_text("Apache License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            metadata, _ = read_pyproject(tmp_path / "pyproject.toml")

    assert metadata.license_name == "MIT"
    assert metadata.license_concluded == "Apache-2.0"


def test_extract_poetry_metadata_license_agrees() -> None:
    """Declared and independently-detected license agree: license_concluded
    is still populated (equal to the declared value) -- G2 records both
    sides regardless of agreement, only the Annotation is conflict-gated."""
    data = {"tool": {"poetry": {"name": "pkg", "version": "1.0.0", "license": "MIT"}}}
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            metadata = extract_poetry_metadata(data, tmp_path)
    assert metadata.license_name == "MIT"
    assert metadata.license_concluded == "MIT"
