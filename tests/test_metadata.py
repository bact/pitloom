# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from pyproject.toml."""

import tempfile
from pathlib import Path

import pytest

from pitloom.core.creation import Creator, ToolInfo
from pitloom.extract.pyproject import read_pyproject


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


def test_extract_pitloom_bad_creator_type_raises_at_config_read() -> None:
    """A bad ``type`` in ``[[tool.pitloom.creator]]`` raises ValueError as
    soon as the config is read, since ``_read_creators`` constructs
    ``Creator`` objects whose ``__post_init__`` validates ``type``."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creator]]
name = "Bot"
type = "robot"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="Invalid creator type"):
            read_pyproject(pyproject_path)


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
        assert config.tools == [ToolInfo(name="Config Tool")]
        assert config.creation_comment == "Created from config"


def test_extract_pitloom_multiple_creators_and_tools() -> None:
    """Multiple ``[[tool.pitloom.creator]]`` / ``[[tool.pitloom.creation-tool]]``
    tables are all read, in order."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creator]]
name = "Acme Corp"
type = "organization"

[[tool.pitloom.creator]]
name = "Alice"
email = "alice@example.com"

[[tool.pitloom.creation-tool]]
name = "Pitloom"

[[tool.pitloom.creation-tool]]
name = "MyWrapper"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.creators == [
            Creator(name="Acme Corp", type="organization"),
            Creator(name="Alice", email="alice@example.com"),
        ]
        assert config.tools == [ToolInfo(name="Pitloom"), ToolInfo(name="MyWrapper")]


def test_extract_pitloom_no_creation_tool_suppresses_tools() -> None:
    """``[tool.pitloom.creation] no-creation-tool = true`` maps to ``tools=[]``."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.creation]
no-creation-tool = true
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.tools == []


@pytest.mark.parametrize(
    "old_key",
    ["creator-name", "creator-email", "creator-type", "creation-tool"],
)
def test_extract_pitloom_moved_creation_keys_raise(old_key: str) -> None:
    """Old single-valued keys under ``[tool.pitloom.creation]`` raise a clear
    moved-key error instead of being silently ignored."""
    pyproject_content = f"""
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.creation]
{old_key} = "whatever"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="has moved to"):
            read_pyproject(pyproject_path)


@pytest.mark.parametrize(
    "old_key",
    ["creator-name", "creator-email", "creator-type", "creation-tool"],
)
def test_extract_pitloom_moved_creation_keys_raise_top_level(old_key: str) -> None:
    """The pre-multi-creator reader also accepted these keys directly under
    ``[tool.pitloom]`` (not just ``[tool.pitloom.creation]``); that top-level
    form must raise the same moved-key error rather than being silently
    ignored."""
    pyproject_content = f"""
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
{old_key} = "whatever"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="has moved to"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creation_tool_array_not_flagged_as_moved() -> None:
    """The *new* ``[[tool.pitloom.creation-tool]]`` array-of-tables reuses
    the ``creation-tool`` name at the top level of ``[tool.pitloom]`` (as a
    list of tables, not a string) -- it must not be mistaken for the old,
    moved, single-valued ``creation-tool = "name"`` usage."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creation-tool]]
name = "MyWrapper"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.tools == [ToolInfo(name="MyWrapper")]


def test_extract_pitloom_creation_tool_missing_name_raises() -> None:
    """A ``[[tool.pitloom.creation-tool]]`` entry missing ``name`` raises
    ValueError instead of being silently dropped (which, if it were the
    only entry, would incorrectly suppress the default ``createdUsing``
    'Pitloom' tool)."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creation-tool]]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="missing a valid 'name'"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creation_tool_blank_name_raises() -> None:
    """A blank (empty-string) ``name`` in ``[[tool.pitloom.creation-tool]]``
    raises ValueError, same as a missing ``name``."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creation-tool]]
name = ""
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="missing a valid 'name'"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creator_missing_name_raises() -> None:
    """A ``[[tool.pitloom.creator]]`` entry missing ``name`` raises
    ValueError instead of being silently dropped (which, if it were the
    only entry, would silently change the effective default from a named
    creator to the unattended SoftwareAgent 'Pitloom')."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creator]]
email = "nobody@example.com"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="missing a valid 'name'"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_empty_creation_tool_array_still_yields_empty_list() -> None:
    """A genuinely empty ``[[tool.pitloom.creation-tool]]`` array (zero
    tables present) still correctly yields ``tools == []`` -- only a
    malformed *entry within* a present array raises."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
creation-tool = []
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.tools == []


def test_extract_pitloom_creator_single_table_raises() -> None:
    """``[tool.pitloom.creator]`` as a single table (not
    ``[[tool.pitloom.creator]]``) raises ValueError instead of being
    silently treated as absent."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.creator]
name = "Alice"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="must be an array of tables"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creator_list_of_strings_raises() -> None:
    """``creator = ["Alice"]`` (a list of strings, not tables) raises
    ValueError instead of silently dropping every entry."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
creator = ["Alice"]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="entry must be a table"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creation_tool_single_table_raises() -> None:
    """``[tool.pitloom.creation-tool]`` as a single table (not
    ``[[tool.pitloom.creation-tool]]``) raises ValueError instead of being
    silently treated as absent."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.creation-tool]
name = "MyWrapper"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="must be an array of tables"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creation_tool_list_of_strings_raises() -> None:
    """``creation-tool = ["MyWrapper"]`` (a list of strings, not tables)
    raises ValueError instead of silently dropping every entry."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
creation-tool = ["MyWrapper"]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="entry must be a table"):
            read_pyproject(pyproject_path)


def test_creator_empty_name_raises() -> None:
    """``Creator(name="")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="Creator name must be non-empty"):
        Creator(name="")


def test_creator_whitespace_name_raises() -> None:
    """``Creator(name="   ")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="Creator name must be non-empty"):
        Creator(name="   ")


def test_tool_info_empty_name_raises() -> None:
    """``ToolInfo(name="")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="ToolInfo name must be non-empty"):
        ToolInfo(name="")


def test_tool_info_whitespace_name_raises() -> None:
    """``ToolInfo(name="   ")`` raises ValueError eagerly at construction."""
    with pytest.raises(ValueError, match="ToolInfo name must be non-empty"):
        ToolInfo(name="   ")


def test_extract_metadata_canonicalises_dependency_names() -> None:
    """Dependency package names are canonicalised per PEP 503.

    ``read_pyproject`` (the CLI path) does not itself normalise a
    project's declared name (that stays whatever ``[project] name``
    says), but each dependency specifier's package name must be
    canonicalised the same way Hatchling's build hook already
    canonicalises it -- otherwise the CLI and the hook would render the
    same dependency differently and feed different strings into
    ``compute_doc_uuid``.
    """
    pyproject_content = """
[project]
name = "My_Package.Extra"
version = "1.0.0"
dependencies = ["typing_extensions>=4.0", "zope.interface>=5.0"]
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        metadata, _ = read_pyproject(pyproject_path)

        # The declared project name itself is preserved verbatim (unlike
        # Hatchling, pyproject-metadata does not normalise [project] name).
        assert metadata.name == "My_Package.Extra"
        assert metadata.dependencies == [
            "typing-extensions>=4.0",
            "zope-interface>=5.0",
        ]
