# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI fragment command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
VALID_FRAGMENT = FIXTURE_DIR / "fragments" / "dataset-fragment.spdx3.json"


@pytest.mark.pypi_network
def test_fragment_validate_command_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A valid SPDX 3 document exits 0 and reports success on stdout.

    Needs a live socket: spdx3-validate fetches its JSON Schema from
    schema_url rather than shipping it bundled.
    """
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "validate", str(VALID_FRAGMENT)]
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert "pitloom fragment validate: 1 document(s) valid" in captured.out


def test_fragment_validate_command_invalid_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An invalid SPDX 3 document exits 1 and prints each finding as its
    own ERROR: line."""
    doc_path = tmp_path / "bad.spdx3.json"
    doc_path.write_text('{"@graph": []}', encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["loom", "fragment", "validate", str(doc_path)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    for line in captured.err.splitlines():
        assert line.startswith("ERROR: ")


def test_fragment_validate_command_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test fragment validate fails gracefully when a path is missing."""
    missing_path = tmp_path / "missing.spdx3.json"

    monkeypatch.setattr("sys.argv", ["loom", "fragment", "validate", str(missing_path)])
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert f"ERROR: file not found: {missing_path}" in captured.err


def test_fragment_validate_command_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test fragment validate reports a clear ERROR when the optional
    'spdx3-validate' dependency isn't installed."""
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "validate", str(VALID_FRAGMENT)]
    )
    with patch.dict("sys.modules", {"spdx3_validate": None}):
        result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert "ERROR: the 'spdx3-validate' package is required" in captured.err
    assert 'pip install "pitloom[validate]"' in captured.err


@pytest.mark.pypi_network
def test_fragment_validate_command_no_merge_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--no-merge is passed through as check_merged=False.

    Needs a live socket: spdx3-validate fetches its JSON Schema from
    schema_url rather than shipping it bundled.
    """
    monkeypatch.setattr(
        "sys.argv",
        ["loom", "fragment", "validate", str(VALID_FRAGMENT), "--no-merge"],
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert "pitloom fragment validate: 1 document(s) valid" in captured.out
