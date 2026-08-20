# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom [tool.pitloom] config-reading: provenance settings
edge cases, multiple creators/tools, moved/renamed keys, and
creation-tool validation.

See also: tests/core/test_metadata.py for basic pyproject.toml metadata
extraction and Creator/Tool construction. tests/core/test_metadata_edge_cases.py
for malformed creator/tool shapes, dependency-name canonicalization, and
license_concluded (G2) tests.
"""

import tempfile
from pathlib import Path

import pytest

from pitloom.core.creation import Creator, Tool
from pitloom.extract._pyproject import read_pyproject


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


def test_extract_pitloom_provenance_detail_invalid_value_raises() -> None:
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.provenance]
detail = "verbose"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="detail"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_provenance_preserve_invalid_value_raises() -> None:
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.provenance]
preserve-source-metadata = "sometimes"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="preserve-source-metadata"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_provenance_format_invalid_value_raises() -> None:
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.provenance]
format = "not-a-real-format"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="format"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_provenance_case_sensitive_values_rejected() -> None:
    """Validation is intentionally exact-case-only, not case-insensitive --
    "Both"/"ANNOTATION"/"Full" are rejected the same as any other unknown
    value, not silently normalized. Documents that case-sensitivity is a
    deliberate choice, not an oversight."""
    for key, value in (
        ("format", "Both"),
        ("format", "ANNOTATION"),
        ("detail", "Full"),
        ("preserve-source-metadata", "Always"),
    ):
        pyproject_content = f"""
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.provenance]
{key} = "{value}"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            pyproject_path = tmppath / "pyproject.toml"
            pyproject_path.write_text(pyproject_content)

            with pytest.raises(ValueError, match=key):
                read_pyproject(pyproject_path)


def test_extract_pitloom_provenance_not_a_table_raises() -> None:
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
provenance = "annotation"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="provenance"):
            read_pyproject(pyproject_path)


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
        assert config.tools == [Tool(name="Pitloom"), Tool(name="MyWrapper")]


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


def test_extract_pitloom_no_creation_tool_false_boolean_keeps_tools() -> None:
    """``no-creation-tool = false`` (a real TOML boolean) must NOT suppress
    tools -- confirms the type-check fix distinguishes it from the string
    ``"false"`` case below."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.creation]
no-creation-tool = false
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        _, config = read_pyproject(pyproject_path)

        assert config.tools is None


def test_extract_pitloom_no_creation_tool_string_raises() -> None:
    """``no-creation-tool = "false"`` (a quoted string, not a TOML boolean)
    raises -- the non-empty string ``"false"`` is truthy in Python, so
    accepting it would suppress tools opposite to the user's intent."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom.creation]
no-creation-tool = "false"
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="must be a boolean"):
            read_pyproject(pyproject_path)


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


@pytest.mark.parametrize(
    "value_toml",
    ["123", '["x"]', "true"],
    ids=["int", "list", "bool"],
)
def test_extract_pitloom_moved_creation_key_non_string_raises(
    value_toml: str,
) -> None:
    """``creator-name`` has no valid form at all directly under
    ``[tool.pitloom]`` -- the new creator schema lives entirely under a
    different key (``[[tool.pitloom.creator]]``). Any value there (int,
    list, bool, ...) is a leftover/typo of the old moved form and must
    raise, not just the ``str`` case."""
    pyproject_content = f"""
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
creator-name = {value_toml}
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        pyproject_path = tmppath / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        with pytest.raises(ValueError, match="has moved to"):
            read_pyproject(pyproject_path)


def test_extract_pitloom_creation_tool_int_top_level_raises() -> None:
    """A non-list, non-string ``creation-tool`` (e.g. an int) directly
    under ``[tool.pitloom]`` is still the old/invalid single-valued form
    and must raise -- only a ``list`` is the valid new array-of-tables
    form."""
    pyproject_content = """
[project]
name = "test-package"
version = "1.0.0"

[tool.pitloom]
creation-tool = 123
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

        assert config.tools == [Tool(name="MyWrapper")]


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
