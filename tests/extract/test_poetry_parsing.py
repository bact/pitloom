# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for low-level [tool.poetry] parsing helpers and read_poetry().

See also: test_poetry_pyproject.py for read_pyproject() poetry-fallback,
fixture integration, and license-conflict tests.
"""

import tempfile
from pathlib import Path

import pytest

from pitloom.extract._poetry import (
    _parse_poetry_authors,
    _parse_poetry_deps,
    _poetry_constraint_to_pep440,
    _poetry_dep_to_pep508,
    extract_poetry_metadata,
    read_poetry,
)

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


def test_parse_authors_unmatched_email_bracket_skipped() -> None:
    """An entry with an unclosed '<' fails the author regex and is skipped."""
    authors = _parse_poetry_authors(["Name <unclosed", "Valid <v@example.com>"])
    assert authors == [{"name": "Valid", "email": "v@example.com"}]


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


def test_parse_deps_skips_unrepresentable_git_dependency() -> None:
    """A git-sourced dependency converts to None and is not appended."""
    deps = {
        "dev-pkg": {"git": "https://github.com/x/y"},
        "requests": "^2.28",
    }
    packages, requires_python = _parse_poetry_deps(deps)
    assert requires_python is None
    assert not any("dev-pkg" in d for d in packages)
    assert any("requests" in d for d in packages)


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
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
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
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.requires_python == ">=3.10,<4.0.0"
    assert any("requests" in d for d in metadata.dependencies)
    assert any("numpy" in d for d in metadata.dependencies)
    assert not any("python" in d for d in metadata.dependencies)


def test_extract_readme_string() -> None:
    data = {"tool": {"poetry": {"name": "pkg", "readme": "README.md"}}}
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.readme == "README.md"


def test_extract_readme_list() -> None:
    data = {
        "tool": {"poetry": {"name": "pkg", "readme": ["README.md", "CHANGELOG.md"]}}
    }
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.readme == "README.md"


def test_extract_missing_section_raises() -> None:
    with pytest.raises(ValueError, match=r"\[tool\.poetry\]"):
        extract_poetry_metadata({}, Path("."))


def test_extract_missing_name_raises() -> None:
    data = {"tool": {"poetry": {"version": "1.0"}}}
    with pytest.raises(ValueError, match="name is required"):
        extract_poetry_metadata(data, Path("."))


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
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
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


def test_convert_caret_and_tilde_edge_cases() -> None:
    """_convert_caret and _convert_tilde handle zero/short/invalid versions."""
    from pitloom.extract._poetry import (
        _convert_caret,
        _convert_tilde,
        _parse_poetry_authors,
        _poetry_constraint_to_pep440,
    )

    # Caret edge cases
    assert _convert_caret("0") == ">=0"
    assert _convert_caret("0.0") == ">=0.0,<0.1.0"
    assert _convert_caret("invalid") == ">=invalid"

    # Tilde edge cases
    assert _convert_tilde("1") == ">=1"
    assert _convert_tilde("abc") == ">=abc"
    assert _convert_tilde("abc.def") == ">=abc.def"

    # Non-string / invalid constraint
    assert _poetry_constraint_to_pep440(12345) is None
    assert _poetry_constraint_to_pep440(None) is None

    # Authors with invalid string formats
    assert _parse_poetry_authors([123, "", "   "]) == []
