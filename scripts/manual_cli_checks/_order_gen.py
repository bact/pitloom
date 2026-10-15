# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Sequences for the order-matrix checks (``O*``) and the POSIX shell
script each one runs as.

Five kinds, all deterministic: exhaustive permutations of a small set of
non-mutating steps (``O1``), seeded random walks that include mutating
steps (``O2``), each reader step three times in a row (``O3``), injected
registry failures (``O4``) and fixed scenarios (``O5``).
``PITLOOM_ORDER_DEPTH=deep`` makes the walks more and longer;
``PITLOOM_ORDER_SEED`` changes their seed (printed in each script's
header).

A script is the whole replayable record: it copies the pristine fixture,
runs every step through ``run``, which keeps each step's exit status,
stdout, stderr and the registry as it is afterwards under ``$WORK/logs``,
and nothing else. POSIX ``sh`` only (``set -eu``; no ``local``, arrays or
``/dev/stderr``), so it runs under macOS bash 3.2 and dash alike; not on
Windows, like the other shell-driven checks.

See also: ``_order_ops.py`` (the steps), ``_checks_order.py``.
"""

from __future__ import annotations

import itertools
import os
import random
import shlex
from dataclasses import dataclass

from _fixtures import SOURCE_DATE_EPOCH
from _harness import DATETIME
from _order_fixtures import NAMESPACE, PROFILES, RETRAIN_PY, Profile
from _order_ops import MUTATING, READERS, Planner, Step, applies

DEFAULT_SEED = 20261015
#: (walks per profile, maximum walk length) per depth.
_DEPTHS = {"quick": (16, 8), "deep": (96, 12)}
#: Permutation sets: (name, setup steps, permuted steps). Every set is
#: non-mutating, so its permutations must converge (invariant G).
PERM_SETS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("surfaces", ("gen",), ("project", "wheel", "model", "train")),
    ("fresh-loom", ("gen-min",), ("gen-ds", "project", "train", "eval")),
    ("import", ("gen", "project"), ("import0", "embed", "eval")),
    ("fresh-cli", ("gen-min", "project"), ("gen", "project", "import0")),
)


def seed() -> int:
    """The walk seed: ``PITLOOM_ORDER_SEED`` or :data:`DEFAULT_SEED`."""
    return int(os.environ.get("PITLOOM_ORDER_SEED", DEFAULT_SEED))


def depth() -> tuple[int, int]:
    """(walks per profile, maximum length) for ``PITLOOM_ORDER_DEPTH``."""
    name = os.environ.get("PITLOOM_ORDER_DEPTH", "quick")
    if name not in _DEPTHS:
        raise SystemExit(f"PITLOOM_ORDER_DEPTH: one of {', '.join(_DEPTHS)}")
    return _DEPTHS[name]


@dataclass(frozen=True)
class Sequence:
    """One planned sequence: its label, profile and steps."""

    label: str
    profile: Profile
    steps: tuple[Step, ...]

    @property
    def ops(self) -> tuple[str, ...]:
        """The non-setup step names, in order."""
        return tuple(s.op for s in self.steps if s.kind != "setup")


def plan(
    label: str, profile: Profile, setup: tuple[str, ...], ops: tuple[str, ...]
) -> Sequence:
    """A sequence of *setup* then *ops*; an op may be ``KIND:op`` for an
    injected failure (``v2:project``)."""
    planner = Planner(profile)
    for op in setup:
        planner.add(op, "setup")
    for item in ops:
        kind, _, op = item.rpartition(":")
        planner.add(op, kind or "step")
    return Sequence(label, profile, tuple(planner.steps))


def permutations(profile: Profile, set_name: str) -> list[Sequence]:
    """Every order of one :data:`PERM_SETS` set on *profile*."""
    _, setup, ops = next(s for s in PERM_SETS if s[0] == set_name)
    usable = tuple(op for op in ops if applies(op, profile))
    return [
        plan(f"{set_name}-{i:02d}", profile, setup, order)
        for i, order in enumerate(itertools.permutations(usable))
    ]


def perm_sets(profile: Profile) -> list[str]:
    """The :data:`PERM_SETS` names worth running on *profile* (three or
    more usable steps)."""
    return [
        name
        for name, _, ops in PERM_SETS
        if sum(applies(op, profile) for op in ops) >= 3
    ]


def walks(profile: Profile, first: int, count: int) -> list[Sequence]:
    """Random walks *first* .. *first + count - 1*: each seeded by
    (seed, profile, index), so one walk replays alone."""
    _, longest = depth()
    pool = sorted(op for op in MUTATING | READERS if applies(op, profile))
    pool = [op for op in pool if op not in ("gen-min", "import0")]
    setup = ("gen-ds",) if profile.loom else ("gen",)
    result = []
    for index in range(first, first + count):
        # Seeded for replay, not security.
        rng = random.Random(f"{seed()}:{profile.name}:{index}")  # nosec B311
        length = rng.randint(4, longest)
        ops = tuple(rng.choice(pool) for _ in range(length))
        result.append(plan(f"walk-{index:03d}", profile, setup, ops))
    return result


def repeats(profile: Profile) -> list[Sequence]:
    """Each reader step three times running, after a full seed (C)."""
    setup = ("gen-ds",) if profile.loom else ("gen",)
    readers = sorted(op for op in READERS if applies(op, profile))
    readers = [op for op in readers if op not in ("gen-min", "import0")]
    # `import` needs an SBOM first: one project run more.
    return [
        plan(
            f"repeat-{op}",
            profile,
            setup + (("project",) if op == "import" else ()),
            (op, op, op),
        )
        for op in readers
    ]


def scenarios(profile: Profile) -> list[Sequence]:
    """Fixed sequences, each the shortest seen to break an invariant, so
    the default budget always covers them (``O5``)."""
    # An id leaves the registry (a harvest replaces the newest file's
    # entry), then the next mint takes its number for another file.
    reuse = ("add-file", "gen", "edit-file", "project", "add-file", "gen")
    found = [plan("reuse", profile, ("gen",), reuse)]
    if profile.shared_stem:
        # loom records the stem's sha256; `id generate` drops it again.
        found.append(plan("stem-sha", profile, ("gen-ds",), ("train", "gen", "train")))
    return found


def failures(profile: Profile) -> Sequence:
    """Injected registry failures (H): v2, invalid JSON and read-only."""
    ops = ["project", "add-file", "readonly:project", "v2:project", "badjson:project"]
    ops += ["badjson:gen", "readonly:gen", "v2:import"]
    if profile.model is not None:
        ops += ["v2:model"]
    if profile.wheel:
        ops += ["v2:wheel", "badjson:embed"]
    if profile.loom:
        ops += ["v2:train", "retrain", "readonly:train"]
    ops += ["project"]
    return plan("failures", profile, ("gen",), tuple(ops))


def all_profiles() -> list[Profile]:
    """Every fixture profile, in a fixed order."""
    return [PROFILES[name] for name in sorted(PROFILES)]


_PROLOGUE = """\
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${{PITLOOM_PYTHON:-{python}}}
FIXTURE=${{ORD_FIXTURE:-$HERE/fixture}}
WORK=${{1:-$(mktemp -d "${{TMPDIR:-/tmp}}/ord-replay-XXXXXX")}}
PROJ=$WORK/proj
LOGS=$WORK/logs
OUT=$WORK/out
DIST=$WORK/dist
REG={registry}
NS={namespace}
DT={datetime}
RETRAIN={retrain}
SOURCE_DATE_EPOCH={epoch}
HF_HUB_OFFLINE=1
export SOURCE_DATE_EPOCH HF_HUB_OFFLINE
unset PITLOOM_DEBUG
rm -rf "$PROJ" "$LOGS" "$OUT" "$DIST"
mkdir -p "$LOGS" "$OUT" "$DIST"
cp -R "$FIXTURE" "$PROJ"
cd "$PROJ"

loom() {{ "$PY" -m pitloom "$@"; }}
# run N CMD...: CMD's exit status, stdout and stderr in $LOGS/N.*, then
# the registry as CMD left it in $LOGS/N.reg
run() {{
  n=$1
  shift
  rc=0
  "$@" >"$LOGS/$n.out" 2>"$LOGS/$n.err" || rc=$?
  echo "$rc" >"$LOGS/$n.rc"
  if [ -f "$REG" ]; then cp "$REG" "$LOGS/$n.reg"; fi
}}
# build N: a fresh wheel of the project in $DIST, its path in $WHEEL
build() {{
  rm -rf "$DIST"
  "$PY" -m build --wheel --no-isolation --outdir "$DIST" . >"$LOGS/$1.build" 2>&1
  for WHEEL in "$DIST"/*.whl; do :; done
}}
retrain() {{ "$PY" -c "$RETRAIN" "$1" "$2"; }}
append() {{ printf '# edit %s\\n' "$2" >>"$1"; }}
add() {{ printf 'N = %s\\n' "$2" >"$1"; }}
"""


def render(seq: Sequence, check_id: str, python: str) -> str:
    """*seq* as a POSIX shell script; argument 1 is the work directory."""
    registry = (
        f"$PROJ/{seq.profile.in_tree}" if seq.profile.in_tree else "$WORK/reg.json"
    )
    head = [
        "#!/bin/sh",
        "# One prologue for every sequence: not each uses every variable.",
        "# shellcheck disable=SC2034",
        f"# Pitloom ID-registry order matrix: {check_id} {seq.label}",
        f"# fixture: {seq.profile.name}; walk seed: {seed()}",
        f"# steps: {' '.join(_label(s) for s in seq.steps)}",
        "# Replay: sh THIS_FILE [WORKDIR]; PITLOOM_PYTHON picks the interpreter",
        "# and ORD_FIXTURE the pristine fixture (default: ./fixture).",
    ]
    body = _PROLOGUE.format(
        python=shlex.quote(python),
        registry=registry,
        namespace=shlex.quote(NAMESPACE),
        datetime=shlex.quote(DATETIME),
        retrain=shlex.quote(RETRAIN_PY),
        epoch=SOURCE_DATE_EPOCH,
    )
    lines = []
    for step in seq.steps:
        lines.append(f"\n# {step.tag}: {_label(step)}")
        lines.extend(step.lines)
    return "\n".join(head) + "\n" + body + "\n".join(lines) + "\n"


def _label(step: Step) -> str:
    if step.kind == "step":
        return step.op
    if step.kind == "setup":
        return f"{step.op}(setup)"
    return f"{step.kind}:{step.op}"
