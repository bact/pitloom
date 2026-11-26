---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Manual CLI checks: the runner and the order matrix

See also: [manual-cli-checks.md](manual-cli-checks.md) (when to run, and the
numbered checks the runner automates), `scripts/manual_cli_checks/`,
[id-registry-v3.md](id-registry-v3.md).

How `scripts/manual_cli_checks` runs the checks, and the order matrix it
adds; split out of manual-cli-checks.md for size.

## Running them: `scripts/manual_cli_checks`

Every check in [manual-cli-checks.md](manual-cli-checks.md#the-checks)
except 6 (skills drift, which needs judgement) runs
unattended from one stdlib-only runner, on Linux, macOS and Windows:

```bash
.venv/bin/python scripts/manual_cli_checks              # offline checks
.venv/bin/python scripts/manual_cli_checks --network    # all checks
.venv/bin/python scripts/manual_cli_checks --only 'M/embed-wheel/*' --only S3
.venv/bin/python scripts/manual_cli_checks --list
.venv/bin/python scripts/manual_cli_checks --report matrix.md
```

Use the checkout's own interpreter: the runner tests the `pitloom` that
interpreter imports, and prints its path first. Besides the numbered
checks (`1`-`26`, `B1`-`B7`) it runs:

- **The CLI matrix** (`M/<command>/<group>/<variant>`): every subcommand
  x its options x the environment variables that change it
  (`PITLOOM_DEBUG`, `SOURCE_DATE_EPOCH`), each cell a real `loom` in its
  own directory behind a socket guard. Groups: `debug` (flag x env,
  checked against the logger level Pitloom configured), `output` (`-o
  FILE`/`-o -`/none x `--pretty`/`--no-pretty`/none), `date`
  (`--creation-datetime` x `SOURCE_DATE_EPOCH`), `offline`, `opt`
  (one-factor variants of every other option, each expected to change
  the output, leave it alone, contain a value or be rejected) and
  `parity` (`generate` vs the dedicated subcommand). The plan is
  `_matrix_plan.py`; `M/completeness` fails on any subcommand or option
  it doesn't classify, and `tests/scripts/test_manual_cli_checks.py`
  runs that check in every CI run. A remote target cannot be a variant
  (a variant adds options to the cell's local target), so the `target`
  cells (`M/<command>/target/<label>`, `_matrix_targets.py`) give a whole
  command line: each refusal made before any request (`--offline`,
  another index, a `files.pythonhosted.org` link) runs in every run behind
  the guard, the CI test included; a fetch per route (a GitHub tag, a PyPI
  release's wheel and sdist) and the download cap run with `--network`.
- **Sequences** (`S1`-`S8`): commands in order where one's side effect
  is the next one's input -- a default output inside the scanned
  project, re-embedding, `embed-wheel` vs `wheel --embed` in both
  orders, registry updates, `id import`, a merge into its own input
  directory, verifying before and after embedding, embedding a
  hook-built wheel.
- **The ID registry order matrix** (`O1`-`O6`): registry operations in
  many orders on several fixtures, each sequence a replayable shell
  script; see [Order matrix](#order-matrix-o1-o6) below.

A failing cell already tracked in the roadmap reports `KNOWN` with the
item's title (`_known.py`) -- only when its failure text is the tracked
one, so any other failure in that cell still fails; drop the entry when
the item is done. To
cover a new option, add it to `PLAN` in `_matrix_plan.py` -- a variant
with an expectation, a group, or an exclusion with its reason. The
`warns:` variants per command are derived from
`pitloom.core.inert_options.INERT`, not listed by hand, so the matrix
cannot disagree with the library on which options have no effect.

## Order matrix (`O1`-`O6`)

Does the order of Pitloom operations change the ids the registry keeps,
and does every outcome match the design
([id-registry-v3.md](id-registry-v3.md),
[build notes](id-registry-v3-build-notes.md))? Each sequence is rendered
as a POSIX shell script (`set -eu`, one `run NN ...` line per step) and
checked by running that script, so what is checked is what a user can
replay. `run` keeps each step's exit status, stdout, stderr and the
registry as the step left it; the invariants read only those files and
the SBOMs written, never registry code.

- **Steps** (`_order_ops.py`): `id generate` (plain, with both datasets
  pinned by `-e`, or `pyproject.toml` alone), `id import` (of the latest
  SBOM or fragment, or of the setup's SBOM), `project`, `sdist`
  (`project` of a fresh sdist), `wheel` and
  `embed-wheel --project-dir` (each on a fresh offline build), `model`,
  two `loom.run` scripts (`set_model`/`use_model(path=)`, a file and a
  directory dataset; run from the profile's `loom_dir`), and the
  mutating `retrain`, `edit-file` (the
  newest module the sequence added, else a fixed one), `edit-data`,
  `rename-file`, `add-file`. Spelling steps, run only by `O6`: `add-nfd`
  (a module named in NFD), `model-upper` and `train-upper` (`model` and
  `train` with the model path in upper case). A profile lists the steps
  that do not apply to its layout (`Profile.unsupported`, with the
  reason). Not covered: `enrich`, `env`,
  `merge`, the Hatchling hook with a registry, setuptools wheels (the
  build writes `*.egg-info` into the project).
- **Fixtures** (`_order_fixtures.py`, built per run, copied by each
  script): `flat` (the demo project plus loom scripts and data),
  `src` (`sampleproject-hatchling`, `src/` layout), `setuptools`
  (`sampleproject-setuptools`, no model), `stems` (two model files with
  one stem), `intree` (the registry declared in `[tool.pitloom]` inside
  the package), `monorepo` (the registry root above the project:
  `pkgs/demo/...`, `id generate .` at the root; `wheel`, `sdist` and
  `embed` pass `--project-dir pkgs/demo`), `subdir` (model, data and the
  `loom.run` scripts in sibling
  directories: the scripts run from `scripts/` and name
  `../models/m.safetensors`, `../data/t.txt`).
- **Sequences** (`_order_gen.py`): `O1/<fixture>/<set>` runs every
  permutation of three or four non-mutating steps; `O2/<fixture>/<n>`
  seeded random walks of 4-8 steps with mutations; `O3/<fixture>` each
  reader step three times running; `O4/<fixture>` a v2, an invalid and
  a read-only registry injected mid-sequence; `O5/<fixture>` fixed
  scenarios, the shortest sequences a walk was seen to break, so the
  default budget always covers them; `O6/<fixture>/<kind>` the spelling
  scenarios (`nfd`, `upper`), skipped with the reason on a file system
  that normalises an NFD name or is case-sensitive. `PITLOOM_ORDER_DEPTH=deep`
  runs 96 walks per fixture of up to 12 steps (default 16 of up to 8);
  `PITLOOM_ORDER_SEED` changes the walks' seed. The default O-group runs
  in about 1.5 minutes with `-j 8`.
- **Invariants** (`_order_invariants.py`, each citing its design
  section): A stability (and harvest records), B typed ids, C
  idempotence, D clean runs and no duplicate id, E cross-surface
  agreement (per registry entry, a layout alias and its twin being one),
  F pinned ids survive, H failures; the path-key rules of
  `_order_paths.py`: `M/stem-key` (a model's registry key is its own
  file's, never its stem), `M/distinct-ids` (two models, one stem, two
  ids), `N/nfc` and `N/case` (a key is NFC and spelt as on disk),
  `S/dotdot` (no `..` or absolute key), `S/dataset-pin` (a loom run
  carries the id `id generate -e` pinned). B/multi-key and A/reuse
  accept only `keys.is_layout_alias` pairs, A/reuse only as a promotion
  (the `src/` key replaces the shorter one); a model is matched to its
  file by stem, a dataset and a model are gated like a file. G, the convergence of the
  final registries over one permutation set (`order-independent`,
  `order-dependent (benign: mint order only)`, `order-dependent (benign:
  id import dropped a content gate)` when only keys an `id import` logged
  `content gate dropped` for differ in sha256, or a violation), is in
  `_checks_order.py`. `-v` prints each check's report: the G line, how
  many comparisons each rule made (a guard against a vacuous pass), the
  `WARNING:`/`ERROR:` shapes logged, known findings.
- **Failures**: a sequence that breaks an invariant keeps its script,
  fixture, logs and outputs in `$TMPDIR/ord-repro-*` (at most five per
  check). The runner never removes them (a concurrent run may still
  need its own); the failure prints the cleanup hint
  `rm -rf <tmp>/ord-repro-*`. Replay with
  `sh <repro>/seq.sh "$(mktemp -d)"`; `PITLOOM_PYTHON` picks the
  interpreter.
- **Known findings**: `_order_known.py` lists accepted ones, each naming
  its [id-registry-followups.md](../design/id-registry-followups.md)
  item; a check failing only on those ends `KNOWN`. Only the per-document
  entities' A/B findings remain: the src-layout and sdist entries went
  with the path keys. A violation is
  matched against the registry of its own step (else the last one
  captured). Each check's `report.txt` lists the first four allow-listed
  violations of each item (`  known: ...`) after its `known xN` counts, to
  see what the allow-list let through.
- POSIX only (skipped on Windows); the read-only cases skip as root.
  `tests/scripts/test_manual_cli_checks_order.py` checks that every
  invariant fires on a doctored step, and that a broken registry lookup
  in a real run is caught.
