# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.py`` and ``setup.cfg`` input that must not crash the read, flood
stderr or forge a log line.

See also: test_setuptools_merge.py (the merge rule, value types).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom.extract.project.setuptools import read_setuptools
from tests.extract.project.test_setuptools_merge import write_project

#: A file name cannot hold a newline on Windows.
_NO_NEWLINE_NAMES = sys.platform == "win32"


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def test_a_long_unread_value_is_cut_in_the_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_project(tmp_path, "[metadata]\nname = c\n", "license=['" + "x" * 5000 + "']")
    caplog.set_level(logging.WARNING)
    assert read_setuptools(tmp_path)[0].license_name is None
    (message,) = _messages(caplog)
    assert "Pitloom does not read" in message
    assert len(message) < 500


@pytest.mark.parametrize(
    ("py", "named"),
    [
        ("name='p', packages=find_packages(), version=V, cmdclass=C", "'version'"),
        # the keywords it holds are unknown, so it may hold one Pitloom reads
        ("name='p', **META", "'**META'"),
        # an expression is never unparsed: that recurses
        ("name='p', **" + "+".join(["a"] * 1500), "'**...'"),
    ],
    ids=["not-literal", "unpacking", "unpacking-expression"],
)
def test_only_a_keyword_pitloom_may_read_warns_when_not_literal(
    py: str, named: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_project(tmp_path, None, py)
    caplog.set_level(logging.WARNING)
    read_setuptools(tmp_path)
    (message,) = _messages(caplog)
    assert named in message


@pytest.mark.skipif(_NO_NEWLINE_NAMES, reason="no newline in a Windows file name")
@pytest.mark.parametrize(
    "py",
    ["setup(name='p', version='2')\n", "setup(\n"],
    ids=["conflict", "unparseable"],
)
def test_a_project_directory_name_cannot_forge_a_log_line(
    py: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = tmp_path / "x\nINFO: forged"
    project.mkdir()
    write_project(project, "[metadata]\nname = p\nversion = 1\n", None)
    (project / "setup.py").write_bytes(py.encode())
    caplog.set_level(logging.WARNING)
    read_setuptools(project)
    (message,) = _messages(caplog)
    assert "\n" not in message
    assert "forged" in message
