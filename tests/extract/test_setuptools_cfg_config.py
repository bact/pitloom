# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for [tool:pitloom] configuration parsing from setup.cfg.

See also:
- :mod:`tests.extract.test_setuptools_cfg` for core metadata extraction from setup.cfg.
- :mod:`tests.extract.test_setuptools_py` for setup.py extraction.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.creation import Creator
from pitloom.extract._setuptools import read_setup_cfg


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
    """``[tool:pitloom:creation] no-creation-tool = true`` maps to ``tools == []``."""
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
    """``no-creation-tool = true`` forces ``tools == []`` even with creation-tool."""
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


def test_read_setup_cfg_no_creation_tool_unrecognized_value_ignored() -> None:
    """An unrecognized ``no-creation-tool`` value (``_bool_val`` returns
    ``None``) leaves the ``creation`` block untouched instead of being
    coerced into a boolean."""
    content = """
[metadata]
name = pkg
version = 1.0

[tool:pitloom]
no-creation-tool = maybe
"""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.tools is None


def test_read_setup_cfg_no_pitloom_section_returns_defaults() -> None:
    """Returns default PitloomConfig when [tool:pitloom] is absent."""
    content = "[metadata]\nname = pkg\nversion = 1.0\n"
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "setup.cfg").write_text(content)
        _, config = read_setup_cfg(Path(d))
    assert config.pretty is False
    assert config.sbom_basename is None
    assert not config.fragments
