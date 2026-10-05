---
Created: 2026-09-17
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Manual CLI integration checks (post-pytest, pre-commit)

See also: [CLAUDE.md](../../CLAUDE.md) ("Testing" section -- test tiers
and a short summary of when to run these).

pytest exercises functions in-process. It does not exercise the `loom`
entry point, subprocess argv parsing, real filesystem/archive I/O across
subcommands, or drift between the CLI/library-API/Hatchling-hook/skills
surfaces (see "Usage surfaces" in CLAUDE.md). Run these by hand -- or have
an agent run them -- against a real project after any change touching
`assemble/`, `extract/`, `core/`, `embed.py`, `__main__.py`, or
`plugins/hatch.py`, before committing. Use a scratch dir (`mktemp -d`),
never the repo tree, for generated output.

## When to run

The full run takes minutes; pytest already runs a slice of it in CI
(`tests/scripts/test_manual_cli_checks.py`: `M/completeness`, check 1,
`B7` and the `M/project/debug/*` cells). So:

- Docs-, tests- or `working-docs/`-only change: skip.
- Each review/fix round: only the touched area's checks, by `--only`
  (ids and globs, comma-separated):

  | Area | `--only` |
  |---|---|
  | wheel, embed | `3,4a,16,S2,S3,S7,S8,M/wheel/*,M/embed-wheel/*,M/verify-wheel/*,M/validate-wheel/*` |
  | registry, ids | `9,14,S4,S5,M/id-*/*` |
  | fragments, merge | `7,S6,M/merge/*,M/fragment-*/*` |
  | build, `--allow-build`, termination | `B*,10` |
  | config, options, cascade | `5,12,13,15,M/completeness`, plus `M/<cmd>/*` per command whose options changed |
  | AI model scan | `15,17,M/model/*` |
  | network, offline | `8,11` |
  | any metadata source or assembly | add `1,2,S1` and `M/<cmd>/*` for each command that reads it |

- Once before handoff, and again after merging main into the branch: the
  full run (`-j 8`; add `--network` when network code changed).

A new numbered check gets a row here. The map is by hand and can drift;
an area field on each check, selectable by `--only`, is a possible
follow-up.

## Running them: `scripts/manual_cli_checks`

Every check below except 6 (skills drift, which needs judgement) runs
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
checks (`1`-`17`, `B1`-`B7`) it runs:

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
  runs that check in every CI run.
- **Sequences** (`S1`-`S8`): commands in order where one's side effect
  is the next one's input -- a default output inside the scanned
  project, re-embedding, `embed-wheel` vs `wheel --embed` in both
  orders, registry updates, `id import`, a merge into its own input
  directory, verifying before and after embedding, embedding a
  hook-built wheel.

A failing cell already tracked in the roadmap reports `KNOWN` with the
item's title (`_known.py`) -- only when its failure text is the tracked
one, so any other failure in that cell still fails; drop the entry when
the item is done. To
cover a new option, add it to `PLAN` in `_matrix_plan.py` -- a variant
with an expectation, a group, or an exclusion with its reason. The
`warns:` variants per command are derived from
`pitloom.core.inert_options.INERT`, not listed by hand, so the matrix
cannot disagree with the library on which options have no effect.

## The checks

**1. Determinism (bit-for-bit, per "SBOM output" in CLAUDE.md)**

```bash
loom project . -o /tmp/a.json --creation-datetime 2026-01-01T00:00:00Z
loom project . -o /tmp/b.json --creation-datetime 2026-01-01T00:00:00Z
diff /tmp/a.json /tmp/b.json && echo DETERMINISTIC
```

Re-run with `--pretty` and without; both must diff-clean against
themselves across repeats. A pinned `--creation-datetime` is required --
without it the `created` timestamp legitimately differs run-to-run.

**2. CLI vs library API vs Hatchling hook parity**

Three entry points must converge on the same document per project
(see "Metadata sources" in CLAUDE.md). Compare with the same pinned
`--creation-datetime`/`SOURCE_DATE_EPOCH` on all three, then diff the
`@graph` bodies (ignore `creationInfo.created`/tool-version fields that
legitimately vary by invocation):

```bash
loom project . -o /tmp/cli.json --creation-datetime 2026-01-01T00:00:00Z
python -c "
from pathlib import Path
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
generate_project_sbom(
    Path('.'),
    output_path=Path('/tmp/api.json'),
    creation_metadata=CreationMetadata(creation_datetime='2026-01-01T00:00:00Z'),
)
"
SOURCE_DATE_EPOCH=1767225600 python -m build --wheel -o /tmp/wheelout .
# hook-produced SBOM lands under .dist-info/sboms/ inside the built wheel
diff <(jq -S 'del(.["@graph"][] | select(.type=="CreationInfo"))' /tmp/cli.json) \
     <(jq -S 'del(.["@graph"][] | select(.type=="CreationInfo"))' /tmp/api.json)
```

An explicit `CreationMetadata` replaces the creator fields the CLI takes
from `[tool.pitloom]`; for a project that sets them, pass the same
values here. The hook's SBOM legitimately differs from the other two in
`software_sbomType` (`build`), `builtTime`, and the `version` provenance
entry (see [sbom-lifecycle-stages.md](sbom-lifecycle-stages.md)).

**3. embed-wheel vs standalone `wheel` SBOM parity**

`embed-wheel` (project-dir-aware) and `wheel --embed` (wheel-only) must
describe the same package for the same wheel -- this is the class of gap
`--debug` fell into (one surface updated, sibling surfaces not). The two
are not byte-comparable by design: `embed-wheel --project-dir` makes a
`build` SBOM from project-directory discovery, `wheel --embed` an
`analyzed` one from the archive itself, and only `embed-wheel` takes
`--sbom-basename`. Both list the payload only (nothing under the wheel's own
`.dist-info`). Compare the package name/version/PURL and the file names
instead:

```bash
python -m build --wheel -o /tmp/wheelout .
wheel=$(ls /tmp/wheelout/*.whl)
cp "$wheel" /tmp/wheelout/copy.whl
loom embed-wheel "$wheel" --project-dir .
loom wheel /tmp/wheelout/copy.whl --embed
unzip -p "$wheel" '*.dist-info/sboms/*' > /tmp/embedded.json
unzip -p /tmp/wheelout/copy.whl '*.dist-info/sboms/*' > /tmp/standalone.json
files() { jq -r '.["@graph"][] | select(.type=="software_File") | .name' "$1" \
  | sort; }
diff <(files /tmp/embedded.json) <(files /tmp/standalone.json)
```

For a project that ships a model (flat layout), also compare the
`ai_AIPackage` elements with `spdxId` removed: they must be equal (the
model found in the project directory and the one found in the wheel), and
neither SBOM has a `hasDataFile` by default.

**4. Round trip: embed -> verify -> validate**

```bash
loom embed-wheel /tmp/wheelout/*.whl --verify --validate
loom verify-wheel /tmp/wheelout/*.whl --fail-on-mismatch
loom validate-wheel /tmp/wheelout/*.whl
```

**5. `--debug`/`PITLOOM_DEBUG` reaches every subcommand and every
non-CLI entry point** (see "Usage surfaces" in CLAUDE.md -- exactly the
bug class that motivated this check):

```bash
for sub in generate project wheel embed-wheel model enrich env merge fragment ids; do
  echo "=== $sub ==="
  loom --debug "$sub" --help >/dev/null 2>&1  # smoke: flag parses on every subcommand
done
PITLOOM_DEBUG=1 loom project . -o /tmp/dbg.json 2>&1 | grep -c '^DEBUG:' # expect >0
PITLOOM_DEBUG=1 loom project . -o /tmp/dbg.json 2>&1 \
  | grep -vc '^\(ERROR\|WARNING\|INFO\|DEBUG\): '             # expect 0
```

Debug lines only come from paths that have something to report: use a
project with an AI model file (e.g. one `.npy`), or a failing
`--allow-build` build, to get a nonzero count -- a clean project can
legitimately print none.

**6. Skills/plugin surface drift** (`skills/*/SKILL.md` has no test
suite -- see "Usage surfaces" in CLAUDE.md): grep each `SKILL.md` for
flags and subcommand names it documents invoking, then confirm each
still exists:

```bash
grep -n -- '--[a-z-]\+\|loom [a-z-]\+' skills/*/SKILL.md
loom <subcommand> --help  # for each one named above
```

**7. Fragment merge determinism** (dynamic-execution / `pitloom.loom` path):

Write the output outside the fragments directory: `loom merge` reads
every `*.spdx3.json` there, so a second run would merge the first run's
output too.

```bash
loom merge /path/to/fragments/ -o /tmp/m1.json
loom merge /path/to/fragments/ -o /tmp/m2.json
diff /tmp/m1.json /tmp/m2.json && echo DETERMINISTIC
loom fragment validate /tmp/m1.json
```

**8. Offline mode has zero network calls**: run any AI-model-involving
command under a network sandbox/firewall (or `strace -e network` /
Little Snitch) with `--offline` and confirm no outbound connections,
vs. confirming at least one occurs without `--offline` against a
Hugging Face Hub URL.

**9. Registry round trip**: `loom id generate` on a project, then
regenerate the SBOM with `--id-registry` pointing at that same file (a
registry is used only when declared -- see "Revised in PR A2" in
[id-registry-autosync.md](id-registry-autosync.md)) and confirm IDs are
stable (byte-identical `@id` values) across repeated runs -- this is
what "Auto-sync the Loom ID registry" in `roadmap.md` depends on.

**10. `--allow-build` with vs. without, and vs. ground truth**: general
pattern for any change touching backend file-discovery dispatch or the
build-and-read mechanism -- run `loom project` twice (with/without
`--allow-build`) against the same project and diff the `software_File`
results; a registered backend whose static discovery already succeeds
must produce byte-identical output either way (a real build must never
run then), and for a backend with no static module the two runs show
exactly what the heuristic fallback gets wrong relative to a real
build. Automated as `scripts/compare_allow_build.py` (works against a
project directory, an sdist archive, or a vendored fixture via
`--fixture BACKEND/NAME`; cross-checks against a fixture's own
`expected.json` when one exists) -- see
[allow-build-validation.md](allow-build-validation.md)'s
"`--allow-build` build-and-read" round for a worked example and
`scripts/compare_allow_build.py`'s own docstring for usage.

**11. A setting reaches the assembler on `project` and `embed-wheel`**: a byte-for-byte
diff cannot see a setting that changes no bytes in an offline fixture
(with `--content-type` off, `--content-type-method` only decides whether
a dependency's remote authors file is fetched), so count the fetch instead. Put a fake
`fakedep-1.0.dist-info` (author `and others (see AUTHORS.txt)`, a GitHub
`Project-URL`) on `PYTHONPATH`, declare `fakedep==1.0`, and run
`loom project` and `loom embed-wheel --project-dir` with
`--content-type-method auto` and `extension` behind the socket guard: `auto`
must show one more blocked connection than `extension` on each surface
(automated as check 11; found `embed-wheel` ignoring the flag). The
argument-level counterpart is `tests/assemble/test_embed_build_seam.py`,
and the same fixture without a socket guard is
`tests/assemble/test_embed_authors_fetch.py`.

**12. No implicit config for a non-project target**: from an empty
directory and from a decoy project directory (a `[tool.pitloom]` with
`pretty`, `enrich`, `update-id-registry`, a relative `id-registry` and a
creation comment, plus a seeded `loom-id-registry.json`; the model file's own
directory gets the same decoy), run `loom wheel`, `generate <wheel>`,
`env`, `model`, `enrich` (no `--project-dir`) and `embed-wheel` (no
`--project-dir`). Each pair of SBOMs must be byte-identical and the
registry untouched; naming the decoy with `--config` must apply its
creation comment (so the decoy is effective). Automated as check 12;
the library-level counterpart is
`tests/assemble/test_generator_no_implicit_config.py`.

**13. An sdist reads its own config**: append a `[tool.pitloom]`
(`pretty`, a creation comment) to the fixture project and pack it as
`demo-0.1.tar.gz`. `loom project` on the directory and on the archive
must both apply it; `-v` on the archive labels it
`demo-0.1.tar.gz:pyproject.toml`. An archive whose config is invalid
(`pretty = 'yes'`) is one `ERROR:` naming that member, and the same run
with `--config good.toml` succeeds. Automated as check 13; the
library-level counterpart is `tests/assemble/test_sdist_own_config.py`.

**14. Declared-but-missing/invalid `--id-registry` is one ERROR, every
CLI surface**: `--id-registry` pointing at a missing file, and again at
one containing `"{"` (invalid JSON), on `project`, `wheel`, `env`,
`model` and `embed-wheel` -- each of the 10 runs must exit 1 with
exactly one `ERROR:` line containing `ID registry file` and no output
file written. Automated as check 14
(`scripts/manual_cli_checks/_checks_core.py::check_registry_missing_invalid`).
This check is flag-only, on those five CLI surfaces; it does not cover
a registry declared via the project's own `[tool.pitloom] id-registry`
key, the Hatchling build hook, or the undeclared (no flag, no config
key) case -- those are covered by pytest instead, in
`tests/id_registry/test_surfaces_failures.py`. See
[id-registry-autosync.md](id-registry-autosync.md)'s "Revised in PR A2"
section.

**15. `--scan-model-usage`: flag beats config on every surface that scans**:
the fixture project carries a tiny model and a script naming it. On
`project`, `embed-wheel --project-dir`, `wheel`, `wheel --embed` and
`embed-wheel` without `--project-dir` (the wheel ones get the key through
`--config`, their only config source), run (i) `--config` with
`scan-model-usage = true`, (ii) `--scan-model-usage`, (iii) (i) plus
`--no-scan-model-usage`, (iv) `--no-scan-model-usage` alone, (v) the
default. (i) and (ii) must be byte-identical with `hasDataFile` and no
hint; (iii)-(v) must be identical with no `hasDataFile`; only (v), where
the setting is never given, prints exactly one `INFO: Found 1 AI model
file(s); pass --scan-model-usage ...`; (i) and (v) must differ (so the
comparison is not vacuous). A hook-built wheel whose project config sets
the key must carry `hasDataFile`. Automated as check 15
(`scripts/manual_cli_checks/_checks_config.py::check_scan_model_usage`).
Config only via `--config` or the project's own `pyproject.toml`, never
the current directory.

**16. A refused wheel is refused alike by every command that reads one**: a
wheel holding `METADATA` twice (a duplicate member name) is given to
`wheel`, `generate`, `wheel --embed -o`, `embed-wheel` (in a batch with a
good wheel), `verify-wheel` and `validate-wheel`. Each must exit 1 with
exactly one `ERROR:` line naming the wheel and ending `-- wheel refused`;
the refused wheel's bytes are unchanged, no `-o` file exists, an
`--id-registry` file (on the commands that take one) is byte-identical, and
the good wheel of the batch is embedded. Automated as check 16
(`scripts/manual_cli_checks/_checks_wheel.py::check_refused_wheel_parity`).
The registry must be valid: an invalid one fails first, with its own error.
Other causes (unreadable member, NUL name, not a ZIP) are covered per
surface by `tests/test_wheel_identity_surfaces.py`.

**17. One outcome per kind of AI model file, whichever command reads it**: a
project with a truncated Safetensors file (a model whose read fails) and Git
LFS pointers named `.gguf`, `.onnx` and `.bin` (not models; `.onnx` admits any
other header, `.bin` names no format), besides a good model. `project` and
`wheel` (of the built project) each give an `ai_AIPackage` for the good and
the truncated model and none for the pointer, and warn exactly once per file;
the two runs' `WARNING:` text is equal once the path is replaced (`failed to
extract metadata ...` or, without the `safetensors` extra, `required library
not installed ...`; `header is a Git LFS pointer; not listed as an AI model`). `loom
model` of the truncated file writes one `ai_AIPackage` with that same warning
and exits 0; `loom model` of any pointer exits 1 with exactly one `ERROR:` and
writes nothing. Automated as check 17
(`scripts/manual_cli_checks/_checks_model.py::check_model_outcome_parity`).
Per-kind detail (parse, bound, library, empty, `.pth` text) is in
`tests/assemble/test_model_outcome_parity.py`.

For a change touching the build subprocess, its kill path or signal
handling (`--build-timeout`), also run these against a scratch project
with an in-tree backend (`requires = []`, `backend-path = ["."]`, run
with `--allow-build --no-build-isolation`):

- a `build_wheel` that sleeps: `--build-timeout 5` returns within ~15 s,
  exit 0, the `timed out after 5s` `WARNING:` and the fallback
  `WARNING:`; no backend process and no `plb-*`/
  `pitloom-build-and-read-*` directory left in `$TMPDIR` (automated as
  `tests/cli/test_cli_build_timeout_process.py`; rerun by hand on a
  platform CI does not cover);
- the same, with `kill -TERM` (exit 143, `received SIGTERM during the
  build`) and `kill -INT` (exit 130) sent mid-build -- start `loom` as
  `( trap - INT; exec loom ... ) &`, since a non-interactive shell
  starts background jobs with SIGINT ignored;
- a `build_wheel` that calls `input()`: fails fast, not after the
  timeout;
- a `build_wheel` that leaves a background `sleep` running: one
  `INFO: Build: killed processes the build left running`, no `sleep`
  left, and two runs with a pinned `--creation-datetime` byte-identical;
- invalid `--build-timeout` values (`0`, `1.5h`, `500ms`, `1H`,
  `604801`): exit 2.
