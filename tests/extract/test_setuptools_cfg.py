# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for metadata extraction from setup.cfg.

See also: test_setuptools_py.py for setup.py and merge/fixture tests.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.creation import Creator
from pitloom.extract._setuptools import detect_build_backend, read_setup_cfg

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


def test_detect_backend_malformed_pyproject_logs_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A pyproject.toml that fails to parse is caught, logged, and the
    function falls back to None -- same as when no backend can be
    determined -- rather than raising."""
    content = "[build-system\nbroken toml"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "pyproject.toml").write_text(content)
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._setuptools"):
            result = detect_build_backend(Path(d))
    assert result is None
    assert any("pyproject.toml" in r.message for r in caplog.records)


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
# read_setup_cfg -- basic fields
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
    """Author entry with name only -- no email key in dict."""
    content = "[metadata]\nname = pkg\nversion = 1.0\nauthor = Bob\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.authors == [{"name": "Bob"}]


def test_read_setup_cfg_author_only_email() -> None:
    """Author entry with email only -- no name key in dict."""
    content = "[metadata]\nname = pkg\nversion = 1.0\nauthor_email = bob@example.com\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        metadata, _ = read_setup_cfg(Path(d))
    assert metadata.authors == [{"email": "bob@example.com"}]


# ---------------------------------------------------------------------------
# read_setup_cfg -- version directives
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
# read_setup_cfg -- long_description file directive
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
# read_setup_cfg -- [tool:pitloom] config
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
    assert config.creators == [Creator(name="Test Creator", email="test@example.com")]


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
    assert config.creators == [Creator(name="Sub Creator")]
    assert config.creation_datetime == "2026-01-01T00:00:00+00:00"


def test_read_setup_cfg_pitloom_config_modern_sections() -> None:
    """Reads [tool:pitloom:fragment], [tool:pitloom:provenance], etc."""
    content = """
[metadata]
name = pkg
version = 1.0

[tool:pitloom]
fragments =
    abc.json
    def.json
describe-relationship = false

[tool:pitloom:fragment]
files =
    xyz.json

[tool:pitloom:provenance]
format = both
detail = minimal

[tool:pitloom:content-type]
enabled = true

[tool:pitloom:content-type:override]
"*.myext" = "application/x-myext"
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))

    assert config.fragments == ["xyz.json"]
    assert config.provenance_format == "both"
    assert config.provenance_detail == "minimal"
    assert config.content_type_enabled is True
    assert config.content_type_overrides == (
        ContentTypeOverride(pattern='"*.myext"', content_type='"application/x-myext"'),
    )
    assert config.describe_relationship is False


def test_read_setup_cfg_no_creation_tool_suppresses_tools() -> None:
    """``[tool:pitloom:creation] no-creation-tool = true`` maps to
    ``tools == []``, mirroring the ``pyproject.toml`` behaviour."""
    content = """
[metadata]
name = pkg
version = 1.0

[tool:pitloom:creation]
no-creation-tool = true
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.tools == []


def test_read_setup_cfg_no_creation_tool_overrides_explicit_tool_name() -> None:
    """``no-creation-tool = true`` forces ``tools == []`` even when a
    ``creation-tool`` name is also set -- suppression wins."""
    content = """
[metadata]
name = pkg
version = 1.0

[tool:pitloom]
creation-tool = MyWrapper
no_creation_tool = yes
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.tools == []


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
# read_setup_cfg -- provenance
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
