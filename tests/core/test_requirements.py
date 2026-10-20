# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.core.requirements: extras as a wheel lists them.

The expected strings are what a built wheel's ``Requires-Dist`` holds.
"""

import logging
import random
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from pitloom.core import requirements
from pitloom.core.pep508 import MAX_MARKER_NESTING, parse_requirement
from pitloom.core.requirements import (
    add_marker,
    flatten_optional_dependencies,
    normalize_dependency_specifier,
)
from tests._bounded import run_bounded
from tests._deep_marker import nested_marker

_SRC = "optional-dependencies"


@pytest.mark.parametrize(
    ("base", "optional", "expected"),
    [
        (["a>=1"], None, ["a>=1"]),
        (["a>=1"], {}, ["a>=1"]),
        (["a>=1"], {"dev": []}, ["a>=1"]),
        ([], {"dev": ["pytest>=8"]}, ['pytest>=8; extra == "dev"']),
        # Extras by canonical name, requirements in declared order.
        (
            [],
            {"zed": ["b", "a"], "Alpha_X": ["c"]},
            ['c; extra == "alpha-x"', 'b; extra == "zed"', 'a; extra == "zed"'],
        ),
        # Two spellings of one extra merge under the canonical name.
        (
            [],
            {"Foo_Bar": ["a"], "foo-bar": ["b"]},
            ['a; extra == "foo-bar"', 'b; extra == "foo-bar"'],
        ),
        # An existing marker is kept; an `or` keeps its parentheses.
        (
            [],
            {
                "e": [
                    "x; python_version < '3.11'",
                    "y; os_name == 'a' or os_name == 'b'",
                ]
            },
            [
                'x; python_version < "3.11" and extra == "e"',
                'y; (os_name == "a" or os_name == "b") and extra == "e"',
            ],
        ),
        # Old-style specifier, an uncanonical name, a self-reference.
        (
            [],
            {"dev": ["idna (>=3)", "Foo_Bar>=1"], "full": ["demo[dev]"]},
            [
                'idna>=3; extra == "dev"',
                'foo-bar>=1; extra == "dev"',
                'demo[dev]; extra == "full"',
            ],
        ),
        # A package in the base and in an extra stays twice (required wins later).
        (["a>=1"], {"dev": ["a>=2"]}, ["a>=1", 'a>=2; extra == "dev"']),
        # A string repeated, or spelled otherwise, in one extra stays once.
        ([], {"dev": ["Foo_Bar", "foo-bar", "Foo_Bar"]}, ['foo-bar; extra == "dev"']),
    ],
    ids=[
        "no-table",
        "empty-table",
        "empty-extra",
        "one-extra",
        "order",
        "spellings-merge",
        "marker-merge",
        "syntax-and-self-reference",
        "base-and-extra",
        "repeat",
    ],
)
def test_flatten_optional_dependencies(
    base: list[str], optional: Any, expected: list[str]
) -> None:
    assert flatten_optional_dependencies(base, optional, source=_SRC) == expected


@pytest.mark.parametrize(
    ("extra", "source", "quiet"),
    [("dev", _SRC, False), ("Dev", "extras_require", False), ("dev", _SRC, True)],
    ids=["dev", "Dev-extras_require", "quiet"],
)
def test_an_invalid_requirement_is_skipped_with_a_warning(
    caplog: pytest.LogCaptureFixture, extra: str, source: str, quiet: bool
) -> None:
    """Left bare it would read as a required dependency; tagged it is
    invalid. The warning names the extra by its canonical name and the
    table by *source*; *quiet* silences it."""
    with caplog.at_level(logging.WARNING):
        flat = flatten_optional_dependencies(
            [], {extra: ["not valid >=", "ok"]}, source=source, quiet=quiet
        )
    assert flat == ['ok; extra == "dev"']
    assert caplog.messages == (
        []
        if quiet
        else [
            f"Skipping extra entry 'not valid >=' of 'dev' ({source}):"
            " not a valid PEP 508 requirement"
        ]
    )


def test_the_inputs_are_not_modified() -> None:
    base, optional = ["a"], {"dev": ["b"]}
    flatten_optional_dependencies(base, optional, source=_SRC)
    assert base == ["a"]
    assert optional == {"dev": ["b"]}


@pytest.mark.parametrize(
    ("optional", "expected"),
    [
        pytest.param(
            {"all": ["demo[test]"], "dev": ["b"], "test": ["demo[dev]", "c"]},
            ['b; extra == "all"', 'c; extra == "all"']
            + ['b; extra == "dev"', 'b; extra == "test"', 'c; extra == "test"'],
            id="chain",
        ),
        pytest.param(
            {"a": ["demo[b]", "x"], "b": ["demo[a]", "y"]},
            ['y; extra == "a"', 'x; extra == "a"']
            + ['x; extra == "b"', 'y; extra == "b"'],
            id="cycle",
        ),
        pytest.param({"all": ["demo[all]", "z"]}, ['z; extra == "all"'], id="self"),
        pytest.param({"all": ["demo", "demo>=1"]}, [], id="no-extras"),
        pytest.param(
            {"Dev": ["b"], "all": ["DEMO[Dev,dev]", "b"]},
            ['b; extra == "all"', 'b; extra == "dev"'],
            id="spelling-and-repeat",
        ),
        pytest.param(
            {"d": ["w"], "c": ["x"], "b": ["y"], "a": ["z"], "all": ["demo[D,c,B,A]"]},
            ['z; extra == "a"']
            + [f'{r}; extra == "all"' for r in "zyxw"]
            + ['y; extra == "b"', 'x; extra == "c"', 'w; extra == "d"'],
            id="several-extras-canonical-order",
        ),
        pytest.param(
            {
                "dev": ["b; os_name=='nt'", "c"],
                "all": ["demo[dev]; python_version>'3'"],
            },
            [
                'b; (os_name == "nt" and python_version > "3") and extra == "all"',
                'c; python_version > "3" and extra == "all"',
                'b; os_name == "nt" and extra == "dev"',
                'c; extra == "dev"',
            ],
            id="marker",
        ),
    ],
)
def test_self_reference_is_expanded(optional: Any, expected: list[str]) -> None:
    """``demo[dev]`` in an extra (``demo`` the project) expanded: see each
    id."""
    assert flatten_optional_dependencies([], optional, "Demo", source=_SRC) == expected


@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
def test_self_reference_to_an_undeclared_extra_warns_once(
    caplog: pytest.LogCaptureFixture, quiet: bool
) -> None:
    """Warned where it is declared, not again where that extra is included;
    *quiet* silences it."""
    optional = {"dev": ["demo[nope]", "b"], "all": ["demo[dev]"]}
    with caplog.at_level(logging.WARNING):
        flat = flatten_optional_dependencies(
            [], optional, "demo", source="Poetry", quiet=quiet
        )
    assert flat == ['b; extra == "all"', 'b; extra == "dev"']
    assert caplog.messages == (
        []
        if quiet
        else [
            "Skipping extra entry 'demo[nope]' of 'dev' (Poetry): extra 'nope'"
            " is not declared"
        ]
    )


@pytest.mark.parametrize(
    ("optional", "warnings"),
    [
        (
            {"b": ["demo[a]; os_name == 'nt'", "y"], "a": ["demo[b]", "x"], "c": []},
            ["'demo[a]; os_name == \"nt\"' of 'b' (P): self-reference cycle among"
             " extras 'a', 'b'"],
        ),
        (
            {"all": ["demo[all]", "z"], "x": ["demo[y]"], "y": ["demo[x,z]"],
             "z": ["q"]},
            ["'demo[all]' of 'all' (P): self-reference cycle among extras 'all'",
             "'demo[x,z]' of 'y' (P): self-reference cycle among extras 'x', 'y'"],
        ),
        ({"all": ["demo[dev]"], "dev": ["demo"]}, []),
    ],
    ids=["two", "self-and-two", "none"],
)  # fmt: skip
@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
def test_a_self_reference_cycle_warns_once(
    caplog: pytest.LogCaptureFixture,
    optional: dict[str, list[str]],
    warnings: list[str],
    quiet: bool,
) -> None:
    """A cycle is reported, not dropped silently: one ``WARNING:`` per
    cycle, in the shared skipping wording, naming the reference back to
    its first extra and every extra on it; *quiet* silences it."""
    with caplog.at_level(logging.WARNING):
        flatten_optional_dependencies([], optional, "demo", source="P", quiet=quiet)
    assert caplog.messages == (
        [] if quiet else [f"Skipping extra entry {w}" for w in warnings]
    )


def test_normalize_dependency_specifier_keeps_invalid_requirement() -> None:
    """A string that is not PEP 508 comes back unchanged."""
    assert normalize_dependency_specifier("invalid requirement syntax >= 1.0 <=") == (
        "invalid requirement syntax >= 1.0 <="
    )


def _chain(length: int, *references: str) -> dict[str, list[str]]:
    """Extras ``e0`` to ``e<length>``: each lists *references* to the next
    (``{}`` the next extra's name), the last one ``x``."""
    optional = {
        f"e{i}": [ref.format(f"demo[e{i + 1}]") for ref in references]
        for i in range(length)
    }
    return {**optional, f"e{length}": ["x"]}


@pytest.mark.parametrize(
    ("optional", "count"),
    [
        # 2**40 paths; one marker level more on each path that takes it.
        (_chain(40, "{}", "{}; os_name == 'a'"), sum(range(42))),
        # Once a RecursionError.
        (_chain(2000, "{}"), 2001),
    ],
    ids=["doubled-40", "chain-2000"],
)
def test_self_reference_expansion_is_bounded(
    caplog: pytest.LogCaptureFixture, optional: Any, count: int
) -> None:
    """Each extra is expanded once, iteratively (not per path, which is
    exponential in the depth of doubled references); the whole result is
    kept, no cap hit."""
    with caplog.at_level(logging.WARNING):
        flat = run_bounded(
            lambda: flatten_optional_dependencies([], optional, "demo", source=_SRC)
        )
    assert len(flat) == count
    assert all(text.startswith("x;") for text in flat)
    assert not caplog.messages


_CAPPED = {
    "all": ["demo[mid]; os_name == 'a'"],
    "mid": ["demo[dev]; os_name == 'b'"],
    "dev": ["x"],
}


@pytest.mark.parametrize(
    ("cap", "limit", "warning"),
    [
        ("MAX_EXPANSION_ENTRIES", 5, None),
        ("MAX_EXPANSION_ENTRIES", 4, "4-entry self-reference expansion"),
        ("MAX_EXPANSION_MARKERS", 2, None),
        ("MAX_EXPANSION_MARKERS", 1, "1-marker self-reference nesting"),
    ],
    ids=["entries-at", "entries-over", "markers-at", "markers-over"],
)
@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
def test_expansion_over_a_cap_keeps_self_references(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    cap: str,
    limit: int,
    warning: str | None,
    quiet: bool,
) -> None:
    """``_CAPPED`` takes 5 entries (3 read, 2 copied) and nests 2 markers.
    Over a cap every self-reference is kept as declared, with one
    ``WARNING:`` naming the table; *quiet* silences it."""
    monkeypatch.setattr(requirements, cap, limit)
    with caplog.at_level(logging.WARNING):
        flat = flatten_optional_dependencies(
            [], _CAPPED, "demo", source=_SRC, quiet=quiet
        )
    assert flat[1] == 'x; extra == "dev"'
    if warning is None:
        assert flat[0] == 'x; (os_name == "b" and os_name == "a") and extra == "all"'
    else:
        assert flat[0] == 'demo[mid]; os_name == "a" and extra == "all"'
    expected = f"FIELD={_SRC}: larger than the {warning} cap; self-references"
    assert caplog.messages == (
        [] if quiet or warning is None else [f"{expected} kept as declared"]
    )


_AT_CAP = "x; " + nested_marker(MAX_MARKER_NESTING)


@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
def test_a_marker_joined_over_the_nesting_cap_is_not_joined(
    caplog: pytest.LogCaptureFixture, quiet: bool
) -> None:
    """A requirement at the nesting cap parses, but joined to another
    marker it nests over it: a required one is kept, an extra's skipped, a
    self-reference reaching it keeps every self-reference as declared, each
    with one ``WARNING:``; *quiet* silences them."""
    optional = {"all": ["demo[dev]; os_name == 'a'"], "dev": [_AT_CAP]}
    with caplog.at_level(logging.WARNING):
        flat = flatten_optional_dependencies(
            [_AT_CAP], optional, "demo", source=_SRC, quiet=quiet
        )
    assert flat == [_AT_CAP, 'demo[dev]; os_name == "a" and extra == "all"']
    cap = "larger than the 64-level marker-nesting cap"
    assert caplog.messages == (
        []
        if quiet
        else [
            f"FIELD={_SRC}: {cap}; self-references kept as declared",
            f"Skipping extra entry {str(parse_requirement(_AT_CAP))[:120]!r}..."
            " of 'dev'"
            f" ({_SRC}): {cap}",
        ]
    )


def _reference_expand(
    by_extra: dict[str, list[Requirement]], chain: tuple[str, ...]
) -> list[Requirement]:
    """The expansion before it was made iterative: recursive, every path
    expanded again; the contract for the result."""
    out = []
    for req in by_extra[chain[-1]]:
        if canonicalize_name(req.name) != "demo":
            out.append(Requirement(str(req)))
            continue
        for name in sorted({canonicalize_name(e) for e in req.extras}):
            if name in by_extra and name not in chain:
                for sub in _reference_expand(by_extra, (*chain, name)):
                    if req.marker:
                        add_marker(sub, str(req.marker))
                    out.append(sub)
    return out


def _reference_flatten(optional: dict[str, list[str]]) -> list[str]:
    by_extra: dict[str, list[Requirement]] = {}
    for extra, texts in optional.items():
        by_extra.setdefault(canonicalize_name(extra), []).extend(
            Requirement(text) for text in texts
        )
    flat: list[str] = []
    for extra in sorted(by_extra):
        tagged = []
        for req in _reference_expand(by_extra, (extra,)):
            add_marker(req, f'extra == "{extra}"')
            tagged.append(normalize_dependency_specifier(str(req)))
        flat.extend(dict.fromkeys(tagged))
    return flat


def _random_extras(rng: random.Random) -> dict[str, list[str]]:
    """Up to 5 extras, any spelling, listing requirements with and without
    markers and self-references (cycles too) with and without markers."""
    names = [rng.choice(["e{}", "E_{}"]).format(i) for i in range(rng.randint(1, 5))]
    leaves = ["a", "b>=1", "a; os_name == 'nt'", "c; os_name == 'a' or os_name == 'b'"]
    markers = ["", "; os_name == 'nt'", "; python_version < '4' or os_name == 'y'"]
    optional: dict[str, list[str]] = {}
    for name in names:
        optional[name] = []
        for _ in range(rng.randint(0, 4)):
            extras = ",".join(rng.sample([*names, "zz"], rng.randint(0, 2)))
            reference = f"Demo[{extras}]{rng.choice(markers)}"
            optional[name].append(rng.choice([rng.choice(leaves), reference]))
    return optional


def test_expansion_matches_the_recursive_reference() -> None:
    """Differential, seeded: same strings, same order, same marker merging
    as the recursive expansion, cycles included."""
    rng = random.Random(20261011)
    cases = [_random_extras(rng) for _ in range(400)]
    cyclic = sum(any("Demo[" in t for t in c.get("e0", [])) for c in cases)
    assert cyclic > 50  # the cases do reference themselves
    for optional in cases:
        flat = flatten_optional_dependencies(
            [], optional, "demo", source=_SRC, quiet=True
        )
        assert flat == _reference_flatten(optional), optional
