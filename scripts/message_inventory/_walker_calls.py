# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How one emission site becomes a record: the record builder and the
handlers for print, KV, over-cap, ``cli_error_handler`` and ``raise`` sites.

See also: ``_walker.py`` (finds the sites and calls these).
"""

from __future__ import annotations

import ast
import re
from typing import Any

from ._astutil import (
    OVER_CAP_HELPERS,
    SANITISERS,
    callee_name,
    kv_value,
    placeholder,
    unparse,
    uses_call,
)
from ._coded import FORWARD, STATIC, CodedChecker
from ._families import analyse, count_args, normalise
from ._index import Module
from ._render import Renderer
from ._siteinfo import cap_fields, name_kind, snippet, status

Record = dict[str, Any]
Stack = list[ast.AST]


def code_fields(kind: str | None) -> dict[str, bool]:
    """The ``coded`` and ``forwards_code`` fields of a record."""
    return {"coded": kind == STATIC, "forwards_code": kind == FORWARD}


class CallSites:
    """Builds the record of each site; :class:`~._walker.Walker` finds them."""

    def __init__(self, idx: Renderer) -> None:
        self.idx = idx
        self.records: list[Record] = []
        self.pending: list[tuple[Module, ast.Call, Stack, list[str], str]] = []
        #: (uses_loggable, uses_quote_source) of the helper body being called;
        #: empty when none.
        self.inherit: list[bool] = []
        self.coder = CodedChecker(idx)

    @staticmethod
    def qual(stack: Stack, clsname: list[str]) -> str:
        """The dotted function name of the site, ``<module>`` at top level."""
        names = [getattr(f, "name", "?") for f in stack]
        if clsname and names:
            return clsname[-1] + "." + ".".join(names)
        return ".".join(names) or "<module>"

    # pylint: disable-next=R0913,R0917,R0914
    def make(
        self,
        mod: Module,
        node: ast.AST,
        scope: tuple[Stack, list[str]],
        emitter: str,
        level: str | None,
        tmpl_node: ast.expr | None,
        tidx: int,
        call: ast.Call | None,
        helper: str | None = None,
        site_kind: str = "raw",
        templates: list[str] | None = None,
        extra: Record | None = None,
    ) -> Record:
        """Build, store and return the record of one site."""
        stack, clsname = scope
        func = stack[-1] if stack else None
        cls = clsname[-1] if clsname else None
        self.idx.builders = []
        if templates is None and tmpl_node is not None:
            templates = self.idx.render(tmpl_node, mod, func, cls)
        builders = sorted(set(self.idx.builders))
        template = templates[0] if templates else None
        alts = templates[1:] if templates and len(templates) > 1 else []
        nodes: list[ast.AST] = []
        if call is not None:
            nodes = [*call.args, *(k.value for k in call.keywords)]
        start = node.lineno  # type: ignore[attr-defined]
        end = getattr(node, "end_lineno", start) or start
        rec: Record = {
            "file": mod.rel,
            "module": mod.name,
            "line": start,
            "end_line": end,
            "function": self.qual(stack, clsname),
            "emitter": emitter,
            "level": level,
            "template": template,
            "alt_templates": alts,
            "template_status": status(template, tmpl_node),
            "args_expr_count": count_args(call, tidx, tmpl_node),
            "helper": helper,
            "site_kind": site_kind,
            "uses_loggable": uses_call(nodes, SANITISERS),
            "uses_quote_source": uses_call(nodes, {"quote_source"}),
            **code_fields(self.coder.site_kind(mod, call)),
            **analyse(template),
            "source_lines": end - start + 1,
            "source_snippet": snippet(mod, start, end),
        }
        self._finish(rec, (tmpl_node, tidx, call), (mod, func, templates), builders)
        if extra:
            rec.update(extra)
        rec["normalised_template"] = normalise(rec["template"])
        self.records.append(rec)
        return rec

    def _finish(
        self,
        rec: Record,
        site: tuple[ast.expr | None, int, ast.Call | None],
        context: tuple[Module, ast.AST | None, list[str] | None],
        builders: list[str],
    ) -> None:
        """Fields that depend on the rendered templates and the helper."""
        tmpl_node, tidx, call = site
        mod, func, templates = context
        alltext = " ".join(templates or [])
        rec["uses_loggable"] |= bool(
            re.search(r"\b(loggable|one_line|excerpt)\(", alltext)
        )
        rec["uses_quote_source"] |= "quote_source(" in alltext
        if call is not None:
            rec["arg_exprs"] = (
                [unparse(a)[:80] for a in call.args[tidx + 1 : tidx + 7]]
                if tmpl_node is not None
                else []
            )
        rec["tmpl_source"] = self.source_kind(tmpl_node, mod, func, templates)
        if builders:
            rec["via_builders"] = builders
        if rec["template"] is None and tmpl_node is not None:
            rec["dynamic_expr"] = unparse(tmpl_node)[:200]
        inherit = self.inherit
        if inherit and rec["site_kind"] == "helper_call":
            rec["uses_loggable"] |= inherit[0]
            rec["uses_quote_source"] |= inherit[1]
        self.inherit = []
        if (
            rec["helper"] in OVER_CAP_HELPERS
            or rec["helper"] == "warn_pointers_not_read"
        ):
            rec["uses_loggable"] = True  # the wrapper escapes the subject

    @staticmethod
    def source_kind(
        node: ast.expr | None,
        mod: Module,
        func: ast.AST | None,
        templates: list[str] | None,
    ) -> str:
        """Where the template text is written: ``literal`` in the call,
        ``constant:NAME`` shared, ``builder`` a message-building function,
        ``local`` a local variable, ``helper`` inside a helper."""
        if node is None:
            return "helper"
        if isinstance(node, ast.Name):
            kind = name_kind(node, mod, func)
            if kind:
                return kind
        if isinstance(node, ast.Attribute):
            return f"constant:{unparse(node)}"
        if isinstance(node, ast.Call) and templates is not None:
            return "builder"
        if isinstance(node, ast.BinOp) and any(
            isinstance(sub, ast.Name)
            and (sub.id in mod.assigns or sub.id in mod.imports)
            for sub in ast.walk(node)
        ):
            return "literal+constant"
        return "literal"

    def handle_print(
        self, mod: Module, call: ast.Call, scope: tuple[Stack, list[str]]
    ) -> None:
        """A ``print(...)`` to stdout, stderr or a file."""
        if not call.args:
            return
        dest = next((k.value for k in call.keywords if k.arg == "file"), None)
        to_err = dest is not None and "stderr" in unparse(dest)
        if dest is not None and not to_err:
            emitter, level = "print_file", "FILE"
        elif to_err:
            emitter, level = "print_stderr", "STDERR"
        else:
            emitter, level = "print_stdout", "STDOUT"
        rec = self.make(mod, call, scope, emitter, level, call.args[0], 0, call)
        text = rec["template"] or ""
        tag = re.match(r"\s*(ERROR|WARNING|INFO):", text)
        if to_err and tag:
            rec["level"] = tag.group(1)
            rest = text[tag.end() :].lstrip()
            rec["literal_tag_in_template"] = tag.group(1)
            rec["template_after_tag"] = rest
            rec.update(analyse(rest))
        elif to_err:
            rec["level"] = "STDERR_UNTAGGED"

    def kv_site(
        self,
        mod: Module,
        call: ast.Call,
        scope: tuple[Stack, list[str]],
        name: str,
    ) -> None:
        """A ``KEY=VALUE`` helper call (``print_kv``, ``log_verbose``...)."""
        kws = [k for k in call.keywords if k.arg]
        keys = [k.arg for k in kws]
        pre = ["PITLOOM_VERSION={__version__}"] if name == "log_verbose" else []
        tmpl = " ".join(pre + [f"{k.arg}={kv_value(k.value)}" for k in kws]) or None
        level = {"print_kv": "STDOUT", "kv_line": "STDOUT_LINE"}.get(name, "INFO")
        rec = self.make(
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
            templates=[tmpl] if tmpl else None,
            extra={
                "kv_keys": keys,
                "kv_dynamic_keys": any(k.arg is None for k in call.keywords),
            },
        )
        rec["args_expr_count"] = len(keys)
        rec["subject_key"] = keys[0] if keys else None
        rec["has_subject_prefix"] = bool(keys)

    def over_cap_site(
        self,
        mod: Module,
        call: ast.Call,
        scope: tuple[Stack, list[str]],
        name: str,
    ) -> None:
        """A ``warn_over_cap`` / ``warn_field_cap`` call."""
        stack, _ = scope
        ci = OVER_CAP_HELPERS[name]
        cap = (
            call.args[ci]
            if len(call.args) > ci
            else next((k.value for k in call.keywords if k.arg == "cap"), None)
        )
        subject, reason, how = self.cap_info(mod, cap)
        if name == "warn_over_cap":
            oc = (
                call.args[3]
                if len(call.args) > 3
                else next((k.value for k in call.keywords if k.arg == "outcome"), None)
            )
            rendered = (
                self.idx.render(oc, mod, stack[-1] if stack else None, None)
                if oc
                else ["skipped"]
            )
            outcome = rendered[0] if rendered else "{outcome}"
            wn = call.args[2] if len(call.args) > 2 else None
        else:
            outcome = "only the first {read} read of {field} / {field} not read"
            wn = call.args[1] if len(call.args) > 1 else None
        where = placeholder(wn) if wn is not None else "{where}"
        self.make(
            mod,
            call,
            scope,
            name,
            "WARNING",
            None,
            0,
            call,
            helper=name,
            site_kind="helper_call",
            templates=[f"{subject}={where}: {reason}; {outcome}"],
            extra={"cap_resolution": how, "template_source": "OVER_CAP_WARNING"},
        )

    def cap_info(self, mod: Module, node: ast.expr | None) -> tuple[str, str, str]:
        """(subject, reason, how it was resolved) of an over-cap call's cap."""
        dflt = ("{cap.subject}", "{cap.reason}", "unresolved")
        if node is None:
            return dflt
        prefix = ""
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "after"
        ):
            keys = self.idx.render(node.args[0], mod, None, None) if node.args else None
            prefix = (keys[0] + " ") if keys else "{keys} "
            node = node.func.value
        cap: ast.expr | None = node
        if isinstance(node, ast.Name):
            cap = self.idx.const_node(mod, node.id)
        if isinstance(cap, ast.Call) and callee_name(cap) == "Cap":
            vals = cap_fields(cap)
            reason = (
                f"larger than the {vals.get('limit', '{limit}')}-"
                f"{vals.get('unit', '{unit}')} {vals.get('purpose', '{purpose}')} cap"
            )
            return prefix + vals.get("subject", "FILE"), reason, "resolved"
        return prefix + dflt[0], dflt[1], "unresolved"

    def cli_error_site(
        self,
        mod: Module,
        dec: ast.Call,
        func: ast.AST,
        scope: tuple[Stack, list[str]],
    ) -> None:
        """A ``@cli_error_handler("...")`` decorator."""
        if not dec.args:
            return
        stack, clsname = scope
        found = self.idx.render(dec.args[0], mod, None, None)
        templates = [x + ": {exception}" for x in found] if found else None
        self.make(
            mod,
            dec,
            (stack + [func], clsname),
            "cli_error_handler",
            "ERROR",
            None,
            0,
            dec,
            helper="cli_error_handler",
            site_kind="helper_call",
            templates=templates,
            extra={"note": "ERROR: added by print_error; ': {exception}' appended"},
        )

    def handle_raise(
        self, mod: Module, node: ast.Raise, scope: tuple[Stack, list[str]]
    ) -> None:
        """A ``raise Exc("text")`` (or a builder call) with a message."""
        exc = node.exc
        if not isinstance(exc, ast.Call) or not exc.args:
            return
        builder = self.idx.lookup(mod, exc.func) is not None
        tnode: ast.expr = exc.args[0]
        if builder:
            self.idx.builders = []
            tnode = exc
        imported = (
            mod.imports.get(exc.func.id) if isinstance(exc.func, ast.Name) else None
        )
        self.make(
            mod,
            node,
            scope,
            "raise",
            "ERROR",
            tnode,
            0,
            exc,
            extra={
                "exc_class": unparse(exc.func),
                # The class's own name when imported under another.
                "exc_origin": imported[1] if imported else None,
                "reaches_cli": "unknown (static)",
            },
        )
