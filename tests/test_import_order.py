# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every ``pitloom`` module imports cleanly as the first Pitloom import.

An import cycle only fails when a module on it is imported first, so a
suite that always starts from ``pitloom`` or ``pitloom.loom`` never sees
it. Each child process walks its modules and, before importing each,
drops all ``pitloom`` entries from :data:`sys.modules` -- the same state
as a fresh interpreter, at a fraction of the cost of one process each.

Two modes:

- ``root``: the real package. Importing any ``pitloom.X`` runs
  ``pitloom/__init__.py`` first, so a module that ``import pitloom``
  already loads can only be imported in that one order; one ``import
  pitloom`` covers all of those, and only the rest are imported singly.
- ``bare``: ``pitloom`` is an empty package, so each module is reached
  through its own imports only. This finds a cycle that works today
  only because ``pitloom/__init__.py`` happens to import one side first,
  and would break the day that import order changes.
"""

from __future__ import annotations

import contextlib
import json
import os
import pkgutil
import subprocess  # nosec B404
import sys
from pathlib import Path

import pitloom

#: Modules on the ``pitloom.assemble`` facade <-> ``pitloom.embed`` cycle:
#: ``assemble/__init__.py`` re-exports ``embed``'s API, and ``embed``
#: needs ``assemble.spdx3``. Only the ``bare`` mode sees it. Remove an
#: entry once the cycle is gone -- the exact match below insists on it.
_BARE_ROOT_KNOWN_FAILURES = frozenset(
    {"pitloom._embed_build_sbom", "pitloom._embed_generate", "pitloom.embed"}
)

_CHILD = """
import importlib, json, os, sys, traceback, types
mode, src_root, names_file = sys.argv[1:4]
sys.path.insert(0, src_root)
root_path = [os.path.join(src_root, "pitloom")]
failures, tried, by_root = {}, [], set()
with open(names_file, encoding="utf-8") as f:
    names = json.load(f)
if mode == "root":
    names = ["pitloom", *names]
for name in names:
    if name in by_root:
        continue
    for loaded in [m for m in sys.modules if m.split(".")[0] == "pitloom"]:
        del sys.modules[loaded]
    if mode == "bare":
        bare = types.ModuleType("pitloom")
        bare.__path__ = root_path
        sys.modules["pitloom"] = bare
    tried.append(name)
    try:
        importlib.import_module(name)
    except Exception:  # every failure is reported, not just ImportError
        failures[name] = traceback.format_exc(limit=-3)
    if mode == "root" and name == "pitloom":
        by_root = {m for m in sys.modules if m.split(".")[0] == "pitloom"}
print(json.dumps({"failures": failures, "tried": tried}))
"""

#: One child's result: the modules it imported first, and the traceback
#: of each that failed.
_Report = tuple[list[str], dict[str, str]]


def _all_module_names() -> list[str]:
    prefix = pitloom.__name__ + "."
    names = [m.name for m in pkgutil.walk_packages(pitloom.__path__, prefix)]
    return sorted([pitloom.__name__, *names])


def _run_children(jobs: list[tuple[str, list[str]]], work_dir: Path) -> list[_Report]:
    """Run one child per ``(mode, names)`` job, all at once."""
    src_root = str(Path(pitloom.__file__).resolve().parents[1])
    reports: list[_Report] = []
    with contextlib.ExitStack() as stack:
        procs = []
        for index, (mode, names) in enumerate(jobs):
            names_file = work_dir / f"names-{index}.json"
            names_file.write_text(json.dumps(names), encoding="utf-8")
            cmd = [sys.executable, "-c", _CHILD, mode, src_root, str(names_file)]
            proc = stack.enter_context(
                subprocess.Popen(  # nosec B603
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
            )
            # Runs before Popen.__exit__ waits, so a hung child cannot
            # outlive the timeout below.
            stack.callback(proc.kill)
            procs.append(proc)
        for proc in procs:
            out, err = proc.communicate(timeout=300)
            assert proc.returncode == 0, err
            report = json.loads(out.strip().splitlines()[-1])
            reports.append((report["tried"], report["failures"]))
    return reports


def _describe(failures: dict[str, str]) -> str:
    return "\n".join(f"{name}:\n{tb}" for name, tb in failures.items())


def test_every_module_imports_first(tmp_path: Path) -> None:
    """Each module, imported first, succeeds (import-cycle regression)."""
    names = _all_module_names()
    workers = max(1, min(4, (os.cpu_count() or 1) - 1))
    jobs = [("root", names)] + [("bare", names[i::workers]) for i in range(workers)]
    (root_tried, root_failures), *bare = _run_children(jobs, tmp_path)

    # Guard against a vacuous pass: the module whose cycle this test was
    # written for is imported on its own, and bare mode tries every module.
    assert "pitloom._loom_active_run" in root_tried
    assert sorted(name for tried, _ in bare for name in tried) == names

    assert not root_failures, _describe(root_failures)
    bare_failures = {name: tb for _, failures in bare for name, tb in failures.items()}
    unexpected = {
        name: tb
        for name, tb in bare_failures.items()
        if name not in _BARE_ROOT_KNOWN_FAILURES
    }
    assert not unexpected, _describe(unexpected)
    assert set(bare_failures) == _BARE_ROOT_KNOWN_FAILURES
