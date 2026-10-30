# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Small AST helpers and the name tables the inventory shares.

See also: ``__init__.py`` (what the package does).
"""

from __future__ import annotations

import ast
import re

#: Alternatives kept when a template has several branches or concatenations.
MAX_ALTS = 8
LEVELS = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "warn": "WARNING",
    "error": "ERROR",
    "exception": "ERROR",
    "critical": "CRITICAL",
}
LOGGER_NAME = re.compile(r"^_*(log|logger|logging|LOG|LOGGER)$")
#: Functions whose name marks them as emitters: their call sites are listed.
HELPER_NAME = re.compile(
    r"^_?(warn|log|report|print|note|notice|emit|say)(?!_traceback)\w*$"
)
#: Helpers handled by hand: name -> (level, index of the message argument).
EXPLICIT_MSG: dict[str, tuple[str | None, int]] = {
    "print_error": ("ERROR", 0),
    "warn_once": ("WARNING", 2),
    "log_once": (None, 3),  # level from argument 1
}
#: Over-cap helper name -> index of its ``cap`` argument.
OVER_CAP_HELPERS = {
    "warn_over_cap": 1,
    "warn_field_cap": 2,
    "warn_archive_member_over_cap": 1,
}
KV_HELPERS = ("kv_line", "print_kv", "log_kv", "log_verbose")
EXC_NAME = re.compile(r"(Error|Exception|Exit|Refused|Warning|Interrupt)$")
#: Calls whose result is not followed when a template is rendered.
NO_EXPAND = {
    "loggable",
    "one_line",
    "excerpt",
    "quote_source",
    "escape_controls",
    "mask_checkout",
    "sanitize_url",
    "sanitize_url_credentials",
    "str",
    "repr",
    "sorted",
    "len",
    "int",
    "join",
    "show",
    "format",
    "exception_label",
}
SANITISERS = {"loggable", "one_line", "excerpt"}


def unparse(node: ast.AST) -> str:
    """Source text of *node*, ``?`` when it cannot be unparsed."""
    try:
        return ast.unparse(node)
    except (ValueError, TypeError, RecursionError):  # pragma: no cover
        return "?"


def placeholder(node: ast.AST) -> str:
    """``{expr}`` for a dynamic piece of a template."""
    return "{" + unparse(node) + "}"


def kv_value(node: ast.expr) -> str:
    """A keyword argument's value as text: a string as is, else ``{expr}``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return placeholder(node)


def callee_name(call: ast.Call) -> str | None:
    """The last name of what *call* calls, ``None`` for anything else."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def local_assigns(func: ast.AST, name: str) -> list[ast.expr]:
    """Every value assigned to the local variable *name* inside *func*."""
    out: list[ast.expr] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                out.append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name) and node.target.id == name:
                out.append(node.value)
    return out


def is_logger(node: ast.expr) -> bool:
    """Whether *node* names or builds a logger."""
    if isinstance(node, ast.Name):
        return bool(LOGGER_NAME.match(node.id))
    if isinstance(node, ast.Attribute):
        return bool(LOGGER_NAME.match(node.attr))
    if isinstance(node, ast.Call):
        func = node.func
        return (isinstance(func, ast.Attribute) and func.attr == "getLogger") or (
            isinstance(func, ast.Name) and func.id == "getLogger"
        )
    return False


def level_of(node: ast.expr | None) -> str | None:
    """The level word a ``logging.WARNING``-like node names."""
    if isinstance(node, ast.Attribute):
        return LEVELS.get(node.attr.lower())
    if isinstance(node, ast.Name):
        return LEVELS.get(node.id.lower())
    return None


def uses_call(nodes: list[ast.AST], want: set[str]) -> bool:
    """Whether any of *nodes* contains a call to one of the names *want*."""
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and callee_name(sub) in want:
                return True
    return False
