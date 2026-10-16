# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The invariants an order-matrix sequence must keep after every step,
checked against black-box facts (the registry file, the SBOMs written,
exit status and stderr), never by re-running registry code. Each rule
names the design text it comes from: ``id-registry-v3.md`` (D*, I*,
sections), ``id-registry-v3-build-notes.md`` (BN).

- A, stability: a key keeps its spdxId unless an `id import` handed it
  the imported one (section 2: the harvested id wins) or a gated entry's
  sha256 changed to the bytes now on disk, under a fresh id (D3, D12,
  D13). A key never vanishes, a recorded sha256 is never erased (D12, BN)
  except by an `id import` handing the key another id with one ``content
  gate dropped`` INFO for it (BN; ``A/gate-info``: that
  INFO only there, once per key), a gated entry never takes new bytes
  under its old id (D3), and an id never passes to another key except a
  src-layout alias (I4).
  ``A/record``: a writer leaves the registry agreeing with what it read
  or emitted (I1, section 5 ``generate()``, section 7 harvest, D13, D15).
- B, typed ids: the id of a key of the four lookup types starts with its
  type's prefix (D2, I6); no id under two types; one key per id except
  the alias (I4).
- C, idempotence: a reader step run again leaves the registry bytes
  unchanged; a third run's SBOM equals the second's (I7, "SBOM output").
- D, clean runs: exit 0, every stderr line tagged, no traceback, no
  ERROR, no duplicate spdxId in an output, no ``shares spdxId`` or
  ``another run saved`` warning (I4, D11, 8.4).
- E, cross-surface agreement: the same key, registry entry and content
  gets one id on every surface (section 7).
- F, pinned ids survive: an element whose key the registry held before
  the step carries the registry's id, under its type's gate (section 7,
  D16 for the ungated AIPackage lookups, D12/D13 for loom's gated one).

H (injected failures) is in ``_order_failures.py``, G (convergence
across permutations) in ``_checks_order.py``.

See also: ``_order_capture.py``, ``_order_known.py`` (accepted findings).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _order_capture import (
    AI,
    DATASET,
    FILE,
    GATED,
    LOOM_SURFACES,
    PREFIX,
    Captured,
    Element,
    Entry,
    Key,
    elements,
    gate_dropped,
    project_files,
    unique,
)
from _order_failures import clean, injected, read_only
from _order_fixtures import Profile
from _order_ops import MUTATING
from _order_paths import (
    candidates,
    dataset_pins,
    expected_hit,
    find,
    model_rules,
    spelling_rules,
)

from pitloom.id_registry.keys import alias_tail, is_layout_alias

_DETERMINISTIC = frozenset({"project", "wheel", "model", "embed", "sdist"})
_HARVESTERS = frozenset({"project", "wheel", "sdist"})


@dataclass(frozen=True)
class Violation:
    """One broken invariant at one step."""

    code: str
    step: int
    op: str
    #: The registry key involved, as ``type name`` (empty if none).
    key: str
    message: str

    def line(self) -> str:
        """One report line."""
        where = f" [{self.key}]" if self.key else ""
        return f"{self.code} step {self.step:02d} {self.op}{where}: {self.message}"


def _alias(a: Key, b: Key) -> bool:
    """I4's name condition: same type, one path the other's layout alias
    (``src/`` or ``lib/`` dropped: the package's own rule)."""
    return a[0] == b[0] and is_layout_alias(a[1], b[1])


class Checker:
    """Runs every invariant over one sequence's captured steps."""

    def __init__(
        self, profile: Profile, fixture: Path, captured: list[Captured]
    ) -> None:
        self.profile = profile
        self.fixture = fixture
        self._captured = captured
        self.found: list[Violation] = []
        self._owner: dict[str, Key] = {}
        self._seen: dict[tuple[Key, Entry, str | None], dict[str, tuple[int, str]]] = (
            defaultdict(dict)
        )
        self._streak = 0
        #: How many comparisons each rule made: a guard against a vacuous pass.
        self.stats: Counter[str] = Counter()

    def fail(self, code: str, cap: Captured, key: Key | None, message: str) -> None:
        """Record a violation at *cap*'s step."""
        text = f"{key[0]} {key[1]}" if key else ""
        self.found.append(Violation(code, cap.step.n, cap.step.op, text, message))

    def run(self) -> list[Violation]:
        """Check every step; then cross-surface agreement (E)."""
        prev: Captured | None = None
        for cap in self._captured:
            if cap.step.kind in ("v2", "badjson"):
                for code, message in injected(cap):
                    self.fail(code, cap, None, message)
                continue
            self._clean(cap)
            reg = cap.registry
            if reg is not None:
                self._typed(cap, reg)
                self._paths(cap, reg)
            before = prev.registry if prev is not None else None
            if cap.step.kind == "readonly":
                for code, message in read_only(cap, prev):
                    self.fail(code, cap, None, message)
            elif reg is not None:
                if before is not None:
                    self._stable(cap, before, reg)
                self._records(cap, reg)
            if before is not None:
                self._pinned(cap, before)
            self._repeat(cap, prev)
            prev = cap
        self._agree()
        return self.found

    # D: every step runs cleanly.
    def _clean(self, cap: Captured) -> None:
        for code, message in clean(cap):
            self.fail(code, cap, None, message)

    def _paths(self, cap: Captured, reg: dict[Key, Entry]) -> None:
        """The path-key rules (``_order_paths.py``)."""
        found = [
            *model_rules(self.profile, reg),
            *spelling_rules(reg, self._disk(cap)),
        ]
        for code, key, message in found:
            self.fail(code, cap, key, message)

    # B: typed ids, one type and one key per id.
    def _typed(self, cap: Captured, reg: dict[Key, Entry]) -> None:
        by_id: dict[str, list[Key]] = defaultdict(list)
        for key, entry in reg.items():
            by_id[entry.spdx_id].append(key)
            prefix = PREFIX.get(key[0])
            fragment = entry.spdx_id.rpartition("#")[2]
            if prefix and fragment.split("-")[0] != prefix:
                self.fail("B/prefix", cap, key, f"{entry.spdx_id} lacks {prefix}-")
        for spdx_id, keys in by_id.items():
            if len({k[0] for k in keys}) > 1:
                self.fail("B/cross-type", cap, keys[0], f"{spdx_id} held by {keys}")
                continue
            for other in keys[1:]:
                sha_a, sha_b = reg[keys[0]].sha, reg[other].sha
                if not (_alias(keys[0], other) and sha_a and sha_a == sha_b):
                    self.fail("B/multi-key", cap, other, f"{spdx_id} also {keys[0]}")
            self._reuse(cap, spdx_id, keys)

    def _reuse(self, cap: Captured, spdx_id: str, keys: list[Key]) -> None:
        """A/reuse: an id stays with the key that first held it, except a
        promotion to its layout key or an import handing it to its name."""
        for key in sorted(keys, key=lambda k: (len(k[1]), k)):
            owner = self._owner.setdefault(spdx_id, key)
            if owner == key:
                continue
            promoted = _alias(owner, key) and alias_tail(key[1]) == owner[1]
            if promoted or key in self._imported(cap):  # section 2
                self._owner[spdx_id] = key
                continue
            self.fail("A/reuse", cap, key, f"{spdx_id} was {owner[0]} {owner[1]}")

    # A: stability against the previous registry.
    def _stable(
        self, cap: Captured, before: dict[Key, Entry], after: dict[Key, Entry]
    ) -> None:
        imported = self._imported(cap)
        said = self._gate_info(cap)
        dropped: set[Key] = set()
        self.stats["A"] += len(before)
        for key, old in before.items():
            new = after.get(key)
            if new is None:
                self.fail("A/vanished", cap, key, f"held {old.spdx_id}")
                continue
            erased = bool(old.sha) and new.sha is None
            if key in imported and imported[key].spdx_id == new.spdx_id:
                # Section 2: the harvested id wins. BN: only an import
                # handing the key another id drops the sha256, and says so.
                if erased and new.spdx_id != old.spdx_id and key in said:
                    dropped.add(key)
                elif erased:
                    self.fail(
                        "A/sha-erased",
                        cap,
                        key,
                        f"import gave {new.spdx_id} and dropped {_short(old.sha)}"
                        + ("" if key in said else " without the INFO"),
                    )
                continue
            if erased:
                # D12, BN: no other step erases a recorded sha256.
                self.fail(
                    "A/sha-erased",
                    cap,
                    key,
                    f"{old.spdx_id} -> {new.spdx_id} lost its sha256",
                )
                continue
            if new.spdx_id != old.spdx_id:
                fresh = new.spdx_id not in {e.spdx_id for e in before.values()}
                if key[0] in GATED and new.sha != old.sha and fresh:
                    self._current_sha(cap, key, new)
                    continue
                self.fail(
                    "A/churn",
                    cap,
                    key,
                    f"{old.spdx_id} -> {new.spdx_id} "
                    f"(sha {_short(old.sha)} -> {_short(new.sha)})",
                )
            elif key[0] in GATED and old.sha and new.sha != old.sha:
                self.fail(
                    "A/sha-swap",
                    cap,
                    key,
                    f"{new.spdx_id} kept for new bytes "
                    f"({_short(old.sha)} -> {_short(new.sha)})",
                )
        for key in sorted(set(said) - dropped):
            self.fail("A/gate-info", cap, key, "content gate dropped, sha256 kept")

    def _gate_info(self, cap: Captured) -> list[Key]:
        """The keys of this step's ``content gate dropped`` INFO lines, each
        logged once. Only an import's drop matches one (:meth:`_stable`)."""
        said = gate_dropped(cap.stderr)
        for key in sorted({k for k in said if said.count(k) > 1}):
            self.fail("A/gate-info", cap, key, "content gate INFO repeated")
        return said

    def _imported(self, cap: Captured) -> dict[Key, Element]:
        """The elements `id import` read at this step, by unique key."""
        if cap.step.imported is None:
            return {}
        source = self._source(cap.step.imported)
        return unique(elements(source)) if source is not None else {}

    def _import_surface(self, cap: Captured) -> str:
        """The surface of the SBOM *cap*'s `id import` read."""
        for other in self._captured:
            for surface, path in other.step.outputs:
                if path == cap.step.imported:
                    return surface
        return ""

    def _source(self, rel: str) -> list[dict[str, Any]] | None:
        for cap in self._captured:
            for surface, path in cap.step.outputs:
                if path == rel and surface in cap.graphs:
                    return cap.graphs[surface]
        return None

    def _disk(self, cap: Captured) -> dict[str, str]:
        return project_files(self.fixture, cap.step, self.profile.in_tree)

    def _current_sha(self, cap: Captured, key: Key, entry: Entry) -> None:
        """A re-minted gated entry records the bytes on disk now."""
        disk = self._disk(cap)
        path = key[1]
        if path in disk and entry.sha != disk[path]:
            self.fail("A/stale-sha", cap, key, f"{_short(entry.sha)} not on disk")

    # A/record: a writer's registry agrees with what it read or emitted.
    def _records(self, cap: Captured, reg: dict[Key, Entry]) -> None:
        op = cap.step.op
        if op in ("gen", "gen-ds", "gen-min"):
            self._generated(cap, reg)
            return
        if op in ("import", "import0"):
            self._import_records(cap, reg)
            return
        disk = self._disk(cap)
        for surface, graph in cap.graphs.items():
            for key, elem in unique(elements(graph)).items():
                cands = candidates(self.profile, surface, elem, disk)
                if cands and self._recorded(surface, key, elem):
                    self._agrees(
                        cap,
                        reg,
                        cands,
                        elem,
                        required=key[0] == FILE or surface in LOOM_SURFACES,
                    )

    @staticmethod
    def _recorded(surface: str, key: Key, elem: Element) -> bool:
        """Whether *surface* leaves *elem* in the registry (D13, D15): a
        harvester every type but a dataset (an unhashed model apart), loom
        its model."""
        if surface in LOOM_SURFACES and key[0] == AI:
            return True
        # A dependency package may be a non-reader, never harvested.
        harvested = surface in _HARVESTERS and key[0] != DATASET
        return harvested and (key[0] != AI or bool(elem.sha))

    def _import_records(self, cap: Captured, reg: dict[Key, Entry]) -> None:
        disk, surface = self._disk(cap), self._import_surface(cap)
        for elem in self._imported(cap).values():
            cands = candidates(self.profile, surface, elem, disk)
            self._carried(cap, reg, cands, elem)

    def _carried(
        self, cap: Captured, reg: dict[Key, Entry], cands: list[Key], elem: Element
    ) -> None:
        """An imported element's id is in the registry: under its own name,
        or kept at the key that held it already (R-keep)."""
        if elem.spdx_id not in {reg[k].spdx_id for k in cands if k in reg}:
            self.fail("A/record", cap, cands[-1], f"{elem.spdx_id} not recorded")

    def _agrees(
        self,
        cap: Captured,
        reg: dict[Key, Entry],
        cands: list[Key],
        elem: Element,
        *,
        required: bool,
    ) -> None:
        key = cands[-1]
        found = find(reg, cands, elem.sha)
        if found is None:
            if required:
                self.fail("A/record", cap, key, f"{elem.spdx_id} not recorded")
            return
        entry = found[1]
        if entry.spdx_id != elem.spdx_id:
            self.fail(
                "A/record", cap, key, f"output {elem.spdx_id}, registry {entry.spdx_id}"
            )
        elif key[0] in GATED and elem.sha and entry.sha != elem.sha:
            self.fail(
                "A/record",
                cap,
                key,
                f"sha {_short(entry.sha)} is not the output's {_short(elem.sha)}",
            )

    def _generated(self, cap: Captured, reg: dict[Key, Entry]) -> None:
        """Section 5: `id generate` registers every file with its sha256
        and each model (D3) under its file's key with the same sha256 (the
        one model rule: no stem entry)."""
        disk = self._disk(cap)
        only = self.profile.pyproject if cap.step.op == "gen-min" else None
        for rel, sha in disk.items():
            if only and rel != only:
                continue
            entry = reg.get((FILE, rel))
            if entry is None or entry.sha != sha:
                self.fail(
                    "A/record",
                    cap,
                    (FILE, rel),
                    f"not registered at {_short(sha)}: {entry}",
                )
        if only:
            return
        for model in self.profile.model_paths:
            entry = reg.get((AI, model))
            if entry is None or entry.sha != disk.get(model):
                self.fail(
                    "A/record",
                    cap,
                    (AI, model),
                    f"model not registered at {_short(disk.get(model))}: {entry}",
                )

    # F (and E's observations): pinned ids survive, under their gates.
    def _pinned(self, cap: Captured, before: dict[Key, Entry]) -> None:
        disk = self._disk(cap)
        for surface, graph in cap.graphs.items():
            for key, elem in unique(elements(graph)).items():
                cands = candidates(self.profile, surface, elem, disk)
                if not cands:
                    continue
                content = disk.get(cands[0][1]) if key[0] == AI else elem.sha
                hit = expected_hit(elem, cands, before)
                if hit is not None:
                    # The registry's own key: an alias and its twin are one.
                    seen = self._seen[(hit[0], hit[1], content)]
                    seen[surface] = (cap.step.n, elem.spdx_id)
                self.stats["F"] += hit is not None
                if hit is not None and elem.spdx_id != hit[1].spdx_id:
                    self.fail(
                        "F/pinned",
                        cap,
                        key,
                        f"{surface} gave {elem.spdx_id}, "
                        f"registry {hit[0][1]} holds {hit[1].spdx_id}",
                    )
            for code, pin, message in dataset_pins(
                cap.step.op, surface, graph, before, disk
            ):
                self.fail(code, cap, pin, message)

    def _agree(self) -> None:
        """E: one id per (element key, its registry entry, content)."""
        for (key, entry, _), seen in sorted(self._seen.items(), key=str):
            self.stats["E"] += len(seen) > 1
            ids = {spdx_id for _, spdx_id in seen.values()}
            if len(ids) > 1:
                detail = ", ".join(
                    f"{s}@{n:02d}={i}" for s, (n, i) in sorted(seen.items())
                )
                self.found.append(
                    Violation(
                        "E/disagree",
                        0,
                        "-",
                        f"{key[0]} {key[1]}",
                        f"entry {entry.spdx_id}: {detail}",
                    )
                )

    # C: a repeated reader step changes nothing.
    def _repeat(self, cap: Captured, prev: Captured | None) -> None:
        same = (
            prev is not None
            and prev.step.op == cap.step.op
            and prev.step.kind == cap.step.kind == "step"
            and cap.step.op not in MUTATING
        )
        self._streak = self._streak + 1 if same else 0
        if not same or prev is None:
            return
        self.stats["C"] += 1
        if prev.reg_raw != cap.reg_raw:
            self.fail("C/registry", cap, None, "a repeat changed the registry bytes")
        if self._streak < 2:
            return  # "a third run equals the second"
        for surface, raw in cap.raw.items():
            if surface in _DETERMINISTIC and raw != prev.raw.get(surface):
                self.fail("C/output", cap, None, f"{surface} SBOM bytes differ")
            if surface in LOOM_SURFACES:
                # Only ids from the registry: a loom fallback id is fresh
                # every run (design problem 11, out of scope).
                held = {e.spdx_id for e in (prev.registry or {}).values()}
                ids, old = (
                    {
                        e.key: e.spdx_id
                        for e in elements(c.graphs.get(surface, []))
                        if e.spdx_id in held
                    }
                    for c in (cap, prev)
                )
                if ids != old:
                    self.fail("C/output", cap, None, f"{surface} registry ids differ")


def _short(sha: str | None) -> str:
    return sha[:8] if sha else "none"


def check_sequence(
    profile: Profile, fixture: Path, captured: list[Captured]
) -> tuple[list[Violation], Counter[str]]:
    """Every invariant over one sequence (see the module docstring), and
    how many comparisons each rule made."""
    checker = Checker(profile, fixture, captured)
    return checker.run(), checker.stats
