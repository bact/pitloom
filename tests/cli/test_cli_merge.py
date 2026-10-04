# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pitloom CLI merge command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from tests._license_graph import (
    fragment_graph,
    license_node,
    license_targets,
    license_values,
    licensed_package,
    write_fragment,
)
from tests._network import assert_spdx3_validate_ok
from tests.assemble.embed_surfaces_shared import run_cli


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
    # The SBOM is all of stdout: no PITLOOM_SBOM_OUTPUT_PATH= line after it.
    assert "@graph" in json.loads(captured.out)
    assert "INFO: merge: merged 1 fragment(s)" in captured.err.splitlines()


_NS = "https://spdx.org/spdxdocs/"


def _document(name: str, created: str) -> dict[str, Any]:
    """Fragment document *name*: an ``SpdxDocument`` rooted at its package,
    which declares the expression ``MIT``."""
    ns = _NS + name
    document = fragment_graph(
        [
            {"type": "SpdxDocument", "spdxId": ns, "rootElement": [f"{ns}#P"]},
            license_node(f"{ns}#L", "expression", "MIT"),
            *licensed_package("P", f"{ns}#L", ns),
        ],
        ns,
    )
    document["@graph"][0]["created"] = created
    return document


def _merge(tmp_path: Path, names: list[str], monkeypatch: pytest.MonkeyPatch) -> str:
    """``loom merge`` of the fragment documents *names*, written in that
    order to a directory under *tmp_path*; the output bytes."""
    created = {"b": "2026-02-01T00:00:00Z", "a": "2026-01-01T00:00:00Z"}
    fragments_dir = tmp_path / "in"
    fragments_dir.mkdir(parents=True)
    for name in names:
        write_fragment(fragments_dir / f"{name}.json", _document(name, created[name]))
    out = tmp_path / "out.spdx3.json"
    run_cli(["merge", str(fragments_dir), "-o", str(out)], monkeypatch)
    return out.read_text(encoding="utf-8")


def test_merge_output_is_one_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = json.loads(_merge(tmp_path, ["a", "b"], monkeypatch))["@graph"]
    (document,) = [e for e in graph if e["type"] == "SpdxDocument"]
    assert document["spdxId"].startswith(_NS + "merged-")
    assert {"core", "software", "simpleLicensing"} <= set(
        document["profileConformance"]
    )
    assert sorted(m["externalSpdxId"] for m in document["import"]) == [
        _NS + "a",
        _NS + "b",
    ]
    assert document["rootElement"] == [_NS + "a#P", _NS + "b#P"]
    (created,) = {
        e["created"] for e in graph if e.get("@id") == document["creationInfo"]
    }
    assert created == "2026-02-01T00:00:00Z"  # the latest fragment's
    # The two MIT expressions are one, "a" (the earlier name) kept.
    assert license_values(graph) == {_NS + "a#L": "MIT"}
    assert license_targets(graph) == ["MIT", "MIT"]


def test_merge_output_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same fragments give the same bytes, whatever the directory or the
    order the files were written in."""
    first = _merge(tmp_path / "1", ["a", "b"], monkeypatch)
    assert first == _merge(tmp_path / "other" / "2", ["b", "a"], monkeypatch)


def test_merge_created_follows_source_date_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    graph = json.loads(_merge(tmp_path, ["a", "b"], monkeypatch))["@graph"]
    (document,) = [e for e in graph if e["type"] == "SpdxDocument"]
    info = next(e for e in graph if e.get("@id") == document["creationInfo"])
    assert info["created"] == "2026-01-01T00:00:00Z"


@pytest.mark.network
def test_merge_output_passes_spdx3_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _merge(tmp_path, ["a", "b"], monkeypatch)
    assert_spdx3_validate_ok(tmp_path / "out.spdx3.json")
