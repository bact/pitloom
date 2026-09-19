# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Temp-dir cleanup of :mod:`pitloom.core._models_wheel_build_and_read`
on failure, timeout, Ctrl-C and termination signals, including a signal
that lands while a temp dir is being removed.

A signal is simulated by calling the installed handler directly at the
point under test, as the interpreter would between two bytecodes;
``signal.raise_signal`` is a spy, so the re-raise ends in the
``SystemExit(128 + signum)`` fallback instead of killing the test process.

See also: tests/core/models_wheel/test_models_wheel_build_and_read.py
(the rest of the module) and
tests/core/test_build_signals.py
(``TerminationGuard`` itself).
"""

import logging
import shutil
import signal
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core import _models_wheel_build_and_read as bar
from pitloom.core._models_wheel_build_and_read import build_and_read_wheel
from pitloom.core._models_wheel_build_subprocess import BuildTimeoutError
from pitloom.core.build_signals import TerminationGuard
from tests.build_and_read_shared import (
    EXTRACT_PREFIX,
    RUN_BUILD,
    TEMP_PREFIXES,
    FakeBuildState,
    deliver_sigterm,
    install_fake_build,
    raising_build,
    spied_raise_signal,
    use_sys_tmp,
)


@pytest.fixture(name="fake_build")
def fixture_fake_build(monkeypatch: pytest.MonkeyPatch) -> FakeBuildState:
    return install_fake_build(monkeypatch)


@pytest.fixture(name="sys_tmp")
def fixture_sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


def test_build_and_read_wheel_never_leaks_temp_dirs_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both temp dirs are removed when the build fails -- only the success
    path hands the extraction dir's cleanup to the caller."""
    seen: set[str] = set()
    monkeypatch.setattr(
        RUN_BUILD, raising_build(RuntimeError("simulated failure"), sys_tmp, seen)
    )

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is None
    assert "simulated failure" in caplog.text
    assert seen == TEMP_PREFIXES
    assert not list(sys_tmp.iterdir())


@pytest.mark.parametrize(
    ("tree_terminated", "outcome"),
    [
        (True, "-- build process tree terminated"),
        (False, "-- could not confirm the build process tree terminated"),
    ],
    ids=["confirmed", "unconfirmed"],
)
def test_build_and_read_wheel_timeout_returns_none_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
    tree_terminated: bool,
    outcome: str,
) -> None:
    """A :class:`BuildTimeoutError` gets its own ``WARNING:`` (not the
    generic "discovery failed" one), worded by whether the kill was
    confirmed, and leaks no temp dir."""
    seen: set[str] = set()
    exc = BuildTimeoutError(42, tree_terminated=tree_terminated)
    monkeypatch.setattr(RUN_BUILD, raising_build(exc, sys_tmp, seen))

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=42)

    assert result is None
    # BuildTimeoutError's own str() also says "timed out after 42s", so
    # check this branch's wording and the generic one's absence.
    assert "build-and-read for" in caplog.text
    assert "timed out after 42s (--build-timeout)" in caplog.text
    assert caplog.text.rstrip().endswith(outcome)
    assert "discovery failed" not in caplog.text
    assert seen == TEMP_PREFIXES
    assert not list(sys_tmp.iterdir())


def test_build_and_read_wheel_keyboard_interrupt_cleans_up_and_reraises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sys_tmp: Path
) -> None:
    """``KeyboardInterrupt`` is not an ``Exception``: the temp dirs must be
    removed by ``finally``/``with``, not by the generic ``except``."""
    seen: set[str] = set()
    monkeypatch.setattr(RUN_BUILD, raising_build(KeyboardInterrupt(), sys_tmp, seen))

    with pytest.raises(KeyboardInterrupt):
        build_and_read_wheel(tmp_path, timeout=60)

    assert seen == TEMP_PREFIXES
    assert not list(sys_tmp.iterdir())


def test_build_and_read_wheel_warns_on_leftover_work_dir(
    fake_build: FakeBuildState,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``ignore_cleanup_errors=True`` must not hide a leftover work dir."""
    del fake_build
    real_rmtree = shutil.rmtree

    def rmtree_skipping_work_dir(path: str, *args: object, **kwargs: object) -> None:
        # A removal failure ignore_cleanup_errors=True would swallow.
        if not Path(path).name.startswith("plb-"):
            real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(shutil, "rmtree", rmtree_skipping_work_dir)

    with caplog.at_level(logging.WARNING):
        result = build_and_read_wheel(tmp_path, timeout=60)

    assert result is not None
    result[1]()
    (leftover,) = sys_tmp.iterdir()
    assert leftover.name.startswith("plb-")
    assert f"Build: could not fully remove temporary directory {leftover}" in (
        caplog.text
    )


def test_build_and_read_wheel_termination_signal_reraised_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SIGTERM during the build: both temp dirs are gone before the signal
    is re-raised; never swallowed into a static-discovery fallback."""
    seen: set[str] = set()

    def build_until_signal(
        project_dir: Path,
        work_dir: Path,
        *,
        isolated: bool,
        timeout: int,
        termination: TerminationGuard,
    ) -> Path:
        del project_dir, work_dir, isolated, timeout
        seen.update(
            p for p in TEMP_PREFIXES for d in sys_tmp.iterdir() if d.name.startswith(p)
        )
        deliver_sigterm()
        # What the real wait loop does on its next slice.
        termination.raise_if_pending()
        pytest.fail("signal not recorded")

    monkeypatch.setattr(RUN_BUILD, build_until_signal)
    left_at_raise: list[list[Path]] = []
    raise_spy.side_effect = lambda signum: left_at_raise.append(list(sys_tmp.iterdir()))

    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit) as excinfo:
        build_and_read_wheel(tmp_path, timeout=60)

    assert excinfo.value.code == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert seen == TEMP_PREFIXES
    assert left_at_raise == [[]]
    assert "discovery failed" not in caplog.text
    assert "Build: received SIGTERM during the build" in caplog.text


@pytest.mark.usefixtures("fake_build")
def test_build_and_read_wheel_signal_during_work_dir_removal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SIGTERM while the work dir (e.g. a large isolated build venv) is
    being removed must not leave it half-removed: the handler repeats that
    removal to completion, removes the extraction dir of the successful
    build too, then re-raises the signal."""
    real_rmtree = shutil.rmtree
    fired: list[str] = []

    def rmtree(path: str, *args: object, **kwargs: object) -> None:
        if Path(path).name.startswith("plb-") and not fired:
            fired.append(str(path))
            deliver_sigterm()
        real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(shutil, "rmtree", rmtree)

    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit) as excinfo:
        build_and_read_wheel(tmp_path, timeout=60)

    assert fired
    assert excinfo.value.code == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert not list(sys_tmp.iterdir())
    assert "could not fully remove" not in caplog.text
    assert "Build: received SIGTERM after the build" in caplog.text


def test_build_and_read_wheel_signal_during_extraction_acts_at_once(
    fake_build: FakeBuildState,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Extracting a (possibly multi-GiB) wheel is not held: a signal then
    must not wait for the rest of it (``docker stop`` sends SIGKILL after
    10 s). The build is over, so the handler removes both dirs, each
    once, and ends the process at once."""
    fake_build.entries = {f"pkg/m{i}.py": b"x = 1\n" for i in range(3)}
    real_copy = shutil.copyfileobj
    copies: list[str] = []

    def copy(src: object, dst: object, *args: object, **kwargs: object) -> None:
        copies.append(str(getattr(dst, "name", dst)))
        if len(copies) == 1:
            deliver_sigterm()
        real_copy(src, dst, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(shutil, "copyfileobj", copy)
    rmtree = mock.Mock(wraps=shutil.rmtree)
    monkeypatch.setattr(shutil, "rmtree", rmtree)
    left_at_raise: list[list[Path]] = []
    raise_spy.side_effect = lambda signum: left_at_raise.append(list(sys_tmp.iterdir()))

    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit) as excinfo:
        build_and_read_wheel(tmp_path, timeout=60)

    assert len(copies) == 1
    assert excinfo.value.code == 128 + signal.SIGTERM
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert left_at_raise == [[]]
    removed = sorted(
        p
        for c in rmtree.call_args_list
        for p in TEMP_PREFIXES
        if Path(c.args[0]).name.startswith(p)
    )
    assert removed == sorted(TEMP_PREFIXES)
    assert "Build: received SIGTERM after the build" in caplog.text


@pytest.mark.usefixtures("fake_build")
def test_build_and_read_wheel_signal_after_success_removes_extract_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
) -> None:
    """SIGTERM once the call has succeeded, before it returns: the caller
    never gets to run the cleanup callback, so the guard must."""
    real_warn = bar._warn_if_left_behind  # pylint: disable=protected-access
    fired: list[bool] = []

    def warn_then_signal(path: Path) -> None:
        # The work dir's leftover check, the last step before returning.
        real_warn(path)
        if not fired:
            fired.append(True)
            deliver_sigterm()

    monkeypatch.setattr(bar, "_warn_if_left_behind", warn_then_signal)

    with pytest.raises(SystemExit):
        build_and_read_wheel(tmp_path, timeout=60)

    assert fired
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert not list(sys_tmp.iterdir())


def test_build_and_read_wheel_signal_right_after_mkdtemp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
) -> None:
    """SIGTERM right after creating the extraction dir is held until its
    removal is registered: it leaks nothing."""
    real_mkdtemp = tempfile.mkdtemp
    fake_build = install_fake_build(monkeypatch)

    def mkdtemp(*args: object, **kwargs: object) -> str:
        path = real_mkdtemp(*args, **kwargs)  # type: ignore[call-overload]
        if Path(path).name.startswith(EXTRACT_PREFIX):
            deliver_sigterm()
        return str(path)

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)

    with pytest.raises(SystemExit):
        build_and_read_wheel(tmp_path, timeout=60)

    assert fake_build.termination_seen
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert not list(sys_tmp.iterdir())


def test_build_and_read_wheel_warns_on_leftover_extract_dir_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sys_tmp: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed build's extraction dir that survives its removal is named
    in a ``WARNING:``, like the work dir."""
    seen: set[str] = set()
    monkeypatch.setattr(RUN_BUILD, raising_build(RuntimeError("x"), sys_tmp, seen))
    real_rmtree = shutil.rmtree

    def rmtree_skipping_extract_dir(path: str, *args: object, **kwargs: object) -> None:
        if not Path(path).name.startswith(EXTRACT_PREFIX):
            real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(shutil, "rmtree", rmtree_skipping_extract_dir)

    with caplog.at_level(logging.WARNING):
        assert build_and_read_wheel(tmp_path, timeout=60) is None

    (leftover,) = sys_tmp.iterdir()
    assert leftover.name.startswith(EXTRACT_PREFIX)
    assert f"Build: could not fully remove temporary directory {leftover}" in (
        caplog.text
    )
