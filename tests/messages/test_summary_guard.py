# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ratchet leaves a ``say_summary`` call out by the definition it
reaches (``scripts/message_inventory/_scope.py``), so the summaries must be
the catalogue's own: every ``Summary(...)`` is built in
``src/pitloom/messages/`` and listed in ``SUMMARIES``, and ``say_summary``
is only ever called by that name. An alias, a ``functools.partial``, a
stored reference or a ``dataclasses.replace`` copy of a catalogue summary
would hide its line from the inventory: an error here, never a silent hide.
Limit: a copy is found by the name it was imported under
(``from pitloom.messages... import S``), not through a module attribute.

See also: tests/scripts/message_inventory/test_summary_scope.py.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import pitloom.messages
from pitloom.messages import SUMMARIES, Summary

pytestmark = pytest.mark.platform  # walks the source tree by path

_SRC = Path(__file__).parents[2] / "src" / "pitloom"
_CATALOGUE = "messages/"
_SAY = "say_summary"


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def _summary_names(tree: ast.Module) -> set[str]:
    """The names *tree* imports from ``pitloom.messages`` that are summaries."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.split(".")[:2] != ["pitloom", "messages"]:
                continue
            module = importlib.import_module(node.module)
            for alias in node.names:
                if isinstance(getattr(module, alias.name, None), Summary):
                    names.add(alias.asname or alias.name)
    return names


def _copies_a_summary(node: ast.AST, summaries: set[str]) -> bool:
    """Whether *node* is a ``replace(S, ...)`` of a summary *S*."""
    return (
        isinstance(node, ast.Call)
        and _name(node.func) == "replace"
        and bool(node.args)
        and _name(node.args[0]) in summaries
    )


def _module_problems(rel: str, tree: ast.Module) -> list[str]:
    summaries = _summary_names(tree) if not rel.startswith(_CATALOGUE) else set()
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }

    def called(node: ast.AST) -> bool:
        call = parents.get(node)
        return isinstance(call, ast.Call) and call.func is node

    problems = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.alias) and node.asname is not None:
            if node.name.rpartition(".")[2] == _SAY:
                problems.append(f"{rel}:{line}: {_SAY} imported under another name")
        name = _name(node)
        if name == "Summary" and called(node) and not rel.startswith(_CATALOGUE):
            problems.append(f"{rel}:{line}: Summary built outside the catalogue")
        if name == _SAY and not called(node):
            problems.append(f"{rel}:{line}: {_SAY} used but not called")
        if _copies_a_summary(node, summaries):
            problems.append(f"{rel}:{line}: a summary copied outside the catalogue")
    return sorted(problems, key=lambda problem: int(problem.split(":")[1]))


def summary_problems(root: Path) -> list[str]:
    """Each place under *root* (a ``src/pitloom``) that builds a summary
    outside the catalogue or reaches ``say_summary`` other than by a call
    of that name."""
    problems = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        problems += _module_problems(rel, ast.parse(path.read_bytes()))
    return problems


def test_summaries_are_the_catalogues_and_called_by_name() -> None:
    assert summary_problems(_SRC) == []


def test_every_summary_built_is_in_summaries() -> None:
    """Counted by ``Summary(`` calls: one built inside a function is no
    module attribute, but it is a call."""
    calls = sum(
        isinstance(node, ast.Call) and _name(node.func) == "Summary"
        for path in sorted((_SRC / "messages").rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_bytes()))
    )
    found = {
        id(value): value
        for info in pkgutil.iter_modules(pitloom.messages.__path__)
        for value in vars(
            importlib.import_module(f"pitloom.messages.{info.name}")
        ).values()
        if isinstance(value, Summary)
    }
    assert calls == len(SUMMARIES) == len(found)
    assert set(found) == {id(summary) for summary in SUMMARIES}


_ADHOC = """\
import dataclasses
import functools
from pitloom.messages import Summary, say_summary
from pitloom.messages import say_summary as say
from pitloom.messages.id_registry_ids import DATASET_PATH_KEY, KEY_NOT_FOUND

S = Summary(template="x %(entity)s", meaning="m", topic="id-registry-ids")


def report(log, messages):
    say_summary(log, S, entity="a")
    functools.partial(say_summary, log, S)
    messages.say_summary(log, S, entity="a")
    keep = messages.say_summary
    dataclasses.replace(DATASET_PATH_KEY, template="y %(entity)s")
    dataclasses.replace(KEY_NOT_FOUND)
"""


def test_an_adhoc_summary_fails_the_guard(tmp_path: Path) -> None:
    (tmp_path / "zz_adhoc.py").write_bytes(_ADHOC.encode("utf-8"))

    assert summary_problems(tmp_path) == [
        "zz_adhoc.py:4: say_summary imported under another name",
        "zz_adhoc.py:7: Summary built outside the catalogue",
        "zz_adhoc.py:12: say_summary used but not called",
        "zz_adhoc.py:14: say_summary used but not called",
        "zz_adhoc.py:15: a summary copied outside the catalogue",
    ]
