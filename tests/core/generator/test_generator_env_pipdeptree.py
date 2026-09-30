# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``generate_env_sbom()`` and ``loom env`` against captured real
``pipdeptree`` output, not hand-written mocks.

Hand-written mocks once hid a ``--json`` vs ``--json-tree`` mismatch that
named every package ``unknown``. The fixtures are in
``tests/fixtures/pipdeptree/`` (method: its README).

See also: :mod:`tests.extract.test_env` for the extractor's own tests.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.assemble import generate_env_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, IdRegistry

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "pipdeptree"
_JSON = FIXTURES / "requests-2.34.2.json"
_JSON_TREE = FIXTURES / "requests-2.34.2.json-tree.json"
_CREATED = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")
_EXPECTED_VERSIONS = {
    "certifi": "2026.7.22",
    "charset-normalizer": "3.5.1",
    "idna": "3.20",
    "requests": "2.34.2",
    "urllib3": "2.8.0",
}


def _stub(path: Path) -> Any:
    result = subprocess.CompletedProcess(
        args=["pipdeptree"], returncode=0, stdout=path.read_bytes(), stderr=b""
    )
    return patch("subprocess.run", return_value=result)


def _generate(**kwargs: Any) -> str:
    with _stub(_JSON):
        return generate_env_sbom(offline=True, creation_metadata=_CREATED, **kwargs)


def _packages(sbom_json: str) -> dict[str, dict[str, Any]]:
    graph = json.loads(sbom_json)["@graph"]
    return {
        e["name"]: e
        for e in graph
        if e.get("type") == "software_Package" and e["name"] != "deployed-environment"
    }


def _edges(sbom_json: str) -> set[tuple[str, str]]:
    """``(from name, to name)`` for every dependsOn relationship."""
    graph = json.loads(sbom_json)["@graph"]
    names = {
        e["spdxId"]: e["name"] for e in graph if e.get("type") == "software_Package"
    }
    return {
        (names[e["from"]], names[to])
        for e in graph
        if e.get("type") == "Relationship" and e["relationshipType"] == "dependsOn"
        for to in e["to"]
    }


def test_real_pipdeptree_json_names_versions_and_edges() -> None:
    sbom_json = _generate()

    packages = _packages(sbom_json)
    assert "unknown" not in packages
    assert "unknown" not in {v["software_packageVersion"] for v in packages.values()}
    assert {
        k: v["software_packageVersion"] for k, v in packages.items()
    } == _EXPECTED_VERSIONS
    root = "deployed-environment"
    assert _edges(sbom_json) == {
        (root, "requests"),
        ("requests", "certifi"),
        ("requests", "charset-normalizer"),
        ("requests", "idna"),
        ("requests", "urllib3"),
    }


def test_real_pipdeptree_json_is_deterministic() -> None:
    assert _generate() == _generate()


def test_real_pipdeptree_json_tree_output_is_an_error() -> None:
    """The former ``--json-tree`` shape must fail loudly, not emit a
    document of ``unknown`` packages."""
    with _stub(_JSON_TREE):
        with pytest.raises(RuntimeError, match="Unexpected pipdeptree output"):
            generate_env_sbom(offline=True)


def test_cli_env_malformed_output_is_one_error_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "env", "--offline", "-o", "out.json"])

    with _stub(_JSON_TREE):
        code = __main__.main()

    captured = capsys.readouterr()
    error_lines = [line for line in captured.err.splitlines() if line]
    assert code == 1
    assert len(error_lines) == 1
    assert error_lines[0].startswith("ERROR: ")
    assert "pipdeptree" in error_lines[0]
    assert not (tmp_path / "out.json").exists()


def test_registry_runs_never_claim_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Registry runs over real ``--json`` output claim no ``unknown`` name
    (the old bug's symptom; the argv and live tests catch its cause)."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    IdRegistry.new("env-sync", path=registry_path).save()

    with caplog.at_level(logging.WARNING):
        first = _generate(id_registry=registry_path)
        second = _generate(id_registry=registry_path)

    assert "unknown" not in caplog.text
    assert not caplog.records
    assert first == second
    assert set(_packages(second)) == set(_EXPECTED_VERSIONS)
    reloaded = IdRegistry.load(registry_path)
    registered = {
        name for (kind, name) in reloaded.entities if kind == "software_Package"
    }
    assert registered == {*_EXPECTED_VERSIONS, "deployed-environment"}
