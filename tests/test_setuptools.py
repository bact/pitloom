# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from setup.cfg and setup.py."""

import tempfile
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract.setuptools import (
    detect_build_backend,
    merge_metadata,
    read_setup_cfg,
    read_setup_py,
    read_setuptools,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SETUPTOOLS_FIXTURE = FIXTURE_DIR / "sampleproject-setuptools"


# ---------------------------------------------------------------------------
# detect_build_backend
# ---------------------------------------------------------------------------


def test_detect_backend_hatchling() -> None:
    """Detects hatchling backend from pyproject.toml build-backend key."""
    content = """
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "hatchling"


def test_detect_backend_setuptools_in_pyproject() -> None:
    """Detects setuptools backend when pyproject.toml declares setuptools.build_meta."""
    content = """
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "mypackage"
version = "1.0.0"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_backend_no_pyproject_with_setup_cfg() -> None:
    """Infers setuptools backend when only setup.cfg exists."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text("[metadata]\nname = pkg\n")
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_backend_no_pyproject_with_setup_py() -> None:
    """Infers setuptools backend when only setup.py exists."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(
            'from setuptools import setup\nsetup(name="pkg")\n'
        )
        assert detect_build_backend(Path(d)) == "setuptools"


def test_detect_backend_no_config_files() -> None:
    """Returns None when no build configuration files are present."""
    with tempfile.TemporaryDirectory() as d:
        assert detect_build_backend(Path(d)) is None


def test_detect_backend_unknown_backend() -> None:
    """Returns the raw backend string for unrecognised build backends."""
    content = """
[build-system]
requires = ["meson-python"]
build-backend = "mesonpy"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        assert detect_build_backend(Path(d)) == "mesonpy"


# ---------------------------------------------------------------------------
# read_setup_cfg — basic fields
# ---------------------------------------------------------------------------


def test_read_setup_cfg_basic() -> None:
    """Extracts core metadata fields from a minimal setup.cfg."""
    content = """
[metadata]
name = mypackage
version = 1.2.3
description = A test package
author = Alice Smith
author_email = alice@example.com
license = MIT
keywords = foo bar baz
url = https://example.com

[options]
python_requires = >=3.9
install_requires =
    requests>=2.0
    click>=8.0
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))

    assert metadata.name == "mypackage"
    assert metadata.version == "1.2.3"
    assert metadata.description == "A test package"
    assert metadata.license_name == "MIT"
    assert metadata.requires_python == ">=3.9"
    assert metadata.authors == [{"name": "Alice Smith", "email": "alice@example.com"}]
    assert metadata.urls == {"Homepage": "https://example.com"}
    assert "requests>=2.0" in metadata.dependencies
    assert "click>=8.0" in metadata.dependencies
    assert "foo" in metadata.keywords
    assert "bar" in metadata.keywords


def test_read_setup_cfg_keywords_comma_separated() -> None:
    """Parses comma-separated keywords into a list."""
    content = "[metadata]\nname = pkg\nversion = 1.0\nkeywords = alpha, beta, gamma\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.keywords == ["alpha", "beta", "gamma"]


def test_read_setup_cfg_project_urls() -> None:
    """Reads project_urls into a dict of label to URL mappings."""
    content = """
[metadata]
name = pkg
version = 1.0
project_urls =
    Homepage = https://example.com
    Source = https://github.com/example/pkg
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.urls["Homepage"] == "https://example.com"
    assert metadata.urls["Source"] == "https://github.com/example/pkg"


def test_read_setup_cfg_missing_file() -> None:
    """Raises FileNotFoundError when setup.cfg does not exist."""
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(FileNotFoundError):
            read_setup_cfg(Path(d))


def test_read_setup_cfg_missing_name() -> None:
    """Raises ValueError when [metadata] name is absent."""
    content = "[metadata]\nversion = 1.0\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        with pytest.raises(ValueError, match="name is required"):
            read_setup_cfg(Path(d))


def test_read_setup_cfg_author_only_name() -> None:
    """Author entry with name only — no email key in dict."""
    content = "[metadata]\nname = pkg\nversion = 1.0\nauthor = Bob\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.authors == [{"name": "Bob"}]


def test_read_setup_cfg_author_only_email() -> None:
    """Author entry with email only — no name key in dict."""
    content = "[metadata]\nname = pkg\nversion = 1.0\nauthor_email = bob@example.com\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.authors == [{"email": "bob@example.com"}]


# ---------------------------------------------------------------------------
# read_setup_cfg — version directives
# ---------------------------------------------------------------------------


def test_read_setup_cfg_version_file_directive() -> None:
    """Resolves `version = file: VERSION` by reading the VERSION file."""
    content = "[metadata]\nname = pkg\nversion = file: VERSION\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        (Path(d) / "VERSION").write_text("3.4.5\n")
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.version == "3.4.5"
    assert "file_directive" in (metadata.provenance.get("version") or "")


def test_read_setup_cfg_version_file_directive_missing_file() -> None:
    """Returns None version when the referenced VERSION file is absent."""
    content = "[metadata]\nname = pkg\nversion = file: VERSION\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.version is None


def test_read_setup_cfg_version_attr_directive() -> None:
    """Resolves `version = attr: pkg.__version__` via AST in package root."""
    content = "[metadata]\nname = mypackage\nversion = attr: mypackage.__version__\n"
    with tempfile.TemporaryDirectory() as d:
        pkg_dir = Path(d) / "mypackage"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('__version__ = "9.8.7"\n')
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.version == "9.8.7"
    assert "attr_directive" in (metadata.provenance.get("version") or "")


def test_read_setup_cfg_version_attr_directive_src_layout() -> None:
    """Resolves attr directive for a src-layout package."""
    content = "[metadata]\nname = mypkg\nversion = attr: mypkg.__version__\n"
    with tempfile.TemporaryDirectory() as d:
        src_pkg = Path(d) / "src" / "mypkg"
        src_pkg.mkdir(parents=True)
        (src_pkg / "__init__.py").write_text('__version__ = "2.0.0"\n')
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.version == "2.0.0"


# ---------------------------------------------------------------------------
# read_setup_cfg — long_description file directive
# ---------------------------------------------------------------------------


def test_read_setup_cfg_readme_file_directive() -> None:
    """Reads long_description = file: README.md content into readme field."""
    content = (
        "[metadata]\nname = pkg\nversion = 1.0\nlong_description = file: README.md\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        (Path(d) / "README.md").write_text("# My Package\n\nA great package.")
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.readme and "My Package" in metadata.readme


def test_read_setup_cfg_readme_file_missing_returns_filename() -> None:
    """Falls back to the filename hint when the README file is absent."""
    content = (
        "[metadata]\nname = pkg\nversion = 1.0\nlong_description = file: README.rst\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    # Falls back to the filename hint rather than raising
    assert metadata.readme == "README.rst"


# ---------------------------------------------------------------------------
# read_setup_cfg — [tool:pitloom] config
# ---------------------------------------------------------------------------


def test_read_setup_cfg_pitloom_config() -> None:
    """Reads [tool:pitloom] settings into PitloomConfig."""
    content = """
[metadata]
name = pkg
version = 1.0

[tool:pitloom]
pretty = true
sbom-basename = my-sbom
creator-name = Test Creator
creator-email = test@example.com
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.pretty is True
    assert config.sbom_basename == "my-sbom"
    assert config.creation_creator_name == "Test Creator"
    assert config.creation_creator_email == "test@example.com"


def test_read_setup_cfg_pitloom_config_creation_section() -> None:
    """Reads [tool:pitloom:creation] sub-section into PitloomConfig."""
    content = """
[metadata]
name = pkg
version = 1.0

[tool:pitloom:creation]
creator-name = Sub Creator
creation-datetime = 2026-01-01T00:00:00+00:00
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.creation_creator_name == "Sub Creator"
    assert config.creation_creation_datetime == "2026-01-01T00:00:00+00:00"


def test_read_setup_cfg_no_pitloom_section_returns_defaults() -> None:
    """Returns default PitloomConfig when [tool:pitloom] is absent."""
    content = "[metadata]\nname = pkg\nversion = 1.0\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.pretty is False
    assert config.sbom_basename is None
    assert not config.fragments


# ---------------------------------------------------------------------------
# read_setup_cfg — provenance
# ---------------------------------------------------------------------------


def test_read_setup_cfg_provenance() -> None:
    """Each extracted field records setup.cfg as its source in provenance."""
    content = "[metadata]\nname = pkg\nversion = 1.0\nauthor = Alice\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert "setup.cfg" in metadata.provenance.get("name", "")
    assert "setup.cfg" in metadata.provenance.get("version", "")
    assert "setup.cfg" in metadata.provenance.get("authors", "")
    assert "inferred_from_authors" in metadata.provenance.get("copyright_text", "")


# ---------------------------------------------------------------------------
# read_setup_py — basic
# ---------------------------------------------------------------------------


def test_read_setup_py_basic() -> None:
    """Extracts core metadata from a fully-populated setup() call."""
    content = """
from setuptools import setup

setup(
    name="mypackage",
    version="1.0.0",
    description="A cool package",
    author="Bob",
    author_email="bob@example.com",
    license="Apache-2.0",
    url="https://example.com",
    python_requires=">=3.8",
    install_requires=["requests>=2.0", "click"],
    keywords=["foo", "bar"],
)
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))

    assert metadata.name == "mypackage"
    assert metadata.version == "1.0.0"
    assert metadata.description == "A cool package"
    assert metadata.authors == [{"name": "Bob", "email": "bob@example.com"}]
    assert metadata.license_name == "Apache-2.0"
    assert metadata.urls == {"Homepage": "https://example.com"}
    assert metadata.requires_python == ">=3.8"
    assert "requests>=2.0" in metadata.dependencies
    assert "click" in metadata.dependencies
    assert "foo" in metadata.keywords


def test_read_setup_py_setuptools_dot_setup() -> None:
    """Recognise setuptools.setup() as well as bare setup()."""
    content = """
import setuptools
setuptools.setup(name="mypkg", version="0.1")
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.name == "mypkg"
    assert metadata.version == "0.1"


def test_read_setup_py_missing_file() -> None:
    """Raises FileNotFoundError when setup.py does not exist."""
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(FileNotFoundError):
            read_setup_py(Path(d))


def test_read_setup_py_no_name_literal() -> None:
    """When name is a variable (not a literal), parsing should raise."""
    content = """
from setuptools import setup
pkg_name = "mypackage"
setup(name=pkg_name, version="1.0")
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        with pytest.raises(ValueError, match="project name"):
            read_setup_py(Path(d))


def test_read_setup_py_dynamic_version_skipped() -> None:
    """Dynamic version (function call) is silently skipped — version is None."""
    content = """
from setuptools import setup
setup(name="mypkg", version=get_version())
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.name == "mypkg"
    assert metadata.version is None


def test_read_setup_py_project_urls() -> None:
    """Reads project_urls dict literal from setup()."""
    content = """
from setuptools import setup
setup(
    name="mypkg",
    version="1.0",
    project_urls={
        "Homepage": "https://example.com",
        "Source": "https://github.com/example/mypkg",
    },
)
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.urls["Homepage"] == "https://example.com"
    assert metadata.urls["Source"] == "https://github.com/example/mypkg"


def test_read_setup_py_keywords_string() -> None:
    """Splits space-separated keywords string into a list."""
    content = (
        "from setuptools import setup\n"
        "setup(name='pkg', version='1.0', keywords='a b c')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert metadata.keywords == ["a", "b", "c"]


def test_read_setup_py_provenance() -> None:
    """Each extracted field records setup.py as its source in provenance."""
    content = (
        "from setuptools import setup\nsetup(name='pkg', version='1.0', author='X')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setup_py(Path(d))
    assert "setup.py" in metadata.provenance["name"]
    assert "setup.py" in metadata.provenance["version"]
    assert "setup.py" in metadata.provenance["authors"]


def test_read_setup_py_returns_default_pitloom_config() -> None:
    """setup.py provides no pitloom config — defaults are returned."""
    content = "from setuptools import setup\nsetup(name='pkg', version='1.0')\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        _, config = read_setup_py(Path(d))
    assert config.pretty is False
    assert config.sbom_basename is None


# ---------------------------------------------------------------------------
# read_setuptools — merging
# ---------------------------------------------------------------------------


def test_read_setuptools_cfg_only() -> None:
    """read_setuptools() succeeds with setup.cfg alone."""
    content = "[metadata]\nname = pkg\nversion = 1.0\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setuptools(Path(d))
    assert metadata.name == "pkg"


def test_read_setuptools_py_only() -> None:
    """read_setuptools() succeeds with setup.py alone."""
    content = "from setuptools import setup\nsetup(name='pkg2', version='2.0')\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.py").write_text(content)
        metadata, _ = read_setuptools(Path(d))
    assert metadata.name == "pkg2"


def test_read_setuptools_cfg_wins_over_py() -> None:
    """setup.cfg fields take precedence over setup.py."""
    cfg = "[metadata]\nname = cfg-pkg\nversion = 3.0\n"
    py = (
        "from setuptools import setup\n"
        "setup(name='py-pkg', version='9.9', description='from py')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(cfg)
        (Path(d) / "setup.py").write_text(py)
        metadata, _ = read_setuptools(Path(d))
    assert metadata.name == "cfg-pkg"
    assert metadata.version == "3.0"
    # description from setup.py fills gap not covered by setup.cfg
    assert metadata.description == "from py"


def test_read_setuptools_neither_exists() -> None:
    """Raises FileNotFoundError when neither setup.cfg nor setup.py exists."""
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(FileNotFoundError):
            read_setuptools(Path(d))


def test_read_setuptools_cfg_config_returned() -> None:
    """PitloomConfig comes from setup.cfg, not setup.py."""
    cfg = "[metadata]\nname = pkg\nversion = 1.0\n\n[tool:pitloom]\npretty = true\n"
    py = "from setuptools import setup\nsetup(name='pkg', version='1.0')\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(cfg)
        (Path(d) / "setup.py").write_text(py)
        _, config = read_setuptools(Path(d))
    assert config.pretty is True


# ---------------------------------------------------------------------------
# merge_metadata
# ---------------------------------------------------------------------------


def test_merge_metadata_primary_wins() -> None:
    """Primary field values are never overwritten by secondary."""
    primary = ProjectMetadata(
        name="primary-pkg",
        version="2.0",
        description="Primary description",
    )
    secondary = ProjectMetadata(
        name="secondary-pkg",
        version="1.0",
        description="Secondary description",
        license_name="MIT",
    )
    merged = merge_metadata(primary, secondary)

    assert merged.name == "primary-pkg"
    assert merged.version == "2.0"
    assert merged.description == "Primary description"
    # Gap filled from secondary
    assert merged.license_name == "MIT"


def test_merge_metadata_secondary_fills_gaps() -> None:
    """Secondary fills all None or empty fields left by primary."""
    primary = ProjectMetadata(name="pkg", version="1.0")
    secondary = ProjectMetadata(
        name="secondary",
        version="0.1",
        description="From secondary",
        requires_python=">=3.9",
        keywords=["x", "y"],
        authors=[{"name": "Author"}],
        dependencies=["dep>=1.0"],
        urls={"Homepage": "https://example.com"},
    )
    merged = merge_metadata(primary, secondary)

    assert merged.name == "pkg"
    assert merged.version == "1.0"
    assert merged.description == "From secondary"
    assert merged.requires_python == ">=3.9"
    assert merged.keywords == ["x", "y"]
    assert merged.authors == [{"name": "Author"}]
    assert "dep>=1.0" in merged.dependencies
    assert merged.urls == {"Homepage": "https://example.com"}


def test_merge_metadata_provenance_merged() -> None:
    """Provenance dicts are merged with primary entries winning on conflict."""
    primary = ProjectMetadata(
        name="pkg",
        version="1.0",
        provenance={
            "name": "Source: pyproject.toml",
            "version": "Source: pyproject.toml",
        },
    )
    secondary = ProjectMetadata(
        name="pkg2",
        version="0.1",
        description="desc",
        provenance={"name": "Source: setup.cfg", "description": "Source: setup.cfg"},
    )
    merged = merge_metadata(primary, secondary)

    # Primary wins on conflict
    assert merged.provenance["name"] == "Source: pyproject.toml"
    # Secondary fills missing keys
    assert merged.provenance["description"] == "Source: setup.cfg"


def test_merge_metadata_empty_lists_filled_from_secondary() -> None:
    """Empty lists in primary are treated as gaps and filled from secondary."""
    primary = ProjectMetadata(name="pkg", version="1.0", keywords=[])
    secondary = ProjectMetadata(name="s", version="0", keywords=["a", "b"])
    merged = merge_metadata(primary, secondary)
    assert merged.keywords == ["a", "b"]


# ---------------------------------------------------------------------------
# Fixture-based integration tests (sampleproject-setuptools)
# ---------------------------------------------------------------------------


def test_fixture_detect_backend() -> None:
    """Fixture project declares setuptools as build backend."""
    assert detect_build_backend(SETUPTOOLS_FIXTURE) == "setuptools"


def test_fixture_read_setup_cfg_name_and_version() -> None:
    """Fixture setup.cfg name and version match expected values."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.name == "sampleproject-setuptools"
    assert metadata.version == "0.1.0"


def test_fixture_read_setup_cfg_description() -> None:
    """Fixture description contains the word 'setuptools'."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.description is not None
    assert "setuptools" in metadata.description.lower()


def test_fixture_read_setup_cfg_author() -> None:
    """Fixture author name and email match CI metadata."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.authors == [{"name": "Pitloom CI", "email": "ci@loom.example"}]


def test_fixture_read_setup_cfg_license() -> None:
    """Fixture license identifier is CC0-1.0."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.license_name == "CC0-1.0"


def test_fixture_read_setup_cfg_urls() -> None:
    """Fixture project_urls includes Source and Tracker entries."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert "Source" in metadata.urls
    assert "Tracker" in metadata.urls


def test_fixture_read_setup_cfg_dependencies() -> None:
    """Fixture install_requires includes a requests dependency."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert any("requests" in dep for dep in metadata.dependencies)


def test_fixture_read_setup_cfg_requires_python() -> None:
    """Fixture python_requires is >=3.10."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.requires_python == ">=3.10"


def test_fixture_read_setup_cfg_pitloom_config() -> None:
    """[tool:pitloom] in setup.cfg populates PitloomConfig correctly."""
    _, config = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert config.sbom_basename == "sbom"
    assert config.creation_creator_name == "Pitloom CI"
    assert config.creation_creator_email == "ci@loom.example"


def test_fixture_read_setup_cfg_readme_content() -> None:
    """long_description = file: README.md is resolved to file content."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.readme is not None
    assert "sampleproject-setuptools" in metadata.readme


def test_fixture_read_setup_py_bare_setup() -> None:
    """setup.py with bare setup() call extracts no metadata (all in setup.cfg)."""
    # The fixture's setup.py calls setup() with no arguments — name comes
    # from setup.cfg which setuptools reads at runtime, but AST sees nothing.
    with pytest.raises(ValueError, match="project name"):
        read_setup_py(SETUPTOOLS_FIXTURE)


def test_fixture_read_setuptools_merges_cfg_and_py() -> None:
    """read_setuptools() falls back gracefully when setup.py has no literals."""
    metadata, config = read_setuptools(SETUPTOOLS_FIXTURE)
    # Metadata comes from setup.cfg (setup.py has no literal args)
    assert metadata.name == "sampleproject-setuptools"
    assert metadata.version == "0.1.0"
    assert config.sbom_basename == "sbom"
