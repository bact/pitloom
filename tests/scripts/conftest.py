# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for testing the helper scripts under ``scripts/``.

The scripts are not an importable package (they also run standalone on the
GitHub Actions runner), so each is loaded by file path.
"""

import importlib
import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(name="scripts_dir")
def scripts_dir_fixture() -> Path:
    """The repository's ``scripts/`` directory."""
    return SCRIPTS_DIR


@pytest.fixture(name="load_script")
def load_script_fixture() -> Callable[[str], ModuleType]:
    """Return a loader: ``load_script("action/python_probe")``."""

    def load(name: str) -> ModuleType:
        path = SCRIPTS_DIR / f"{name}.py"
        module_name = "scripts_" + name.replace("/", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        # NamedTuple/dataclass resolution needs the module registered.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    return load


@pytest.fixture(name="mcc")
def mcc_fixture(scripts_dir: Path, tmp_path: Path) -> Iterator[dict[str, ModuleType]]:
    """The order-matrix modules, loaded as the runner loads them (their
    directory first on ``sys.path``), with fixtures under *tmp_path*."""
    checks_dir = scripts_dir / "manual_cli_checks"
    names = {p.stem for p in checks_dir.glob("_*.py")}
    previous = {name: sys.modules.pop(name, None) for name in names}
    sys.path.insert(0, str(checks_dir))
    try:
        mods = {
            name: importlib.import_module(name)
            for name in (
                "_fixtures",
                "_harness",
                "_order_capture",
                "_order_fixtures",
                "_order_gen",
                "_order_invariants",
                "_order_known",
                "_order_ops",
                "_checks_order",
            )
        }
        mods["_fixtures"].install(mods["_fixtures"].Fixtures(tmp_path / "fx"))
        yield mods
    finally:
        sys.path.remove(str(checks_dir))
        for name in names:
            sys.modules.pop(name, None)
            restore = previous[name]
            if restore is not None:
                sys.modules[name] = restore
