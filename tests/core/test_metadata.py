# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from pyproject.toml.

See also: tests/core/test_metadata_pitloom_creators.py for pitloom
provenance edge cases, multiple creators/tools, and moved/renamed key
validation. tests/core/test_metadata_edge_cases.py for malformed
creator/tool shapes, dependency-name canonicalization, and license
concluded (G2) tests.
"""

import tempfile
from pathlib import Path

import pytest

from pitloom.core.creation import Creator, Tool
from pitloom.extract._pyproject import read_pyproject


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
    """Test graceful fallback when [project] section is absent."""
    pyproject_content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.black]
line-length = 88
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata, _ = read_pyproject(pyproject_path)
        assert metadata.name == ""
        assert metadata.version is None
        assert metadata.description is None
        assert not metadata.keywords
        assert not metadata.dependencies


def test_extract_metadata_missing_name() -> None:
    """Test graceful fallback when project name is absent from [project] section."""
    pyproject_content = """
[project]
version = "1.0.0"
description = "A test package"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata, _ = read_pyproject(pyproject_path)
        assert metadata.name == ""
        assert metadata.version is None
        assert metadata.description is None


def test_extract_metadata_no_project_section_reads_pitloom_config() -> None:
    """[tool.pitloom] config is still read even when [project] section is absent."""
    pyproject_content = """
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[tool.pitloom]
pretty = true
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata, config = read_pyproject(pyproject_path)
        assert metadata.name == ""
        assert config.pretty is True


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


@pytest.mark.parametrize(
    "raw_type,normalized",
    [
        ("person", "person"),
        ("organization", "organization"),
        ("software-agent", "software-agent"),
        ("agent", "agent"),
        ("Person", "person"),
        (" organization ", "organization"),
    ],
)
def test_creator_valid_types_construct_and_normalize(
    raw_type: str, normalized: str
) -> None:
    """Every valid creator type constructs fine; type is normalised to
    stripped lower-case."""
    creator = Creator(name="Someone", type=raw_type)
    assert creator.type == normalized


def test_creator_invalid_type_raises_at_construction() -> None:
    """``Creator(type="bogus")`` raises ValueError eagerly at construction,
    not only later at SPDX assembly time."""
    with pytest.raises(ValueError, match="Invalid creator type"):
        Creator(name="Bot", type="bogus")


def test_extract_pitloom_creation_settings() -> None:
    """Read creation metadata settings from ``[[tool.pitloom.creator]]`` /
    ``[[tool.pitloom.creation-tool]]`` / ``[tool.pitloom.creation]``."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creator]]
name = "Config Creator"
email = "config@example.com"

[[tool.pitloom.creation-tool]]
name = "Config Tool"

[tool.pitloom.creation]
creation-datetime = "2026-01-01T00:00:00+00:00"
creation-comment = "Created from config"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.creators == [
            Creator(name="Config Creator", email="config@example.com")
        ]
        assert config.creation_datetime == "2026-01-01T00:00:00+00:00"
        assert config.tools == [Tool(name="Config Tool")]
        assert config.creation_comment == "Created from config"


def test_extract_pitloom_provenance_settings_default() -> None:
    """Absent ``[tool.pitloom.provenance]`` defaults to format='both' and
    schema='pitloom/1' (see pitloom.assemble.spdx3.provenance.DEFAULT_SCHEMA_ID)."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.provenance_format == "both"
        assert config.provenance_schema == "pitloom/1"
        assert config.provenance_detail == "minimal"
        assert config.provenance_preserve_source_metadata == "auto"


def test_extract_pitloom_provenance_settings_explicit() -> None:
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.provenance]
format = "annotation"
schema = "custom/1"
detail = "full"
preserve-source-metadata = "always"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.provenance_format == "annotation"
        assert config.provenance_schema == "custom/1"
        assert config.provenance_detail == "full"
        assert config.provenance_preserve_source_metadata == "always"


def test_creator_empty_name_raises() -> None:
    """``Creator(name="")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="Creator name must be non-empty"):
        Creator(name="")


def test_creator_whitespace_name_raises() -> None:
    """``Creator(name="   ")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="Creator name must be non-empty"):
        Creator(name="   ")


def test_tool_empty_name_raises() -> None:
    """``Tool(name="")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="Tool name must be non-empty"):
        Tool(name="")


def test_tool_whitespace_name_raises() -> None:
    """``Tool(name="   ")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="Tool name must be non-empty"):
        Tool(name="   ")
