# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A name too long for the file system names nothing: ``input-not-found``
on every route, on every OS and Python (``ENAMETOOLONG`` on POSIX, which
``Path.exists()`` raises before Python 3.14; ``WinError 206`` on Windows).
A whole path past PATH_MAX whose names all exist is not missing.

See also: tests/core/test_path_probe.py.
"""

from __future__ import annotations

import errno
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import (
    enrich_model,
    generate,
    generate_merged_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core._models_wheel_unlistable import warn_unlistable_dirs
from pitloom.core.path_probe import is_missing_errno
from pitloom.embed import embed_wheel_sbom
from pitloom.messages import CodedFileNotFoundError, code_of

pytestmark = pytest.mark.platform

_LONG = "x" * 300
_POSIX = os.name != "nt"


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


@pytest.mark.parametrize(
    ("entry", "name"),
    [
        (generate_wheel_sbom, _LONG + "-1-py3-none-any.whl"),
        (embed_wheel_sbom, _LONG + "-1-py3-none-any.whl"),
        (generate_model_sbom, _LONG + ".gguf"),
        (enrich_model, _LONG + ".gguf"),
        (generate_project_sbom, _LONG),
        (generate_project_sbom, _LONG + ".tar.gz"),
        (generate, _LONG),
        (generate, _LONG + ".tar.gz"),
        (generate_merged_sbom, _LONG),
    ],
    ids=[
        "wheel",
        "embed",
        "model",
        "enrich",
        "project",
        "project-sdist",
        "generate",
        "generate-sdist",
        "merged",
    ],
)
def test_library_long_name_is_not_found(
    entry: Callable[..., Any],
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CodedFileNotFoundError) as caught:
        entry(name, output_path=tmp_path / "out.json")
    assert code_of(caught.value) == "input-not-found"
    assert not list(tmp_path.iterdir())


def test_the_system_says_too_long_as_missing(tmp_path: Path) -> None:
    """The system's own answer, read without ``Path.exists()`` (which
    swallows it on Python 3.14): the probe counts it as missing."""
    with pytest.raises(OSError) as caught:
        os.stat(tmp_path / _LONG)
    assert is_missing_errno(caught.value)


@pytest.mark.parametrize(
    ("filename", "missing"),
    [
        (os.path.join("a", _LONG, "b"), True),
        ("n" * 255, False),
        ("n" * 256, True),
        ("\u00e9" * 128, True),
        (os.path.join(*["d" * 200] * 30), False),
        (None, False),
    ],
    ids=["long-name", "name-max", "past-max", "long-in-bytes", "long-path", "no-name"],
)
def test_enametoolong_is_missing_only_for_a_long_name(
    filename: str | None, missing: bool
) -> None:
    exc = OSError(errno.ENAMETOOLONG, "File name too long", filename)
    assert is_missing_errno(exc) is missing


@pytest.mark.skipif(not _POSIX, reason="ENAMETOOLONG past PATH_MAX is POSIX")
def test_a_path_past_path_max_is_still_warned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An existing directory chain longer than PATH_MAX (4096 on Linux,
    1024 on macOS), every name short: a scan warns it, never drops it."""
    monkeypatch.chdir(tmp_path)
    name = "d" * 100
    try:
        for _ in range(46):
            os.mkdir(name)
            os.chdir(name)
    except OSError:
        pytest.skip("the file system refused the deep chain")
    deep = os.path.join(str(tmp_path), *[name] * 46)
    with pytest.raises(OSError) as caught:
        os.stat(deep)
    assert caught.value.errno == errno.ENAMETOOLONG
    os.chdir(tmp_path)
    caplog.set_level(logging.WARNING, logger="pitloom")
    with warn_unlistable_dirs(tmp_path):
        with pytest.raises(OSError):
            os.scandir(deep)
    codes = [getattr(r, "pitloom_code", None) for r in caplog.records]
    assert codes == ["dir-unlistable"]
