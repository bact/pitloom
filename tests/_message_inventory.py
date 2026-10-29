# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Load ``scripts/message_inventory`` (a package of relative imports) the way
the other script tests load a script: by path, with no ``scripts`` package
and nothing added to ``sys.path``.

See also: ``tests/test_message_ratchet.py`` and
``tests/scripts/message_inventory/`` (the tool's tests).
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "scripts" / "message_inventory"
NAME = "message_inventory"


def load() -> ModuleType:
    """The package, loaded once per process as ``message_inventory``."""
    module = sys.modules.get(NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(
        NAME,
        PACKAGE_DIR / "__init__.py",
        submodule_search_locations=[str(PACKAGE_DIR)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {PACKAGE_DIR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[NAME] = module
    spec.loader.exec_module(module)
    return module


def load_main() -> ModuleType:
    """The package's ``__main__`` module (its ``main(argv)``)."""
    load()
    return importlib.import_module(f"{NAME}.__main__")
