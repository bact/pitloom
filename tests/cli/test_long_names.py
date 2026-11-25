# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A name too long for the file system names nothing: ``input-not-found``
on every route, on every OS and Python (``ENAMETOOLONG`` on POSIX, which
``Path.exists()`` raises before Python 3.14; ``WinError 206`` on Windows).

See also: tests/core/test_path_probe.py.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.path_probe import is_missing_errno

pytestmark = pytest.mark.platform

_LONG = "x" * 300


@pytest.mark.parametrize(
    "argv",
    [
        ["model", _LONG + ".gguf"],
        ["enrich", _LONG + ".gguf"],
        ["wheel", _LONG + "-1-py3-none-any.whl"],
        ["project", _LONG],
        ["merge", _LONG],
        ["fragment", "validate", _LONG + ".json"],
    ],
    ids=lambda argv: argv[0] if argv[0] != "fragment" else "fragment validate",
)
def test_long_name_is_not_found(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    (error,) = [ln for ln in capsys.readouterr().err.splitlines() if "ERROR" in ln]
    assert error.endswith("[input-not-found]")
    assert not list(tmp_path.iterdir())


def test_the_system_says_too_long_as_missing(tmp_path: Path) -> None:
    """The system's own answer, read without ``Path.exists()`` (which
    swallows it on Python 3.14): the probe counts it as missing."""
    with pytest.raises(OSError) as caught:
        os.stat(tmp_path / _LONG)
    assert is_missing_errno(caught.value)


def test_enametoolong_is_missing() -> None:
    assert is_missing_errno(OSError(errno.ENAMETOOLONG, "File name too long"))
