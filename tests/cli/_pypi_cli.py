# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers of the PyPI URL CLI tests: run ``loom`` against the fake
PyPI of ``tests/assemble/_pypi_dists.py`` and check what it wrote to stderr.

See also: tests/cli/test_cli_wheel_pypi_url.py and
tests/cli/test_cli_project_pypi_url.py.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.creation import CreationMetadata
from tests._fake_pypi_server import FakePypi
from tests.assemble._pypi_dists import fake_pypi, publish_demo

#: 2026-11-10T00:00:00Z, the creation time the library side pins.
EPOCH = "1794268800"
#: The creation metadata the CLI resolves with nothing given, so the library
#: call it is compared with gives the same bytes.
CLI_CREATION = CreationMetadata(
    creation_datetime="2026-11-10T00:00:00Z",
    creation_comment="Generated via Pitloom CLI",
)
_TAGGED = re.compile(r"(ERROR|WARNING|INFO): ")


def pinned_fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakePypi]:
    """A fake PyPI publishing ``demo``, with the creation time pinned."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", EPOCH)
    for fake, _temp in fake_pypi(monkeypatch, tmp_path):
        publish_demo(fake)
        yield fake


def run(monkeypatch: pytest.MonkeyPatch, cwd: Path, *argv: str) -> int:
    """``loom *argv`` in *cwd*; its exit status."""
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return __main__.main()


def assert_clean_stderr(err: str) -> None:
    """Every stderr line starts with exactly one level tag, and nothing
    names the temporary download directory."""
    assert "pitloom-pypi-" not in err
    for line in err.splitlines():
        assert _TAGGED.match(line), line
        assert not _TAGGED.match(line[line.index(": ") + 2 :]), line
