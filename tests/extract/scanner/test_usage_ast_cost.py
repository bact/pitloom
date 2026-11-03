# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The cost of the AST model-usage walk: a script within the 1 MiB cap costs
time in its size, not in its size squared. Each shape here once took longer
the more of one thing a call held: arguments that name the model, keywords of
an ``open``-like call, the names of a long callee, nested conditionals.

See also: :mod:`tests.extract.scanner.test_usage_ast_edges` (the caps).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import ast
from typing import Any

import pytest

from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_ast import _Scan, find_usages
from pitloom.extract._usage_match import UsageModel
from pitloom.extract._usage_parse import parse_python
from tests._bounded import run_bounded

_MODEL = UsageModel("model.onnx", ("pkg/model.onnx",))
_N = 2000


class _CountingList(list[Any]):
    """A list that counts the searches made in it."""

    searches = 0

    def __contains__(self, item: object) -> bool:
        type(self).searches += 1
        return super().__contains__(item)

    def index(self, *args: Any) -> int:
        type(self).searches += 1
        return super().index(*args)


class _CountingDict(dict[Any, Any]):
    """A dict that counts the reads made of it with ``get``."""

    def __init__(self, data: dict[Any, Any]) -> None:
        super().__init__(data)
        self.reads = 0

    def get(self, *args: Any) -> Any:
        self.reads += 1
        return super().get(*args)


def _count_reads(source: str, field: str) -> tuple[int, set[UsageAccess]]:
    """Scan *source*; the reads made of the ``_Scan`` dict *field*, and the
    accesses found."""
    tree = parse_python(source)
    scan = _Scan(tree, [_MODEL])
    counting = _CountingDict(getattr(scan, field))
    setattr(scan, field, counting)
    scan.run(tree)
    return counting.reads, set(scan.results()[0])


@pytest.mark.parametrize(
    "source",
    [
        'p = "model.onnx"\nload(' + "p," * _N + ")\n",
        'p = "model.onnx"\nload(' + "*p," * _N + ")\n",
    ],
    ids=["names", "starred"],
)
def test_the_argument_list_is_not_searched_per_argument(source: str) -> None:
    tree = parse_python(source)
    (call,) = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    call.args = _CountingList(call.args)
    _CountingList.searches = 0
    (found,) = find_usages(tree, [_MODEL])
    assert _CountingList.searches < _N
    assert found == frozenset({UsageAccess.READ})


def test_an_open_like_call_reads_its_mode_once() -> None:
    keywords = "".join(f"k{i}=p, " for i in range(_N))
    tree = parse_python(f'p = "model.onnx"\nopen({keywords}mode="rb")\n')
    (call,) = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    searched: list[int] = []

    class _Keywords(list[Any]):
        def __iter__(self) -> Any:
            searched.append(1)
            return super().__iter__()

    call.keywords = _Keywords(call.keywords)
    assert find_usages(tree, [_MODEL]) == [frozenset({UsageAccess.READ})]
    assert len(searched) < _N // 10


def test_a_long_callee_is_resolved_once() -> None:
    source = 'p = "model.onnx"\nx' + ".b" * 200 + ".load(" + "p," * _N + ")\n"
    reads, found = _count_reads(source, "_aliases")
    assert found == {UsageAccess.READ}
    assert reads < _N


def test_nested_conditionals_are_climbed_once() -> None:
    depth = 1000
    source = "load(" + '"model.onnx" if c else ' * depth + '"model.onnx")\n'
    reads, found = _count_reads(source, "_parents")
    assert found == {UsageAccess.READ}
    assert reads < 20 * depth


def test_a_call_naming_the_model_in_every_argument_ends_in_time() -> None:
    """A 780 KB call took about a minute before (CPython 3.10)."""
    source = "load(" + '"model.onnx",' * 60_000 + ")\n"
    found = run_bounded(lambda: find_usages(parse_python(source), [_MODEL]))
    assert found == [frozenset({UsageAccess.READ})]
