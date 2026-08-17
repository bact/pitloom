# ruff: noqa: F403, F405
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble import (
    generate_env_sbom,
)

from .conftest import *


def test_generate_env_sbom_mocked_pipdeptree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_env_sbom() wires read_environment()'s pipdeptree tree
    into a valid SPDX 3 JSON-LD document containing the installed package."""
    monkeypatch.chdir(tmp_path)
    tree = [
        {
            "package": {
                "key": "requests",
                "package_name": "requests",
                "installed_version": "2.31.0",
            }
        }
    ]
    fake_result = subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )

    with patch("subprocess.run", return_value=fake_result):
        sbom_json = generate_env_sbom()

    data = json.loads(sbom_json)

    assert "@graph" in data
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    requests_pkg = next(p for p in packages if p["name"] == "requests")
    assert requests_pkg["software_packageVersion"] == "2.31.0"
