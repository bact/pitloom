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
import re
import sys
import warnings
from collections.abc import Sequence
from typing import Final

from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_match import UsageModel, matches
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

_ROOT_START: Final = re.compile(r"^(?:[A-Za-z]:)?[/\\]")
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
_SAME_PATH_METHODS: Final = frozenset({"resolve", "expanduser", "absolute", "format"})


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


def _after_first_separator(text: str) -> str | None:
    """What follows the first separator of *text*, ``None`` when there is
    none or nothing follows: the first component may be only the end of one
    (the text came after something not known), so it is left out."""
    for index, char in enumerate(text):
        if char in "/\\":
            return text[index + 1 :] or None
    return None


def _join(left: str | None, right: str) -> str:
    """*right* appended to *left* as a path component; a rooted *right*
    replaces it, as in ``os.path.join``."""
    if left is None or _ROOT_START.match(right):
        return right
    head = left.rstrip("/\\")
    return f"{head}/{right}"


def _join_all(parts: Sequence[str | None]) -> str | None:
    """*parts* joined; what comes after the last part that is not known.
    ``None`` when the last part is not known."""
    joined: str | None = None
    for part in parts:
        joined = None if part is None else _join(joined, part)
    return joined


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """Each name the file imports to the dotted name it stands for
    (``np`` to ``numpy``, ``load`` to ``joblib.load``)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                top = item.name.split(".")[0]
                aliases[item.asname or top] = item.name if item.asname else top
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
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
        self._loads = collections.Counter(
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        )
        self._consts: dict[str, str] = {}
        self._track_constants(tree)
        self.found: list[set[UsageAccess]] = [set() for _ in models]

    def run(self, tree: ast.Module) -> None:
        """Walk *tree* from the top. A path that names a model, or one that
        is a path but names none, is not walked into: its parts are not paths
        of their own (``Path("a") / "m.bin"`` is not also ``"m.bin"``)."""
        stack: list[ast.AST] = [tree]
        while stack:
            node = stack.pop()
            if not self._take(node):
                stack.extend(ast.iter_child_nodes(node))

    def results(self) -> list[frozenset[UsageAccess]]:
        """The accesses recorded for each model in the order given."""
        return [frozenset(found) for found in self.found]

    # -- paths ---------------------------------------------------------

    def _track_constants(self, tree: ast.Module) -> None:
        """Remember each name that is assigned a path once, in source order
        (so ``B = A + "/x"`` finds ``A``)."""
        counts = _bind_counts(tree)
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

    def _static(self, node: ast.AST) -> str | None:
        """The path *node* spells, or the end of it when its start is not
        known; ``None`` when it is no path of this file."""
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) and node.value else None
        if isinstance(node, ast.Name):
            ok = isinstance(node.ctx, ast.Load)
            return self._consts.get(node.id) if ok else None
        if isinstance(node, ast.JoinedStr):
            return self._fstring(node)
        if isinstance(node, ast.BinOp):
            return self._binop(node)
        if isinstance(node, ast.Call):
            return self._call_path(node)
        return None

    def _fstring_part(self, part: ast.expr) -> str | None:
        """The text of one part of an f-string; ``None`` when not known."""
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            return part.value
        if (
            isinstance(part, ast.FormattedValue)
            and part.conversion == -1
            and part.format_spec is None
        ):
            return self._static(part.value)
        return None

    def _fstring(self, node: ast.JoinedStr) -> str | None:
        """An f-string as a path; after a part that is not known, only what
        follows its last one, from the first separator on (the end of the
        unknown part may be the start of a component)."""
        text, restarted = "", False
        for part in node.values:
            piece = self._fstring_part(part)
            if piece is None:
                text, restarted = "", True
            else:
                text += piece
        if restarted:
            return _after_first_separator(text)
        return text or None

    def _binop(self, node: ast.BinOp) -> str | None:
        """``a + b``, ``a / b`` (``Path``) and ``a % b`` as a path."""
        if isinstance(node.op, ast.Mod):
            return self._static(node.left)
        right = self._static(node.right)
        if right is None or not isinstance(node.op, (ast.Add, ast.Div)):
            return None
        left = self._static(node.left)
        if isinstance(node.op, ast.Div):
            return _join(left, right)
        if left is None:
            return _after_first_separator(right)
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

    def _call_path(self, call: ast.Call) -> str | None:
        """What a call that builds or passes on a path gives, else ``None``."""
        dotted, last = self._callee(call.func)
        parts = [self._static(arg) for arg in call.args]
        if dotted in _JOINS or last in _PATH_TYPES:
            return _join_all(parts) if parts else None
        if last in _PATH_FUNCTIONS and len(parts) == 1:
            return parts[0]
        if isinstance(call.func, ast.Attribute):
            receiver = self._static(call.func.value)
            if call.func.attr in _SAME_PATH_METHODS:
                return receiver
            if call.func.attr == "joinpath":
                return _join_all([receiver, *parts])
        return None

    # -- uses ----------------------------------------------------------

    def _take(self, node: ast.AST) -> bool:
        """Record *node* if it is a path that names a model; whether it is a
        path or a concatenation (so its parts are not looked at again)."""
        if not isinstance(
            node, (ast.Constant, ast.Name, ast.JoinedStr, ast.BinOp, ast.Call)
        ):
            return False
        text = self._static(node)
        if text is None:
            return isinstance(node, ast.JoinedStr) or (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, (ast.Add, ast.Div))
                and self._static(node.right) is not None
            )
        hits = [i for i, model in enumerate(self._models) if matches(text, model)]
        if hits:
            access = self._access(node)
            if access is not None:
                for index in hits:
                    self.found[index].add(access)
        return True

    def _access(self, node: ast.AST) -> UsageAccess | None:
        """What the code does with the path *node*; ``None`` when it only
        mentions it."""
        parent = self._parents.get(node)
        argument = node
        while isinstance(parent, (ast.keyword, ast.Starred)):
            argument, parent = parent, self._parents.get(parent)
        if isinstance(parent, ast.Call) and argument is not parent.func:
            return self._call_access(parent)
        if isinstance(parent, ast.Attribute) and argument is parent.value:
            return self._attribute_access(parent)
        if isinstance(parent, (ast.Expr, ast.Raise, ast.Assert)):
            return None
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            return self._binding(parent)
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

    def _binding(self, assign: ast.Assign | ast.AnnAssign) -> UsageAccess | None:
        """A path assigned to a name this file reads is used where the name
        is read; any other assignment (an attribute, a name never read, one
        that is assigned twice) says only that the file holds the path."""
        targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
        if len(targets) == 1 and isinstance(targets[0], ast.Name):
            name = targets[0].id
            if name in self._consts and self._loads[name]:
                return None
        return UsageAccess.UNKNOWN


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
