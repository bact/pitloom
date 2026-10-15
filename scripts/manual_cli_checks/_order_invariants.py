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
    PACKAGE,
    PREFIX,
    Captured,
    Element,
    Entry,
    Key,
    duplicate_ids,
    elements,
    gate_dropped,
    project_files,
    unique,
)
from _order_failures import injected, read_only
from _order_fixtures import Profile

_FORBIDDEN = ("shares spdxId", "another run saved")
_DETERMINISTIC = frozenset({"project", "wheel", "model", "embed"})
_HARVESTERS = frozenset({"project", "wheel"})


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
    """I4's name condition: same type, one path a strict suffix of the other."""
    return a[0] == b[0] and (a[1].endswith("/" + b[1]) or b[1].endswith("/" + a[1]))


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
        readonly = cap.step.kind == "readonly"
        if cap.rc != 0 and not readonly:
            self.fail("D/exit", cap, None, f"exit {cap.rc}: {cap.stderr_lines[-3:]}")
        if "Traceback (most recent call last)" in cap.stderr:
            self.fail("D/traceback", cap, None, cap.stderr_lines[-1][:200])
        tags = ("ERROR: ", "WARNING: ", "INFO: ")
        untagged = [ln for ln in cap.stderr_lines if not ln.startswith(tags)]
        if untagged and "Traceback" not in cap.stderr:
            self.fail("D/untagged", cap, None, repr(untagged[:2]))
        errors = [ln for ln in cap.stderr_lines if ln.startswith("ERROR: ")]
        if errors and not readonly:
            self.fail("D/error", cap, None, errors[0][:200])
        for needle in _FORBIDDEN:
            hits = [ln for ln in cap.stderr_lines if needle in ln]
            if hits:
                self.fail("D/warning", cap, None, hits[0][:200])
        for surface, why in cap.broken.items():
            self.fail("D/output", cap, None, f"{surface}: {why}")
        for surface, graph in cap.graphs.items():
            dups = duplicate_ids(graph)
            if dups:
                self.fail("D/dup-id", cap, None, f"{surface}: {dups[:3]}")

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
            for key in keys:
                owner = self._owner.setdefault(spdx_id, key)
                if owner != key and not _alias(owner, key):
                    self.fail(
                        "A/reuse", cap, key, f"{spdx_id} was {owner[0]} {owner[1]}"
                    )

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
        path = self.profile.model if key == (AI, self.profile.stem) else key[1]
        if path in disk and entry.sha != disk[path]:
            self.fail("A/stale-sha", cap, key, f"{_short(entry.sha)} not on disk")

    # A/record: a writer's registry agrees with what it read or emitted.
    def _records(self, cap: Captured, reg: dict[Key, Entry]) -> None:
        op = cap.step.op
        if op in ("gen", "gen-ds", "gen-min"):
            self._generated(cap, reg)
            return
        if op in ("import", "import0"):
            for key, elem in self._imported(cap).items():
                self._agrees(cap, reg, key, elem, required=True)
            return
        for surface, graph in cap.graphs.items():
            for key, elem in unique(elements(graph)).items():
                if surface in _HARVESTERS and key[0] != DATASET:
                    if key[0] != AI or elem.sha:  # D15
                        # A dependency package may be a non-reader, never
                        # harvested; every file is a reader.
                        self._agrees(cap, reg, key, elem, required=key[0] == FILE)
                if surface in LOOM_SURFACES and key[0] == AI:
                    self._agrees(cap, reg, key, elem, required=True)  # D13

    def _agrees(
        self,
        cap: Captured,
        reg: dict[Key, Entry],
        key: Key,
        elem: Element,
        *,
        required: bool,
    ) -> None:
        entry = reg.get(key)
        if entry is None:
            if required:
                self.fail("A/record", cap, key, f"{elem.spdx_id} not recorded")
            return
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
        """Section 5: `id generate` registers every file with its sha256,
        and (D3) the model stem with the model's sha256. A stem two model
        files share has no one file to match: its entry is left as is (BN;
        A checks it kept its sha256)."""
        disk = self._disk(cap)
        only = "pyproject.toml" if cap.step.op == "gen-min" else None
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
        stem, model = self.profile.stem, self.profile.model
        if only or stem is None or model is None:
            return
        entry = reg.get((AI, stem))
        if entry is None:
            self.fail("A/record", cap, (AI, stem), "model stem not registered")
        elif not self.profile.shared_stem and entry.sha != disk.get(model):
            self.fail(
                "A/record",
                cap,
                (AI, stem),
                f"sha {_short(entry.sha)} is not the model's {_short(disk.get(model))}",
            )

    # F (and E's observations): pinned ids survive, under their gates.
    def _pinned(self, cap: Captured, before: dict[Key, Entry]) -> None:
        disk = self._disk(cap)
        for surface, graph in cap.graphs.items():
            for key, elem in unique(elements(graph)).items():
                content = (
                    disk.get(str(self.profile.model)) if key[0] == AI else elem.sha
                )
                held = before.get(key)
                gated = surface in LOOM_SURFACES or key[0] == FILE
                if held and not (gated and key[0] in GATED and held.sha != content):
                    observed = self._seen[(key, held, content)]
                    observed[surface] = (cap.step.n, elem.spdx_id)
                hit = self._expected(surface, elem, before, disk)
                self.stats["F"] += hit is not None
                if hit is not None and elem.spdx_id != hit[1].spdx_id:
                    self.fail(
                        "F/pinned",
                        cap,
                        key,
                        f"{surface} gave {elem.spdx_id}, "
                        f"registry {hit[0][1]} holds {hit[1].spdx_id}",
                    )

    def _expected(
        self,
        surface: str,
        elem: Element,
        before: dict[Key, Entry],
        disk: dict[str, str],
    ) -> tuple[Key, Entry] | None:
        """The registry entry *elem*'s lookup must hit (section 7)."""
        type_name, name = elem.key
        if type_name in (PACKAGE, DATASET) or (type_name == FILE and not elem.sha):
            entry = before.get(elem.key)  # ungated (a File: a directory)
            return (elem.key, entry) if entry else None
        if type_name == FILE:
            # A project file: its physical path, then its distribution path;
            # a wheel member or a loom path: its own name. Gated by sha256.
            names = [name]
            if surface == "project":
                names = [p for p in disk if p.endswith("/" + name)] + names
            for candidate in names:
                entry = before.get((FILE, candidate))
                if entry and entry.sha and entry.sha == elem.sha:
                    return (FILE, candidate), entry
            return None
        return self._expected_model(surface, elem, before)

    def _expected_model(
        self, surface: str, elem: Element, before: dict[Key, Entry]
    ) -> tuple[Key, Entry] | None:
        """D16: name, then stem, ungated; loom (D13): its name, gated."""
        name = elem.key[1]
        loom = surface in LOOM_SURFACES
        for candidate in [name] if loom else [name, str(self.profile.stem)]:
            entry = before.get((AI, candidate))
            if entry is None:
                continue
            if loom and (not entry.sha or entry.sha != elem.sha):
                return None  # D12: a miss re-mints (checked by A)
            return (AI, candidate), entry
        return None

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
            and cap.step.op not in ("retrain", "edit-file", "edit-data", "add-file")
            and cap.step.op != "rename-file"
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
