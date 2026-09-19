# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A build-and-read extraction dir is removed when Pitloom is interrupted
or terminated while its callers still use the files: during AI-model
scanning in ``generate_project_sbom()`` and ``embed_wheel_sbom()``, right
after ``get_wheel_files()`` returns, and between the wheels of a
``loom embed-wheel`` batch -- plus a real SIGTERM/SIGHUP to a process
running ``generate_project_sbom()`` (POSIX).

In-process, the build is the fake of :mod:`tests.build_and_read_shared`,
a signal is simulated by calling the installed handler, and
``signal.raise_signal`` is a spy, so a termination ends in
``SystemExit(128 + signum)``.

See also: tests/core/test_build_signals.py (``TerminationGuard`` itself)
and tests/core/models_wheel/test_models_wheel_termination.py
(``get_wheel_files()`` before it returns).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest

from pitloom import __main__, _embed_build_sbom
from pitloom.assemble import _generators, generate_project_sbom
from pitloom.cli.commands import embed_wheel as embed_wheel_cmd
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from tests.build_and_read_shared import (
    EXTRACT_PREFIX,
    deliver_sigterm,
    extract_dirs,
    install_fake_build,
    spied_raise_signal,
    use_sys_tmp,
)

from .conftest import _make_dummy_wheel

_PYPROJECT = (
    '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n\n'
    '[project]\nname = "pkg"\nversion = "1.0.0"\n'
)
_ALLOW = BuildOptions(allow=True)


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
    it), built by the fake build."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    install_fake_build(monkeypatch)
    return project


def _signal_during_scan(
    monkeypatch: pytest.MonkeyPatch, sys_tmp: Path
) -> list[list[Path]]:
    """Replace the AI-model scan of both SBOM generators with one that
    delivers SIGTERM; returns the extraction dirs that existed when it
    started."""
    seen: list[list[Path]] = []

    def scan(project_dir: Path, project_files: object) -> list[object]:
        del project_dir, project_files
        seen.append(extract_dirs(sys_tmp))
        deliver_sigterm()
        pytest.fail("the signal did not end the scan")

    for module in (_generators, _embed_build_sbom):
        monkeypatch.setattr(module, "scan_project_for_ai_models", scan)
    return seen


def _record_dirs_at_raise(raise_spy: mock.Mock, sys_tmp: Path) -> list[list[Path]]:
    left: list[list[Path]] = []
    raise_spy.side_effect = lambda signum: left.append(extract_dirs(sys_tmp))
    return left


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda project, wheel: generate_project_sbom(
                project, offline=True, build_options=_ALLOW
            ),
            id="generate_project_sbom",
        ),
        pytest.param(
            lambda project, wheel: embed_wheel_sbom(
                wheel,
                project_dir=project,
                overrides=ConfigOverrides(build_options=_ALLOW),
            ),
            id="embed_wheel_sbom",
        ),
    ],
)
def test_sigterm_during_ai_model_scan_removes_extract_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    project: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
    call: object,
) -> None:
    wheel = _make_dummy_wheel(tmp_path / "dist", "pkg", "1.0.0")
    seen = _signal_during_scan(monkeypatch, sys_tmp)
    left_at_raise = _record_dirs_at_raise(raise_spy, sys_tmp)

    assert callable(call)
    with pytest.raises(SystemExit) as excinfo:
        call(project, wheel)

    assert excinfo.value.code == 128 + signal.SIGTERM
    assert seen and seen[0], "no extraction dir during the scan"
    assert left_at_raise == [[]]
    raise_spy.assert_called_once_with(signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


@pytest.mark.usefixtures("raise_spy")
def test_interrupt_right_after_get_wheel_files_returns_removes_extract_dir(
    monkeypatch: pytest.MonkeyPatch, project: Path, sys_tmp: Path
) -> None:
    """Ctrl-C after get_wheel_files() returned but before the caller holds
    its cleanup callback: the caller's guard removes the dir."""
    real = get_wheel_files
    seen: list[list[Path]] = []

    def interrupted(*args: object, **kwargs: object) -> object:
        real(*args, **kwargs)  # type: ignore[arg-type]
        seen.append(extract_dirs(sys_tmp))
        raise KeyboardInterrupt

    monkeypatch.setattr(_generators, "get_wheel_files", interrupted)

    with pytest.raises(KeyboardInterrupt):
        generate_project_sbom(project, offline=True, build_options=_ALLOW)

    assert seen and seen[0], "no extraction dir after get_wheel_files()"
    assert not extract_dirs(sys_tmp)


def test_embed_batch_sigterm_between_wheels_cleans_up_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    project: Path,
    sys_tmp: Path,
    raise_spy: mock.Mock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SIGTERM after the first wheel of a batch: the batch's one extraction
    dir is removed once, before the signal is re-raised, and the second
    wheel is never embedded."""
    wheels = [_make_dummy_wheel(tmp_path / f"dist{i}", "pkg", "1.0.0") for i in (1, 2)]
    real_embed = embed_wheel_sbom
    embedded: list[Path] = []

    def embed_then_signal(wheel: Path, **kwargs: object) -> object:
        real_embed(wheel, **kwargs)  # type: ignore[arg-type]
        embedded.append(wheel)
        assert extract_dirs(sys_tmp), "no extraction dir between wheels"
        deliver_sigterm()
        pytest.fail("the signal did not end the batch")

    monkeypatch.setattr(embed_wheel_cmd, "embed_wheel_sbom", embed_then_signal)
    rmtree = mock.Mock(wraps=shutil.rmtree)
    monkeypatch.setattr(shutil, "rmtree", rmtree)
    left_at_raise = _record_dirs_at_raise(raise_spy, sys_tmp)
    argv = ["loom", "embed-wheel", *map(str, wheels), "--project-dir", str(project)]
    monkeypatch.setattr(sys, "argv", [*argv, "--allow-build"])

    with pytest.raises(SystemExit) as excinfo:
        __main__.main()

    assert excinfo.value.code == 128 + signal.SIGTERM
    assert embedded == wheels[:1]
    assert left_at_raise == [[]]
    removed = [c for c in rmtree.call_args_list if EXTRACT_PREFIX in str(c.args[0])]
    assert len(removed) == 1
    # Not "during the build": that was over before the first wheel.
    assert "WARNING: Build: received SIGTERM after the build" in capsys.readouterr().err


# Runs generate_project_sbom() in a process of its own, with a fake build
# and an AI-model scan that signals readiness, then sleeps.
_DRIVER = textwrap.dedent(
    """
    import sys, time, zipfile
    from pathlib import Path
    from pitloom.assemble import _generators
    from pitloom.core import _models_wheel_build_and_read as bar
    from pitloom.core.build_options import BuildOptions

    def fake_build(project_dir, work_dir, *, isolated, timeout, termination):
        wheel = work_dir / "pkg-1.0.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as zf:
            zf.writestr("pkg/__init__.py", "x = 1\\n")
        return wheel

    def slow_scan(project_dir, project_files):
        Path(sys.argv[2]).write_text("scanning")
        time.sleep(120)
        return []

    bar.run_build_subprocess = fake_build
    _generators.scan_project_for_ai_models = slow_scan
    _generators.generate_project_sbom(
        Path(sys.argv[1]), offline=True, build_options=BuildOptions(allow=True)
    )
    print("generate_project_sbom returned")
    """
)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("sig_name", ["SIGTERM", "SIGHUP"])
def test_real_signal_during_scan_removes_extract_dir(
    tmp_path: Path, sig_name: str
) -> None:
    sig = signal.Signals[sig_name]
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    sys_tmp = tmp_path / "sys-tmp"
    sys_tmp.mkdir()
    ready = tmp_path / "ready"
    src_dir = Path(_generators.__file__).resolve().parents[2]
    env = {
        **os.environ,
        "TMPDIR": str(sys_tmp),
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(src_dir), os.environ.get("PYTHONPATH")])
        ),
    }
    with subprocess.Popen(
        [sys.executable, "-c", _DRIVER, str(project), str(ready)],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as driver:
        try:
            deadline = time.monotonic() + 60
            while not ready.exists() and driver.poll() is None:
                assert time.monotonic() < deadline, "the scan never started"
                time.sleep(0.05)
            assert ready.exists(), driver.communicate()[1].decode()
            # Exists while scanning, so the check after the signal is not vacuous.
            assert extract_dirs(sys_tmp)
            driver.send_signal(sig)
            out, err = driver.communicate(timeout=60)
        finally:
            if driver.poll() is None:
                driver.kill()
                driver.communicate()
    assert not extract_dirs(sys_tmp)
    # Terminated by the signal itself, after cleanup; not a normal return.
    assert driver.returncode == -sig
    assert b"generate_project_sbom returned" not in out
    assert f"WARNING: Build: received {sig_name} after the build".encode() in err
