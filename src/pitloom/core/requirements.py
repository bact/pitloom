# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PEP 508 dependency strings as a built wheel's ``Requires-Dist`` lists
them: names canonicalized, extras tagged ``extra == "x"``.

No Pitloom imports but :mod:`pitloom.logging_config` and
:mod:`pitloom.core.pep508`, so any extractor can use it without an import
cycle through :mod:`pitloom.core.models`.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple, TypeAlias

from hatchling.metadata.utils import normalize_requirement
from packaging.markers import InvalidMarker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from pitloom.core.pep508 import MAX_MARKER_NESTING, parse_marker, parse_requirement
from pitloom.logging_config import excerpt
from pitloom.messages import Cap, warn_over_cap

log = logging.getLogger(__name__)

#: Most entries expanding the project's self-references may read and copy,
#: every extra together: a requirement or self-reference read, or a
#: requirement copied into the extra that includes it. Real projects need a
#: few hundred; over it, every self-reference is kept as declared.
MAX_EXPANSION_ENTRIES = 100_000
#: Most self-reference markers one expanded requirement may nest:
#: ``packaging`` parses a marker recursively, a few frames a level. Over
#: it, every self-reference is kept as declared.
MAX_EXPANSION_MARKERS = 64
#: The reason a skipping ``WARNING:`` gives for a requirement that cannot
#: be parsed.
NOT_PEP_508 = "not a valid PEP 508 requirement"

__all__ = [
    "NOT_PEP_508",
    "add_marker",
    "flatten_optional_dependencies",
    "normalize_dependency_specifier",
    "warn_joined_extra_entry",
    "warn_skipped_dependency",
    "warn_skipped_extra_entry",
]


def warn_skipped_dependency(
    source: str, entry: object, reason: str, *, quiet: bool = False
) -> None:
    """``WARNING:`` that the dependency *entry* declared in *source* (e.g.
    ``Poetry``) is not listed: the wording of
    :func:`warn_skipped_extra_entry` for an entry of no particular extra.
    Silent when *quiet*."""
    if not quiet:
        log.warning("Skipping dependency %s (%s): %s", excerpt(entry), source, reason)


def warn_skipped_extra_entry(
    source: str, extra: str, entry: object, reason: str, *, quiet: bool = False
) -> None:
    """``WARNING:`` that *entry* of *extra* declared in *source* (e.g.
    ``optional-dependencies``) is not used: the one wording every route
    shares, *entry* as :func:`~pitloom.logging_config.excerpt` shows it.
    Silent when *quiet*."""
    if not quiet:
        log.warning(
            "Skipping extra entry %s of %r (%s): %s",
            excerpt(entry),
            extra,
            source,
            reason,
        )


def warn_joined_extra_entry(entry: str, extras: Iterable[str]) -> None:
    """``WARNING:`` that *entry*, requiring several *extras* together (a
    requirement with an extra marker of its own, declared in another
    extra), is recorded as optional for any of them: the wording of
    :func:`warn_skipped_extra_entry` for an entry kept. Read when the
    document is assembled, so never from a read whose value is discarded
    (no *quiet*)."""
    log.warning(
        "Ignoring the inner extra condition of extra entry %r: recorded as"
        " optional (extras: %s)",
        entry,
        ", ".join(sorted(extras)),
    )


def add_marker(req: Requirement, marker: str) -> None:
    """Join *marker* to *req*'s own marker with ``and``, in place.

    Raises:
        packaging.markers.InvalidMarker: *marker* is not a valid marker,
            or the joined one nests too deep
            (:func:`~pitloom.core.pep508.parse_marker`, quietly).
    """
    joined = f"({req.marker}) and ({marker})" if req.marker else marker
    req.marker = parse_marker(joined, quiet=True)


def normalize_dependency_specifier(dep: str, *, quiet: bool = False) -> str:
    """Return *dep* with its package name and extras canonicalized to PEP
    503 form, its specifier and marker spelt as ``packaging`` spells them;
    *dep* as it is when not PEP 508 (*quiet* silences the nesting-cap
    ``WARNING:``)."""
    try:
        req = parse_requirement(dep, quiet=quiet)
    except InvalidRequirement:
        return dep
    normalize_requirement(req)
    return str(req)


def flatten_optional_dependencies(
    base: Iterable[str],
    optional: Mapping[str, Iterable[str]] | None,
    project_name: str | None = None,
    *,
    source: str,
    quiet: bool = False,
) -> list[str]:
    """*base* followed by each extra's requirements, tagged ``extra == "x"``.

    The shape of a built wheel's ``Requires-Dist``. Extras are ordered by
    their PEP 685 canonical name (two spellings of one extra merge), each
    extra's requirements in declared order, a repeated string once. An
    existing marker is kept: ``x; python_version < "3.11"`` in extra ``e``
    becomes ``x; python_version < "3.11" and extra == "e"``. A requirement
    that is not valid PEP 508 is skipped with a ``WARNING:``, since it
    cannot be tagged and left bare it would read as a required dependency;
    so is one whose tagged marker nests over
    :data:`~pitloom.core.pep508.MAX_MARKER_NESTING`. ``None`` (no table)
    and ``{}`` (an empty table) add nothing.

    A requirement on *project_name* itself (``demo[dev]`` in extra ``all``)
    is expanded Pitloom's own way: replaced by the requirements of the
    extras it names, transitively, in canonical extra-name order, its own
    marker joined to theirs. It names no extra: it adds nothing. It names
    an extra not declared: that extra is skipped with a ``WARNING:``. A
    cycle of self-references is dropped where it closes (an extra already
    being expanded adds nothing again), with one ``WARNING:`` per cycle
    naming its extras. An expansion over :data:`MAX_EXPANSION_ENTRIES` or
    :data:`MAX_EXPANSION_MARKERS`, or joining a marker nesting over
    :data:`~pitloom.core.pep508.MAX_MARKER_NESTING`, is not done: every
    self-reference is kept as declared, with one ``WARNING:``.

    No build backend writes exactly these strings: Hatchling 1.32.3 drops
    the self-reference's marker and fails the build on a cycle; setuptools
    and flit_core keep ``demo[dev]`` as declared. The routes reading a
    wheel's ``Requires-Dist`` therefore list other strings, but every route
    assembles the same edges (each requirement's extras, the
    self-reference's gate included).

    *source* names the table in each ``WARNING:`` (e.g. ``extras_require``,
    see :func:`warn_skipped_extra_entry`); *quiet* silences them.
    """
    by_extra = _parse_extras(optional, source, quiet)
    texts = {extra: [str(req) for req in reqs] for extra, reqs in by_extra.items()}
    own = canonicalize_name(project_name) if project_name else None
    if own is not None:
        _warn_undeclared_self_extras(by_extra, own, source, quiet)
        expansion = _Expansion(by_extra, own)
        try:
            texts = expansion.texts()
        except _OverCap as over:
            if not quiet:
                warn_over_cap(log, over.cap, source, "self-references kept as declared")
        else:
            _warn_cycles(expansion, source, quiet)
    flat = list(base)
    for extra in sorted(texts):
        tag = f'extra == "{extra}"'
        seen: set[str] = set()
        for text in texts[extra]:
            try:
                tagged = normalize_dependency_specifier(_with_marker(text, tag))
            except (InvalidMarker, InvalidRequirement) as exc:
                warn_skipped_extra_entry(source, extra, text, str(exc), quiet=quiet)
                continue
            if tagged not in seen:
                seen.add(tagged)
                flat.append(tagged)
    return flat


def _parse_extras(
    optional: Mapping[str, Iterable[str]] | None, source: str, quiet: bool
) -> dict[str, list[Requirement]]:
    """*optional*'s requirements parsed, by canonical extra name; one that
    is not valid PEP 508 is skipped with a ``WARNING:``."""
    by_extra: dict[str, list[Requirement]] = {}
    for extra, requirements in (optional or {}).items():
        parsed = by_extra.setdefault(canonicalize_name(extra), [])
        for text in requirements:
            try:
                parsed.append(parse_requirement(text, quiet=quiet))
            except InvalidRequirement:
                warn_skipped_extra_entry(
                    source,
                    canonicalize_name(extra),
                    text,
                    NOT_PEP_508,
                    quiet=quiet,
                )
    return by_extra


def _warn_undeclared_self_extras(
    by_extra: dict[str, list[Requirement]], own: str, source: str, quiet: bool
) -> None:
    """Warn of each extra a requirement on the project *own* names but
    *by_extra* does not declare, once, in the extra listing it."""
    for extra in sorted(by_extra):
        for req in by_extra[extra]:
            if canonicalize_name(req.name) != own:
                continue
            for missing in sorted({canonicalize_name(e) for e in req.extras}):
                if missing not in by_extra:
                    warn_skipped_extra_entry(
                        source,
                        extra,
                        str(req),
                        f"extra {missing!r} is not declared",
                        quiet=quiet,
                    )


def _warn_cycles(expansion: _Expansion, source: str, quiet: bool) -> None:
    """One skipping ``WARNING:`` per cycle of self-references the
    *expansion* dropped (:meth:`_Expansion.cycles`), naming its extras."""
    for extra, entry, members in expansion.cycles():
        cycle = ", ".join(repr(member) for member in members)
        warn_skipped_extra_entry(
            source,
            extra,
            entry,
            f"self-reference cycle among extras {cycle}",
            quiet=quiet,
        )


def _with_marker(text: str, marker: str | None) -> str:
    """The requirement *text* with *marker* joined to its own
    (:func:`add_marker`); *text* as is when *marker* is ``None``.

    Raises:
        packaging.markers.InvalidMarker: the joined marker nests too deep
            (:func:`~pitloom.core.pep508.parse_marker`).
        packaging.requirements.InvalidRequirement: *text* cannot be
            parsed (:func:`~pitloom.core.pep508.parse_requirement`).
    """
    if marker is None:
        return text
    req = parse_requirement(text, quiet=True)
    add_marker(req, marker)
    return str(req)


#: The parentheses a marker joined while expanding may nest.
_NESTING_CAP = Cap(MAX_MARKER_NESTING, "level", "marker-nesting", "FIELD")


class _OverCap(Exception):
    """The expansion is over *cap*."""

    def __init__(self, cap: Cap) -> None:
        super().__init__(cap.purpose)
        self.cap = cap


class _Ref(NamedTuple):
    """A self-reference to the extra *name*, with its *marker*, from the
    requirement declared as *text*."""

    name: str
    marker: str | None
    text: str


@dataclass(frozen=True)
class _Expanded:
    """An extra's requirement texts, repeats dropped, and how many
    self-reference markers the deepest one nests."""

    texts: list[str]
    markers: int


#: ``(extra, the extras being expanded that it can reach)``: the expansion
#: of the extra depends on nothing else.
_Key: TypeAlias = "tuple[str, frozenset[str]]"


# pylint: disable-next=too-few-public-methods
class _Components:
    """The strongly connected components of a graph (Tarjan's algorithm,
    iterative): :attr:`of` maps each node to its component."""

    def __init__(self, graph: Mapping[str, Sequence[str]]) -> None:
        self.of: dict[str, int] = {}
        self._graph = graph
        self._index: dict[str, int] = {}
        self._low: dict[str, int] = {}
        self._stack: list[str] = []
        for root in graph:
            if root not in self._index:
                self._visit(root)

    def _visit(self, root: str) -> None:
        work = [(root, self._open(root))]
        while work:
            node, edges = work[-1]
            nxt = next((n for n in edges if self._is_new(node, n)), None)
            if nxt is not None:
                work.append((nxt, self._open(nxt)))
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                self._low[parent] = min(self._low[parent], self._low[node])
            self._close(node)

    def _open(self, node: str) -> Iterator[str]:
        self._index[node] = self._low[node] = len(self._index)
        self._stack.append(node)
        return iter(self._graph[node])

    def _is_new(self, node: str, nxt: str) -> bool:
        """Whether *nxt*, an edge of *node*, is not visited yet; one on the
        stack lowers *node*'s link."""
        if nxt not in self._index:
            return True
        if nxt not in self.of:
            self._low[node] = min(self._low[node], self._index[nxt])
        return False

    def _close(self, node: str) -> None:
        """Pop *node*'s component when *node* is its root."""
        if self._low[node] == self._index[node]:
            while (member := self._stack.pop()) != node:
                self.of[member] = self._index[node]
            self.of[node] = self._index[node]


# pylint: disable-next=too-few-public-methods
class _Expansion:
    """Every extra's requirements, self-references expanded.

    Iterative, and each extra expanded once per set of extras being
    expanded that it can reach. Off a cycle that set is fixed: a long
    chain or repeated references cost about the result's size. On a cycle
    there is one expansion per such set, exponential in the size of a
    dense cycle (6 extras each naming all 6 read 2,784 entries, 8 read
    23,552, 10 pass 100,000): :data:`MAX_EXPANSION_ENTRIES` bounds it.
    """

    def __init__(self, by_extra: Mapping[str, Sequence[Requirement]], own: str):
        self._items = {
            extra: [item for req in reqs for item in _items(req, own, by_extra)]
            for extra, reqs in by_extra.items()
        }
        self._component = _Components(
            {
                extra: [i.name for i in items if isinstance(i, _Ref)]
                for extra, items in self._items.items()
            }
        ).of
        # The extras being expanded, by component.
        self._chain: dict[int, set[str]] = defaultdict(set)
        self._memo: dict[_Key, _Expanded] = {}
        self._entries = 0

    def texts(self) -> dict[str, list[str]]:
        """Each extra's requirement texts.

        Raises:
            _OverCap: The expansion is over a cap.
        """
        return {extra: self._expand(extra).texts for extra in self._items}

    def cycles(self) -> list[tuple[str, str, list[str]]]:
        """``(extra, entry, members)`` for each cycle of self-references, by
        its first member: *members* its extras in order, *entry* the first
        reference back to the first member, declared in *extra* (the one
        dropped expanding it)."""
        members: dict[int, list[str]] = {}
        for extra in sorted(self._items):
            members.setdefault(self._component[extra], []).append(extra)
        found = []
        for cycle in members.values():
            first = cycle[0]
            entry = next(
                (
                    (extra, item.text)
                    for extra in cycle
                    for item in self._items[extra]
                    if isinstance(item, _Ref) and item.name == first
                ),
                None,
            )
            # A lone extra is a cycle only when it names itself.
            if entry is not None:
                found.append((*entry, cycle))
        return found

    def _key(self, extra: str) -> _Key:
        chain = self._chain[self._component[extra]]
        return extra, frozenset(chain | {extra})

    def _expand(self, root: str) -> _Expanded:
        root_key = self._key(root)
        if root_key in self._memo:
            return self._memo[root_key]
        stack = [(root_key, self._walk(root))]
        self._chain[self._component[root]].add(root)
        while stack:
            key, walk = stack[-1]
            try:
                child = next(walk)
            except StopIteration as done:
                self._memo[key] = done.value
                stack.pop()
                self._chain[self._component[key[0]]].discard(key[0])
                continue
            self._chain[self._component[child[0]]].add(child[0])
            stack.append((child, self._walk(child[0])))
        return self._memo[root_key]

    def _walk(self, extra: str) -> Generator[_Key, None, _Expanded]:
        """Expand *extra* into the memo; yields the key of each expansion
        it needs that the memo does not hold yet, to be expanded first."""
        texts: dict[str, None] = {}
        markers = 0
        for item in self._items[extra]:
            self._count(1)
            if isinstance(item, str):
                texts.setdefault(item)
                continue
            if item.name in self._chain[self._component[item.name]]:
                continue
            key = self._key(item.name)
            if key not in self._memo:
                yield key
            sub = self._memo[key]
            markers = max(markers, sub.markers + (item.marker is not None))
            if markers > MAX_EXPANSION_MARKERS:
                raise _OverCap(
                    Cap(
                        MAX_EXPANSION_MARKERS,
                        "marker",
                        "self-reference nesting",
                        "FIELD",
                    )
                )
            self._count(len(sub.texts))
            for text in sub.texts:
                try:
                    texts.setdefault(_with_marker(text, item.marker))
                except (InvalidMarker, InvalidRequirement) as exc:
                    raise _OverCap(_NESTING_CAP) from exc
        return _Expanded(list(texts), markers)

    def _count(self, entries: int) -> None:
        self._entries += entries
        if self._entries > MAX_EXPANSION_ENTRIES:
            raise _OverCap(
                Cap(MAX_EXPANSION_ENTRIES, "entry", "self-reference expansion", "FIELD")
            )


def _items(
    req: Requirement, own: str, by_extra: Mapping[str, object]
) -> list[str | _Ref]:
    """*req* as entries of its extra: a requirement on the project *own*
    becomes one self-reference per declared extra it names, in canonical
    order."""
    if canonicalize_name(req.name) != own:
        return [str(req)]
    marker = str(req.marker) if req.marker else None
    names = sorted({canonicalize_name(e) for e in req.extras})
    return [_Ref(name, marker, str(req)) for name in names if name in by_extra]
