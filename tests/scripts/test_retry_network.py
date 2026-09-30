# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/retry_network.py``, the build workflow's network retry
around ``spdx3-validate`` and ``loom validate-wheel``."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_NETWORK = (
    "Traceback (most recent call last):\n"
    "urllib.error.URLError: <urlopen error [Errno 104] Connection reset by peer>"
)
_CLI_NETWORK = "ERROR: validate-wheel failed: <urlopen error [Errno 61] refused>"
# A validator finding quoting network-like words is still a finding.
_FINDING = "[shacl] Value Node: 'Request timed out'\nURLError: nope"


@pytest.fixture(name="module")
def module_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("retry_network")


def _stub(tmp_path: Path, outputs: list[tuple[int, str]]) -> list[str]:
    """Argv of a command whose n-th run prints/exits as ``outputs[n]``."""
    counter = tmp_path / "count"
    script = tmp_path / "stub.py"
    script.write_text(
        "import pathlib, sys\n"
        f"outputs = {outputs!r}\n"
        f"c = pathlib.Path({str(counter)!r})\n"
        "n = int(c.read_text()) if c.exists() else 0\n"
        "c.write_text(str(n + 1))\n"
        "code, text = outputs[min(n, len(outputs) - 1)]\n"
        'sys.stderr.buffer.write(text.encode() + b"\\n")\n'
        "sys.exit(code)\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def _runs(tmp_path: Path) -> int:
    return int((tmp_path / "count").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("outputs", "expected", "runs"),
    [
        pytest.param([(0, "ok")], 0, 1, id="pass"),
        pytest.param([(1, _NETWORK), (0, "ok")], 0, 2, id="network-then-pass"),
        pytest.param([(1, _CLI_NETWORK), (1, "bad")], 1, 2, id="network-then-invalid"),
        pytest.param([(1, _NETWORK)], 75, 3, id="network-every-time"),
        pytest.param([(1, "[schema] bad")], 1, 1, id="invalid-no-retry"),
        pytest.param([(1, _FINDING)], 1, 1, id="finding-quoting-network-words"),
        pytest.param([(2, "Traceback\nValueError: x")], 1, 1, id="crash-no-retry"),
    ],
)
def test_retries_only_network_failures(
    module: ModuleType,
    tmp_path: Path,
    outputs: list[tuple[int, str]],
    expected: int,
    runs: int,
) -> None:
    command = _stub(tmp_path, outputs)
    assert module.main(["--attempts", "3", "--delay", "0", "--", *command]) == expected
    assert _runs(tmp_path) == runs


def test_timeout_counts_as_network(module: ModuleType) -> None:
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    rc = module.main(
        ["--attempts", "2", "--delay", "0", "--timeout", "0.5", "--", *command]
    )
    assert rc == module.EXIT_NETWORK


def test_backoff_triples(
    module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(module, "sleep", sleeps.append)
    command = _stub(tmp_path, [(1, _NETWORK)])
    assert module.main(["--attempts", "3", "--delay", "10", "--", *command]) == 75
    assert sleeps == [10, 30]


def test_output_fenced_against_workflow_commands(
    module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    command = _stub(tmp_path, [(0, "::error::injected")])
    assert module.main(["--", *command]) == 0
    lines = capsys.readouterr().out.splitlines()
    start = lines[0].removeprefix("::stop-commands::")
    assert start != lines[0] and len(start) == 32
    assert lines.index("::error::injected") < lines.index(f"::{start}::")


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no-command"),
        pytest.param(["--"], id="empty-after-separator"),
        pytest.param(["--attempts", "0", "--", "x"], id="zero-attempts"),
        pytest.param(["--timeout", "0", "--", "x"], id="zero-timeout"),
        pytest.param(["--delay", "-1", "--", "x"], id="negative-delay"),
    ],
)
def test_usage_errors(module: ModuleType, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        module.main(argv)
    assert exc.value.code == 2


def test_standalone_exit_status(scripts_dir: Path, tmp_path: Path) -> None:
    """Run as the workflow does: a separate process, from any directory."""
    command = _stub(tmp_path, [(1, _NETWORK)])
    res = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "retry_network.py"),
            "--delay",
            "0",
            "--attempts",
            "2",
            "--",
            *command,
        ],
        capture_output=True,
        cwd=tmp_path,
        check=False,
    )
    assert res.returncode == 75, res.stdout + res.stderr
    assert b"all 2 attempts failed because of the network" in res.stdout


@pytest.mark.parametrize(
    ("outputs", "expected"),
    [
        pytest.param([(0, "✔ valid")], 0, id="pass"),
        pytest.param([(1, _NETWORK + " ✔")], 75, id="network-cause-line"),
    ],
)
def test_non_ascii_output_on_cp1252_stdout(
    scripts_dir: Path,
    tmp_path: Path,
    outputs: list[tuple[int, str]],
    expected: int,
) -> None:
    """A Windows runner's cp1252 stdout must not turn a verdict into a crash."""
    command = _stub(tmp_path, outputs)
    res = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "retry_network.py"),
            "--delay",
            "0",
            "--attempts",
            "2",
            "--",
            *command,
        ],
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
        check=False,
    )
    assert res.returncode == expected, res.stdout + res.stderr
    assert "✔".encode() in res.stdout
