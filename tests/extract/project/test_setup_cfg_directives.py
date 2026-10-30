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

import ast
import errno
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from pitloom.core.path_confine import open_inside
from pitloom.extract.project import (
    _setup_cfg_directives,
    read_project,
    resolve_project_with_lockfile,
)
from pitloom.extract.project._setup_cfg_directives import (
    _resolve_cfg_attr_directive,
)
from pitloom.extract.project.setuptools_cfg import read_setup_cfg
from tests._bounded import run_bounded_in_child

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
    (tmp_path / "b.txt").write_bytes(b"two\r\n")  # read in text mode
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
        real = open_inside

        def denied(written: Path, root: Path) -> Any:
            if written.name == "bad":
                raise PermissionError(errno.EACCES, "Permission denied", str(written))
            return real(written, root)

        monkeypatch.setattr(_setup_cfg_directives, "open_inside", denied)
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


@pytest.mark.parametrize(
    ("name", "warning"),
    [
        ("VER", None),
        ("s/../VER", None),
        ("../out", "could not read for {what}; outside the project directory"),
        ("{out}", "could not read for {what}; outside the project directory"),
        ("link", "could not read for {what}; outside the project directory"),
        ("big", "larger than the 3-byte file-directive cap; skipped for {what}"),
    ],
    ids=["inside", "dotdot-inside", "dotdot-out", "absolute", "symlink-out", "cap"],
)
@pytest.mark.parametrize(
    ("manifest", "what"),
    [
        ("setup.cfg", "setup.cfg metadata.version"),
        ("pyproject.toml", "pyproject.toml tool.setuptools.dynamic.version"),
    ],
    ids=["cfg", "toml"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_version_file_is_read_only_inside_the_project_and_under_the_cap(
    name: str,
    warning: str | None,
    manifest: str,
    what: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ``file`` version directive follows the dynamic requirements reader's
    limits: outside the project (``..``, absolute, symlink) or over the cap,
    no version and one ``WARNING:`` naming the file as written."""
    monkeypatch.setattr(_setup_cfg_directives, "MAX_LISTED_FILE_BYTES", 3)
    project = tmp_path / "p"
    (project / "s").mkdir(parents=True)
    (project / "VER").write_bytes(b"2.0")
    (project / "big").write_bytes(b"2.0\n")
    (tmp_path / "out").write_bytes(b"6.6")
    if name == "link":
        try:
            (project / "link").symlink_to(tmp_path / "out")
        except OSError:  # Windows without the symlink privilege
            pytest.skip("cannot create a symlink here")
    name = name.format(out=(tmp_path / "out").as_posix())
    if manifest == "setup.cfg":
        _setup_cfg(project, f"version = file: {name}\n")
    else:
        (project / manifest).write_text(
            _PYPROJECT_VERSION_FILE.format(files=f"'{name}'"), encoding="utf-8"
        )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata = read_project(project)[0]
    assert metadata.version == (None if warning else "2.0")
    expected = [] if warning is None else [f"FILE={name}: {warning.format(what=what)}"]
    assert caplog.messages == expected


_ATTR = "pitloom.extract.project._setup_cfg_directives:_resolve_cfg_attr_directive"
_NINE = ("9", "Source: m.py | Method: attr_directive")


@pytest.mark.parametrize(
    "value",
    [
        ".".join(["a"] * 300000),
        "-" * 500000 + "1",
        "not " * 200000 + "1",
        "(\n" + ".".join(["a"] * 300000) + "\n)",
        "(" * 300000 + "1" + ")" * 300000,
    ],
    ids=["attributes", "unary-minus", "not", "joined-lines", "brackets"],
)
def test_attr_directive_survives_a_deep_assignment(tmp_path: Path, value: str) -> None:
    """Only a logical line assigning the attribute is parsed, not the whole
    module (a file under the cap could crash the run: a C stack overflow on
    3.10, ``RecursionError`` or ``MemoryError`` later); one over the line cap
    (its physical lines joined) is skipped. Runs in a child, so a crash fails
    the test and not the session."""
    module = f"__version__ = {value}\n__version__ = '9'\n"
    (tmp_path / "m.py").write_text(module, encoding="utf-8")
    assert run_bounded_in_child(_ATTR, "m.__version__", tmp_path, "t") == _NINE


@pytest.mark.parametrize(
    ("template", "digits"),
    [("__version__ = '{}'", 240), ("__version__ = (\n    '{}'\n)", 232)],
    ids=["one-line", "joined-lines"],
)
@pytest.mark.parametrize("over", [0, 1], ids=["at-cap", "over-cap"])
def test_attr_line_over_the_cap_is_skipped(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    template: str,
    digits: int,
    over: int,
) -> None:
    """A logical line of :data:`MAX_ATTR_LINE_CHARS` characters, its
    physical lines joined, is parsed; a longer one is skipped with one
    ``WARNING:`` and the next assignment read."""
    line = template.format("9" * (digits + over))
    assert len(line) == _setup_cfg_directives.MAX_ATTR_LINE_CHARS + over
    (tmp_path / "m.py").write_text(f"{line}\n__version__ = '9'\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = _resolve_cfg_attr_directive("m.__version__", tmp_path, "t")
    assert found == (_NINE if over else ("9" * digits, _NINE[1]))
    cap = "FILE=m.py: larger than the 256-character attr-directive-line cap;"
    assert caplog.messages == [f"{cap} __version__ line skipped for t"] * over


@pytest.mark.parametrize(
    "module",
    [
        "__version__ = (\n    '1.0'\n)\n",
        "__version__ = \\\n    '1.0'\n",
        "x = 1; __version__ = '1.0'\n",
        "__version__ = 1; __version__ = 2\n__version__ = '1.0'\n",
        "__version__: str = '1.0'\n",
        "version = __version__ = '1.0'\n",
        "if True:\n    __version__ = '1.0'\n",
        "__version__: str\n__version__ = ('1.0'  # ')'\n)",
    ],
    ids=[
        "parenthesised",
        "backslash",
        "after-semicolon",
        "twice-on-a-line",
        "annotated",
        "chained",
        "indented",
        "annotation-only-then-comment",
    ],
)
def test_attr_directive_reads_each_assignment_form(tmp_path: Path, module: str) -> None:
    """Every form setuptools reads statically gives a version: a parenthesised
    or ``;``-joined logical line, an annotated or a chained target, after a
    ``;``."""
    (tmp_path / "m.py").write_text(module, encoding="utf-8")
    found = _resolve_cfg_attr_directive("m.__version__", tmp_path, "t")
    assert found == ("1.0", _NINE[1])


@pytest.mark.parametrize("error", [RecursionError, MemoryError])
def test_attr_line_the_parser_cannot_hold_is_skipped(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    error: type[BaseException],
) -> None:
    """A line the parser runs out of stack or memory on is a skipped read
    with one ``WARNING:``, never a crash or an empty ``ERROR:``."""
    parser = mock.Mock(spec=ast)
    parser.parse.side_effect = error
    monkeypatch.setattr(_setup_cfg_directives, "ast", parser)
    (tmp_path / "m.py").write_text("__version__ = '1'\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = _resolve_cfg_attr_directive("m.__version__", tmp_path, "t")
    assert found == (None, None)
    assert caplog.messages == [
        f"FILE=m.py: {error.__name__} parsing the __version__ line; skipped for t"
    ]
