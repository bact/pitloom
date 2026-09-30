# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keeps ``scripts/manual_cli_checks`` runnable, and its CLI matrix
complete: a new subcommand or option the matrix plan does not classify
fails here, in every CI run, not only when someone runs the checks.
"""

import importlib
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from tests.build_and_read_shared import pitloom_subprocess_env


def _run(scripts_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = pitloom_subprocess_env()
    env.pop("PITLOOM_DEBUG", None)
    return subprocess.run(  # nosec B603
        [sys.executable, str(scripts_dir / "manual_cli_checks"), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def test_lists_unique_check_ids(scripts_dir: Path) -> None:
    result = _run(scripts_dir, "--list")
    assert result.returncode == 0, result.stderr
    ids = [line.split()[0] for line in result.stdout.splitlines()]
    assert len(ids) == len(set(ids)), "duplicate check ids"
    # Non-vacuous: every kind of check is registered.
    for expected in (
        "1",
        "B1",
        "S1",
        "M/completeness",
        "M/project/debug/--debug+PITLOOM_DEBUG=0",
    ):
        assert expected in ids


def test_matrix_plan_covers_the_cli_and_fast_checks_pass(scripts_dir: Path) -> None:
    result = _run(
        scripts_dir, "--only", "M/completeness,1,B7,M/project/debug/*", "-j", "4", "-v"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS  M/completeness" in result.stdout
    assert " 0 fail" in result.stdout.splitlines()[-1]


# `manual_cli_checks` is not an importable package -- like `__main__.py`
# itself, `_matrix.py` and its siblings do plain `import _fixtures` /
# `from _harness import ...`, resolved by having their own directory
# first on `sys.path` (as running `python scripts/manual_cli_checks`
# does). Load them that way here too, restoring `sys.path`/`sys.modules`
# afterwards so this doesn't leak into other tests.
_MATRIX_SIBLINGS = ("_matrix", "_matrix_run", "_matrix_plan", "_harness", "_fixtures")


@dataclass(frozen=True)
class _MatrixEnv:
    """The ``_matrix``/``_harness`` sibling modules, loaded in-process."""

    matrix: ModuleType
    harness: ModuleType


@pytest.fixture(name="matrix_env")
def matrix_env_fixture(scripts_dir: Path) -> Iterator[_MatrixEnv]:
    checks_dir = str(scripts_dir / "manual_cli_checks")
    path_added = checks_dir not in sys.path
    if path_added:
        sys.path.insert(0, checks_dir)
    previous = {name: sys.modules.pop(name, None) for name in _MATRIX_SIBLINGS}
    try:
        yield _MatrixEnv(
            importlib.import_module("_matrix"), importlib.import_module("_harness")
        )
    finally:
        for name in _MATRIX_SIBLINGS:
            sys.modules.pop(name, None)
            restore = previous[name]
            if restore is not None:
                sys.modules[name] = restore
        if path_added:
            sys.path.remove(checks_dir)


# Only ("loom", "--debug") is the case under test; ("sub", "--offline")
# just needs *some* plan entry so it does not itself show up as missing.
_PARENT_OPTION_PLAN = {
    ("loom", "--debug"): "group:offline",
    ("sub", "--offline"): "group:offline",
}


@pytest.mark.parametrize(
    ("subcommand_declares_offline", "expect_covered"),
    [
        pytest.param(False, False, id="no-subcommand-runs-the-group"),
        pytest.param(True, True, id="one-subcommand-runs-the-group"),
    ],
)
def test_completeness_needs_a_subcommand_to_actually_run_the_group(
    matrix_env: _MatrixEnv,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    subcommand_declares_offline: bool,
    expect_covered: bool,
) -> None:
    """``M/completeness`` (``_cell_completeness`` in ``_matrix.py``) must
    treat a parent-parser-only option (e.g. ``loom``'s ``--debug``, which
    runs no cells of its own) as covered only while some subcommand's own
    cells actually run the group it maps to -- not merely because the
    parent itself has no ``Command`` entry (b167dfe).

    ``--offline`` stands in as the group here: ``_group_cells``'s debug
    cells run unconditionally for every ``Command``, so the real
    ``debug`` group can never exercise the "nobody runs it" branch this
    guards against.
    """
    surface = {
        "loom": [["--debug"]],
        "sub": [["--offline"]] if subcommand_declares_offline else [],
    }
    mx = matrix_env.matrix.Matrix(surface)
    monkeypatch.setattr(
        matrix_env.matrix,
        "COMMANDS",
        [matrix_env.matrix.Command("sub", lambda _fx, _cell: [], "stdout")],
    )
    monkeypatch.setattr(
        matrix_env.matrix,
        "plan_for",
        lambda cmd, opt: _PARENT_OPTION_PLAN.get((cmd, opt)),
    )
    # White-box: the completeness rule has no public entry point of its
    # own, and running it for real means a full `loom` invocation per
    # cell -- exactly what this synthetic matrix avoids.
    run = matrix_env.matrix._cell_completeness(mx)  # pylint: disable=protected-access
    ctx = matrix_env.harness.Context(work=tmp_path, network=False, verbose=False)

    if expect_covered:
        run(ctx)  # does not raise: "loom: --debug" is reported as covered
    else:
        with pytest.raises(matrix_env.harness.CheckFailed, match=r"loom: --debug"):
            run(ctx)


def test_child_env_makes_pythonpath_absolute(
    matrix_env: _MatrixEnv, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Checks run ``loom`` in scratch dirs: a relative ``PYTHONPATH=src``
    must still select the runner's ``pitloom``, not fall back to one the
    interpreter has installed from another checkout."""
    base = tmp_path.resolve()
    (base / "pkgs").mkdir()
    (base / "pkgs" / "mcc_probe_mod.py").write_text("", encoding="utf-8")
    other = base / "other"
    other.mkdir()
    monkeypatch.chdir(base)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["pkgs", "", str(other)]))

    env = matrix_env.harness.child_env()

    # An empty entry is the current directory, for Python as for abspath().
    assert env["PYTHONPATH"].split(os.pathsep) == [
        str(base / "pkgs"),
        str(base),
        str(other),
    ]
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import mcc_probe_mod; print(mcc_probe_mod.__file__)"],
        env=env,
        cwd=other,
        capture_output=True,
        text=True,
        check=True,
    )
    assert Path(proc.stdout.strip()).resolve() == base / "pkgs" / "mcc_probe_mod.py"
    # An empty PYTHONPATH adds nothing; it must not become the cwd.
    monkeypatch.setenv("PYTHONPATH", "")
    assert matrix_env.harness.child_env()["PYTHONPATH"] == ""
