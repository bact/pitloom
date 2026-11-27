---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pre-release review for 0.25.0

See also: [testing-and-review-policy.md](testing-and-review-policy.md#pre-release-review)
(the procedure), [release-checklist.md](release-checklist.md),
[findings, code surfaces](pre-release-review-0.25.0/findings-code.md),
[findings, docs, skills, Action](pre-release-review-0.25.0/findings-docs.md).

The first pre-release review, over `v0.24.0..ff3960a1` (76 merged PRs,
numbered #481 to #557; 449 files under `src/`). Release candidate: `ff3960a1` (main
after #557). Policy step 3 (the golden-snapshot harness and the seeded hostile-input
generator) was skipped by the user's ruling for 0.25.0; it is a 1.0 roadmap
item.

## Summary

- Gates on the candidate: all green, apart from local-environment noise
  (below). No regression test or manual check fails.
- Every stderr, exit-code and SBOM change against v0.24.0 on 75 fixture
  commands traces to a CHANGELOG entry.
- Nine read-only reviews (CLI, library, hook, catalogue, Action, registry,
  skills, docs, a downstream trial) reported 76 findings, 71 after merging
  duplicates. None was dropped: each reproduced in a re-run or was confirmed
  at the cited line (CLI-7 by reading only, to stay offline). Triage: 5
  release blockers (6 ids), 38 cheap fixes for 0.25.0, 31 for the next
  release (four ids are split between buckets), after an Opus second
  opinion whose amendments were all taken (LIB-2 and the TRY-1 caveat up to
  blockers, SKL-1 down to cheap, LIB-10 and the empty `--creator-email` up
  to cheap, the batch fences below).

## Gate results (ff3960a1)

Local: macOS, the shared `.venv` (CPython 3.10), `PYTHONPATH` on the
worktree.

| Check | Result |
| --- | --- |
| `pytest -n 4 -m "not network"` | 31,371 passed, 91 skipped, 0 failed (402 s) |
| `pytest -m network` | 30 passed (91 s) |
| ruff check, ruff format --check, flake8, mypy (1,667 files), pyrefly, bandit | clean |
| pylint `examples/ src/ tests/ tests/*/` | 10.00/10 |
| pyright | 8 errors, all from the local `.venv` lacking the `conformance` group (`ntia_conformance_checker`; the `model_dir` build of spdx3-validate); CI's "Type checking" on ff3960a1 is green |
| `python -m scripts.message_inventory --check` | pass |
| `python scripts/generate_message_reference.py --check` | pass |
| `scripts/check_version_consistency.py` | pass (0.24.0 everywhere) |
| `mkdocs build --strict` | fails in the local `.venv` (pymdown-extensions 12.3 with mkdocstrings 1.0.6: `Highlight.__init__() missing ... 'md'`); passes in a fresh Python 3.14 venv (13.1.2, 1.0.8) and in CI |
| `scripts/manual_cli_checks -j 8 --network` | 650 pass, 0 fail, 29 KNOWN (all one tracked item: "Harvest rewrites per-document entities", order matrix O2/O4/O6) |
| Parity/determinism (manual checks 1, 2 and the `M/*/parity` cells) | pass |
| CI on ff3960a1 (push to main) | Unit tests (all four legs, full suite), Type checking, Lint, Bandit, Build wheels + validate SBOM, Hatch integration, Action self-test, plugin validate, docs: green |

Not run here: mutation testing and a Windows run (per PR, not per release;
each reviewer did a Windows dry run of its area).

## Output diff against v0.24.0

`v0.24.0` and `ff3960a1` sources run by the same interpreter on 75
commands: every subcommand on the manual checks' `demo` project and wheel,
every `tests/fixtures/projects/*`, up to four files per
`tests/fixtures/aimodels/*` format, the fragments, `enrich`, `env` and
refusals (missing path, bad date, unknown command). Pinned
`--creation-datetime` and `SOURCE_DATE_EPOCH`, `--offline`, scratch paths
normalised. 22 cases are byte-identical (`merge` among them), 53 differ;
every difference traces to the CHANGELOG:

| Change | Cases | CHANGELOG |
| --- | --- | --- |
| `ERROR:` lines start `loom <command>:` and end in a `[code]`; wording per the catalogue (`project path not found`, `no SBOM under .dist-info/sboms/`, `not valid [project] metadata`) | missing path, `id generate` without a registry, `verify-wheel`, `validate-wheel`, `enrich`, `model` on a non-model, the dynamic-version project | Changed: missing-input errors reworded (#481/#482); codes (#482-#534) |
| `[option-no-effect]`, `[option-invalid]`, `[license-expression-invalid/resolved]` appended to existing lines | every `model --offline`, `project --trust-model-files`, unknown subcommand, `env` licence lines | Added: messages carry a code |
| `--creation-datetime yesterday`: exit 1 to 2, refused at parse | bad date | Changed: refused at parse, exit 2 (#545) |
| Usage hint drops "or pitloom_config" on the CLI | `wheel`, `embed-wheel` | Changed: advice names the surface's option (#556) |
| Installed-metadata lines reworded: `DIR=`, `[metadata-conflict]`, `[installed-metadata-unusable]` | 5 `installed-metadata-*` projects | Added: codes (#501) |
| Poetry lines: `FILE=poetry.lock PACKAGE=...` `[lock-entry-conflict]`; `Build:` prefix dropped, `[file-discovery-unusable]` | `sampleproject-poetry` | Fixed: discovery lines drop `Build:` (#501) |
| A `[build-system]`-only `pyproject.toml` no longer warns (said at DEBUG) | `sampleproject-setuptools`, `-data` | Fixed: no longer warns of a missing name (#501) |
| `fragment validate` relays each spdx3-validate finding once, framed | the fixture fragments (the merged check fails on both trees: TRY-1) | Changed: each finding once (#515) |
| SBOM: parameter count for CRFsuite and PT2; ONNX `producer_name` as a `Model file written by:` comment line and `writing_tool` provenance; PyTorch `.pt` type `Linear` not `OrderedDict`; Safetensors `framework` provenance names `__metadata__.format`; reworded parameter-count comment | CRFsuite, PT2, ONNX, PyTorch, Safetensors | Added/Changed/Fixed (#509) |

`tests/fixtures/aimodels/hostile/hdf5-hang.h5` times out (120 s) on both
trees: a local model file is trusted and h5py is native, as designed
(model-sbom-from-git.md D1); not a finding.

## Findings and triage

Full entries, with reproducers: [findings-code.md](pre-release-review-0.25.0/findings-code.md)
(CLI, LIB, REG, HOOK) and [findings-docs.md](pre-release-review-0.25.0/findings-docs.md)
(SKL, MSG, DOC, ACT, TRY). Duplicates: DOC-1 = LIB-3; DOC-6 = TRY-4 = SKL-2;
TRY-3 = CLI-5; TRY-10 and MSG-5 are parts of CLI-10; CLI-6 and HOOK-1 share
one cause.

### Release blockers

| Id | What | Why it blocks | PR |
| --- | --- | --- | --- |
| LIB-1 | Library `project_dir=""` reads the cwd; the embedded SBOM carries another project's creators | wrong SBOM content; this release's CHANGELOG says `""` never reads the cwd | A |
| LIB-2 | `loom.add_dataset("")` hashes the cwd as a dataset named `''`, silently | same class and same CHANGELOG claim, on the SDK's main call | A |
| CLI-1 | `--creator-name ''` ends in a traceback on every generating command | a traceback on a user input (in v0.24.0 too) | A |
| TRY-1 (+ TRY-6) | `loom fragment validate A B`, as documented, fails every pair of valid Pitloom SBOMs whose `created` differ (spdx3-validate shares blank nodes) | a documented command fails on the normal case: a caveat (or `--no-merge` by default) before tagging; the fix is upstream | C |
| SKL-2 | 37 skill and doc lines require `pitloom >= 0.24.1`, a version that does not exist | a documented install command cannot resolve | D |

### Cheap fixes for 0.25.0

| PR | Ids |
| --- | --- |
| A, argument checks | LIB-4, LIB-5, LIB-8, LIB-10, REG-3, CLI-2, CLI-9 (`''` only), LIB-9 (CHANGELOG wording only) |
| B, catalogue | LIB-6, MSG-1, MSG-2, MSG-6, LIB-7, CLI-3, HOOK-4 (catalogue text) |
| C, docs and skills | DOC-1, REG-1, MSG-3, MSG-4, TRY-2, DOC-2, DOC-3, TRY-9a, DOC-4, DOC-5, DOC-7, TRY-11, REG-2, SKL-3, SKL-4, SKL-5, SKL-6, ACT-3, ACT-4, ACT-5, HOOK-4 (page quote), CLI-6 (soften the `docs/cli.md` line) |
| D, the bump | SKL-1, HOOK-6, the bump cautions (findings-docs.md, "Version text") |

### Next release

CLI-4, CLI-5, CLI-6 and HOOK-1 (code), CLI-7, CLI-8, CLI-9 (format check),
CLI-10 with MSG-5, CLI-11, CLI-12, LIB-9 (code), LIB-11, LIB-12, LIB-13,
LIB-14, REG-4, REG-5, REG-6, REG-7, HOOK-2, HOOK-3, HOOK-5, MSG-7, ACT-1,
ACT-2, TRY-1 (the spdx3-validate fix, by a handoff), TRY-5, TRY-7, TRY-8,
TRY-12. The roadmap points here ([roadmap.md](../design/roadmap.md),
"Pre-release review 0.25.0"). Shared root causes to fix as one change each:

- CLI values checked by library dataclasses after parsing (exit 1 or a
  traceback instead of exit 2): CLI-1, CLI-2, CLI-9, CLI-12's
  `--sbom-basename a/b`; validate at parse time in one place (A covers the
  first three).
- Empty or wrong-type path arguments: LIB-1, LIB-2, LIB-4, LIB-5, REG-3;
  one non-empty path helper (`require_path_argument`, `_loom_args._is_named`
  exist; no third copy).
- Inert-option coverage: CLI-6, HOOK-1, TRY-5 (`--content-type-method`
  without `--content-type`).
- Paths as typed versus absolute: CLI-10, MSG-5, TRY-9b, TRY-10, SKL-5's
  `Build:` line, REG-5's `FILE=`; one helper.

## Proposed fix plan

In the policy's order: output-changing fixes first, docs and skills last,
so one docs pass describes the final output. One owner per file;
`CHANGELOG.md` is the only file both A and B touch (CI requires it in each
PR): B adds its lines after A merges.

1. **PR A, argument checks** (exit codes, error lines): LIB-1, LIB-2, LIB-4
   (`embed.py`, `assemble/_generators_shared.py` and the wheel generators'
   `project_dir` check, `_loom_args.py`), LIB-5 and REG-3
   (`id_registry/_registry.py`, `_format.py`, `_sbom_io.py` for the
   directory case), LIB-8 (`configure_logging()` in the `IdRegistry` entry
   points, `resolve_registry`, `fetch_git_project`, `find_embedded_sbom`),
   LIB-10 (`extract/remote/git.py:298`), CLI-1, CLI-2 and CLI-9 `''`
   (`cli/parser.py`, `cli/options_resolve.py`: an `argparse` error at
   parse). Existing codes only; no `src/pitloom/messages/` or generated page.
   CHANGELOG: fold into the #545/#557 bullet and narrow it (LIB-9). Gate A
   area: registry, config and options rows of
   [manual-cli-checks.md](manual-cli-checks.md#when-to-run).
2. **PR B, catalogue** (stderr wording), at the same time as A. Fence:
   `src/pitloom/messages/`, `messages/_sbom_validation_say.py`, the
   generated `docs/message-codes*.md` and `skills/*/references/messages-*.md`,
   `assemble/_generators_git.py` and `_generators_pypi.py` (LIB-6, with its
   `one-of-*` entries in `_config_place.py`). MSG-1 (a library twin for
   `embed_wheel_sbom()` naming `overrides=ConfigOverrides(...)`, unless the
   user rules otherwise), MSG-6, LIB-7, MSG-2 (the `did` text: `TypeError`
   for a wrong type), HOOK-4 (the generated "exit 1" text), CLI-3 (escape the
   line break, as for ESC). Regenerate the reference; `since` stays 0.25.0.
3. **PR C, docs and skills**, after A and B (it quotes their final text),
   merged with the planned docs/working-docs/skills sweep: TRY-1 and TRY-6
   (the caveat), then the docs batch above. DOC-5 (splitting
   `docs/python-api.md`) last, since DOC-1, REG-1, TRY-2, TRY-11 and DOC-7
   edit that page; the split breaks `docs/id-registry-keys.md:13`
   (`python-api.md#tracking-decorator`). MSG-4 is a `src/` docstring: run the
   linters. Budgets: `sbom-enrich` body 12 bytes spare, `sbom-generate`
   body 16,188 of 16,384 bytes and description 3 characters.
4. **PR D, the 0.25.0 bump** (the user tags): SKL-2, SKL-1, HOOK-6, the bump
   cautions; extend `tests/test_licenseid_floor_docs.py` to the prose form
   "LicenseID 0.x.y".

A and B in parallel, then C, then D; then Gate A and Gate B on the release
commit and the release checklist (policy step 7).

## Decisions for the user

Not decisions: LIB-1, LIB-2, CLI-1 and the TRY-1 caveat block the release by
the review's definition; SKL-2 is the tracked cut sweep. These are open:

1. **TRY-1 for 0.25.0**: ship a caveat in `docs/fragments.md` and
   `sbom-validate`, or make `--no-merge` the default until spdx3-validate
   keeps blank nodes apart? The fix itself goes to spdx3-validate (the
   user's repository) by a handoff prompt.
2. **MSG-1**: a library twin of the advice (proposed), or let
   `embed_wheel_sbom()` take `trust_model_files`/`scan_model_usage` (a public
   API change)?
3. **TRY-2 semantics**: should `loom.add_dataset()` in a `use_model()` run
   record `trainedOn`, be refused, or become `testedOn`? PR C fixes only the
   example.
4. **CLI-7**: a missing local path shaped `a/b` is sent to huggingface.co
   (a local directory name leaves the machine) and, when the Hub says the
   repository does not exist, an SBOM is still written with exit 0. Keep
   (documented under `download-network-failed`), or make "repository not
   found" an error, per "a read/access failure is an error"?
5. **TRY-8**: `[project.urls] Homepage` as `software_downloadLocation` when
   there is no `Source` (arguably wrong content); **TRY-7**: a `uuid4`
   document namespace per `loom.run` fragment against "no random UUIDs".
   Next release either way.
