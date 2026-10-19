# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by test_loom_dataset_sources.py and
test_loom_dataset_sources_rules.py: a project directory, source files, a run
and readers of the fragment it writes.

See also: test_loom_dataset_sources.py, test_loom_dataset_sources_rules.py.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.core.license_individuals import INDIVIDUAL_BY_REFERENCE

Graph = list[dict[str, Any]]

EXPRESSION = "simplelicensing_LicenseExpression"
TEXT = "simplelicensing_SimpleLicensingText"
LINK = "https://example.org/terms"


def enter_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project directory holding ``t.txt``, entered; no calling
    script captured."""
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    (root / "t.txt").write_bytes(b"data\n")
    return root


def croissant_file(path: Path, **fields: object) -> Path:
    """A Croissant file at *path* named ``from-croissant``, with *fields*."""
    path.write_text(json.dumps({"name": "from-croissant", **fields}), "utf-8")
    return path


def dir_dataset(path: Path, frontmatter: str | None) -> Path:
    """A directory dataset at *path*, with a card holding *frontmatter*."""
    path.mkdir()
    (path / "a.txt").write_bytes(b"a\n")
    if frontmatter is not None:
        (path / "README.md").write_text(f"---\n{frontmatter}---\n# Card\n", "utf-8")
    return path


def run_graph(output: Path, body: Callable[[], None]) -> Graph:
    """The ``@graph`` of the fragment a run calling *body* writes."""
    with loom.run(output):
        body()
    graph: Graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return graph


def package_of(graph: Graph, name: str) -> dict[str, Any]:
    """The one dataset package named *name*."""
    (found,) = [
        e for e in graph if e["type"] == "dataset_DatasetPackage" and e["name"] == name
    ]
    return found


def declared(graph: Graph, name: str) -> list[tuple[str, str]]:
    """``(licence type, value)`` of each ``hasDeclaredLicense`` from the
    dataset *name*; an individual as ``("individual", its SPDX name)``."""
    package_id = package_of(graph, name)["spdxId"]
    by_id = {e.get("spdxId"): e for e in graph}
    out: list[tuple[str, str]] = []
    for rel in graph:
        if (
            rel.get("relationshipType") != "hasDeclaredLicense"
            or rel["from"] != package_id
        ):
            continue
        for target in rel["to"]:
            if target in INDIVIDUAL_BY_REFERENCE:
                out.append(("individual", INDIVIDUAL_BY_REFERENCE[target].spdx_name))
                continue
            element = by_id[target]
            value = element.get("simplelicensing_licenseExpression") or element.get(
                "simplelicensing_licenseText"
            )
            out.append((str(element["type"]), str(value)))
    return out


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The messages of the ``WARNING:`` and worse records."""
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
