# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by test_registry_generate.py and test_registry_generate_paths.py.

See also: test_registry_generate.py, test_registry_generate_paths.py.
"""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

from pathlib import Path


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"print(1)\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_bytes(b"hello\n")
    return tmp_path
