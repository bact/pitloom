# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.cfg``'s ``file:`` directive: several files joined as setuptools
does, and a file that cannot be read left out with one ``WARNING:`` instead
of ending the read; the same for a ``version`` file.

See also: :mod:`tests.extract.project.test_setuptools_cfg`.
"""

from __future__ import annotations

import errno
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.project import read_project, resolve_project_with_lockfile
from pitloom.extract.project.setuptools_cfg import read_setup_cfg

_MIT = "License :: OSI Approved :: MIT License"


def _setup_cfg(directory: Path, metadata: str) -> None:
    (directory / "setup.cfg").write_text(
        f"[metadata]\nname = pkg\n{metadata}", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("spec", "readme"),
    [
        ("a.txt, missing.txt ,b.txt", "one\ntwo\n"),
        ("a.txt,\n    b.txt", "one\ntwo\n"),  # wrapped across lines
        ("a.txt, b.txt,", "one\ntwo\n"),  # a trailing comma is no file
        # no file at all: the names, as a hint
        ("c.txt ,  d.txt", "c.txt, d.txt"),
        (",", None),
    ],
    ids=["one-line", "wrapped", "trailing-comma", "all-missing", "all-blank"],
)
def test_several_files_are_joined_as_setuptools_joins_them(
    spec: str, readme: str | None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "a.txt").write_bytes(b"one")
    (tmp_path / "b.txt").write_bytes(b"two\n")
    _setup_cfg(tmp_path, f"version = 1.0\nlong_description = file: {spec}\n")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _ = read_setup_cfg(tmp_path)
    assert metadata.readme == readme
    assert not caplog.records


@contextmanager
def _stat_denied(target: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """``stat()`` and ``lstat()`` of *target* raise ``PermissionError``, as
    for a file under a directory without search permission."""
    denied = os.path.abspath(target)
    with monkeypatch.context() as patch:
        for name in ("stat", "lstat"):
            real = getattr(os, name)

            def fake(path: Any, *args: Any, _real: Any = real, **kwargs: Any) -> Any:
                if isinstance(path, (str, os.PathLike)) and (
                    os.path.abspath(path) == denied
                ):
                    raise PermissionError(errno.EACCES, "Permission denied", path)
                return _real(path, *args, **kwargs)

            patch.setattr(os, name, fake)
        yield


@contextmanager
def _unreadable(
    tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """``bad`` under *tmp_path*: present but unreadable, as *kind*."""
    bad = tmp_path / "bad"
    if kind == "directory":
        bad.mkdir()
    elif kind == "not-utf-8":
        bad.write_bytes(b"\xff\xfe\x00bad")
    else:
        bad.write_text("x", encoding="utf-8")
    if kind == "open-denied":
        real = Path.read_text

        def denied(self: Path, *args: Any, **kwargs: Any) -> str:
            if self.name == "bad":
                raise PermissionError(errno.EACCES, "Permission denied", str(self))
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    with _stat_denied(bad, monkeypatch) if kind == "stat-denied" else nullcontext():
        yield


_KINDS = ["directory", "not-utf-8", "open-denied", "stat-denied"]


def _warned(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Each ``WARNING:`` message, cut to its file and what it was read for."""
    return sorted(
        r.getMessage().split("; ", 1)[0]
        for r in caplog.records
        if r.levelno == logging.WARNING
    )


@pytest.mark.parametrize("kind", _KINDS)
def test_an_unreadable_listed_file_is_left_out_with_one_warning(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "good.txt").write_text(_MIT, encoding="utf-8")
    _setup_cfg(
        tmp_path,
        "version = 1.0\nclassifiers = file: bad, good.txt\n"
        "long_description = file: bad\n",
    )
    with (
        _unreadable(tmp_path, kind, monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        metadata, _ = read_setup_cfg(tmp_path)
    assert metadata.license_name == "MIT License"
    assert metadata.readme is None
    assert _warned(caplog) == [
        "FILE=bad: could not read for setup.cfg metadata.classifiers",
        "FILE=bad: could not read for setup.cfg metadata.long_description",
    ]


def test_a_dangling_symlink_is_missing_as_setuptools_reads_it(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """setuptools skips what ``os.path.isfile`` rejects: no ``WARNING:``,
    the name is the filename hint as for any missing file."""
    try:
        (tmp_path / "link.txt").symlink_to(tmp_path / "gone.txt")
    except OSError:  # Windows without the symlink privilege
        pytest.skip("cannot create a symlink here")
    _setup_cfg(tmp_path, "version = 1.0\nlong_description = file: link.txt\n")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _ = read_setup_cfg(tmp_path)
    assert metadata.readme == "link.txt"
    assert not caplog.records


def test_each_unreadable_file_of_one_field_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "bad1").mkdir()
    (tmp_path / "bad2").mkdir()
    _setup_cfg(tmp_path, "version = 1.0\nclassifiers = file: bad1, bad2\n")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_setup_cfg(tmp_path)
    assert _warned(caplog) == [
        f"FILE={name}: could not read for setup.cfg metadata.classifiers"
        for name in ("bad1", "bad2")
    ]


def test_one_warning_per_run_although_the_project_is_read_twice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "bad").mkdir()
    _setup_cfg(tmp_path, "version = 1.0\nlong_description = file: bad\n")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        resolve_project_with_lockfile(tmp_path, None)
    assert _warned(caplog) == [
        "FILE=bad: could not read for setup.cfg metadata.long_description"
    ]


@pytest.mark.parametrize("kind", ["directory", "not-utf-8"])
@pytest.mark.parametrize(
    ("manifest", "what"),
    [
        ("setup.cfg", "setup.cfg metadata.version"),
        ("pyproject.toml", "pyproject.toml tool.setuptools.dynamic.version"),
    ],
)
def test_an_unreadable_version_file_is_no_version_with_one_warning(
    kind: str,
    manifest: str,
    what: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    if manifest == "setup.cfg":
        _setup_cfg(tmp_path, "version = file: bad\n")
    else:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\ndynamic = ["version"]\n'
            '[tool.setuptools.dynamic]\nversion = {file = "bad"}\n',
            encoding="utf-8",
        )
    with (
        _unreadable(tmp_path, kind, monkeypatch),
        caplog.at_level(logging.WARNING, logger="pitloom"),
    ):
        metadata = read_project(tmp_path)[0]
    assert metadata.version is None
    assert _warned(caplog) == [f"FILE=bad: could not read for {what}"]


_PYPROJECT_VERSION_FILE = (
    '[project]\nname = "pkg"\ndynamic = ["version"]\n'
    "[tool.setuptools.dynamic]\nversion = {{file = {files}}}\n"
)


@pytest.mark.parametrize(
    ("manifest", "text", "version", "readme"),
    [
        (
            "setup.cfg",
            "[metadata]\nname = pkg\nversion = file: V\x00ER\n",
            None,
            None,
        ),
        (
            "setup.cfg",
            "[metadata]\nname = pkg\nversion = 1.0\n"
            "long_description = file: R\x00EADME\n",
            "1.0",
            "R\x00EADME",  # no file: the name, as a hint
        ),
        (
            "pyproject.toml",
            _PYPROJECT_VERSION_FILE.format(files='"V\\u0000ER"'),
            None,
            None,
        ),
        (
            "pyproject.toml",
            _PYPROJECT_VERSION_FILE.format(files='["", "VER"]'),
            "2.0",
            None,
        ),
        ("pyproject.toml", _PYPROJECT_VERSION_FILE.format(files="3"), None, None),
    ],
    ids=[
        "cfg-nul-version",
        "cfg-nul-readme",
        "toml-nul",
        "toml-blank-first",
        "toml-int",
    ],
)
def test_a_name_that_is_no_file_is_skipped_silently(
    manifest: str,
    text: str,
    version: str | None,
    readme: str | None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A NUL in the name, a blank entry or a non-string names no file: it is
    skipped as setuptools skips it, without a ``WARNING:`` or a crash."""
    (tmp_path / "VER").write_text("2.0\n", encoding="utf-8")
    (tmp_path / manifest).write_text(text, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata = read_project(tmp_path)[0]
    assert (metadata.version, metadata.readme) == (version, readme)
    assert not caplog.records
