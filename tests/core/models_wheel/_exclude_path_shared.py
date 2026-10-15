# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by test_models_wheel_exclude_path*.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.walk_rules import REGISTRY_IN_FILE_SET_WARNING


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[str]:
    needle = REGISTRY_IN_FILE_SET_WARNING.split("%s")[1]
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


def write_file(root: Path, name: str, data: bytes | None) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        path.mkdir()
    else:
        path.write_bytes(data)
    return path


REG = b'{"files": {}}\n'
