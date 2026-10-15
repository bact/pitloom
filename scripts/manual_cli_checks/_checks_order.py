# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The order-matrix checks (``O*``): Pitloom operations run in many
orders against several fixture projects, each sequence written as a
replayable POSIX shell script and run as that script, every step checked
against the invariants of ``_order_invariants.py``.

- ``O1/<fixture>/<set>``: every permutation of a set of non-mutating
  steps; besides the per-step invariants, the final registries must
  converge (G): ``order-independent``, ``order-dependent (benign: mint
  order only)`` -- the same keys, ids a type-preserving bijection --,
  ``order-dependent (benign: id import dropped a content gate)`` -- as
  that, the sha256 differing only for keys an `id import` logged
  ``content gate dropped`` for (BN ruling 2026-10-15) -- or a violation.
- ``O2/<fixture>/<n>``: seeded random walks with mutating steps.
- ``O3/<fixture>``: each reader step three times running (C).
- ``O4/<fixture>``: injected v2, invalid and read-only registries (H).
- ``O5/<fixture>``: fixed scenarios, the shortest sequences seen to break
  an invariant.

A sequence that breaks an invariant keeps its script, fixture, logs and
outputs in a ``ord-repro-*`` directory under the temp dir; the failure
names it and the command that replays it. POSIX only (the scripts are
``sh``): skipped on Windows.

See also: ``_order_gen.py``, ``_order_ops.py``, ``_order_fixtures.py``,
``_order_known.py``, manual-cli-checks.md ("Order matrix").
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from _harness import CheckFailed, CheckSkipped, Context, check, child_env
from _order_capture import Entry, Key, capture, gate_dropped, warning_shapes
from _order_fixtures import Profile, fixture_dir
from _order_gen import (
    Sequence,
    all_profiles,
    depth,
    failures,
    perm_sets,
    permutations,
    render,
    repeats,
    scenarios,
    walks,
)
from _order_invariants import Violation, check_sequence
from _order_known import known_item
from _order_ops import IMPORTS

KNOWN_SIGN = "allow-listed order-matrix findings only"
_WALK_CHUNK = 4
_MAX_REPROS = 5


@dataclass
class Outcome:
    """One sequence's result."""

    seq: Sequence
    final: dict[Key, Entry] | None
    violations: list[Violation]
    known: list[tuple[Violation, str]]
    repro: Path | None = None
    shapes: list[str] = field(default_factory=list)
    stats: Counter[str] = field(default_factory=Counter)
    #: Keys an `id import` step logged ``content gate dropped`` for.
    gate_dropped: frozenset[Key] = frozenset()


def _execute(ctx: Context, check_id: str, seq: Sequence, index: int) -> Outcome:
    """Run *seq* as its script, check it, keep a repro on a violation."""
    fixture = fixture_dir(seq.profile.name)
    script = ctx.work / f"s{index:03d}.sh"
    work = ctx.work / f"s{index:03d}"
    script.write_text(render(seq, check_id, sys.executable), encoding="utf-8")
    proc = subprocess.run(  # nosec B603 B607
        ["sh", str(script), str(work)],
        env=child_env(ORD_FIXTURE=str(fixture)),
        cwd=ctx.work,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=900,
        check=False,
    )
    captured = capture(work, seq.steps)
    found, stats = check_sequence(seq.profile, fixture, captured)
    if proc.returncode != 0 or len(captured) != len(seq.steps):
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        message = f"exit {proc.returncode}: {stderr[-300:]}"
        found.append(Violation("S/script", len(captured), "-", "", message))
    outcome = Outcome(
        seq,
        next((c.registry for c in reversed(captured) if c.reg_raw), None),
        [v for v in found if not known_item(v, seq.profile.name)],
        [(v, item) for v in found if (item := known_item(v, seq.profile.name))],
        shapes=[s for c in captured for s in warning_shapes(c.stderr)],
        stats=stats,
        gate_dropped=frozenset(
            key
            for c in captured
            if c.step.op in IMPORTS
            for key in gate_dropped(c.stderr)
        ),
    )
    if outcome.violations:
        outcome.repro = _keep(check_id, script, work, fixture, outcome.violations)
    shutil.rmtree(work, ignore_errors=True)
    return outcome


def _keep(
    check_id: str, script: Path, work: Path, fixture: Path, found: list[Violation]
) -> Path:
    """A self-contained repro directory: script, fixture, logs, outputs."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", check_id).strip("-")
    repro = Path(tempfile.mkdtemp(prefix=f"ord-repro-{slug}-"))
    shutil.copy2(script, repro / "seq.sh")
    shutil.copytree(fixture, repro / "fixture")
    for name in ("logs", "out"):
        if (work / name).exists():
            shutil.copytree(work / name, repro / name)
    lines = [v.line() for v in found]
    (repro / "violations.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repro


def classify(
    finals: list[dict[Key, Entry] | None], gated_off: frozenset[Key] = frozenset()
) -> tuple[str, set[Key]]:
    """G: the verdict on one permutation group's final registries, and the
    keys that make it a violation. *gated_off*: the keys an `id import`
    logged ``content gate dropped`` for in any of the sequences."""
    if not finals or any(f is None for f in finals):
        return "VIOLATION (no registry)", set()
    tables = [f for f in finals if f is not None]
    first = tables[0]
    if all(t == first for t in tables):
        return "order-independent", set()
    odd = {k for t in tables for k in set(t) ^ set(first)}
    if odd:
        return "VIOLATION (key sets differ)", odd

    def classes(table: dict[Key, Entry]) -> dict[Key, tuple[frozenset[Key], str]]:
        by_id: dict[str, set[Key]] = {}
        for key, entry in table.items():
            by_id.setdefault(entry.spdx_id, set()).add(key)
        return {
            key: (frozenset(by_id[entry.spdx_id]), _prefix(entry.spdx_id))
            for key, entry in table.items()
        }

    shape = classes(first)
    odd = {k for t in tables for k, c in classes(t).items() if c != shape[k]}
    if odd:
        return "VIOLATION (ids not a type-preserving bijection)", odd
    odd = {k for t in tables for k, e in t.items() if e.sha != first[k].sha}
    if odd and not odd <= gated_off:
        return "VIOLATION (sha256 values differ)", odd - gated_off
    if odd:
        return "order-dependent (benign: id import dropped a content gate)", set()
    return "order-dependent (benign: mint order only)", set()


def _prefix(spdx_id: str) -> str:
    return spdx_id.rpartition("#")[2].split("-")[0]


def _report(
    check_id: str, outcomes: list[Outcome], verdict: str, g_unknown: list[Violation]
) -> list[str]:
    """The check's report: counts, convergence, what the steps logged,
    known findings and each failing sequence with its repro."""
    report = [f"{check_id}: {len(outcomes)} sequence(s)"]
    report += [verdict] if verdict else []
    report += [f"  {v.line()}" for v in g_unknown[:8]]
    stats: Counter[str] = Counter()
    for o in outcomes:
        stats.update(o.stats)
    report.append(
        "compared: " + " ".join(f"{k}={stats[k]}" for k in ("A", "C", "E", "F"))
    )
    shapes = Counter(s for o in outcomes for s in o.shapes)
    report += [f"  {n:4d}x {shape}" for shape, n in sorted(shapes.items())]
    for o in outcomes:
        if o.violations:
            report.append(f"{o.seq.label} ({' '.join(o.seq.ops)}): {o.repro}")
            report += [f"  {v.line()}" for v in o.violations[:8]]
    return report


def _finish(
    ctx: Context,
    check_id: str,
    outcomes: list[Outcome],
    converge: tuple[str, list[Violation]] = ("", []),
) -> None:
    """Report *outcomes* (notes and ``report.txt``) and decide the check;
    *converge* is O1's convergence line and its violations (G)."""
    verdict, diverging = converge
    profile = outcomes[0].seq.profile.name if outcomes else ""
    g_unknown = [v for v in diverging if not known_item(v, profile)]
    known = Counter(item for o in outcomes for _, item in o.known)
    known.update(item for v in diverging if (item := known_item(v, profile)))
    report = _report(check_id, outcomes, verdict, g_unknown)
    report += [f"known x{n}: {item}" for item, n in sorted(known.items())]
    (ctx.work / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    for line in report:
        ctx.note(line)
    if g_unknown:
        raise CheckFailed(f"G: {verdict}: {g_unknown[0].line()}")
    failing = [o for o in outcomes if o.violations]
    if failing:
        first = failing[0]
        raise CheckFailed(
            f"{len(failing)} sequence(s) broke invariants; first: {first.seq.label}: "
            f"{first.violations[0].line()}\n  replay: sh {first.repro}/seq.sh "
            f'"$(mktemp -d)"  (repro: {first.repro})'
        )
    if known:
        raise CheckFailed(f"{KNOWN_SIGN}: " + "; ".join(sorted(known)))


def _run_all(ctx: Context, check_id: str, seqs: list[Sequence]) -> list[Outcome]:
    if os.name == "nt":
        raise CheckSkipped("POSIX sh scripts; not on Windows")
    if (
        os.name == "posix"
        and os.geteuid() == 0
        and any(s.kind == "readonly" for q in seqs for s in q.steps)
    ):
        raise CheckSkipped("root ignores a read-only registry")
    outcomes = [_execute(ctx, check_id, seq, i) for i, seq in enumerate(seqs)]
    kept = [o for o in outcomes if o.repro]
    for o in kept[_MAX_REPROS:]:
        if o.repro is not None:
            shutil.rmtree(o.repro, ignore_errors=True)
            o.repro = Path("(not kept: over the repro limit)")
    return outcomes


def _perm_check(ctx: Context, profile: Profile, set_name: str) -> None:
    check_id = f"O1/{profile.name}/{set_name}"
    seqs = permutations(profile, set_name)
    outcomes = _run_all(ctx, check_id, seqs)
    gated_off = frozenset(key for o in outcomes for key in o.gate_dropped)
    verdict, odd = classify([o.final for o in outcomes], gated_off)
    code = "G/" + verdict.rsplit("(", maxsplit=1)[-1].rstrip(")").replace(" ", "-")
    diverging = [
        Violation(code, 0, "-", f"{k[0]} {k[1]}", verdict) for k in sorted(odd)
    ]
    line = f"G {' '.join(seqs[0].ops)} x{len(seqs)} -> {verdict}"
    _finish(ctx, check_id, outcomes, (line, diverging))


def _walk_check(ctx: Context, profile: Profile, chunk: int) -> None:
    check_id = f"O2/{profile.name}/{chunk}"
    seqs = walks(profile, chunk * _WALK_CHUNK, _WALK_CHUNK)
    _finish(ctx, check_id, _run_all(ctx, check_id, seqs))


def _repeat_check(ctx: Context, profile: Profile) -> None:
    check_id = f"O3/{profile.name}"
    _finish(ctx, check_id, _run_all(ctx, check_id, repeats(profile)))


def _failure_check(ctx: Context, profile: Profile) -> None:
    check_id = f"O4/{profile.name}"
    _finish(ctx, check_id, _run_all(ctx, check_id, [failures(profile)]))


def _scenario_check(ctx: Context, profile: Profile) -> None:
    check_id = f"O5/{profile.name}"
    _finish(ctx, check_id, _run_all(ctx, check_id, scenarios(profile)))


def _register() -> None:
    walks_per_profile, _ = depth()
    for profile in all_profiles():
        name = profile.name
        for set_name in perm_sets(profile):
            check(f"O1/{name}/{set_name}", f"order: {set_name} permutations, {name}")(
                functools.partial(_perm_check, profile=profile, set_name=set_name)
            )
        for chunk in range(-(-walks_per_profile // _WALK_CHUNK)):
            check(f"O2/{name}/{chunk}", f"order: random walks, {name}")(
                functools.partial(_walk_check, profile=profile, chunk=chunk)
            )
        check(f"O3/{name}", f"order: each step three times running, {name}")(
            functools.partial(_repeat_check, profile=profile)
        )
        check(f"O4/{name}", f"order: v2, invalid, read-only registry, {name}")(
            functools.partial(_failure_check, profile=profile)
        )
        check(f"O5/{name}", f"order: fixed scenarios, {name}")(
            functools.partial(_scenario_check, profile=profile)
        )


_register()
