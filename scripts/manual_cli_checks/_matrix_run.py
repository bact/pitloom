# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Running one matrix cell: the CLI surface read from the real parser,
``loom`` with the matrix defaults behind the network guard and log-level
probe, the artefact a cell compares, and the universal invariants.

See also: ``_matrix.py`` (the cells), ``_matrix_plan.py`` (the plan).
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import sys
import threading
from pathlib import Path
from typing import Any

import _fixtures
from _harness import (
    DATETIME,
    DEBUG_TAGS,
    LEVEL_PROBE,
    NETGUARD,
    TAGS,
    Result,
    child_env,
    embedded_sboms,
    expect,
    require,
    run_loom,
)
from _matrix_plan import Command

DATETIME_2 = "2026-02-02T00:00:00Z"
_SURFACE_CODE = """
import argparse, json
from pitloom.cli.parser import _build_parser
out = {}
def walk(parser, prefix):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    opts = []
    for a in parser._actions:
        if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        opts.append(list(a.option_strings) or ["<" + a.dest + ">"])
    out[prefix or "loom"] = opts
    for s in subs:
        for name, sp in s.choices.items():
            walk(sp, (prefix + " " + name).strip())
walk(_build_parser(), "")
print(json.dumps(out))
"""


def cli_surface() -> dict[str, list[list[str]]]:
    """Every (sub)command's options, each as its list of spellings, read
    from the real parser of the ``pitloom`` under test."""
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-c", _SURFACE_CODE],
        capture_output=True,
        text=True,
        check=True,
        env=child_env(),
    )
    surface: dict[str, list[list[str]]] = json.loads(proc.stdout)
    return surface


class Matrix:
    """The CLI surface, and cells run against it (with cached plain runs)."""

    def __init__(self, surface: dict[str, list[list[str]]]) -> None:
        self.surface = surface
        self.spellings = {
            cmd: {s for opt in opts for s in opt} for cmd, opts in surface.items()
        }
        self._lock = threading.Lock()
        self._baselines: dict[str, tuple[int, str | None]] = {}
        # A failed baseline fails every cell compared against it the same way.
        self._baseline_failures: dict[str, Exception] = {}

    def takes(self, command: Command, option: str) -> bool:
        return option in self.spellings.get(command.name, set())

    # pylint: disable-next=too-many-arguments
    def run(
        self,
        command: Command,
        cell: Path,
        *,
        pre: tuple[str, ...] = (),
        extra: tuple[str, ...] = (),
        env: dict[str, str] | None = None,
        output: bool = True,
        offline: bool = True,
        dated: bool = True,
        network: bool = False,
    ) -> tuple[Result, str | None]:
        """Run *command* in *cell* with the matrix defaults; return the
        result and the normalised artefact. *network* (or a network
        command) runs without the network guard."""
        cell.mkdir(parents=True, exist_ok=True)
        args = [*pre, *command.name.split(), *command.target(_fixtures.get(), cell)]
        if output and command.artefact == "output":
            args += ["-o", "out.json"]
        if offline and self.takes(command, "--offline"):
            args.append("--offline")
        if dated and self.takes(command, "--creation-datetime"):
            args += ["--creation-datetime", DATETIME]
        args += extra
        guarded = not (network or command.network)
        result = run_loom(
            *args,
            env=env or child_env(),
            cwd=cell,
            bootstrap=(NETGUARD if guarded else "") + LEVEL_PROBE,
        )
        return result, artefact(command, cell, result)

    def baseline(self, command: Command) -> tuple[int, str | None]:
        with self._lock:
            if command.name in self._baseline_failures:
                raise self._baseline_failures[command.name]
            if command.name not in self._baselines:
                cell = (
                    _fixtures.get().root / "baselines" / command.name.replace(" ", "-")
                )
                try:
                    result, plain = self.run(command, cell)
                    universal(result, debug=False, network_ok=command.network)
                    # Cells compare against it: a failing plain run would
                    # make "same as the baseline" vacuous.
                    expect(result.returncode == 0, f"baseline: {result.describe()}")
                except Exception as exc:
                    self._baseline_failures[command.name] = exc
                    raise
                self._baselines[command.name] = (result.returncode, plain)
            return self._baselines[command.name]


_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


def normalise(text: str, cell: Path) -> str:
    """Cell paths, and random (version 4) UUIDs, which only `id generate`
    mints (a fresh registry's namespace), made comparable."""
    text = text.replace(str(cell.resolve()), "<CELL>").replace(str(cell), "<CELL>")
    return _UUID4.sub("<UUID4>", text)


def artefact(command: Command, cell: Path, result: Result) -> str | None:
    if command.artefact == "stdout":
        return normalise(result.stdout, cell)
    path: Path | None = None
    if command.artefact == "output":
        path = cell / "out.json"
    elif command.artefact == "registry":
        path = cell / "reg.json"
    elif command.artefact == "wheel-sbom":
        wheels = sorted(cell.glob("*.whl"))
        if not wheels:
            return None
        sboms = embedded_sboms(wheels[0])
        text = "\n".join(sboms) + "\n" + "".join(v.decode() for v in sboms.values())
        return normalise(text, cell)
    if path is None or not path.exists():
        return None
    return normalise(path.read_text(encoding="utf-8"), cell)


def universal(result: Result, *, debug: bool, network_ok: bool = False) -> None:
    expect(
        "Traceback (most recent call last)" not in result.stderr,
        f"traceback:\n{result.describe()}",
    )
    tags = DEBUG_TAGS if debug else TAGS
    untagged = [line for line in result.stderr_lines if not line.startswith(tags)]
    expect(not untagged, f"untagged stderr lines: {untagged[:4]}")
    if not network_ok:
        expect(
            result.network_attempts == 0,
            f"{result.network_attempts} network attempts:\n{result.describe()}",
        )


def created(text: str | None) -> list[str]:
    text = require(text, "no SBOM written")
    start = text.find("{")
    doc: Any = json.loads(text[start:])
    return sorted(
        e["created"] for e in doc["@graph"] if e.get("type") == "CreationInfo"
    )
