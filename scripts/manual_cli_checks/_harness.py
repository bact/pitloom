# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared plumbing for the manual CLI checks: running ``loom`` as a real
process, fixture projects, SBOM comparison helpers and the check registry.

See also: ``__main__.py`` (the runner), ``_checks_core.py`` and
``_checks_build.py`` (the checks).
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
DATETIME = "2026-01-01T00:00:00Z"
TAGS = ("ERROR: ", "WARNING: ", "INFO: ")
DEBUG_TAGS = (*TAGS, "DEBUG: ")
# Env vars that change what `loom` prints or writes, or whether it
# reaches the network.
_SCRUBBED_ENV = (
    "PITLOOM_DEBUG",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "SOURCE_DATE_EPOCH",
)


# Blocks every socket connection/lookup and reports it on stderr, so a
# check can count network attempts without a firewall.
NETGUARD = """
import socket, sys
def _blocked(name):
    def _guard(*args, **kwargs):
        sys.stderr.write("NETGUARD: blocked " + name + "\\n")
        raise OSError("NETGUARD: network access blocked")
    return _guard
socket.socket.connect = _blocked("connect")
socket.create_connection = _blocked("create_connection")
socket.getaddrinfo = _blocked("getaddrinfo")
"""
NETGUARD_MARK = "NETGUARD: blocked"
# Reports, at exit, the level the run configured for the "pitloom" logger
# (10 = DEBUG, 20 = INFO, 0 = never configured): the debug decision
# itself, observable even when nothing was logged at DEBUG.
LEVEL_PROBE = """
import atexit, logging, sys
atexit.register(lambda: sys.stderr.write(
    "PROBE: pitloom-log-level=%d\\n" % logging.getLogger("pitloom").level))
"""
_PROBE_MARK = "PROBE: pitloom-log-level="


class CheckFailed(Exception):
    """A check's expectation did not hold."""


class CheckSkipped(Exception):
    """A check cannot run here (platform, missing extra, no --network)."""


@dataclass(frozen=True)
class Check:
    """One manual check, numbered as in manual-cli-checks.md."""

    check_id: str
    title: str
    func: CheckFunc
    network: bool = False


@dataclass
class Context:
    """What every check gets: a private scratch dir and runner options."""

    work: Path
    network: bool
    verbose: bool
    notes: list[str] = field(default_factory=list)

    def note(self, text: str) -> None:
        """Record a detail printed under the check's result line."""
        self.notes.append(text)


CheckFunc = Callable[[Context], None]
CHECKS: list[Check] = []


def check(
    check_id: str, title: str, *, network: bool = False
) -> Callable[[Callable[[Context], None]], Callable[[Context], None]]:
    """Register a check function under *check_id*."""

    def _register(func: Callable[[Context], None]) -> Callable[[Context], None]:
        CHECKS.append(Check(check_id, title, func, network))
        return func

    return _register


def expect(condition: bool, message: str) -> None:
    """Fail the current check with *message* unless *condition* holds."""
    if not condition:
        raise CheckFailed(message)


def require(value: str | None, message: str) -> str:
    """*value*, or fail the current check with *message* if it is None."""
    if value is None:
        raise CheckFailed(message)
    return value


@dataclass(frozen=True)
class Result:
    """A finished ``loom`` run."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed: float

    @property
    def stderr_lines(self) -> list[str]:
        """Non-blank stderr lines, minus the network guard's own."""
        return [
            line
            for line in self.stderr.splitlines()
            if line.strip() and not line.startswith((NETGUARD_MARK, _PROBE_MARK))
        ]

    @property
    def log_level(self) -> int | None:
        """The level :data:`LEVEL_PROBE` reported, if it ran."""
        for line in self.stderr.splitlines():
            if line.startswith(_PROBE_MARK):
                return int(line[len(_PROBE_MARK) :])
        return None

    @property
    def network_attempts(self) -> int:
        """Connections/lookups the network guard blocked."""
        return self.stderr.count(NETGUARD_MARK)

    def describe(self) -> str:
        """The command, exit code and stderr tail, for a failure message."""
        tail = "\n".join(self.stderr_lines[-15:])
        return f"`loom {' '.join(self.argv)}` exited {self.returncode}\n{tail}"


def child_env(**extra: str) -> dict[str, str]:
    """``os.environ`` minus the scrubbed vars, plus *extra*, with
    ``PYTHONPATH`` made absolute.

    Children run in scratch dirs: a relative entry (``PYTHONPATH=src``)
    would resolve there, find nothing, and silently fall back to whatever
    ``pitloom`` the interpreter has installed -- possibly another checkout.
    """
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED_ENV}
    env.update(extra)
    if env.get("PYTHONPATH"):
        # An empty entry means the current directory, as abspath("") does.
        env["PYTHONPATH"] = os.pathsep.join(
            os.path.abspath(p) for p in env["PYTHONPATH"].split(os.pathsep)
        )
    return env


def loom_argv(*args: str, bootstrap: str | None = None) -> list[str]:
    """The argv running ``loom`` under this interpreter; *bootstrap* is
    Python code run first (e.g. a network guard), then ``loom`` itself."""
    if bootstrap is None:
        return [sys.executable, "-m", "pitloom", *args]
    runner = "import runpy; runpy.run_module('pitloom', run_name='__main__')"
    return [sys.executable, "-c", f"{bootstrap}\n{runner}", *args]


def run_loom(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: float = 300,
    bootstrap: str | None = None,
    cwd: Path | None = None,
) -> Result:
    """Run ``loom *args`` to completion with stdin closed."""
    start = time.monotonic()
    proc = subprocess.run(  # nosec B603
        loom_argv(*args, bootstrap=bootstrap),
        env=child_env() if env is None else env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=cwd,
    )
    return Result(
        list(args),
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
        time.monotonic() - start,
    )


def run_ok(
    *args: str, env: dict[str, str] | None = None, network: bool = False
) -> Result:
    """Run ``loom *args`` and fail the check unless it exits 0 -- and,
    unless *network*, behind the network guard with no attempt."""
    result = run_loom(*args, env=env, bootstrap=None if network else NETGUARD)
    expect(result.returncode == 0, result.describe())
    expect(
        result.network_attempts == 0,
        f"{result.network_attempts} network attempts:\n{result.describe()}",
    )
    return result


def expect_tagged(result: Result, tags: tuple[str, ...] = TAGS) -> None:
    """Every stderr line starts with exactly one level tag."""
    untagged = [line for line in result.stderr_lines if not line.startswith(tags)]
    expect(not untagged, f"untagged stderr lines: {untagged[:5]}")


def embedded_sboms(wheel: Path) -> dict[str, bytes]:
    """The SBOMs embedded in *wheel* (PEP 770 ``.dist-info/sboms/``)."""
    with zipfile.ZipFile(wheel) as zf:
        return {n: zf.read(n) for n in zf.namelist() if ".dist-info/sboms/" in n}


def load_graph(path: Path | bytes) -> list[dict[str, Any]]:
    """The ``@graph`` of an SPDX 3 JSON-LD document."""
    raw = path if isinstance(path, bytes) else path.read_bytes()
    graph = json.loads(raw)["@graph"]
    expect(isinstance(graph, list), "@graph is not a list")
    return cast("list[dict[str, Any]]", graph)


def without_creation_info(graph: Iterable[dict[str, Any]]) -> list[str]:
    """The graph's elements as sorted canonical JSON, CreationInfo
    elements dropped (they legitimately differ by invocation)."""
    return sorted(
        json.dumps(element, sort_keys=True)
        for element in graph
        if element.get("type") != "CreationInfo"
    )


def package(graph: Iterable[dict[str, Any]], name: str) -> dict[str, Any]:
    """The ``software_Package`` element named *name*."""
    for element in graph:
        if element.get("type") == "software_Package" and element.get("name") == name:
            return element
    raise CheckFailed(f"no software_Package named {name!r}")


def file_names(graph: Iterable[dict[str, Any]]) -> list[str]:
    """Sorted ``software_File`` names outside ``.dist-info/``."""
    return sorted(
        element["name"]
        for element in graph
        if element.get("type") == "software_File"
        and ".dist-info/" not in element.get("name", "")
    )
