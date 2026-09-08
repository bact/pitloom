# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for extract_poetry_metadata() -- the higher-level [tool.poetry]
entry point built on the low-level parsing helpers. Split out of
test_poetry_parsing.py to keep that file under this repo's file-size
soft limit.

See also: test_poetry_parsing.py for the low-level [tool.poetry] parsing
helper tests; test_poetry_pyproject.py for read_pyproject() poetry-fallback,
fixture integration, and license-conflict tests.
"""

import tempfile
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata, merge_project_metadata
from pitloom.extract._poetry import extract_poetry_metadata

from .conftest import assert_declared_empty_authors_no_copyright_text

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


def test_extract_provenance_empty_declared_dependencies() -> None:
    """An explicitly declared but empty [tool.poetry.dependencies] (besides
    the always-present `python` key) must still record provenance for
    `dependencies` -- merge_project_metadata() relies on that presence to
    treat the empty list as authoritative, not absent."""
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "dependencies": {"python": "^3.10"},
                "keywords": [],
            }
        }
    }
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.dependencies == []
    assert metadata.keywords == []
    assert "dependencies" in metadata.provenance
    assert "keywords" in metadata.provenance
    assert "requires_python" in metadata.provenance


def test_extract_non_list_keywords_treated_as_empty() -> None:
    """A malformed `keywords` value that isn't a list (e.g. a bare string)
    must resolve to an empty list, not raise or pass the raw value
    through."""
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "keywords": "not-a-list",
            }
        }
    }
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.keywords == []


def test_extract_provenance_declared_empty_authors_no_copyright_text() -> None:
    """An explicitly declared but empty `authors = []` must still record
    provenance for `authors`, but with no authors to derive a name from,
    no `copyright_text` is inferred."""
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "authors": [],
            }
        }
    }
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert_declared_empty_authors_no_copyright_text(metadata)


def test_extract_provenance_wildcard_python_records_requires_python() -> None:
    """`python = "*"` (no real constraint) resolves requires_python to
    None, but that's a deliberate, explicitly-declared answer, not an
    absent field -- provenance must record it so merge_project_metadata()
    can protect it against a lower-priority source's real (possibly
    wrong) constraint, the same presence-based rule every container field
    already follows."""
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "dependencies": {"python": "*"},
            }
        }
    }
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.requires_python is None
    assert "requires_python" in metadata.provenance


def test_extract_provenance_capitalized_python_key_records_requires_python() -> None:
    """A capitalized `Python` key (unusual, but _parse_poetry_deps()
    matches it case-insensitively for the *value*) must get the same
    provenance treatment -- a case-sensitive presence check would
    silently miss it, reopening a narrower version of the misattribution
    bug the presence-based check exists to close."""
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "dependencies": {"Python": "^3.9"},
            }
        }
    }
    with tempfile.TemporaryDirectory() as d:
        metadata = extract_poetry_metadata(data, Path(d))
    assert metadata.requires_python is not None
    assert "requires_python" in metadata.provenance


def test_poetry_wildcard_python_survives_merge_as_primary() -> None:
    """Poetry-derived metadata with an explicit `python = "*"` must keep
    requires_python as None when merged as *primary* against a secondary
    with a real constraint -- the end-to-end proof (real producer output
    fed through the real merge function) that the presence-based
    provenance fix actually changes merge_project_metadata()'s decision,
    not just a synthetic ProjectMetadata literal."""
    data = {
        "tool": {
            "poetry": {
                "name": "my-pkg",
                "version": "1.0.0",
                "dependencies": {"python": "*"},
            }
        }
    }
    with tempfile.TemporaryDirectory() as d:
        poetry_metadata = extract_poetry_metadata(data, Path(d))
    secondary = ProjectMetadata(
        name="my-pkg",
        version="1.0.0",
        requires_python=">=3.8",
        provenance={
            "requires_python": "Source: setup.py | Field: setup(python_requires=...)"
        },
    )
    merged = merge_project_metadata(poetry_metadata, secondary)
    assert merged.requires_python is None


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
