# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI merge command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom import __main__


def test_merge_command_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test successful merging of fragment JSON files."""
    fragments_dir = tmp_path / "fragments"
    fragments_dir.mkdir()

    # Create dummy fragment files
    frag1_content = (
        '{"@graph": [{"@id": "urn:uuid:frag1", "type": "SoftwareAgent", '
        '"name": "Agent1", "creationInfo": "_:ci"}, {"@id": "_:ci", '
        '"type": "CreationInfo", "specVersion": "3.0.1", '
        '"created": "2023-01-01T00:00:00Z", "createdBy": ["urn:uuid:frag1"]}]}'
    )
    frag2_content = (
        '{"@graph": [{"@id": "urn:uuid:frag2", "type": "SoftwareAgent", '
        '"name": "Agent2", "creationInfo": "_:ci2"}, {"@id": "_:ci2", '
        '"type": "CreationInfo", "specVersion": "3.0.1", '
        '"created": "2023-01-01T00:00:00Z", "createdBy": ["urn:uuid:frag2"]}]}'
    )
    (fragments_dir / "frag1.json").write_text(frag1_content, encoding="utf-8")
    (fragments_dir / "frag2.json").write_text(frag2_content, encoding="utf-8")

    out_file = tmp_path / "merged.spdx3.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "merge",
            str(fragments_dir),
            "--output",
            str(out_file),
            "--pretty",
        ],
    )
    result = __main__.main()
    assert result == 0
    assert out_file.exists()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "@graph" in data
    # Basic structural check (Spdx3JsonExporter logic is tested elsewhere,
    # we just need to ensure the merge was called and output produced).


def test_merge_command_fragments_dir_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test merge fails gracefully when fragments_dir is missing."""
    fragments_dir = tmp_path / "nonexistent"

    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "merge",
            str(fragments_dir),
        ],
    )
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert "ERROR: fragments directory not found" in captured.err


def test_merge_command_no_json_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test merge fails gracefully when fragments_dir has no JSON files."""
    fragments_dir = tmp_path / "empty"
    fragments_dir.mkdir()

    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "merge",
            str(fragments_dir),
        ],
    )
    result = __main__.main()
    assert result == 1

    captured = capsys.readouterr()
    assert "ERROR: no JSON fragment files found" in captured.err


def test_merge_command_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test merge writes to stdout when output is '-'."""
    fragments_dir = tmp_path / "fragments"
    fragments_dir.mkdir()
    frag1_content = (
        '{"@graph": [{"@id": "urn:uuid:frag1", "type": "SoftwareAgent", '
        '"name": "Agent", "creationInfo": "_:ci"}, {"@id": "_:ci", '
        '"type": "CreationInfo", "specVersion": "3.0.1", '
        '"created": "2023-01-01T00:00:00Z", "createdBy": ["urn:uuid:frag1"]}]}'
    )
    (fragments_dir / "frag1.json").write_text(frag1_content, encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "merge",
            str(fragments_dir),
            "--output",
            "-",
        ],
    )
    result = __main__.main()
    assert result == 0

    captured = capsys.readouterr()
    assert '"@graph":' in captured.out
