# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the file reads and warning shapes of
:mod:`pitloom.extract.lock.requirements`.

See also: tests/extract/lock/test_requirements.py (extraction correctness).
"""

import logging
import sys
from pathlib import Path

import pytest

from pitloom.extract._extract_utils import FETCH_MAX_BYTES
from pitloom.extract.lock import requirements
from pitloom.extract.lock.requirements import extract_pinned_requirements_dependencies
from pitloom.logging_config import CODE_ATTR


def _write_requirements(project_dir: Path, text: str) -> None:
    (project_dir / "requirements.txt").write_text(text, encoding="utf-8")


def test_directory_named_requirements_txt_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "requirements.txt").mkdir()

    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None

    assert "not a regular file" in caplog.text


def test_unreadable_file_returns_none_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_requirements(tmp_path, "requests==2.31.0\n")

    def _denied(path: Path) -> bytes:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(requirements, "read_lock_bytes", _denied)
    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None

    (record,) = caplog.records
    assert record.getMessage() == (
        "FILE=requirements.txt: could not read for dependency pins; Permission denied"
    )
    assert getattr(record, CODE_ATTR) == "file-unreadable"


def test_requirements_file_over_the_size_cap_is_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with (tmp_path / "requirements.txt").open("wb") as handle:
        handle.truncate(FETCH_MAX_BYTES + 1)

    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None

    assert f"over {FETCH_MAX_BYTES} bytes" in caplog.text


@pytest.mark.parametrize(
    "line",
    ["foo==1.0 bar\n", "foo==1.0 bar\x1b[31m\n"],
    ids=["plain", "control-character"],
)
def test_malformed_requirement_warning_is_one_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, line: str
) -> None:
    """packaging's message echoes the source line and a caret line: only its
    first line, escaped, reaches the log."""
    _write_requirements(tmp_path, line)

    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(tmp_path) is None

    (message,) = caplog.messages
    assert "malformed requirement line" in message
    assert message.isprintable()  # no newline, caret line or raw ESC
    assert "foo==1.0 bar" not in message


def test_arbitrary_equality_pins_agree_only_on_the_exact_string(
    tmp_path: Path,
) -> None:
    """``foo===1.0`` matches the string ``1.0`` only, not ``1.0.0``."""
    _write_requirements(tmp_path, "foo===1.0\nfoo===1.0.0\n")

    assert extract_pinned_requirements_dependencies(tmp_path) is None


@pytest.mark.skipif(sys.platform == "win32", reason="a newline is not valid in a name")
def test_a_path_with_a_newline_cannot_split_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = tmp_path / "a\nWARNING: forged"
    project.mkdir()
    _write_requirements(project, "foo\n")

    with caplog.at_level(logging.WARNING):
        assert extract_pinned_requirements_dependencies(project) is None

    assert caplog.records and all("\n" not in m for m in caplog.messages)
