# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Walk every module and find the message emission sites: logging calls,
``print``, ``warnings.warn``, ``sys.exit``, ``raise Exc("text")``, the named
helpers (``print_error``, ``warn_once``, over-cap, KV) and the calls of any
function whose body emits (a *helper call*; its body is a *helper body*).

See also: ``_walker_calls.py`` (builds a record from each site).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ._astutil import (
    EXPLICIT_MSG,
    HELPER_NAME,
    KV_HELPERS,
    LEVELS,
    OVER_CAP_HELPERS,
    callee_name,
    is_logger,
    level_of,
    unparse,
)
from ._coded import FORWARD, STATIC, best_kind
from ._index import Module
from ._render import Renderer
from ._walker_calls import CallSites, Record, Stack, code_fields

if TYPE_CHECKING:
    from ._index import FuncNode

_WRAPPERS = set(KV_HELPERS) | set(EXPLICIT_MSG) | set(OVER_CAP_HELPERS)
#: The catalogue package, whose helpers say a message through ``emit``.
_CATALOGUE = "src/pitloom/messages/"
#: Call text -> (emitter, level, note) of the calls that emit their first
#: argument as it is.
_SIMPLE_EMITTERS: dict[str, tuple[str, str, str | None]] = {
    "warnings.warn": ("warnings.warn", "WARNING", None),
    "parser.error": (
        "argparse.error",
        "ERROR",
        "argparse adds usage and 'prog: error:'",
    ),
    "sys.stdout.write": ("sys.stdout.write", "STDOUT", None),
}


class Walker(CallSites):
    """Finds the emission sites of an :class:`~._render.Renderer`'s tree."""

    def run(self) -> None:
        """Walk every module, then resolve the helper call sites."""
        for mod in self.idx.mods.values():
            self.walk_module(mod)
        self.resolve_helpers()

    def walk_module(self, mod: Module) -> None:
        """Visit every node of *mod*, tracking the function and class stack."""
        stack: Stack = []
        clsname: list[str] = []

        def visit(node: ast.AST) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._decorators(mod, node, (stack, clsname))
                stack.append(node)
            elif isinstance(node, ast.ClassDef):
                clsname.append(node.name)
            elif isinstance(node, ast.Call):
                self.handle_call(mod, node, (stack, clsname))
            elif isinstance(node, ast.Raise):
                self.handle_raise(mod, node, (stack, clsname))
            for child in ast.iter_child_nodes(node):
                visit(child)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stack.pop()
            elif isinstance(node, ast.ClassDef):
                clsname.pop()

        visit(mod.tree)

    def _decorators(
        self,
        mod: Module,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        scope: tuple[Stack, list[str]],
    ) -> None:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and callee_name(dec) == "cli_error_handler":
                self.cli_error_site(mod, dec, node, scope)

    def handle_call(
        self, mod: Module, call: ast.Call, scope: tuple[Stack, list[str]]
    ) -> None:
        """Classify one call: an emission, a helper call or neither."""
        stack, clsname = scope
        func = call.func
        name = callee_name(call)
        here = getattr(stack[-1], "name", None) if stack else None
        if isinstance(func, ast.Attribute) and is_logger(func.value):
            self._logging_call(mod, call, scope, func.attr)
            return
        if self._special_call(mod, call, scope, name):
            return
        if name in _WRAPPERS and here in _WRAPPERS:
            return  # a wrapper calling another wrapper: counted at its callers
        self._helper_call(mod, call, scope, name, here, clsname)

    def _special_call(
        self,
        mod: Module,
        call: ast.Call,
        scope: tuple[Stack, list[str]],
        name: str | None,
    ) -> bool:
        """``print``, ``warnings.warn``, ``parser.error``, ``sys.stdout.write``
        and ``sys.exit``; whether *call* was one of them."""
        if name == "print":
            self.handle_print(mod, call, scope)
            return True
        text = unparse(call.func)
        if text in _SIMPLE_EMITTERS and call.args:
            emitter, level, note = _SIMPLE_EMITTERS[text]
            extra = {"note": note} if note else None
            self.make(
                mod, call, scope, emitter, level, call.args[0], 0, call, extra=extra
            )
            return True
        if text == "sys.exit" and call.args:
            arg = call.args[0]
            if isinstance(arg, (ast.JoinedStr, ast.BinOp)) or (
                isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            ):
                self.make(mod, call, scope, "sys.exit", "ERROR", arg, 0, call)
            return True
        return False

    def _logging_call(
        self,
        mod: Module,
        call: ast.Call,
        scope: tuple[Stack, list[str]],
        attr: str,
    ) -> None:
        level = LEVELS.get(attr)
        if level and call.args:
            self.make(mod, call, scope, f"logging.{attr}", level, call.args[0], 0, call)
        elif attr == "log" and len(call.args) >= 2:
            self.make(
                mod,
                call,
                scope,
                "logging.log",
                level_of(call.args[0]) or "DYNAMIC",
                call.args[1],
                1,
                call,
            )

    def _helper_call(
        self,
        mod: Module,
        call: ast.Call,
        scope: tuple[Stack, list[str]],
        name: str | None,
        here: str | None,
        clsname: list[str],
    ) -> None:
        if name in KV_HELPERS:
            self.kv_site(mod, call, scope, name)
        elif name in OVER_CAP_HELPERS:
            self.over_cap_site(mod, call, scope, name)
        elif name in EXPLICIT_MSG:
            level, i = EXPLICIT_MSG[name]
            if name == "log_once" and len(call.args) > 1:
                level = level_of(call.args[1]) or "DYNAMIC"
            if len(call.args) > i:
                self.make(
                    mod,
                    call,
                    scope,
                    name,
                    level,
                    call.args[i],
                    i,
                    call,
                    helper=name,
                    site_kind="helper_call",
                )
        elif name and HELPER_NAME.match(name) and here != name:
            self.pending.append((mod, call, list(scope[0]), list(clsname), name))

    def resolve_helpers(self) -> None:
        """Second pass: mark the sites inside emitter functions as helper
        bodies and add a record for each call of such a function. Then the
        same for a catalogue helper (:data:`_CATALOGUE`) that says its
        message through ``emit``, whose own call of ``emit`` the first round
        recorded, coded: each call of it is a coded site."""
        found = self._resolve_round(
            lambda rec: rec["site_kind"] == "raw" and rec["emitter"] != "raise",
            set(),
        )
        self._resolve_round(
            lambda rec: (
                rec["file"].startswith(_CATALOGUE)
                and rec["site_kind"] == "helper_call"
                and bool(rec["coded"])
            ),
            found,
        )

    def _resolve_round(
        self, body: Callable[[Record], bool], done: set[str]
    ) -> set[str]:
        """Resolve the pending calls of the helpers not in *done* whose body
        holds a record *body* accepts; their names."""
        by_func: dict[tuple[str, str], list[Record]] = defaultdict(list)
        for rec in self.records:
            if body(rec):
                by_func[(rec["file"], rec["function"])].append(rec)
        defs: dict[str, list[tuple[Module, FuncNode, list[Record]]]] = defaultdict(list)
        for mod in self.idx.mods.values():
            for fname, fn in mod.funcs.items():
                recs = by_func.get((mod.rel, fname))
                if HELPER_NAME.match(fname) and recs and fname not in done:
                    defs[fname].append((mod, fn, recs))
        for fname, found in defs.items():
            for _mod, _fn, recs in found:
                for rec in recs:
                    rec["site_kind"] = "helper_body"
                    rec["helper_def"] = fname
        for mod, call, stack, clsname, name in self.pending:
            if name in defs:
                self._resolved_call(mod, call, (stack, clsname), name, defs[name])
        return set(defs)

    def _resolved_call(
        self,
        mod: Module,
        call: ast.Call,
        scope: tuple[Stack, list[str]],
        name: str,
        cands: list[tuple[Module, FuncNode, list[Record]]],
    ) -> None:
        dmod, dfn, recs = _pick_def(mod, name, cands)
        params = [a.arg for a in dfn.args.args]
        level = recs[0]["level"]
        msg_param = _message_param(params, recs)
        arg = None
        if msg_param:
            i = params.index(msg_param)
            arg = (
                call.args[i]
                if i < len(call.args)
                else next((k.value for k in call.keywords if k.arg == msg_param), None)
            )
        if arg is not None:
            new = self.make(
                mod,
                call,
                scope,
                name,
                level,
                arg,
                params.index(str(msg_param)),
                call,
                helper=name,
                site_kind="helper_call",
            )
        else:
            tmpls = [r["template"] for r in recs if r["template"] is not None]
            self.inherit = [
                any(r["uses_loggable"] for r in recs),
                any(r["uses_quote_source"] for r in recs),
            ]
            new = self.make(
                mod,
                call,
                scope,
                name,
                level,
                None,
                0,
                call,
                helper=name,
                site_kind="helper_call",
                templates=tmpls or None,
                extra={"helper_def": f"{dmod.rel}:{recs[0]['line']}"},
            )
        # A helper whose body codes its message codes every caller's line.
        body = self.coder.body_kind(dmod, dfn)
        new.update(code_fields(best_kind({_kind_of(new), body})))


def _kind_of(rec: Record) -> str | None:
    if rec["forwards_code"]:
        return FORWARD
    return STATIC if rec["coded"] else None


def _pick_def(
    mod: Module, name: str, cands: list[tuple[Module, FuncNode, list[Record]]]
) -> tuple[Module, FuncNode, list[Record]]:
    """The definition of helper *name* that *mod* imports, else the first."""
    pick = cands[0]
    src = mod.imports.get(name)
    for cand in cands:
        if src and cand[0].name == src[0]:
            pick = cand
    return pick


def _message_param(params: list[str], recs: list[Record]) -> str | None:
    """The parameter a helper passes on as its message (``{param}``)."""
    found = None
    for rec in recs:
        for param in params:
            if param not in ("self", "cls") and rec["template"] == "{" + param + "}":
                found = param
    return found


def walk(root: Path) -> list[Record]:
    """Every emission site of the tree under *root*, in a stable order."""
    walker = Walker(Renderer(root))
    walker.run()
    return sorted(
        walker.records,
        key=lambda r: (
            r["file"],
            r["line"],
            r["emitter"],
            r["function"],
            r["helper"] or "",
        ),
    )
