# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``generate_merged_sbom()``, the library half of ``loom merge``: its input
errors, and the document envelope's id and ``created`` when a fragment
gives nothing to go by.

See also: tests/cli/test_cli_merge.py (the envelope through the CLI).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_merged_sbom, generate_project_sbom
from pitloom.id_registry import sha256_file
from tests._license_graph import fragment_graph, write_fragment
from tests.assemble.embed_surfaces_shared import demo_project


def _document(graph: list[dict[str, Any]]) -> dict[str, Any]:
    (document,) = [e for e in graph if e["type"] == "SpdxDocument"]
    return document


@pytest.mark.parametrize(
    ("make", "error", "match"),
    [
        (lambda d: d / "missing", FileNotFoundError, "fragments directory not found"),
        (lambda d: d, ValueError, "no JSON fragment files found"),
    ],
    ids=["missing", "empty"],
)
def test_input_errors(
    tmp_path: Path, make: Any, error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        generate_merged_sbom(make(tmp_path))


def test_no_creation_time_anywhere_is_the_epoch_start(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``created`` is never the current time: with no fragment stating one,
    it is 1970-01-01, said once."""
    write_fragment(
        tmp_path / "f.json",
        {"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []},
    )
    with caplog.at_level(logging.WARNING):
        graph = json.loads(generate_merged_sbom(tmp_path))["@graph"]
    info = next(e for e in graph if e.get("@id") == _document(graph)["creationInfo"])
    assert info["created"] == "1970-01-01T00:00:00Z"
    assert [
        r
        for r in caplog.records
        if "no fragment states a creation time" in r.getMessage()
    ]


def test_unhashable_fragment_counts_by_nothing_in_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fragment that cannot be hashed leaves the document id as if it
    were absent; the merge itself reports any read failure."""
    write_fragment(tmp_path / "a" / "f.json", fragment_graph([]))
    alone = _document(json.loads(generate_merged_sbom(tmp_path / "a"))["@graph"])
    write_fragment(tmp_path / "a" / "g.json", fragment_graph([]))

    def unreadable(path: Path) -> str:
        if path.name == "g.json":
            raise PermissionError(path)
        return sha256_file(path)

    monkeypatch.setattr(
        "pitloom.assemble.spdx3._fragments_envelope.sha256_file", unreadable
    )
    both = _document(json.loads(generate_merged_sbom(tmp_path / "a"))["@graph"])
    assert both["spdxId"] == alone["spdxId"]


def test_file_names_count_in_the_id(tmp_path: Path) -> None:
    """The names decide which equal element survives, so the same two
    fragments under swapped names are a different document."""
    first, second = (fragment_graph([], f"https://spdx.org/spdxdocs/{n}") for n in "xy")
    write_fragment(tmp_path / "1" / "a.json", first)
    write_fragment(tmp_path / "1" / "b.json", second)
    write_fragment(tmp_path / "2" / "a.json", second)
    write_fragment(tmp_path / "2" / "b.json", first)
    ids = {
        _document(json.loads(generate_merged_sbom(tmp_path / d))["@graph"])["spdxId"]
        for d in "12"
    }
    assert len(ids) == 2


def _declaring(profiles: list[str]) -> dict[str, Any]:
    """A fragment whose own document declares *profiles*."""
    ns = "https://spdx.org/spdxdocs/declaring"
    return fragment_graph(
        [
            {
                "type": "SpdxDocument",
                "spdxId": ns,
                "rootElement": [f"{ns}#P"],
                "profileConformance": profiles,
            },
            {"type": "software_Package", "spdxId": f"{ns}#P", "name": "p"},
        ],
        ns,
    )


@pytest.mark.parametrize("surface", ["merge", "project"])
def test_fragment_declared_profiles_are_kept(surface: str, tmp_path: Path) -> None:
    """What a fragment's own document declares stays declared, after the
    known profiles, in one order, on ``loom merge`` and on a project."""
    fragment = _declaring(["security", "core", "build"])
    if surface == "merge":
        write_fragment(tmp_path / "f.json", fragment)
        sbom = generate_merged_sbom(tmp_path)
    else:
        toml = '\n[tool.pitloom.fragment]\nfiles = ["f.json"]\n'
        project = demo_project(tmp_path, toml)
        write_fragment(project / "f.json", fragment)
        sbom = generate_project_sbom(project, offline=True)
    profiles = _document(json.loads(sbom)["@graph"])["profileConformance"]
    assert profiles[:2] == ["core", "software"]
    assert profiles[-2:] == ["build", "security"]
    assert len(profiles) == len(set(profiles))
