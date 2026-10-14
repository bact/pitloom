# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for :mod:`pitloom.assemble.spdx3._dep_scope`: the edge kind of
a dependency read from its extra marker, and self-references.

See also: :mod:`tests.assemble.test_deps_extras_edges` (the same rules
through document assembly and the wheel route).
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

import random
from collections.abc import Sequence

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _dep_scope
from pitloom.assemble.spdx3._dep_scope import DependencyEdge, is_self_reference
from pitloom.core.extra_gate import Gate, MarkerShapeError, parse_gate
from tests._bounded import run_bounded

_REQ = spdx3.RelationshipType.dependsOn
_OPT = spdx3.RelationshipType.hasOptionalDependency


def dependency_edge(declared: list[str], project_name: str) -> DependencyEdge:
    """The edge to the one package *declared* resolve to, self-references
    dropped as :func:`pitloom.assemble.spdx3.deps.add_dependencies` does."""
    scopes = _dep_scope.DependencyScopes(declared, project_name)
    return scopes.edge([dep for dep in declared if not scopes.is_self_reference(dep)])


#: (declared strings of one package) -> (relationship type, comment).
_EDGES: dict[str, tuple[list[str], str, str | None]] = {
    "plain": (["foo>=1"], _REQ, None),
    "extra": (['foo; extra == "x"'], _OPT, "extras: x"),
    "two-extras": (['foo; extra == "b"', 'foo; extra == "a"'], _OPT, "extras: a, b"),
    "or-extras": (['foo; extra == "b" or extra == "a"'], _OPT, "extras: a, b"),
    "required-wins": (['foo; extra == "x"', "foo"], _REQ, None),
    "python-only": (['foo; python_version < "3.9"'], _REQ, None),
    "python-and-extra": (
        ['foo; python_version < "3.9" and extra == "x"'],
        _OPT,
        "extras: x",
    ),
    "parenthesised": (
        ['foo; (extra == "a" or extra == "b") and os_name == "nt"'],
        _OPT,
        "extras: a, b",
    ),
    "three-or": (
        ['foo; extra == "c" or extra == "a" or extra == "b"'],
        _OPT,
        "extras: a, b, c",
    ),
    "three-and": (
        ['foo; python_version < "3.9" and os_name == "nt" and extra == "x"'],
        _OPT,
        "extras: x",
    ),
    "not-in": (['foo; os_name not in "nt" and extra == "x"'], _OPT, "extras: x"),
    "less-equal": (
        ['foo; python_version <= "3.9" and extra == "x"'],
        _OPT,
        "extras: x",
    ),
    "reversed": (['foo; "x" == extra'], _OPT, "extras: x"),
    "spelling": (
        ['foo; extra == "Foo_Bar"', "foo; 'Foo.Bar' == extra"],
        _OPT,
        "extras: foo-bar",
    ),
    "old-style-specifier": (['idna (>=3); extra == "x"'], _OPT, "extras: x"),
    "empty": ([], _REQ, None),
}


@pytest.mark.parametrize(
    ("declared", "rel_type", "comment"), _EDGES.values(), ids=list(_EDGES)
)
def test_dependency_edge(
    declared: list[str],
    rel_type: str,
    comment: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        edge = dependency_edge(declared, "demo")

    assert (edge.rel_type, edge.scope, edge.comment) == (
        rel_type,
        None if rel_type == _OPT else spdx3.LifecycleScopeType.runtime,
        comment,
    )
    assert not caplog.records


@pytest.mark.parametrize(
    "dep",
    [
        'foo; extra != "x"',
        'foo; extra == "a" or python_version < "3.9"',
        'foo; extra in "ab"',
        'foo; "a" not in extra',
        'foo; extra == ""',
        'foo; extra == " "',
        "foo; extra == os_name",
    ],
    ids=[
        "not-equal",
        "or-python",
        "in",
        "not-in",
        "empty-name",
        "blank-name",
        "variable",
    ],
)
def test_unisolatable_extra_gate_is_required_with_one_warning(
    dep: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        edge = dependency_edge([dep, dep], "demo")

    assert (edge.rel_type, edge.comment) == (_REQ, None)
    assert [r.getMessage() for r in caplog.records] == [
        f"Dependency 'foo' declared as {dep!r} has an extra marker that can't be"
        " isolated -- recorded as a required dependency"
    ]


#: An entry with its own extra marker, declared in extra ``dev``, as each
#: backend writes it to ``Requires-Dist``: (marker, comment, warned).
_JOINED = {
    "setuptools-pdm": ('extra == "x" and extra == "dev"', "extras: dev, x", True),
    "hatchling": ("(extra == 'x') and extra == 'dev'", "extras: dev, x", True),
    "flit": ("extra == \"dev\" and ( extra == 'x')", "extras: dev, x", True),
    "or-and": (
        '(extra == "a" or extra == "b") and extra == "dev"',
        "extras: a, b, dev",
        True,
    ),
    "same-extra": ('extra == "dev" and extra == "dev"', "extras: dev", False),
    "hatchling-same": ("(extra == 'dev') and extra == 'dev'", "extras: dev", False),
}


@pytest.mark.parametrize(
    ("marker", "comment", "warned"), _JOINED.values(), ids=list(_JOINED)
)
def test_entry_requiring_extras_together_is_optional(
    marker: str, comment: str, warned: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: ``foo; extra == 'x'`` declared in extra ``dev`` (``extra
    == "x" and extra == "dev"``) was recorded as required, though never
    installed without an extra. It is optional for any of them, with one
    ``WARNING:`` that the inner condition is ignored; an extra repeated
    is no inner condition."""
    dep = f"foo; {marker}"
    with caplog.at_level("WARNING"):
        edge = dependency_edge([dep, dep], "demo")

    assert (edge.rel_type, edge.scope, edge.comment) == (_OPT, None, comment)
    assert caplog.messages == (
        [
            f"Ignoring the inner extra condition of extra entry {dep!r}: recorded"
            f" as optional ({comment})"
        ]
        if warned
        else []
    )


def test_unparsable_dependency_is_required_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Not PEP 508, so no gate can be read: required, warned once for the
    string however often it is declared."""
    dep = 'foo >= ; extra == "x"'
    with caplog.at_level("WARNING"):
        edge = dependency_edge([dep, dep], "demo")

    assert (edge.rel_type, edge.scope, edge.comment) == (
        _REQ,
        spdx3.LifecycleScopeType.runtime,
        None,
    )
    assert [r.getMessage() for r in caplog.records] == [
        f"Dependency {dep!r} is not a valid PEP 508 requirement"
        " -- recorded as a required dependency"
    ]


def test_unisolatable_self_reference_warns_what_it_does(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The requirements of the requested extra become required; no package
    is recorded for the self-reference itself."""
    declared = ['foo; extra == "y"', 'demo[y]; extra == "x" or python_version<"3"']
    with caplog.at_level("WARNING"):
        scopes = _dep_scope.DependencyScopes(declared, "demo")

    assert scopes.edge([declared[0]]).rel_type == _REQ
    [record] = caplog.records
    assert "requirements of the extras it requests" in record.getMessage()
    assert "recorded as a required dependency" not in record.getMessage()


@pytest.mark.parametrize(
    "marker",
    ["extra ==", '(extra == "a" b', 'extra == "a" )', 'extra == "a" ;', "extra == x"],
    ids=["end", "unbalanced", "trailing", "bad-char", "unquoted"],
)
def test_malformed_marker_text_is_rejected(marker: str) -> None:
    with pytest.raises(MarkerShapeError):
        parse_gate(marker)


#: Declared list with one non-self package -> its comment (None: required).
_SELF_REFERENCES: dict[str, tuple[list[str], str | None]] = {
    "includes": (
        ['foo; extra == "dev"', 'demo[dev]; extra == "full"'],
        "extras: dev, full",
    ),
    "chain": (
        [
            'foo; extra == "dev"',
            'demo[dev]; extra == "full"',
            'demo[full]; extra == "all"',
        ],
        "extras: all, dev, full",
    ),
    "self-cycle": (['foo; extra == "b"', 'demo[b]; extra == "b"'], "extras: b"),
    "mutual-cycle": (
        ['foo; extra == "a"', 'demo[b]; extra == "a"', 'demo[a]; extra == "b"'],
        "extras: a, b",
    ),
    "required-self-reference": (['foo; extra == "dev"', "demo[dev]"], None),
    "spelling": (
        ['foo; extra == "Dev_X"', 'Demo[dev.x]; extra == "full"'],
        "extras: dev-x, full",
    ),
    "other-extra": (
        ['foo; extra == "test"', 'demo[dev]; extra == "full"'],
        "extras: test",
    ),
}


@pytest.mark.parametrize(
    ("declared", "comment"), _SELF_REFERENCES.values(), ids=list(_SELF_REFERENCES)
)
def test_self_reference_adds_its_extra_to_included_requirements(
    declared: list[str], comment: str | None
) -> None:
    edge = dependency_edge(declared, "demo")

    assert edge.comment == comment
    assert edge.rel_type == (_REQ if comment is None else _OPT)


@pytest.mark.parametrize(
    ("dep", "expected"),
    [
        ('demo[x]; extra == "all"', True),
        ("Demo", True),
        ("demo-extra", False),
        (">=bad", False),
    ],
    ids=["extra", "spelling", "other-name", "unparsable"],
)
def test_is_self_reference(dep: str, expected: bool) -> None:
    assert is_self_reference(dep, "demo") is expected


def test_project_name_compared_canonically() -> None:
    """A project name spelled otherwise (``My_Demo``) still finds its
    self-references."""
    declared = ['foo; extra == "dev"', 'my-demo[dev]; extra == "full"']
    scopes = _dep_scope.DependencyScopes(declared, "My_Demo")

    assert scopes.edge(declared[:1]).comment == "extras: dev, full"
    assert is_self_reference("my.demo", "My_Demo")


def test_self_reference_closure_is_bounded() -> None:
    """Regression: every dependency walked every self-reference again,
    cubic in a chain's length (7 s for 800, a minute for 1600). Each
    extra's closure is worked out once."""
    length = 1600
    declared = [f'demo[e{i}]; extra == "e{i + 1}"' for i in range(length)]
    declared += [f'p{i}; extra == "e0"' for i in range(length)]

    scopes = run_bounded(lambda: _dep_scope.DependencyScopes(declared, "demo"))

    comment = scopes.edge([declared[-1]]).comment
    assert comment is not None
    assert len(comment.split(", ")) == length + 1


def _reference_closure(
    gate: Gate, includes: Sequence[tuple[Gate, frozenset[str]]]
) -> Gate:
    """The closure before it was memoised: one walk per gate; the contract."""
    if gate is None:
        return None
    extras, pending = set(gate), sorted(gate)
    while pending:
        extra = pending.pop()
        for including, requested in includes:
            if extra in requested:
                if including is None:
                    return None
                pending.extend(sorted(including - extras))
                extras |= including
    return frozenset(extras)


def test_closure_matches_the_reference() -> None:
    """Differential, seeded: required and gated self-references, cycles."""
    rng = random.Random(20261011)
    names = "abcdef"
    checked = 0
    for _ in range(300):
        includes = [
            (
                None if rng.random() < 0.15 else frozenset(rng.sample(names, 1)),
                frozenset(rng.sample(names, rng.randint(1, 2))),
            )
            for _ in range(rng.randint(0, 6))
        ]
        closures = _dep_scope._Closures(includes)
        for size in (1, 2):
            gate = frozenset(rng.sample(names, size))
            assert closures.of(gate) == _reference_closure(gate, includes)
            checked += _reference_closure(gate, includes) is None
    assert _dep_scope._Closures([]).of(None) is None
    assert checked > 20  # a required self-reference does end some closures
