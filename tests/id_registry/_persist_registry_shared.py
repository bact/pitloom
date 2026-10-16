# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by test_persist_registry.py and test_persist_registry_save.py.

See also: test_persist_registry.py, test_persist_registry_save.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.id_registry import (
    FILE_TYPE,
)
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/test-1"


def _messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


def _registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "reg.json"
    make_registry({(FILE_TYPE, "x.py"): (f"{_NS}#File-1", "f" * 64)}, path=path)
    return path
