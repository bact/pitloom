# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from [tool.poetry] in pyproject.toml."""

import tempfile
from pathlib import Path

import pytest

from pitloom.extract.poetry import (
    _parse_poetry_authors,
    _parse_poetry_deps,
    _poetry_constraint_to_pep440,
    _poetry_dep_to_pep508,
    extract_poetry_metadata,
    read_poetry,
)
from pitloom.extract.pyproject import read_pyproject

FIXTURE_DIR = Path(__file__).parent / "fixtures"
POETRY_FIXTURE = FIXTURE_DIR / "sampleproject-poetry"


# ---------------------------------------------------------------------------
# _parse_poetry_authors
# ---------------------------------------------------------------------------


def test_parse_authors_name_and_email() -> None:
    authors = _parse_poetry_authors(["Alice Smith <alice@example.com>"])
    assert authors == [{"name": "Alice Smith", "email": "alice@example.com"}]


def test_parse_authors_name_only() -> None:
    authors = _parse_poetry_authors(["Bob Jones"])
    assert authors == [{"name": "Bob Jones"}]


def test_parse_authors_email_only() -> None:
    authors = _parse_poetry_authors(["<carol@example.com>"])
    assert authors == [{"email": "carol@example.com"}]


def test_parse_authors_multiple() -> None:
    authors = _parse_poetry_authors(
        [
            "Alice <a@example.com>",
            "Bob <b@example.com>",
        ]
    )
    assert len(authors) == 2
    assert authors[0]["name"] == "Alice"
    assert authors[1]["name"] == "Bob"


def test_parse_authors_non_string_skipped() -> None:
    authors = _parse_poetry_authors([42, None, "Valid <v@example.com>"])
    assert len(authors) == 1
    assert authors[0]["name"] == "Valid"


def test_parse_authors_empty_list() -> None:
    assert not _parse_poetry_authors([])


# ---------------------------------------------------------------------------
# _poetry_constraint_to_pep440
# ---------------------------------------------------------------------------


def test_caret_major_positive() -> None:
    assert _poetry_constraint_to_pep440("^1.2.3") == ">=1.2.3,<2.0.0"


def test_caret_major_zero() -> None:
    assert _poetry_constraint_to_pep440("^0.3.0") == ">=0.3.0,<0.4.0"


def test_caret_major_only() -> None:
    result = _poetry_constraint_to_pep440("^3")
    assert result == ">=3,<4.0.0"


def test_tilde_with_minor() -> None:
    assert _poetry_constraint_to_pep440("~1.2.3") == ">=1.2.3,<1.3.0"


def test_tilde_major_only() -> None:
    assert _poetry_constraint_to_pep440("~2") == ">=2"


def test_wildcard_returns_none() -> None:
    assert _poetry_constraint_to_pep440("*") is None


def test_empty_returns_none() -> None:
    assert _poetry_constraint_to_pep440("") is None


def test_plain_pep440_passthrough() -> None:
    assert _poetry_constraint_to_pep440(">=2.28.0") == ">=2.28.0"
    assert _poetry_constraint_to_pep440("==1.0.0") == "==1.0.0"


def test_bare_version_becomes_exact() -> None:
    assert _poetry_constraint_to_pep440("7.4.4") == "==7.4.4"
    assert _poetry_constraint_to_pep440("4.24.0.20240129") == "==4.24.0.20240129"


def test_dict_constraint_uses_version_key() -> None:
    assert (
        _poetry_constraint_to_pep440({"version": "^2.0", "optional": True})
        == ">=2.0,<3.0.0"
    )


def test_dict_constraint_missing_version() -> None:
    assert _poetry_constraint_to_pep440({"optional": True}) is None


# ---------------------------------------------------------------------------
# _poetry_dep_to_pep508
# ---------------------------------------------------------------------------


def test_dep_caret() -> None:
    assert _poetry_dep_to_pep508("requests", "^2.28.0") == "requests>=2.28.0,<3.0.0"


def test_dep_wildcard() -> None:
    assert _poetry_dep_to_pep508("numpy", "*") == "numpy"


def test_dep_plain() -> None:
    assert _poetry_dep_to_pep508("click", ">=8.0") == "click>=8.0"


def test_dep_dict_with_version() -> None:
    result = _poetry_dep_to_pep508("boto3", {"version": "^1.20", "optional": True})
    assert result == "boto3>=1.20,<2.0.0"


def test_dep_dict_path_returns_none() -> None:
    assert _poetry_dep_to_pep508("local-pkg", {"path": "../local-pkg"}) is None


def test_dep_dict_git_returns_none() -> None:
    assert _poetry_dep_to_pep508("dev-pkg", {"git": "https://github.com/x/y"}) is None


# ---------------------------------------------------------------------------
# _parse_poetry_deps
# ---------------------------------------------------------------------------


def test_parse_deps_python_extracted() -> None:
    deps = {"python": "^3.10", "requests": "^2.28"}
    packages, requires_python = _parse_poetry_deps(deps)
    assert requires_python == ">=3.10,<4.0.0"
    assert any("requests" in d for d in packages)
    assert not any("python" in d for d in packages)


def test_parse_deps_no_python_key() -> None:
    deps = {"click": ">=8.0"}
    packages, requires_python = _parse_poetry_deps(deps)
    assert requires_python is None
    assert any("click" in d for d in packages)


def test_parse_deps_empty() -> None:
    packages, requires_python = _parse_poetry_deps({})
    assert not packages
    assert requires_python is None


def test_parse_deps_not_a_dict() -> None:
    packages, requires_python = _parse_poetry_deps("invalid")
    assert not packages
    assert requires_python is None


# ---------------------------------------------------------------------------
# extract_poetry_metadata -- from dict
# ---------------------------------------------------------------------------


def test_extract_basic_fields() -> None:
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.2.3",
                "description": "A test package",
                "license": "MIT",
                "keywords": ["foo", "bar"],
                "authors": ["Alice <alice@example.com>"],
                "homepage": "https://example.com",
                "repository": "https://github.com/example/my-pkg",
                "documentation": "https://docs.example.com",
            }
        }
    }
    metadata = extract_poetry_metadata(data)
    assert metadata.name == "my-pkg"
    assert metadata.version == "1.2.3"
    assert metadata.description == "A test package"
    assert metadata.license_name == "MIT"
    assert metadata.keywords == ["foo", "bar"]
    assert metadata.authors == [{"name": "Alice", "email": "alice@example.com"}]
    assert metadata.urls["Homepage"] == "https://example.com"
    assert metadata.urls["Repository"] == "https://github.com/example/my-pkg"
    assert metadata.urls["Documentation"] == "https://docs.example.com"


def test_extract_dependencies() -> None:
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "dependencies": {
                    "python": "^3.10",
                    "requests": "^2.28",
                    "numpy": ">=1.23",
                },
            }
        }
    }
    metadata = extract_poetry_metadata(data)
    assert metadata.requires_python == ">=3.10,<4.0.0"
    assert any("requests" in d for d in metadata.dependencies)
    assert any("numpy" in d for d in metadata.dependencies)
    assert not any("python" in d for d in metadata.dependencies)


def test_extract_readme_string() -> None:
    data = {"tool": {"poetry": {"name": "pkg", "readme": "README.md"}}}
    metadata = extract_poetry_metadata(data)
    assert metadata.readme == "README.md"


def test_extract_readme_list() -> None:
    data = {
        "tool": {"poetry": {"name": "pkg", "readme": ["README.md", "CHANGELOG.md"]}}
    }
    metadata = extract_poetry_metadata(data)
    assert metadata.readme == "README.md"


def test_extract_missing_section_raises() -> None:
    with pytest.raises(ValueError, match=r"\[tool\.poetry\]"):
        extract_poetry_metadata({})


def test_extract_missing_name_raises() -> None:
    data = {"tool": {"poetry": {"version": "1.0"}}}
    with pytest.raises(ValueError, match="name is required"):
        extract_poetry_metadata(data)


def test_extract_provenance_sources() -> None:
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "description": "desc",
                "authors": ["Alice <a@example.com>"],
            }
        }
    }
    metadata = extract_poetry_metadata(data)
    assert "tool.poetry.name" in metadata.provenance.get("name", "")
    assert "tool.poetry.version" in metadata.provenance.get("version", "")
    assert "tool.poetry.description" in metadata.provenance.get("description", "")
    assert "tool.poetry.authors" in metadata.provenance.get("authors", "")
    assert "inferred_from_authors" in metadata.provenance.get("copyright_text", "")


# ---------------------------------------------------------------------------
# read_poetry -- file-based
# ---------------------------------------------------------------------------


def test_read_poetry_missing_file() -> None:
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(FileNotFoundError):
            read_poetry(Path(d) / "pyproject.toml")


def test_read_poetry_no_poetry_section() -> None:
    content = "[project]\nname = 'pkg'\nversion = '1.0'\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        with pytest.raises(ValueError, match=r"\[tool\.poetry\]"):
            read_poetry(Path(d) / "pyproject.toml")


def test_read_poetry_returns_pitloom_config() -> None:
    content = """
[tool.poetry]
name = "pkg"
version = "1.0"

[tool.pitloom]
pretty = true
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        _, config = read_poetry(Path(d) / "pyproject.toml")
    assert config.pretty is True


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
# The fixture at tests/fixtures/sampleproject-poetry/ is a copy of
# https://github.com/mistralai/mistral-inference/blob/main/pyproject.toml
# It uses Poetry as build backend with no [project] section.
# ---------------------------------------------------------------------------


def test_fixture_read_poetry_name_and_version() -> None:
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.name == "mistral_inference"
    assert metadata.version == "1.6.0"


def test_fixture_read_poetry_description_empty() -> None:
    # mistral-inference has description = "" -- maps to None after stripping.
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.description is None


def test_fixture_read_poetry_author() -> None:
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.authors == [{"name": "bam4d", "email": "bam4d@mistral.ai"}]


def test_fixture_read_poetry_license_absent() -> None:
    # mistral-inference has no license field in [tool.poetry].
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.license_name is None


def test_fixture_read_poetry_keywords_empty() -> None:
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert not metadata.keywords


def test_fixture_read_poetry_urls_empty() -> None:
    # mistral-inference declares no homepage/repository/documentation.
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert not metadata.urls


def test_fixture_read_poetry_requires_python() -> None:
    # python = "^3.9.10" -> >=3.9.10,<4.0.0
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.requires_python == ">=3.9.10,<4.0.0"


def test_fixture_read_poetry_main_dependencies_only() -> None:
    # Only [tool.poetry.dependencies] (not group deps) end up in SBOM deps.
    metadata, _ = read_poetry(POETRY_FIXTURE / "pyproject.toml")
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
    _, config = read_poetry(POETRY_FIXTURE / "pyproject.toml")
    assert config.sbom_basename is None
    assert config.pretty is False
    assert config.creation_creator_name is None


def test_fixture_read_pyproject_falls_back_to_poetry() -> None:
    # No [project] section -> falls back to [tool.poetry].
    metadata, _ = read_pyproject(POETRY_FIXTURE / "pyproject.toml")
    assert metadata.name == "mistral_inference"
    assert metadata.version == "1.6.0"
