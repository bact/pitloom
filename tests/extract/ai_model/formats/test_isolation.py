# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The format readers import the standard library and each other only, so
the package can leave Pitloom as it is: checked in the source (every import
statement) and live (imported with the rest of Pitloom blocked).

See also: :mod:`tests.extract.ai_model.formats.test_pickle_walk`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import ast
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

from pitloom.extract.ai_model import formats

_PACKAGE = formats.__name__
_DIR = Path(formats.__file__).parent
_MODULES = sorted(_DIR.rglob("*.py"))


def _imports(path: Path) -> list[tuple[int, str]]:
    """``(level, module)`` of every import in *path*, statements and
    ``importlib.import_module``/``__import__`` calls alike; level 0 is
    absolute. A dynamic call whose name is not a literal is ``(0, "?")``."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(0, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.level, node.module or ""))
        elif isinstance(node, ast.Call) and _is_dynamic_import(node.func):
            arg = node.args[0] if node.args else None
            name = "?"
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                name = arg.value
            found.append((0, name))
    return found


def _is_dynamic_import(func: ast.expr) -> bool:
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return name in ("import_module", "__import__")


@pytest.mark.parametrize("path", _MODULES, ids=lambda p: p.relative_to(_DIR).as_posix())
def test_a_module_imports_the_standard_library_and_its_siblings_only(
    path: Path,
) -> None:
    depth = len(path.relative_to(_DIR).parts)  # 1 for a top-level module
    for level, module in _imports(path):
        if level:
            assert level <= depth, f"{path.name}: import reaches outside the package"
        else:
            top = module.partition(".")[0]
            assert top == "__future__" or top in sys.stdlib_module_names, (
                f"{path.name}: imports {module}"
            )


def test_the_source_check_sees_imports() -> None:
    """Non-vacuous: the walk finds both kinds in the package."""
    found = {entry for path in _MODULES for entry in _imports(path)}
    assert (0, "pickletools") in found
    assert (1, "_errors") in found


_SCRIPT = r"""
import importlib, importlib.abc, sys, types

root, package, *modules = sys.argv[1:]
# Empty parent packages: the real ones import the rest of Pitloom.
parents = package.split(".")[:-1]
for depth in range(1, len(parents) + 1):
    stub = types.ModuleType(".".join(parents[:depth]))
    stub.__path__ = ["/".join([root, *parents[1:depth]])]
    sys.modules[stub.__name__] = stub


class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.partition(".")[0] == parents[0] and not (
            name == package or name.startswith(package + ".")
        ):
            raise ImportError("blocked: " + name)
        return None


sys.meta_path.insert(0, Block())
before = set(sys.modules)
for module in modules:
    importlib.import_module(package + "." + module)
from pitloom.extract.ai_model.formats import Limits
from pitloom.extract.ai_model.formats.pickle_walk import first_pickle

assert first_pickle(b"\x80\x02N.", Limits()).end == 4
for name in sorted(set(sys.modules) - before):
    top = name.partition(".")[0]
    if not name.startswith(package) and top not in sys.stdlib_module_names:
        print("imported:", name)
print("ok")
"""


def test_the_package_imports_and_runs_with_the_rest_of_pitloom_blocked() -> None:
    modules = [
        ".".join(p.relative_to(_DIR).with_suffix("").parts).removesuffix(".__init__")
        for p in _MODULES
        if p != _DIR / "__init__.py"
    ]
    root = _DIR.parents[2].as_posix()
    result = subprocess.run(  # nosec B603
        [sys.executable, "-I", "-c", _SCRIPT, root, _PACKAGE, *modules],
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout.decode().split() == ["ok"]
