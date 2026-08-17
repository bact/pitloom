# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and license fallback tests for read_setuptools().

See also:
- :mod:`tests.extract.test_setuptools_cfg` for setup.cfg metadata tests.
- :mod:`tests.extract.test_setuptools_py` for setup.py extraction tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.core.creation import Creator
from pitloom.extract._setuptools import (
    detect_build_backend,
    read_setup_cfg,
    read_setuptools,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
SETUPTOOLS_FIXTURE = FIXTURE_DIR / "projects" / "sampleproject-setuptools"


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


def test_read_setuptools_invalid_pitloom_config_raises() -> None:
    """A malformed [tool:pitloom:creation] in setup.cfg propagates as ValueError."""
    cfg = (
        "[metadata]\nname = pkg\nversion = 1.0\n\n"
        "[tool:pitloom:creation]\ncreator-name = Alice\ncreator-type = bogus\n"
    )
    py = "from setuptools import setup\nsetup(name='pkg', version='1.0')\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(cfg)
        (Path(d) / "setup.py").write_text(py)
        with pytest.raises(ValueError, match="Invalid creator type"):
            read_setuptools(Path(d))


def test_read_setuptools_no_name_falls_through_to_setup_py() -> None:
    """setup.cfg with no [metadata] name falls through to setup.py."""
    cfg = "[metadata]\ndescription = no name here\n"
    py = "from setuptools import setup\nsetup(name='fallback-pkg', version='1.0.0')\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(cfg)
        (Path(d) / "setup.py").write_text(py)
        metadata, _ = read_setuptools(Path(d))
    assert metadata.name == "fallback-pkg"


def test_read_setuptools_license_fallback_detection_cfg_only() -> None:
    """No license declared in setup.cfg: falls back to directory detection."""
    cfg = "[metadata]\nname = pkg\nversion = 1.0\n"
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "setup.cfg").write_text(cfg)
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        metadata, _ = read_setuptools(tmp_path)
    assert metadata.license_name == "MIT"
    assert metadata.license_concluded is None


def test_read_setuptools_license_conflict_cfg_only() -> None:
    """Declared MIT in setup.cfg + independently-detected Apache-2.0."""
    cfg = "[metadata]\nname = pkg\nversion = 1.0\nlicense = MIT\n"
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "setup.cfg").write_text(cfg)
        (tmp_path / "LICENSE").write_text("Apache License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            metadata, _ = read_setuptools(tmp_path)
    assert metadata.license_name == "MIT"
    assert metadata.license_concluded == "Apache-2.0"
    assert "LICENSE" in (metadata.provenance.get("license_concluded") or "")


def test_read_setuptools_license_conflict_py_only() -> None:
    """Same conflict scenario, declared via setup.py alone (no setup.cfg)."""
    py = (
        "from setuptools import setup\n"
        "setup(name='pkg', version='1.0', license='MIT')\n"
    )
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "setup.py").write_text(py)
        (tmp_path / "LICENSE").write_text("Apache License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            metadata, _ = read_setuptools(tmp_path)
    assert metadata.license_name == "MIT"
    assert metadata.license_concluded == "Apache-2.0"


def test_read_setuptools_license_resolution_runs_once_when_both_files_present() -> None:
    """When both setup.cfg and setup.py exist, license resolution runs once."""
    cfg = "[metadata]\nname = cfg-pkg\nversion = 1.0\nlicense = MIT\n"
    py = "from setuptools import setup\nsetup(name='py-pkg', version='2.0')\n"
    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "setup.cfg").write_text(cfg)
        (tmp_path / "setup.py").write_text(py)
        (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")
        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ) as mock_detect:
            metadata, _ = read_setuptools(tmp_path)
    assert metadata.license_concluded == "MIT"
    assert mock_detect.call_count == 1


def test_fixture_detect_backend() -> None:
    """Fixture project declares setuptools as build backend."""
    assert detect_build_backend(SETUPTOOLS_FIXTURE) == "setuptools"


def test_fixture_read_setup_cfg_name_and_version() -> None:
    """Fixture setup.cfg name and version match expected values."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.name == "sampleproject_setuptools"
    assert metadata.version == "0.1.0"


def test_fixture_read_setup_cfg_description() -> None:
    """Fixture description contains the word 'sample project'."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.description is not None
    assert "sample project" in metadata.description.lower()


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
    assert config.creators == [Creator(name="Pitloom CI", email="ci@loom.example")]


def test_fixture_read_setup_cfg_readme_content() -> None:
    """long_description = file: README.md is resolved to file content."""
    metadata, _ = read_setup_cfg(SETUPTOOLS_FIXTURE)
    assert metadata.readme is not None
    assert "sampleproject-setuptools" in metadata.readme


def test_fixture_read_setuptools_merges_cfg_and_py() -> None:
    """read_setuptools() falls back gracefully when setup.py has no literals."""
    metadata, config = read_setuptools(SETUPTOOLS_FIXTURE)
    assert metadata.name == "sampleproject_setuptools"
    assert metadata.version == "0.1.0"
    assert config.sbom_basename == "sbom"
