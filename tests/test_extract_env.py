# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.env.read_environment()."""

import json
import subprocess
from unittest.mock import patch

from pitloom.extract.env import read_environment


def _fake_pipdeptree_result(tree: list) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )


def test_read_environment_provenance_distinguishes_synthetic_from_tool() -> None:
    """name/version are Pitloom's own synthetic root, not something
    pipdeptree reported -- only dependencies is genuinely sourced from it."""
    tree = [{"package": {"key": "requests", "package_name": "requests"}}]
    with patch("subprocess.run", return_value=_fake_pipdeptree_result(tree)):
        metadata, returned_tree = read_environment()

    assert metadata.name == "deployed-environment"
    assert returned_tree == tree
    assert "pipdeptree" not in metadata.provenance["name"]
    assert "Pitloom generator" in metadata.provenance["name"]
    assert "pipdeptree" not in metadata.provenance["version"]
    assert metadata.provenance["dependencies"] == "Source: pipdeptree"


def test_read_environment_pipdeptree_missing_raises() -> None:
    """A missing pipdeptree executable surfaces as a clear RuntimeError."""
    with patch("subprocess.run", side_effect=FileNotFoundError("pipdeptree")):
        try:
            read_environment()
        except RuntimeError as exc:
            assert "pipdeptree" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
