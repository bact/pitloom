# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for the matrix and sequence checks, built once per run and
copied into each cell's own directory, so no cell sees another's side
effects (an embedded SBOM, an updated registry, a default output file).

See also: ``_matrix.py``, ``_sequences.py``.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import struct
import subprocess  # nosec B404
import sys
import textwrap
import threading
from collections.abc import Callable
from pathlib import Path

from _harness import DATETIME, REPO_ROOT, CheckSkipped, child_env, expect, run_loom

MODEL = "tiny.safetensors"
SOURCE_DATE_EPOCH = "1767225600"  # DATETIME as a Unix timestamp

_PYPROJECT = textwrap.dedent(
    """
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"

    [project]
    name = "demo"
    version = "0.1"
    description = "Manual CLI check fixture"
    dependencies = ["packaging>=20"]

    [tool.hatch.build.targets.wheel]
    packages = ["demo"]
    """
)


def write_project(root: Path, *, hook: bool = False) -> Path:
    """A small Hatchling project ``demo`` 0.1 with a dependency, an SPDX
    header and a tiny AI model referenced by a script; *hook* enables the
    Pitloom build hook."""
    (root / "demo").mkdir(parents=True)
    # An SPDX header, so --extract-file-header has something to find.
    (root / "demo" / "__init__.py").write_text(
        "# SPDX-FileCopyrightText: 2026 Demo Author\n"
        "# SPDX-License-Identifier: MIT\nx = 1\n",
        encoding="utf-8",
    )
    (root / "demo" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    # A model plus a script naming it: an AIPackage and a usage reference.
    _write_model(root / "demo" / MODEL)
    (root / "demo" / "load.py").write_text(f'MODEL = "{MODEL}"\n', encoding="utf-8")
    hook_table = "\n[tool.hatch.build.hooks.pitloom]\n" if hook else ""
    (root / "pyproject.toml").write_text(_PYPROJECT + hook_table, encoding="utf-8")
    return root


def _write_model(path: Path) -> None:
    """A one-tensor safetensors file (readable with no optional extra)."""
    header = json.dumps(
        {"t": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}
    ).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\0" * 4)


def build_wheel(project: Path, out: Path) -> Path:
    """Build *project*'s wheel offline (``--no-isolation``) with a pinned
    ``SOURCE_DATE_EPOCH``; skip without ``build``/``hatchling``."""
    for module in ("build", "hatchling"):
        if importlib.util.find_spec(module) is None:
            raise CheckSkipped(f"needs '{module}' installed (pitloom[build])")
    proc = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(out),
            str(project),
        ],
        env=child_env(SOURCE_DATE_EPOCH=SOURCE_DATE_EPOCH),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=300,
        check=False,
    )
    expect(proc.returncode == 0, f"wheel build failed: {proc.stderr[-1500:]!r}")
    (wheel,) = out.glob("*.whl")
    return wheel


class Fixtures:
    """Lazily built, shared, read-only fixtures; :meth:`stage` copies one
    into a cell's directory for it to use (and modify)."""

    def __init__(self, root: Path) -> None:
        self._root = root
        # Re-entrant: building one fixture gets another (wheel -> project).
        self._lock = threading.RLock()
        self._built: dict[str, Path] = {}
        # A failed or skipped build: every later user gets the same outcome.
        self._failed: dict[str, Exception] = {}
        self._builders: dict[str, Callable[[Path], Path]] = {
            "project": self._project,
            "wheel": self._wheel,
            "embedded-wheel": self._embedded_wheel,
            "hook-wheel": self._hook_wheel,
            "model": self._model,
            "fragments": self._fragments,
            "sbom": self._sbom,
        }

    @property
    def root(self) -> Path:
        """Where the fixtures (and matrix baselines) live."""
        return self._root

    def get(self, name: str) -> Path:
        """The shared fixture *name*, built on first use. Never modify it."""
        with self._lock:
            if name in self._failed:
                raise self._failed[name]
            if name not in self._built:
                target = self._root / name
                target.mkdir(parents=True)
                try:
                    self._built[name] = self._builders[name](target)
                except Exception as exc:
                    self._failed[name] = exc
                    raise
            return self._built[name]

    def stage(self, name: str, cell_dir: Path) -> Path:
        """A private copy of fixture *name* inside *cell_dir*."""
        source = self.get(name)
        dest = cell_dir / source.name
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        return dest

    def _project(self, target: Path) -> Path:
        project = target / "demo-project"
        write_project(project)
        return project

    def _wheel(self, target: Path) -> Path:
        return build_wheel(self.get("project"), target)

    def _hook_wheel(self, target: Path) -> Path:
        project = target / "demo-project"
        write_project(project, hook=True)
        return build_wheel(project, target / "dist")

    def _embedded_wheel(self, target: Path) -> Path:
        wheel = target / self.get("wheel").name
        shutil.copy2(self.get("wheel"), wheel)
        result = run_loom(
            "embed-wheel",
            str(wheel),
            "--project-dir",
            str(self.get("project")),
            "--offline",
            "--creation-datetime",
            DATETIME,
        )
        expect(result.returncode == 0, result.describe())
        return wheel

    def _model(self, target: Path) -> Path:
        model = target / MODEL
        _write_model(model)
        return model

    def _fragments(self, target: Path) -> Path:
        fragments = target / "fragments"
        fragments.mkdir()
        source = REPO_ROOT / "tests" / "fixtures" / "fragments"
        for path in sorted(source.glob("*.spdx3.json")):
            shutil.copy2(path, fragments / path.name)
        return fragments

    def _sbom(self, target: Path) -> Path:
        sbom = target / "demo.spdx3.json"
        result = run_loom(
            "project",
            str(self.get("project")),
            "-o",
            str(sbom),
            "--offline",
            "--creation-datetime",
            DATETIME,
        )
        expect(result.returncode == 0, result.describe())
        return sbom


_current: list[Fixtures] = []


def install(fixtures: Fixtures) -> None:
    """Make *fixtures* the run's shared fixtures (see :func:`get`)."""
    _current[:] = [fixtures]


def get() -> Fixtures:
    """The run's shared fixtures, installed by the runner."""
    if not _current:
        raise RuntimeError("no fixtures installed")
    return _current[0]
