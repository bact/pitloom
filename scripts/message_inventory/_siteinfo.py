# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Small facts about one site: its source snippet, whether its template
resolved, the parts of a ``Cap(...)`` call and the kind of a name.

See also: ``_walker_calls.py`` (stores them on each record).
"""

from __future__ import annotations

import ast
import re

from ._astutil import local_assigns, placeholder
from ._index import Module


def snippet(mod: Module, start: int, end: int) -> str:
    text = "\n".join(mod.lines[start - 1 : end])
    return text[:400] + "..." if len(text) > 400 else text


def status(template: str | None, tmpl_node: ast.expr | None) -> str:
    if template is None:
        return "none"
    dynamic = re.search(r"\{[^{}]*\}", template)
    if dynamic and tmpl_node is not None and not isinstance(tmpl_node, ast.Constant):
        return "resolved_with_dynamic_parts"
    return "resolved"


def cap_fields(cap: ast.Call) -> dict[str, str]:
    """The ``limit``, ``unit``, ``purpose`` and ``subject`` of a ``Cap(...)``
    call, a literal as text and anything else as ``{expr}``."""
    vals: dict[str, str] = {}
    for i, fld in enumerate(("limit", "unit", "purpose", "subject")):
        arg = (
            cap.args[i]
            if i < len(cap.args)
            else next((k.value for k in cap.keywords if k.arg == fld), None)
        )
        if arg is not None:
            vals[fld] = (
                str(arg.value) if isinstance(arg, ast.Constant) else placeholder(arg)
            )
    return vals


def name_kind(node: ast.Name, mod: Module, func: ast.AST | None) -> str | None:
    if func is not None and local_assigns(func, node.id):
        return "local"
    if node.id in mod.assigns or node.id in mod.imports:
        return f"constant:{node.id}"
    return None
