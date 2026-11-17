# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A lock warning names the lock by its file name, never its project
directory: one line, whatever the directory is called."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock.cascade import apply_locked_dependencies
from pitloom.extract.lock.pylock import extract_pylock_dependencies
from pitloom.extract.lock.uv import extract_uv_lock_dependencies
from tests._code_records import coded, has_parts

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="a Windows directory name cannot hold a newline"
)

_PYLOCK = 'lock-version = "1.0"\n'
_UV = (
    'version = 1\n[[package]]\nname = "demo"\nversion = "1.0"\n'
    'source = { editable = "." }\ndependencies = 5\n'
)


@pytest.fixture(name="nasty_dir")
def _nasty_dir(tmp_path: Path) -> Path:
    path = tmp_path / "a\nINFO: forged"
    path.mkdir()
    return path


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [line for r in caplog.records for line in r.getMessage().split("\n")]


@pytest.mark.parametrize(
    "pylock",
    [_PYLOCK + "packages = []\n", _PYLOCK + 'created-by = "t"\n'],
    ids=["no-created-by", "no-packages"],
)
def test_pylock_warnings(
    caplog: pytest.LogCaptureFixture, nasty_dir: Path, pylock: str
) -> None:
    (nasty_dir / "pylock.toml").write_text(pylock, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert extract_pylock_dependencies(nasty_dir) is None
    [(code, text)] = coded(caplog)
    assert code == "lock-file-malformed" and len(_lines(caplog)) == 1
    assert has_parts(text, "FILE=pylock.toml") and "forged" not in caplog.text


def test_uv_warning(caplog: pytest.LogCaptureFixture, nasty_dir: Path) -> None:
    (nasty_dir / "uv.lock").write_text(_UV, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert extract_uv_lock_dependencies(nasty_dir, "demo") is None
    [(code, text)] = coded(caplog)
    assert code == "lock-file-malformed" and len(_lines(caplog)) == 1
    assert has_parts(text, "FILE=uv.lock") and "forged" not in caplog.text


def test_cascade_warnings(caplog: pytest.LogCaptureFixture, nasty_dir: Path) -> None:
    (nasty_dir / "pylock.toml").write_text(
        _PYLOCK + 'created-by = "t"\n[[packages]]\nname = "a"\nversion = "1"\n',
        encoding="utf-8",
    )
    metadata = ProjectMetadata(
        name="pkg",
        locked_dependencies=["b==1"],
        provenance={"locked_dependencies": "Source: poetry.lock | Method: x"},
    )
    with caplog.at_level(logging.WARNING):
        apply_locked_dependencies(metadata, nasty_dir)
    [(code, text)] = coded(caplog)
    assert code == "lock-file-conflict" and len(_lines(caplog)) == 1
    assert "forged" not in text
