# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared stand-ins for build-and-read tests: a fake
``run_build_subprocess``, a per-test system temp dir, and a simulated
termination signal.

See also: tests/core/models_wheel/test_models_wheel_build_and_read.py,
tests/core/models_wheel/test_models_wheel_build_and_read_cleanup.py,
tests/core/models_wheel/test_models_wheel_termination.py,
tests/core/test_build_signals.py and
tests/assemble/test_build_termination.py (the users).
"""

from __future__ import annotations

import contextlib
import dataclasses
import signal
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core.build_signals import TerminationGuard

RUN_BUILD = "pitloom.core._models_wheel_build_and_read.run_build_subprocess"
EXTRACT_PREFIX = "pitloom-build-and-read-"
TEMP_PREFIXES = {"plb-", EXTRACT_PREFIX}

# A run_build_subprocess() stand-in.
FakeRun = Callable[..., Path]


def write_fake_wheel(
    wheel_path: Path, entries: dict[str, bytes], *, dist_info: bool = True
) -> None:
    """Write a small, hand-built ``.whl`` zip at *wheel_path* with
    *entries* (distribution_path -> content), plus an optional
    ``.dist-info/METADATA`` entry (present by default, since a real
    wheel always has one)."""
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
        if dist_info:
            zf.writestr("pkg-1.0.dist-info/METADATA", b"Metadata-Version: 2.1\n")


@dataclasses.dataclass
class FakeBuildState:
    """Mutable state a test can adjust before calling
    ``build_and_read_wheel()``, backing :func:`install_fake_build`."""

    entries: dict[str, bytes] = dataclasses.field(
        default_factory=lambda: {"pkg/__init__.py": b"print('hi')\n"}
    )
    dist_info: bool = True
    isolated_seen: list[bool] = dataclasses.field(default_factory=list)
    timeout_seen: list[int] = dataclasses.field(default_factory=list)
    termination_seen: list[TerminationGuard] = dataclasses.field(default_factory=list)


def install_fake_build(monkeypatch: pytest.MonkeyPatch) -> FakeBuildState:
    """Monkeypatch ``run_build_subprocess`` to write a fake wheel instead
    of actually invoking PyPA build -- keeps these tests fast, offline,
    and deterministic. Returns state the test can mutate
    (``entries``/``dist_info``) before calling ``build_and_read_wheel()``."""
    state = FakeBuildState()

    def _fake_run(
        project_dir: Path,
        work_dir: Path,
        *,
        isolated: bool,
        timeout: int,
        termination: TerminationGuard,
    ) -> Path:
        del project_dir
        state.isolated_seen.append(isolated)
        state.timeout_seen.append(timeout)
        state.termination_seen.append(termination)
        wheel_path = work_dir / "pkg-1.0-py3-none-any.whl"
        write_fake_wheel(wheel_path, state.entries, dist_info=state.dist_info)
        return wheel_path

    monkeypatch.setattr(RUN_BUILD, _fake_run)
    return state


def use_sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A per-test system temp dir: a leftover temp dir shows up in it."""
    root = tmp_path / "sys-tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def raising_build(exc: BaseException, sys_tmp: Path, seen: set[str]) -> FakeRun:
    """A ``run_build_subprocess`` stand-in raising *exc*; it records into
    *seen* which temp-dir prefixes exist when the build starts."""

    def _run(
        project_dir: Path,
        work_dir: Path,
        *,
        isolated: bool,
        timeout: int,
        termination: TerminationGuard,
    ) -> Path:
        del project_dir, work_dir, isolated, timeout, termination
        seen.update(
            p for p in TEMP_PREFIXES for d in sys_tmp.iterdir() if d.name.startswith(p)
        )
        raise exc

    return _run


@contextlib.contextmanager
def spied_raise_signal(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    """SIGTERM starts at SIG_DFL (restored afterwards), and
    ``signal.raise_signal`` is a spy, so a re-raise never kills the test
    process. Returning, it behaves as for PID 1 in a container: the guard
    then ends in its ``SystemExit(128 + signum)`` fallback."""
    spy = mock.create_autospec(signal.raise_signal)
    monkeypatch.setattr(signal, "raise_signal", spy)
    previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        yield spy
    finally:
        signal.signal(signal.SIGTERM, previous)


def deliver_sigterm() -> None:
    """Run the installed SIGTERM handler, as a delivered signal would
    between two bytecodes."""
    handler = signal.getsignal(signal.SIGTERM)
    assert callable(handler), "no SIGTERM handler installed"
    handler(signal.SIGTERM, None)


def extract_dirs(sys_tmp: Path) -> list[Path]:
    """The build-and-read extraction dirs currently in *sys_tmp*."""
    return [d for d in sys_tmp.iterdir() if d.name.startswith(EXTRACT_PREFIX)]
