# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read what Python code does with a model file, from its syntax tree.

The usage scan used to look for the model's file name in the text of a file.
This reads the tree instead: a string that is path-shaped and names a model is
followed to where it is used, and that use says the access: a call that opens
or loads it reads, one that saves or dumps it writes, one that only prints it
(or logs it, or puts it in an exception message) is no use at all. Comments
and docstrings are not in the tree. Nothing is run or imported.

Paths are followed within one file: a name assigned once, ``Path(...) / "x"``,
``os.path.join``, f-strings, ``str.format`` and ``%``. A path that comes from
another module, a call's result or a configuration file is not seen.

See also: :mod:`pitloom.extract._usage_table` (the calls),
:mod:`pitloom.extract._usage_match` (what names a model) and
:mod:`pitloom.extract.scanner` (``attach_usage_references``: the file
reading, the pre-filter and the messages).
"""

from __future__ import annotations

import ast
import collections
import sys
import warnings
from collections.abc import Sequence
from typing import Final

from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_match import (
    UsageModel,
    after_first_separator,
    format_template,
    join_path,
    join_paths,
    matches,
    percent_template,
)
from pitloom.extract._usage_table import (
    MODE_CALLS,
    RECEIVER_MODE_POSITION,
    access_of_mode,
    access_of_name,
    is_mention_call,
)

__all__ = ["PARSE_ERRORS", "find_usages", "parse_python", "python_version"]

#: What parsing a file can raise besides a mistake in it: a null byte
#: (``ValueError`` before Python 3.12), a tree too deep for the parser
#: (``MemoryError``) or the compiler (``RecursionError``). A file can also
#: fail only on this Python: syntax it is too old to know.
PARSE_ERRORS: Final = (SyntaxError, ValueError, MemoryError, RecursionError)

_MAX_DEPTH: Final = 64
_MAX_PATH_CHARS: Final = 4096
#: Calls that build a path from their arguments, by the last name of the
#: callee (the module is not told apart: ``Path`` is ``pathlib.Path``).
_PATH_TYPES: Final = frozenset({"Path", "PurePath", "PurePosixPath", "PureWindowsPath"})
#: Calls that give their one argument's path back.
_PATH_FUNCTIONS: Final = frozenset(
    {"str", "fspath", "normpath", "abspath", "realpath", "expanduser", "expandvars"}
)
#: ``os.path.join`` as the callee is spelt after its imports are resolved.
_JOINS: Final = frozenset({"os.path.join", "posixpath.join", "ntpath.join"})
#: Methods that give the receiver's path back (``Path(...).resolve()``).
_SAME_PATH_METHODS: Final = frozenset({"resolve", "expanduser", "absolute"})


def python_version() -> str:
    """The running interpreter as ``3.10``: the grammar a file was read as."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def parse_python(text: str) -> ast.Module:
    """*text* as a module tree. A leading byte-order mark is dropped. An
    invalid escape (``"data\\model.ftz"``) only warns on the way, whatever
    the user's warning filters say, so the warning is dropped.

    Raises:
        SyntaxError: Not Python of this interpreter's grammar (or, after
            3.12, a null byte).
        ValueError: A null byte (before Python 3.12).
        MemoryError: The source nests too deeply for the parser.
        RecursionError: The source nests too deeply for the compiler.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(text.removeprefix("\ufeff"))


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Each name the file imports to the dotted name it stands for
    (``np`` to ``numpy``, ``load`` to ``joblib.load``)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                top = item.name.split(".")[0]
                aliases[item.asname or top] = item.name if item.asname else top
        elif isinstance(node, ast.ImportFrom):
            prefix = f"{node.module}." if node.module and not node.level else ""
            for item in node.names:
                aliases[item.asname or item.name] = f"{prefix}{item.name}"
    return aliases


def _bind_counts(tree: ast.AST) -> collections.Counter[str]:
    """How many times each name is bound anywhere in the file."""
    counts: collections.Counter[str] = collections.Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            counts[node.id] += 1
        elif isinstance(node, ast.arg):
            counts[node.arg] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for item in node.names:
                counts[(item.asname or item.name).split(".")[0]] += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            counts[node.name] += 1
        elif isinstance(node, ast.ExceptHandler) and node.name:
            counts[node.name] += 1
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            counts[node.name] += 1
    return counts


class _Scan:
    """One file's walk: the facts about its names, then the hits."""

    def __init__(self, tree: ast.Module, models: Sequence[UsageModel]) -> None:
        self._models = models
        self._parents: dict[ast.AST, ast.AST] = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        self._aliases = _import_aliases(tree)
        self._consts: dict[str, str] = {}
        self._defaults: dict[ast.AST, str] = {}
        self._cache: dict[ast.AST, str | None] = {}
        self._track_constants(tree)
        self._cache.clear()
        self._reached: list[set[str]] = [set() for _ in models]
        self.found: list[set[UsageAccess]] = [set() for _ in models]

    def run(self, tree: ast.Module) -> None:
        """Walk *tree* and record every top-level path expression that names a
        model. Non-binding expressions run first so a constant bound to a model
        path only falls back to ``unknown access`` when no read of that constant
        in the file reaches the model."""
        bindings: list[tuple[ast.AST, str]] = []
        for node in ast.walk(tree):
            bound = self._bound_name(node)
            if bound is not None:
                bindings.append((node, bound))
            else:
                self._take(node)
        for node, name in bindings:
            for index in self._hits(node):
                if name not in self._reached[index]:
                    self.found[index].add(UsageAccess.UNKNOWN)

    def results(self) -> list[frozenset[UsageAccess]]:
        """The accesses recorded for each model in the order given."""
        return [frozenset(found) for found in self.found]

    # -- paths ---------------------------------------------------------

    def _track_constants(self, tree: ast.Module) -> None:
        """Remember each name that is bound to a path once, in source order
        (so ``B = A + "/x"`` finds ``A``), including function defaults."""
        counts = _bind_counts(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._track_defaults(node.args, counts)
        assigns = sorted(
            (n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))),
            key=lambda n: (n.lineno, n.col_offset),
        )
        for node in assigns:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if node.value is None or len(targets) != 1:
                continue
            target = targets[0]
            if isinstance(target, ast.Name) and counts[target.id] == 1:
                value = self._static(node.value)
                if value is not None:
                    self._consts[target.id] = value

    def _track_defaults(
        self, args: ast.arguments, counts: collections.Counter[str]
    ) -> None:
        """Record single-bound parameter defaults as path constants."""
        pos = args.posonlyargs + args.args
        offset = len(pos) - len(args.defaults)
        pairs = [
            *zip(pos[offset:], args.defaults, strict=True),
            *zip(args.kwonlyargs, args.kw_defaults, strict=True),
        ]
        for arg, default in pairs:
            if default is not None and counts[arg.arg] == 1:
                value = self._static(default)
                if value is not None:
                    self._consts[arg.arg] = value
                    self._defaults[default] = arg.arg

    def _static(self, node: ast.AST, depth: int = 0) -> str | None:
        """The path *node* spells, or the end of it when its start is not
        known; ``None`` when it is no path of this file."""
        if depth > _MAX_DEPTH:
            return None
        if node in self._cache:
            return self._cache[node]
        value = self._eval_static(node, depth + 1)
        if value is not None and len(value) > _MAX_PATH_CHARS:
            value = None
        self._cache[node] = value
        return value

    def _eval_static(self, node: ast.AST, depth: int) -> str | None:
        """Compute the static path string for *node* at *depth*."""
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) and node.value else None
        if isinstance(node, ast.Name):
            ok = isinstance(node.ctx, ast.Load)
            return self._consts.get(node.id) if ok else None
        if isinstance(node, ast.JoinedStr):
            return self._fstring(node, depth)
        if isinstance(node, ast.BinOp):
            return self._binop(node, depth)
        if isinstance(node, ast.Call):
            return self._call_path(node, depth)
        return None

    def _fstring_part(self, part: ast.expr, depth: int) -> str | None:
        """The text of one part of an f-string; ``None`` when not known."""
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            return part.value
        if (
            isinstance(part, ast.FormattedValue)
            and part.conversion == -1
            and part.format_spec is None
        ):
            return self._static(part.value, depth)
        return None

    def _fstring(self, node: ast.JoinedStr, depth: int) -> str | None:
        """An f-string as a path; after a part that is not known, only what
        follows its last one, from the first separator on."""
        text, restarted = "", False
        for part in node.values:
            piece = self._fstring_part(part, depth)
            if piece is None:
                text, restarted = "", True
            else:
                text += piece
        if restarted:
            return after_first_separator(text)
        return text or None

    def _binop(self, node: ast.BinOp, depth: int) -> str | None:
        """``a + b``, ``a / b`` (``Path``) and ``a % b`` as a path."""
        if isinstance(node.op, ast.Mod):
            template = self._static(node.left, depth)
            if template is None:
                return None
            elts = (
                node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
            )
            return percent_template(template, [self._static(e, depth) for e in elts])
        right = self._static(node.right, depth)
        if right is None or not isinstance(node.op, (ast.Add, ast.Div)):
            return None
        left = self._static(node.left, depth)
        if isinstance(node.op, ast.Div):
            return join_path(left, right)
        if left is None:
            return after_first_separator(right)
        return left + right

    def _callee(self, func: ast.AST) -> tuple[str | None, str | None]:
        """The dotted name a call's callee stands for, with the file's
        imports resolved, and its last name; ``None`` where the callee is not
        a name (``f()()``), the last name still given for ``obj().method``."""
        names: list[str] = []
        node = func
        while isinstance(node, ast.Attribute):
            names.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None, func.attr if isinstance(func, ast.Attribute) else None
        names.append(node.id)
        names.reverse()
        dotted = ".".join([self._aliases.get(names[0], names[0]), *names[1:]])
        return dotted, dotted.rsplit(".", 1)[-1]

    def _call_path(self, call: ast.Call, depth: int) -> str | None:
        """What a call that builds or passes on a path gives, else ``None``."""
        dotted, last = self._callee(call.func)
        parts = [self._static(arg, depth) for arg in call.args]
        if dotted in _JOINS or last in _PATH_TYPES:
            return join_paths(parts) if parts else None
        if last in _PATH_FUNCTIONS and len(parts) == 1:
            return parts[0]
        if isinstance(call.func, ast.Attribute):
            receiver = self._static(call.func.value, depth)
            if call.func.attr in _SAME_PATH_METHODS:
                return receiver
            if call.func.attr == "joinpath":
                return join_paths([receiver, *parts])
            if call.func.attr == "format" and receiver is not None:
                kwargs = {
                    kw.arg: self._static(kw.value, depth)
                    for kw in call.keywords
                    if kw.arg is not None
                }
                return format_template(receiver, parts, kwargs)
        return None

    def _is_path_call(self, call: ast.Call) -> bool:
        """Whether *call* builds, passes through or formats a path."""
        dotted, last = self._callee(call.func)
        if dotted in _JOINS or last in _PATH_TYPES:
            return bool(call.args)
        if last in _PATH_FUNCTIONS:
            return len(call.args) == 1
        return isinstance(call.func, ast.Attribute) and call.func.attr in (
            *_SAME_PATH_METHODS,
            "joinpath",
            "format",
        )

    def _in_parent_path(self, node: ast.AST) -> bool:
        """Whether *node* is an operand of an enclosing path expression."""
        parent = self._parents.get(node)
        if isinstance(parent, (ast.JoinedStr, ast.FormattedValue)):
            return True
        if isinstance(parent, ast.BinOp):
            return isinstance(parent.op, (ast.Add, ast.Div, ast.Mod))
        if isinstance(parent, ast.Tuple):
            grand = self._parents.get(parent)
            return isinstance(grand, ast.BinOp) and isinstance(grand.op, ast.Mod)
        if isinstance(parent, ast.keyword):
            parent = self._parents.get(parent)
        if isinstance(parent, ast.Attribute) and parent.value is node:
            call = self._parents.get(parent)
            return (
                isinstance(call, ast.Call)
                and call.func is parent
                and self._is_path_call(call)
            )
        return (
            isinstance(parent, ast.Call)
            and node is not parent.func
            and self._is_path_call(parent)
        )

    # -- uses ----------------------------------------------------------

    def _bound_name(self, node: ast.AST) -> str | None:
        """If *node* is the value of a single-bound constant or parameter
        default, that name; else ``None``."""
        if node in self._defaults:
            return self._defaults[node]
        parent = self._parents.get(node)
        if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node:
            targets = (
                parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            )
            if len(targets) == 1 and isinstance(targets[0], ast.Name):
                name = targets[0].id
                if name in self._consts:
                    return name
        return None

    def _hits(self, node: ast.AST) -> list[int]:
        """Indices of *self._models* that top-level path *node* matches."""
        if not isinstance(
            node, (ast.Constant, ast.Name, ast.JoinedStr, ast.BinOp, ast.Call)
        ):
            return []
        if self._in_parent_path(node):
            return []
        text = self._static(node)
        if text is None:
            return []
        return [i for i, model in enumerate(self._models) if matches(text, model)]

    def _take(self, node: ast.AST) -> None:
        """Record *node* if it is a top-level path expression naming a model."""
        hits = self._hits(node)
        if not hits:
            return
        names = {
            sub.id
            for sub in ast.walk(node)
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
        }
        access = self._access(node)
        for index in hits:
            self._reached[index].update(names)
            if access is not None:
                self.found[index].add(access)

    def _access(self, node: ast.AST) -> UsageAccess | None:
        """What the code does with the path *node*; ``None`` when it only
        mentions it."""
        parent = self._parents.get(node)
        argument = node
        while isinstance(parent, (ast.keyword, ast.Starred, ast.BoolOp)) or (
            isinstance(parent, ast.IfExp) and argument is not parent.test
        ):
            argument, parent = parent, self._parents.get(parent)
        if isinstance(parent, ast.Call) and argument is not parent.func:
            return self._call_access(parent)
        if isinstance(parent, ast.Attribute) and argument is parent.value:
            return self._attribute_access(parent)
        if isinstance(parent, (ast.Expr, ast.Raise, ast.Assert)):
            return None
        return UsageAccess.UNKNOWN

    def _attribute_access(self, attr: ast.Attribute) -> UsageAccess:
        """What ``path.method(...)`` or ``path.attr`` does with ``path``."""
        call = self._parents.get(attr)
        if isinstance(call, ast.Call) and call.func is attr:
            if attr.attr == "open":
                return self._mode_access(call, RECEIVER_MODE_POSITION, "r")
            return access_of_name(attr.attr)
        return UsageAccess.UNKNOWN

    def _call_access(self, call: ast.Call) -> UsageAccess | None:
        """What a call does with a path it is given."""
        if isinstance(self._parents.get(call), ast.Raise):
            return None
        _, last = self._callee(call.func)
        if last is None:
            return UsageAccess.UNKNOWN
        if is_mention_call(last):
            return None
        if last in MODE_CALLS:
            position, default = MODE_CALLS[last]
            return self._mode_access(call, position, default)
        return access_of_name(last)

    def _mode_access(self, call: ast.Call, position: int, default: str) -> UsageAccess:
        """The access of an ``open``-like call from its mode argument; its
        default mode when left out, unknown when not a string."""
        mode: ast.AST | None = None
        if len(call.args) > position:
            mode = call.args[position]
        else:
            mode = next((kw.value for kw in call.keywords if kw.arg == "mode"), None)
        if mode is None:
            return access_of_mode(default)
        text = self._static(mode)
        return UsageAccess.UNKNOWN if text is None else access_of_mode(text)


def find_usages(
    tree: ast.Module, models: Sequence[UsageModel]
) -> list[frozenset[UsageAccess]]:
    """For each of *models*, the accesses *tree* makes to it, in the order of
    *models*; an empty set for a model it does not use.

    Raises:
        RecursionError: *tree* is nested too deeply to follow a path in it.
    """
    scan = _Scan(tree, models)
    scan.run(tree)
    return scan.results()
