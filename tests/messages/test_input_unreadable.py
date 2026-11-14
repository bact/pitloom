# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An input the system will not let Pitloom look at (a directory above it
without search permission) is ``file-unreadable`` for the input check, never
``input-not-found``, on every surface; a command given several paths
reports each one; the probe tells the kinds apart.

See also: tests/messages/test_input_wrong_kind.py (an input of the wrong
kind), tests/messages/test_input_not_found_surfaces.py (a missing input).
"""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import pitloom.messages._input_not_found_say as say
from pitloom import __main__
from pitloom.assemble import (
    generate_merged_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.core.path_probe import stat_if_present
from pitloom.extract.project.sdist import read_sdist
from pitloom.id_registry import resolve_registry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.targets import input_exists, is_input_dir, is_input_file
from tests._unreadable import POSIX_NON_ROOT

pytestmark = pytest.mark.platform

_WHL = "d-1.0-py3-none-any.whl"


def _loom(argv: list[str], monkeypatch: pytest.MonkeyPatch, err: Any) -> list[str]:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    return [ln for ln in err.readouterr().err.splitlines() if ln.startswith("ERROR:")]


def _deny_stat(monkeypatch: pytest.MonkeyPatch) -> None:
    """The probe's ``stat`` raises ``PermissionError``, as under a directory
    without search permission (patched where the probe looks it up, not on
    the shared ``os`` module)."""

    def _stat(path: Any) -> Any:
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)

    monkeypatch.setattr(say, "stat_if_present", _stat)


_UNREADABLE = "FILE={}: could not read for the input check; "


@pytest.mark.parametrize(
    "argv",
    [
        ["wheel", _WHL],
        ["merge", "frag"],
        ["project", "proj"],
        ["generate", "proj", "-o", "o.json"],
        ["id", "import", "s.json"],
        ["fragment", "validate", "s.json"],
    ],
    ids=["wheel", "merge", "project", "generate", "id-import", "fragment"],
)
def test_an_input_the_system_will_not_show_is_file_unreadable_on_the_cli(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _deny_stat(monkeypatch)
    lines = _loom(argv, monkeypatch, capsys)
    named = argv[-1] if argv[0] != "generate" else argv[1]
    assert any(
        _UNREADABLE.format(named) in ln and ln.endswith(" [file-unreadable]")
        for ln in lines
    ), lines


@pytest.mark.parametrize(
    "call",
    [
        lambda: generate_wheel_sbom(_WHL),
        lambda: generate_merged_sbom("frag"),
        lambda: generate_project_sbom("proj"),
        lambda: read_sdist(Path("a-1.tar.gz")),
        lambda: resolve_registry("reg.json", None, Path()),
    ],
    ids=["wheel", "merge", "project", "sdist", "registry"],
)
def test_an_input_the_system_will_not_show_is_file_unreadable_in_the_library(
    call: Callable[[], object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _deny_stat(monkeypatch)
    with pytest.raises(
        ValueError, match="could not read for the input check"
    ) as caught:
        call()
    assert getattr(caught.value, CODE_ATTR) == "file-unreadable"


@pytest.mark.parametrize(
    ("make", "exists", "is_file", "is_dir"),
    [
        (None, False, False, False),
        ("file", True, True, False),
        ("dir", True, False, True),
        ("dangling", False, False, False),
    ],
    ids=["missing", "file", "dir", "dangling-link"],
)
def test_the_probe_tells_the_kinds_apart(
    make: str | None, exists: bool, is_file: bool, is_dir: bool, tmp_path: Path
) -> None:
    path = tmp_path / "p"
    if make == "file":
        path.write_bytes(b"")
    elif make == "dir":
        path.mkdir()
    elif make == "dangling":
        try:
            path.symlink_to(tmp_path / "gone")
        except OSError:
            pytest.skip("symbolic links need privilege here")
    assert (input_exists(path), is_input_file(path), is_input_dir(path)) == (
        exists,
        is_file,
        is_dir,
    )


def test_a_path_no_file_can_have_is_missing() -> None:
    """An embedded NUL makes ``os.stat`` raise ``ValueError``: nothing is
    there, as ``os.path.exists`` says."""
    assert not input_exists("a\x00b")


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root")
def test_a_real_directory_without_search_permission_is_file_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    monkeypatch.chdir(tmp_path)
    locked.chmod(0o600)
    try:
        (line,) = _loom(["wheel", f"locked/{_WHL}"], monkeypatch, capsys)
    finally:
        locked.chmod(0o700)
    assert line.startswith(
        f"ERROR: loom wheel: FILE=locked/{_WHL}: could not read for the input check; "
    )
    assert line.endswith(" [file-unreadable]")


@pytest.mark.parametrize(
    ("command", "first", "second"),
    [
        ("fragment validate", "a.json", "b.json"),
        ("verify-wheel", "a-1.0-py3-none-any.whl", _WHL),
        ("validate-wheel", "a-1.0-py3-none-any.whl", _WHL),
        ("embed-wheel", "a-1.0-py3-none-any.whl", _WHL),
    ],
    ids=["fragment", "verify-wheel", "validate-wheel", "embed-wheel"],
)
def test_an_unreadable_path_does_not_hide_the_next_one(
    command: str,
    first: str,
    second: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The first path cannot be looked at, the second is not there: both
    are said, each with its code, and the run fails."""
    monkeypatch.chdir(tmp_path)

    def deny_first(path: Any) -> Any:
        if os.fspath(path).endswith(first):
            raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)
        return stat_if_present(path)

    monkeypatch.setattr(say, "stat_if_present", deny_first)
    lines = _loom([*command.split(), first, second], monkeypatch, capsys)
    frame = f"ERROR: loom {command}: "
    assert [ln for ln in lines if first in ln or second in ln] == [
        f"{frame}{_UNREADABLE.format(first)}"
        f"{os.strerror(errno.EACCES)} [file-unreadable]",
        f"{frame}{'SBOM' if command.startswith('f') else 'wheel'} file not found: "
        f"'{second}' [input-not-found]",
    ]
