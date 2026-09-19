# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``get_wheel_files()`` never leaks a build-and-read extraction dir before
it hands the cleanup callback to its caller: an interrupt, termination
signal or propagated error in its per-file hashing loop or Merkle-root
computation removes the dir, and a run without a build leaves signal
handling alone.

The build is the fake of :mod:`tests.build_and_read_shared`; a signal is
simulated by calling the installed handler, and ``signal.raise_signal``
is a spy, so a termination ends in ``SystemExit(128 + signum)``.

See also: tests/core/test_build_signals.py (``TerminationGuard`` itself)
and tests/assemble/test_build_termination.py (the callers holding the
result afterwards).
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core import _models_wheel, models
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files
from tests.build_and_read_shared import (
    deliver_sigterm,
    extract_dirs,
    install_fake_build,
    spied_raise_signal,
    use_sys_tmp,
)

# pylint: disable-next=protected-access
_REAL_ENTRY = _models_wheel._build_project_file_entry


@pytest.fixture(name="raise_spy")
def fixture_raise_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[mock.Mock]:
    with spied_raise_signal(monkeypatch) as spy:
        yield spy


@pytest.fixture(name="sys_tmp")
def fixture_sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


@pytest.fixture(name="project")
def fixture_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A uv_build project (no static discoverer, so --allow-build builds
    it) whose fake build yields a three-file wheel."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    fake = install_fake_build(monkeypatch)
    fake.entries = {f"pkg/m{i}.py": b"x = 1\n" for i in range(3)}
    return project


def _interrupt_second_file(
    monkeypatch: pytest.MonkeyPatch, interrupt: object, sys_tmp: Path
) -> list[list[Path]]:
    """Make the hashing loop call *interrupt* on its second file; returns
    the extraction dirs that existed at that point."""
    seen: list[list[Path]] = []

    def entry(*args: object, **kwargs: object) -> object:
        seen.append(extract_dirs(sys_tmp))
        if len(seen) == 2:
            assert callable(interrupt)
            interrupt()
            pytest.fail("the interrupt did not stop the loop")
        return _REAL_ENTRY(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_models_wheel, "_build_project_file_entry", entry)
    return seen


def _raise_keyboard_interrupt() -> None:
    raise KeyboardInterrupt


@pytest.mark.usefixtures("raise_spy")
def test_keyboard_interrupt_in_hashing_loop_removes_extract_dir(
    monkeypatch: pytest.MonkeyPatch, project: Path, sys_tmp: Path
) -> None:
    seen = _interrupt_second_file(monkeypatch, _raise_keyboard_interrupt, sys_tmp)

    with pytest.raises(KeyboardInterrupt):
        get_wheel_files(project, build_options=BuildOptions(allow=True))

    assert len(seen) == 2 and seen[1], "no extraction dir while hashing"
    assert not extract_dirs(sys_tmp)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


def test_sigterm_in_hashing_loop_removes_extract_dir_then_terminates(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
) -> None:
    """The handler acts at once outside the build: the extraction dir is
    gone by the time the signal is re-raised."""
    seen = _interrupt_second_file(monkeypatch, deliver_sigterm, sys_tmp)
    left_at_raise: list[list[Path]] = []
    raise_spy.side_effect = lambda signum: left_at_raise.append(extract_dirs(sys_tmp))

    with pytest.raises(SystemExit) as excinfo:
        get_wheel_files(project, build_options=BuildOptions(allow=True))

    assert excinfo.value.code == 128 + signal.SIGTERM
    assert len(seen) == 2 and seen[1], "no extraction dir while hashing"
    assert left_at_raise == [[]]
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


@pytest.mark.usefixtures("raise_spy")
def test_interrupt_in_hashing_loop_runs_an_unregistered_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """get_wheel_files() runs the discovery's cleanup itself on an
    interrupt, not only on an Exception: a discovery whose cleanup is not
    registered with the guard has no other way to be released."""
    source = tmp_path / "m.py"
    source.write_text("x = 1\n", encoding="utf-8")
    cleanup = mock.Mock()
    monkeypatch.setattr(
        _models_wheel,
        "_discover_included_files",
        lambda *_args, **_kwargs: (
            [IncludedFile(path=str(source), distribution_path="pkg/m.py")],
            cleanup,
        ),
    )
    monkeypatch.setattr(
        _models_wheel,
        "_build_project_file_entry",
        mock.Mock(side_effect=KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        get_wheel_files(tmp_path)

    cleanup.assert_called_once_with()


@pytest.mark.usefixtures("raise_spy")
def test_merkle_root_error_propagates_and_removes_extract_dir(
    monkeypatch: pytest.MonkeyPatch, project: Path, sys_tmp: Path
) -> None:
    """Only a per-file read failure degrades to "no files"; an error in
    the pure Merkle-root computation is a bug that must surface -- with
    the extraction dir still removed."""
    monkeypatch.setattr(
        models, "_build_merkle_tree", mock.Mock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError, match="boom"):
        get_wheel_files(project, build_options=BuildOptions(allow=True))

    assert not extract_dirs(sys_tmp)


@pytest.mark.usefixtures("raise_spy")
def test_direct_caller_owns_the_dir_once_it_returns(
    project: Path, sys_tmp: Path
) -> None:
    """Called on its own, get_wheel_files() is the outermost guard: the
    handlers are gone when it returns, and the dir is the caller's until
    it runs the cleanup callback."""
    _root, files, cleanup = get_wheel_files(
        project, build_options=BuildOptions(allow=True)
    )

    assert len(files) == 3
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    assert extract_dirs(sys_tmp)
    cleanup()
    assert not extract_dirs(sys_tmp)


@pytest.mark.usefixtures("raise_spy")
def test_no_build_leaves_signal_handling_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Static discovery (the path of the Hatchling hook and model SBOMs)
    never installs a handler."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    spy = mock.Mock(wraps=signal.signal)
    monkeypatch.setattr(signal, "signal", spy)

    _root, files, _cleanup = get_wheel_files(tmp_path)

    assert files
    spy.assert_not_called()
