# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The parsed ``src/pitloom`` tree: modules, their imports, constants and
functions, and the lookups that follow a call to its definition.

See also: ``_render.py`` (turns a message argument into a template).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    #: A function definition node.
    FuncNode = ast.FunctionDef | ast.AsyncFunctionDef
    #: What a parameter was bound to at a call: (argument, caller module,
    #: caller function, caller class).
    Binding = tuple[ast.expr, "Module", ast.AST | None, str | None]


# pylint: disable-next=too-few-public-methods
class Module:
    """One parsed module: its names, imports, functions and classes."""

    def __init__(self, root: Path, path: Path) -> None:
        self.rel = path.relative_to(root).as_posix()
        parts = list(path.relative_to(root / "src").with_suffix("").parts)
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        self.name = ".".join(parts)
        self.package = self.name if is_pkg else ".".join(parts[:-1])
        self.src = path.read_text(encoding="utf-8")
        self.lines = self.src.splitlines()
        self.tree = ast.parse(self.src)
        self.assigns: dict[str, ast.expr] = {}
        self.class_assigns: dict[str, dict[str, ast.expr]] = {}
        self.imports: dict[str, tuple[str, str | None]] = {}
        self.funcs: dict[str, FuncNode] = {}
        self.classes: dict[str, ast.ClassDef] = {}
        self._index()

    def _abs(self, node: ast.ImportFrom) -> str:
        if not node.level:
            return node.module or ""
        base = self.package.split(".") if self.package else []
        if node.level > 1:
            base = base[: len(base) - (node.level - 1)]
        return ".".join(base + ([node.module] if node.module else []))

    def _index(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                mod = self._abs(node)
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (mod, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    key = alias.asname or alias.name.split(".")[0]
                    self.imports[key] = (alias.name, None)
        for node in self.tree.body:
            self._assign(node, self.assigns)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
            if isinstance(node, ast.ClassDef):
                self.classes[node.name] = node
                table = self.class_assigns.setdefault(node.name, {})
                for sub in node.body:
                    self._assign(sub, table)

    @staticmethod
    def _assign(node: ast.stmt, table: dict[str, ast.expr]) -> None:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    table[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                table[node.target.id] = node.value


class Index:
    """Every module under ``root/src/pitloom``, by dotted name."""

    def __init__(self, root: Path) -> None:
        self.mods: dict[str, Module] = {}
        for path in sorted((root / "src" / "pitloom").rglob("*.py")):
            mod = Module(root, path)
            self.mods[mod.name] = mod
        #: Builders (message-building functions) the last render followed.
        self.builders: list[str] = []
        #: id(callee def) -> {parameter: what the last call bound it to}
        self.bind: dict[int, dict[str, Binding]] = {}

    def bind_args(
        self,
        call: ast.Call,
        fn: FuncNode,
        caller: tuple[Module, ast.AST | None, str | None],
        skip_self: bool,
    ) -> None:
        """Record what *call* passes for each parameter of *fn*."""
        cmod, cfunc, ccls = caller
        params = [a.arg for a in fn.args.args]
        if skip_self and params and params[0] in ("self", "cls"):
            params = params[1:]
        table: dict[str, Binding] = {}
        for param, arg in zip(params, call.args, strict=False):
            table[param] = (arg, cmod, cfunc, ccls)
        for kw in call.keywords:
            if kw.arg:
                table[kw.arg] = (kw.value, cmod, cfunc, ccls)
        self.bind[id(fn)] = table

    def _callee(self, mod: Module, func: ast.expr) -> tuple[Module, str] | None:
        """The module and name a callee expression refers to."""
        if isinstance(func, ast.Name):
            if func.id in mod.funcs or func.id in mod.classes:
                return mod, func.id
            imp = mod.imports.get(func.id)
            target = self.mods.get(imp[0]) if imp else None
            if imp is None or target is None or imp[1] is None:
                return None
            return target, imp[1]
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            imp = mod.imports.get(func.value.id)
            if not imp:
                return None
            full = imp[0] if imp[1] is None else f"{imp[0]}.{imp[1]}"
            target = self.mods.get(full) or self.mods.get(imp[0])
            return (target, func.attr) if target is not None else None
        return None

    def lookup(
        self, mod: Module, func: ast.expr
    ) -> tuple[Module, FuncNode | ast.ClassDef] | None:
        """The in-package function or class a call's callee names."""
        callee = self._callee(mod, func)
        if callee is None:
            return None
        target, name = callee
        if name in target.funcs:
            return target, target.funcs[name]
        if name in target.classes:
            return target, target.classes[name]
        # re-export through a package __init__
        imp = target.imports.get(name)
        if imp and imp[1] and imp[0] in self.mods and imp[0] != target.name:
            other = self.mods[imp[0]]
            if imp[1] in other.funcs:
                return other, other.funcs[imp[1]]
            if imp[1] in other.classes:
                return other, other.classes[imp[1]]
        return None

    def const_node(self, mod: Module, name: str, depth: int = 0) -> ast.expr | None:
        """The expression assigned to the module constant *name*, followed
        through imports."""
        if name in mod.assigns:
            return mod.assigns[name]
        if name in mod.imports and depth < 6:
            src, orig = mod.imports[name]
            target = self.mods.get(src)
            if target is not None and orig is not None:
                return self.const_node(target, orig, depth + 1)
        return None
