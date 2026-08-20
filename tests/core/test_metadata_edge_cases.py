# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for malformed [[tool.pitloom.creator]]/[[tool.pitloom.creation-tool]]
shapes, dependency-name canonicalization, and license_concluded
(G2: declared-vs-detected disagreement).

See also: tests/core/test_metadata.py for basic pyproject.toml metadata
extraction and Creator/Tool construction. tests/core/test_metadata_pitloom_creators.py
for provenance settings edge cases, multiple creators/tools, and
moved/renamed key validation.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._pyproject import read_pyproject


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


def test_extract_pitloom_creator_type_wrong_pytype_raises() -> None:
    """A ``[[tool.pitloom.creator]]`` entry with a non-string ``type``
    (e.g. an int) raises ValueError instead of silently falling back to
    the default ``"person"`` type."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creator]]
name = "Alice"
type = 123
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="'type' must be a string"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creator_email_wrong_pytype_raises() -> None:
    """A ``[[tool.pitloom.creator]]`` entry with a non-string ``email``
    (e.g. an int) raises ValueError instead of silently becoming ``None``."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[[tool.pitloom.creator]]
name = "Alice"
email = 123
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="'email' must be a string"):
            read_pyproject(pyproject_path)


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
    silently treated as absent.

    Caught by ``_check_moved_creation_keys`` (any non-list ``creation-tool``
    is the old single-valued form) before ``_read_tools`` ever runs."""
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

        with pytest.raises(ValueError, match="has moved to"):
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


# ---------------------------------------------------------------------------
# license_concluded (G2: declared-vs-detected disagreement)
# ---------------------------------------------------------------------------


def _write_pyproject(tmppath: Path, license_line: str = 'license = "MIT"\n') -> Path:
    pyproject_content = f"""
[project]
name = "test-package"
version = "1.0.0"
{license_line}"""
    pyproject_path = tmppath / "pyproject.toml"
    pyproject_path.write_text(pyproject_content)
    return pyproject_path


def test_license_concluded_populated_on_conflict() -> None:
    """A declared MIT license and an independently-detected Apache-2.0
    LICENSE file both surface -- declared value untouched, concluded value
    is the independent detection, disagreement visible to the caller."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = _write_pyproject(tmppath)
        (tmppath / "LICENSE").write_text("Apache License\nVersion 2.0" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            metadata, _ = read_pyproject(pyproject_path)

        assert metadata.license_name == "MIT"
        assert metadata.license_concluded == "Apache-2.0"
        assert metadata.provenance["license"] == (
            "Source: pyproject.toml | Field: project.license"
        )
        concluded_prov = metadata.provenance["license_concluded"]
        assert "LICENSE" in concluded_prov
        assert "Method: licenseid_detection" in concluded_prov
        assert "Tool: licenseid==" in concluded_prov


def test_license_concluded_matches_declared_no_conflict() -> None:
    """Declared and independently-detected agree -- concluded is still
    populated (needed to build the second native relationship), just equal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = _write_pyproject(tmppath)
        (tmppath / "LICENSE").write_text("MIT License\n\nPermission" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            metadata, _ = read_pyproject(pyproject_path)

        assert metadata.license_name == "MIT"
        assert metadata.license_concluded == "MIT"


def test_license_concluded_none_when_no_license_file() -> None:
    """Declared value present, nothing in the directory to independently
    detect from -- concluded stays unset, single-relationship path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = _write_pyproject(tmppath)

        metadata, _ = read_pyproject(pyproject_path)

        assert metadata.license_name == "MIT"
        assert metadata.license_concluded is None
        assert "license_concluded" not in metadata.provenance


def test_license_concluded_none_when_nothing_declared() -> None:
    """No project.license field at all -- G2's independent-scan gate never
    fires (license_name itself already comes from pure detection in this
    case, existing pre-G2 behavior, unaffected)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = _write_pyproject(tmppath, license_line="")
        (tmppath / "LICENSE").write_text("MIT License\n\nPermission" + "x" * 200)

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            metadata, _ = read_pyproject(pyproject_path)

        assert metadata.license_name == "MIT"
        assert metadata.license_concluded is None
