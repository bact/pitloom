# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Turn the message argument of an emission site into candidate templates
(``{expr}`` for each dynamic piece): literals, f-strings, concatenations,
module constants, local variables, ``%`` and ``.format`` calls, and message
builders (functions and exception classes that return or wrap the text).

See also: ``_index.py`` (the parsed tree this renders against).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from ._astutil import (
    EXC_NAME,
    MAX_ALTS,
    NO_EXPAND,
    callee_name,
    local_assigns,
    placeholder,
    unparse,
)
from ._index import Index, Module

if TYPE_CHECKING:
    from ._index import FuncNode


def _product(left: list[str], right: list[str]) -> list[str]:
    return [x + y for x in left for y in right][:MAX_ALTS]


class Renderer(Index):
    """An :class:`Index` that also renders message arguments."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._memo: dict[tuple[str, str], list[str] | None] = {}
        self._busy: set[tuple[str, str]] = set()
        self._depth = 0

    def render_call(
        self,
        node: ast.Call,
        mod: Module,
        func: ast.AST | None = None,
        cls: str | None = None,
    ) -> list[str] | None:
        """Templates of a call to a message builder, ``None`` if none."""
        if self._depth >= 4 or callee_name(node) in NO_EXPAND:
            return None
        found = self.lookup(mod, node.func)
        if found is None:
            cname = unparse(node.func).rsplit(".", 1)[-1]
            if EXC_NAME.search(cname) and node.args:
                return self.render(node.args[0], mod, func, cls)
            return None
        tmod, target = found
        self._depth += 1
        try:
            if isinstance(target, ast.ClassDef):
                return self._render_class(node, mod, func, cls, tmod, target)
            return self._render_function(node, mod, func, cls, tmod, target)
        finally:
            self._depth -= 1

    def _render_class(
        self,
        node: ast.Call,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        tmod: Module,
        target: ast.ClassDef,
    ) -> list[str] | None:
        outs: list[str] = []
        for item in target.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                self.bind_args(node, item, (mod, func, cls), True)
                outs.extend(self._super_texts(item, tmod, target.name))
        if outs:
            self.builders.append(target.name)
            return outs[:MAX_ALTS]
        if node.args:
            found = self.render(node.args[0], mod, func, cls)
            if found:
                self.builders.append(target.name)
                return found
        return None

    def _super_texts(self, init: ast.FunctionDef, mod: Module, cls: str) -> list[str]:
        """Templates of the message ``__init__`` hands to ``super().__init__``."""
        outs: list[str] = []
        for sub in ast.walk(init):
            is_super = (
                isinstance(sub, ast.Call)
                and unparse(sub.func) == "super().__init__"
                and sub.args
            )
            if is_super and isinstance(sub, ast.Call):
                outs.extend(self.render(sub.args[0], mod, init, cls) or [])
        return outs

    def _render_function(
        self,
        node: ast.Call,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        tmod: Module,
        target: FuncNode,
    ) -> list[str] | None:
        outs: list[str] = []
        self.bind_args(node, target, (mod, func, cls), False)
        for sub in ast.walk(target):
            if isinstance(sub, ast.Return) and sub.value is not None:
                found = self.render(sub.value, tmod, target, None)
                if found:
                    outs.extend(found)
        if outs:
            self.builders.append(target.name)
        return outs[:MAX_ALTS] or None

    def const(self, mod: Module, name: str) -> list[str] | None:
        """Templates of the module constant *name* (strict: all literal)."""
        key = (mod.name, name)
        if key in self._memo:
            return self._memo[key]
        if key in self._busy:
            return None
        self._busy.add(key)
        out: list[str] | None = None
        if name in mod.assigns:
            out = self.render(mod.assigns[name], mod, None, None, strict=True)
        elif name in mod.imports:
            src, orig = mod.imports[name]
            target = self.mods.get(src)
            if target is not None and orig is not None:
                out = self.const(target, orig)
        self._busy.discard(key)
        self._memo[key] = out
        return out

    # pylint: disable-next=too-many-return-statements
    def render(
        self,
        node: ast.expr | None,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        strict: bool = False,
    ) -> list[str] | None:
        """Candidate templates for *node* (``{expr}`` for dynamic pieces);
        ``None`` when the node is not string-like. *strict* (module
        constants): ``None`` also when any piece is dynamic."""
        if node is None:
            return None
        if isinstance(node, ast.Constant):
            return [node.value] if isinstance(node.value, str) else None
        if isinstance(node, ast.JoinedStr):
            return self._render_fstring(node, mod, func, cls, strict)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._render_concat(node, mod, func, cls, strict)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            return self.render(node.left, mod, func, cls, strict)
        if isinstance(node, ast.IfExp):
            return self._render_ifexp(node, mod, func, cls, strict)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("format", "strip", "lstrip", "rstrip"):
                return self.render(node.func.value, mod, func, cls, strict)
        if isinstance(node, ast.Call) and not strict:
            return self.render_call(node, mod, func, cls)
        if isinstance(node, ast.Name):
            return self._render_name(node, mod, func, cls, strict)
        if isinstance(node, ast.Attribute):
            return self._render_attribute(node, mod, cls, strict)
        return None

    def _render_concat(
        self,
        node: ast.BinOp,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        strict: bool,
    ) -> list[str] | None:
        left = self.render(node.left, mod, func, cls, strict)
        right = self.render(node.right, mod, func, cls, strict)
        if left is None and right is None:
            return None
        if strict and (left is None or right is None):
            return None
        return _product(
            left or [placeholder(node.left)], right or [placeholder(node.right)]
        )

    def _render_ifexp(
        self,
        node: ast.IfExp,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        strict: bool,
    ) -> list[str] | None:
        body = self.render(node.body, mod, func, cls, strict)
        orelse = self.render(node.orelse, mod, func, cls, strict)
        if body is None and orelse is None:
            return None
        if strict and (body is None or orelse is None):
            return None
        both = (body or [placeholder(node.body)]) + (
            orelse or [placeholder(node.orelse)]
        )
        return both[:MAX_ALTS]

    def _render_fstring(
        self,
        node: ast.JoinedStr,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        strict: bool,
    ) -> list[str] | None:
        outs = [""]
        for part in node.values:
            if isinstance(part, ast.Constant):
                piece = [str(part.value)]
            elif isinstance(part, ast.FormattedValue):
                sub = (
                    None
                    if isinstance(part.value, ast.Call)
                    else self.render(part.value, mod, func, cls, strict)
                )
                if sub is not None and isinstance(
                    part.value, (ast.Name, ast.Attribute)
                ):
                    piece = sub
                elif strict:
                    return None
                else:
                    piece = [placeholder(part.value)]
            else:  # pragma: no cover
                return None
            outs = _product(outs, piece)
        return outs

    def _render_name(
        self,
        node: ast.Name,
        mod: Module,
        func: ast.AST | None,
        cls: str | None,
        strict: bool,
    ) -> list[str] | None:
        bound = self.bind.get(id(func), {}).get(node.id) if func is not None else None
        if func is not None and bound is not None:
            if not local_assigns(func, node.id):
                arg, cmod, cfunc, ccls = bound
                found = self.render(arg, cmod, cfunc, ccls)
                return found if found is not None else [placeholder(arg)]
        if func is not None and not strict:
            outs: list[str] = []
            for expr in local_assigns(func, node.id):
                found = self.render(expr, mod, None, cls, False)
                if found is not None:
                    outs.extend(found)
            if outs:
                return outs[:MAX_ALTS]
        return self.const(mod, node.id)

    def _render_attribute(
        self, node: ast.Attribute, mod: Module, cls: str | None, strict: bool
    ) -> list[str] | None:
        if node.attr == "reason" and "cap" in unparse(node.value).lower():
            return ["larger than the {limit}-{unit} {purpose} cap"]
        if isinstance(node.value, ast.Name):
            base = node.value.id
            table = mod.class_assigns.get(cls or "", {})
            if base in ("self", "cls") and node.attr in table:
                return self.render(table[node.attr], mod, None, cls, strict)
            if base in mod.imports:
                src, orig = mod.imports[base]
                full = src if orig is None else f"{src}.{orig}"
                target = self.mods.get(full) or self.mods.get(src)
                if target is not None:
                    return self.const(target, node.attr)
        return None
