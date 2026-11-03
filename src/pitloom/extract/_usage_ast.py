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
:mod:`pitloom.extract._usage_match` (what names a model),
:mod:`pitloom.extract._usage_parse` (the parse) and
:mod:`pitloom.extract.scanner` (``attach_usage_references``: the file
reading, the pre-filter and the messages).
"""

from __future__ import annotations

import ast
import collections
from collections.abc import Sequence
from typing import Any, Final

from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_match import (
    UsageModel,
    after_first_separator,
    format_template,
    join_path,
    join_paths,
    literal_text,
    matches,
    percent_template,
)
from pitloom.extract._usage_table import (
    MODE_CALLS,
    RECEIVER_MODE_POSITION,
    access_of_argument,
    access_of_mode,
    access_of_name,
    is_mention_call,
)

__all__ = ["find_usages"]

#: Caps on following one path expression. An expression over either is not
#: followed at all (no edge from it), not read as its tail.
_MAX_DEPTH: Final = 64
_MAX_PATH_CHARS: Final = 4096
#: An f-string conversion that leaves a string as it is: none or ``!s``.
_PLAIN_CONVERSIONS: Final = (-1, ord("s"))
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


#: The nodes that bind a type parameter (``def f[P]``): Python 3.12 or later.
_TYPE_PARAMS: Final[tuple[type[Any], ...]] = tuple(
    getattr(ast, name)
    for name in ("TypeVar", "ParamSpec", "TypeVarTuple")
    if hasattr(ast, name)
)


class _OverCap(Exception):
    """A path expression is deeper or longer than the caps allow."""


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
        elif isinstance(node, ast.MatchMapping) and node.rest:
            counts[node.rest] += 1
        elif isinstance(node, _TYPE_PARAMS):
            param: Any = node
            counts[param.name] += 1
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
        # Per node, so a call with many arguments, a long callee or nested
        # conditionals costs time in its size, not in its size squared.
        self._callees: dict[ast.AST, tuple[str | None, str | None]] = {}
        self._arg_indices: dict[ast.Call, dict[ast.AST, int]] = {}
        self._modes: dict[tuple[ast.Call, int], UsageAccess] = {}
        self._climbs: dict[ast.AST, tuple[ast.AST, ast.AST | None, bool]] = {}
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
        hit = [(node, name, self._hits(node)) for node, name in bindings]
        self._propagate_reach(hit)
        for _, name, indices in hit:
            for index in indices:
                if name not in self._reached[index]:
                    self.found[index].add(UsageAccess.UNKNOWN)

    def _propagate_reach(self, hit: list[tuple[ast.AST, str, list[int]]]) -> None:
        """A constant built from others is a read of them when it is read."""
        built: dict[str, list[tuple[set[str], list[int]]]] = {}
        for node, name, indices in hit:
            built.setdefault(name, []).append((self._loaded_names(node), indices))
        for index, reached in enumerate(self._reached):
            pending = list(reached)
            while pending:
                for loaded, indices in built.get(pending.pop(), ()):
                    if index in indices:
                        new = loaded - reached
                        reached |= new
                        pending.extend(new)

    def results(self) -> list[frozenset[UsageAccess]]:
        """The accesses recorded for each model in the order given."""
        return [frozenset(found) for found in self.found]

    # -- paths ---------------------------------------------------------

    def _track_constants(self, tree: ast.Module) -> None:
        """Remember each name that is bound to a path once, in source order
        (so ``B = A + "/x"`` finds ``A``), including function defaults."""
        counts = _bind_counts(tree)
        binders = sorted(
            (
                n
                for n in ast.walk(tree)
                if isinstance(
                    n,
                    (ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.AsyncFunctionDef),
                )
            ),
            key=lambda n: (n.lineno, n.col_offset),
        )
        for node in binders:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._track_defaults(node.args, counts)
                continue
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

    def _static(self, node: ast.AST) -> str | None:
        """The path *node* spells, or the end of it when its start is not
        known; ``None`` when it is no path of this file or is over the caps."""
        try:
            return self._sub(node, 0)
        except _OverCap:
            return None

    def _sub(self, node: ast.AST, depth: int) -> str | None:
        """:meth:`_static` for a part of an expression, *depth* levels in.

        Raises:
            _OverCap: The expression is too deep or too long to follow.
        """
        if depth > _MAX_DEPTH:
            raise _OverCap
        if node in self._cache:
            return self._cache[node]
        value = self._eval_static(node, depth + 1)
        if value is not None and len(value) > _MAX_PATH_CHARS:
            raise _OverCap
        self._cache[node] = value
        return value

    def _eval_static(self, node: ast.AST, depth: int) -> str | None:
        """Compute the static path string for *node* at *depth*."""
        if isinstance(node, ast.Constant):
            return literal_text(node.value) or None
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
        if isinstance(part, ast.Constant):
            return literal_text(part.value)
        if (
            isinstance(part, ast.FormattedValue)
            and part.conversion in _PLAIN_CONVERSIONS
            and part.format_spec is None
        ):
            return self._sub(part.value, depth)
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

    def _values(self, nodes: Sequence[ast.expr], depth: int) -> list[str | None]:
        """The paths of *nodes*, up to the first ``*iterable`` (what follows
        it has no known position)."""
        values: list[str | None] = []
        for node in nodes:
            if isinstance(node, ast.Starred):
                break
            values.append(self._sub(node, depth))
        return values

    def _percent(self, node: ast.BinOp, depth: int) -> str | None:
        """``template % values`` as a path."""
        template = self._sub(node.left, depth)
        if template is None:
            return None
        operand = node.right
        if isinstance(operand, ast.Dict):
            named: dict[str, str | None] = {}
            for key, value in zip(operand.keys, operand.values, strict=True):
                if not isinstance(key, ast.Constant):
                    # ``**d`` or a computed key may replace any earlier key.
                    named.update(dict.fromkeys(named))
                elif isinstance(key.value, str):
                    named[key.value] = self._sub(value, depth)
            return percent_template(template, named)
        elts = operand.elts if isinstance(operand, ast.Tuple) else [operand]
        return percent_template(template, self._values(elts, depth))

    def _binop(self, node: ast.BinOp, depth: int) -> str | None:
        """``a + b``, ``a / b`` (``Path``) and ``a % b`` as a path."""
        if isinstance(node.op, ast.Mod):
            return self._percent(node, depth)
        right = self._sub(node.right, depth)
        if right is None or not isinstance(node.op, (ast.Add, ast.Div)):
            return None
        left = self._sub(node.left, depth)
        if isinstance(node.op, ast.Div):
            return join_path(left, right)
        if left is None:
            return after_first_separator(right)
        return left + right

    def _callee(self, func: ast.AST) -> tuple[str | None, str | None]:
        """The dotted name a call's callee stands for, with the file's
        imports resolved, and its last name; ``None`` where the callee is not
        a name (``f()()``), the last name still given for ``obj().method``."""
        if func not in self._callees:
            self._callees[func] = self._resolve_callee(func)
        return self._callees[func]

    def _resolve_callee(self, func: ast.AST) -> tuple[str | None, str | None]:
        """:meth:`_callee`, not remembered."""
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
        parts = [self._sub(arg, depth) for arg in call.args]
        if dotted in _JOINS or last in _PATH_TYPES:
            return join_paths(parts) if parts else None
        if last in _PATH_FUNCTIONS and len(parts) == 1:
            return parts[0]
        if isinstance(call.func, ast.Attribute):
            receiver = self._sub(call.func.value, depth)
            if call.func.attr in _SAME_PATH_METHODS:
                return receiver
            if call.func.attr == "joinpath":
                return join_paths([receiver, *parts])
            if call.func.attr == "format" and receiver is not None:
                kwargs = {
                    kw.arg: self._sub(kw.value, depth)
                    for kw in call.keywords
                    if kw.arg is not None
                }
                return format_template(receiver, self._values(call.args, depth), kwargs)
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
        if isinstance(parent, ast.JoinedStr):
            return True
        if isinstance(parent, ast.FormattedValue):
            return parent.conversion in _PLAIN_CONVERSIONS and not parent.format_spec
        if isinstance(parent, ast.BinOp):
            return isinstance(parent.op, (ast.Add, ast.Div, ast.Mod))
        if isinstance(parent, (ast.Tuple, ast.Dict)):
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

    @staticmethod
    def _loaded_names(node: ast.AST) -> set[str]:
        """The names *node* reads."""
        return {
            sub.id
            for sub in ast.walk(node)
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load)
        }

    def _take(self, node: ast.AST) -> None:
        """Record *node* if it is a top-level path expression naming a model."""
        hits = self._hits(node)
        if not hits:
            return
        names = self._loaded_names(node)
        access = self._access(node)
        for index in hits:
            self._reached[index].update(names)
            if access is not None:
                self.found[index].add(access)

    def _access(self, node: ast.AST) -> UsageAccess | None:
        """What the code does with the path *node*; ``None`` when it only
        mentions it. A path rendered into a string (``f"{path!r}"``) is not the
        path any more: whatever consumes it, other than a mention, is unknown."""
        argument, parent, rendered = self._climb(node)
        access = self._consumer_access(argument, parent)
        return UsageAccess.UNKNOWN if rendered and access is not None else access

    @staticmethod
    def _passes_on(argument: ast.AST, parent: ast.AST) -> bool:
        """Whether *parent* hands the value *argument* on to its own parent."""
        if isinstance(parent, ast.IfExp):
            return argument is not parent.test
        return isinstance(
            parent,
            (ast.keyword, ast.Starred, ast.BoolOp, ast.JoinedStr, ast.FormattedValue),
        )

    def _climb(self, node: ast.AST) -> tuple[ast.AST, ast.AST | None, bool]:
        """The outermost node that hands *node*'s value on unchanged or
        rendered, its parent, and whether an f-string rendered it on the way.
        Each node climbed through remembers its own answer."""
        trail: list[tuple[ast.AST, bool]] = []
        argument, parent = node, self._parents.get(node)
        while (
            argument not in self._climbs
            and parent is not None
            and self._passes_on(argument, parent)
        ):
            trail.append((argument, isinstance(parent, ast.FormattedValue)))
            argument, parent = parent, self._parents.get(parent)
        top, consumer, rendered = self._climbs.setdefault(
            argument, (argument, parent, False)
        )
        for passed, into_fstring in reversed(trail):
            rendered = rendered or into_fstring
            self._climbs[passed] = (top, consumer, rendered)
        return self._climbs[node]

    def _consumer_access(
        self, argument: ast.AST, parent: ast.AST | None
    ) -> UsageAccess | None:
        """What *parent* does with *argument*, the path it was given."""
        if isinstance(parent, ast.Call) and argument is not parent.func:
            return self._call_access(parent, argument)
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

    def _call_access(self, call: ast.Call, argument: ast.AST) -> UsageAccess | None:
        """What a call does with the path it is given as *argument*."""
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
        if call not in self._arg_indices:
            self._arg_indices[call] = {arg: i for i, arg in enumerate(call.args)}
        return access_of_argument(last, self._arg_indices[call].get(argument))

    def _mode_access(self, call: ast.Call, position: int, default: str) -> UsageAccess:
        """The access of an ``open``-like call from its mode argument; its
        default mode when left out, unknown when not a string."""
        key = (call, position)
        if key not in self._modes:
            self._modes[key] = self._read_mode(call, position, default)
        return self._modes[key]

    def _read_mode(self, call: ast.Call, position: int, default: str) -> UsageAccess:
        """:meth:`_mode_access`, not remembered."""
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
    *models*; an empty set for a model it does not use. A path expression
    over the depth or length caps is not followed.
    """
    scan = _Scan(tree, models)
    scan.run(tree)
    return scan.results()
