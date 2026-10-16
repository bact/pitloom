# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by the two in-tree surfaces test modules.

See also: test_surfaces_in_tree_registry.py,
test_surfaces_in_tree_registry_archive.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.id_registry import IdRegistry

_NEEDLE = "is inside the project's file set; left out of it"


def _in_tree_registry(tmp_path: Path) -> Path:
    """An existing, empty registry in the demo project's package."""
    path = tmp_path / "proj" / "demo" / "reg.json"
    path.parent.mkdir(parents=True)
    IdRegistry.new("demo").save(path)
    return path


def _left_out_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if _NEEDLE in r.getMessage()]
