# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from pyproject.toml."""

import tempfile
from pathlib import Path

import pytest

from loom.extractors.pyproject import read_pyproject


def test_extract_metadata_basic() -> None:
    """Test basic metadata extraction from pyproject.toml."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
description = "A test package"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
keywords = ["test", "package"]
dependencies = ["requests>=2.28.0", "numpy==1.24.0"]

[[project.authors]]
name = "Test Author"
email = "test@example.com"

[project.urls]
Homepage = "https://example.com"
Source = "https://github.com/test/test-package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata, _ = read_pyproject(pyproject_path)

        assert metadata.name == "test-package"
        assert metadata.version == "1.0.0"
        assert metadata.description == "A test package"
        assert metadata.readme == "README.md"
        assert metadata.requires_python == ">=3.10"
        assert metadata.license_name == "MIT"
        assert metadata.keywords == ["test", "package"]
        assert len(metadata.authors) == 1
        assert metadata.authors[0]["name"] == "Test Author"
        assert metadata.authors[0]["email"] == "test@example.com"
        assert metadata.urls["Homepage"] == "https://example.com"
        assert metadata.urls["Source"] == "https://github.com/test/test-package"
        assert "requests>=2.28.0" in metadata.dependencies
        assert "numpy==1.24.0" in metadata.dependencies


def test_extract_metadata_missing_file() -> None:
    """Test extraction with missing pyproject.toml file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"

        with pytest.raises(FileNotFoundError):
            read_pyproject(pyproject_path)


def test_extract_metadata_missing_project_section() -> None:
    """Test extraction with missing [project] section."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="No \\[project\\] section found"):
            read_pyproject(pyproject_path)


def test_extract_metadata_missing_name() -> None:
    """Test extraction with missing project name."""
    pyproject_content = """
[project]
version = "1.0.0"
description = "A test package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="Project name is required"):
            read_pyproject(pyproject_path)


def test_extract_metadata_dynamic_version() -> None:
    """Test extraction with dynamic version from __about__.py."""
    pyproject_content = """
[project]
name = "test-package"
dynamic = ["version"]
description = "A test package"
"""

    about_content = '__version__ = "2.0.0"'

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Create __about__.py in src directory
        src_dir = tmppath / "src"
        src_dir.mkdir()
        about_path = src_dir / "__about__.py"
        about_path.write_text(about_content)

        metadata, _ = read_pyproject(pyproject_path)

        assert metadata.name == "test-package"
        assert metadata.version == "2.0.0"
