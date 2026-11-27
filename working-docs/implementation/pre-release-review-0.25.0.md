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
[findings, docs, skills, Action](pre-release-review-0.25.0/findings-docs.md),
[docs batch done](pre-release-review-0.25.0/docs-batch-done.md).

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
  release blockers (6 ids), 39 fixes for 0.25.0, 30 for the next release
  (four ids are split between buckets), after an Opus second opinion
  whose amendments were all taken (LIB-2 and the TRY-1 caveat up to
  blockers, SKL-1 down to cheap, LIB-10 and the empty `--creator-email` up
  to cheap, the batch fences below) and the user's rulings of 2026-11-27
  (TRY-2 and CLI-7 become 0.25.0 code fixes).

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
| A, argument checks | LIB-4, LIB-5, LIB-8, LIB-10, REG-3, CLI-2, CLI-9 (`''` only), LIB-9 (CHANGELOG wording only), TRY-2 (code, ruled) |
| B, catalogue | LIB-6, MSG-1, MSG-2, MSG-6, LIB-7, CLI-3, HOOK-4 (catalogue text) |
| E, Hub "repository not found" | CLI-7 (ruled) |
| C, docs and skills | DOC-1, REG-1, MSG-3, MSG-4, TRY-2, DOC-2, DOC-3, TRY-9a, DOC-4, DOC-5, DOC-7, TRY-11, REG-2, SKL-3, SKL-4, SKL-5, SKL-6, ACT-3, ACT-4, ACT-5, HOOK-4 (page quote), CLI-6 (soften the `docs/cli.md` line) |
| D, the bump | SKL-1, HOOK-6, the bump cautions (findings-docs.md, "Version text") |

### Next release

CLI-4, CLI-5, CLI-6 and HOOK-1 (code), CLI-8, CLI-9 (format check),
CLI-10 with MSG-5, CLI-11, CLI-12, LIB-9 (code), LIB-11, LIB-12, LIB-13,
LIB-14, REG-4, REG-5, REG-6, REG-7, HOOK-2, HOOK-3, HOOK-5, MSG-7, ACT-1,
ACT-2, TRY-1 (the spdx3-validate fix, by the handoff below), TRY-5, TRY-7
and TRY-8 (ruled: next release), TRY-12. The roadmap points here ([roadmap.md](../design/roadmap.md),
"Pre-release review 0.25.0").

Also for the next release (user, 2026-11-27; moved from the roadmap):

- **A malformed Hub repo id gets "not found" advice.** `_HF_ID_RE` accepts
  `a/b--c`, `a/b..c`, `a/b.git`, `a/b-`, `a/b.` and names over 96
  characters, which `huggingface_hub.validate_repo_id` rejects before any
  request. Before #561 this was said as `hub-response-invalid`; since #561
  it is `input-not-found/hub` (exit 1), whose advice ("if it is private,
  set HF_TOKEN ...") does not fit an id no repository can have. Refuse
  these ids in `parse_hf_model_id` with `hf-url-invalid`, reusing the
  dataset rule (`core/dataset_names.is_hub_dataset_id`), and test it.
- **A revision URL is read at the default branch with no message.**
  `https://huggingface.co/o/m/tree/<sha>` parses to `o/m` and the revision
  is dropped (checked on #562's tree): a silent deviation from the URL as
  given. Say it (`INFO:`) or honour the revision.

Shared root causes to fix as one change each:

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
so one docs pass describes the final output. One owner per file.
`CHANGELOG.md` is the one file every code PR touches (CI's "Changelog entry
required" needs it): each PR adds its own lines and the later one rebases.

0. **This review** (`working-docs/` only: the review doc, its two findings
   files, `roadmap.md`): its own small PR, first. Docs-only, so the
   CHANGELOG check and the code CI skip it; the fix PRs can then link it,
   and their diffs stay code-only.
1. **PR A, argument checks and the SDK relationship** (exit codes, error
   lines, fragment bytes). Fence: `src/pitloom/embed.py`,
   `assemble/_generators_shared.py` and the wheel generators' `project_dir`
   check, `src/pitloom/_loom_args.py`, `src/pitloom/_loom_active_run.py`,
   `src/pitloom/id_registry/` (`_registry.py`, `_format.py`),
   `src/pitloom/_sbom_io.py`, `extract/remote/git.py`, the
   `fetch_git_project`/`find_embedded_sbom` modules (LIB-8),
   `cli/parser.py`, `cli/options_resolve.py`, their tests. LIB-1, LIB-2,
   LIB-4 (one non-empty path helper), LIB-5 and REG-3, LIB-8, LIB-10, CLI-1,
   CLI-2 and CLI-9 `''` (an `argparse` error at parse), TRY-2 (in
   `_emit_model_dataset_relationships()`, `_loom_active_run.py:364-373`:
   `self.datasets` relate as `testedOn` when `self._model_generated` is
   false, i.e. a `use_model()` run). Existing codes only: no
   `src/pitloom/messages/`, no generated page. CHANGELOG: fold into the
   #545/#557 bullet and narrow it (LIB-9); TRY-2 a "Changed" line. Gate A
   area: registry, config, options and `loom.run` rows of
   [manual-cli-checks.md](manual-cli-checks.md#when-to-run) (`O1/*/fresh-loom`,
   `O3/*` for TRY-2).
2. **PR B, catalogue** (stderr wording), at the same time as A. Fence:
   `src/pitloom/messages/`, the generated `docs/message-codes*.md` and
   `skills/*/references/messages-*.md`, `assemble/_generators_git.py`,
   `assemble/_generators_pypi.py`. LIB-6 (with its `one-of-*` entries in
   `messages/_config_place.py`), MSG-1 (ruled: library-specific wording on
   the embed route naming the `ConfigOverrides` fields; no API change),
   MSG-6, LIB-7, MSG-2 (the `did` text: `TypeError` for a wrong type),
   HOOK-4 (the generated "exit 1" text), CLI-3 (escape the line break, as
   for ESC). Regenerate the reference; `since` stays 0.25.0.
3. **PR E, Hub "repository not found"** (CLI-7, ruled), after B: it needs
   a catalogue line and a regenerated reference, B's fence. Fence:
   `src/pitloom/extract/remote/huggingface*.py`, `_hub_api.py`,
   `assemble/__init__.py` (the `hf` route), `src/pitloom/messages/` and the
   generated pages, their tests. A target that is neither a local path nor
   a repository the Hub knows is an error naming the local path as not found
   too (`input-not-found`, or a variant of it): no SBOM, exit 1, on
   `generate` and `model`, CLI and library. Other Hub failures (timeouts,
   gated repositories, 5xx) keep today's `download-network-failed`
   behaviour; decide 401 (anonymous "not found or private") with the user's
   gated-repository cases in mind. Gate A: `M/model/*`, `M/*/target/*`
   with `--network`, and `pytest -m network` for the Hub tests.
4. **PR C, docs and skills**, after A, B and E (it quotes their final
   text), merged with the planned docs/working-docs/skills sweep. Fence:
   `docs/` (not the generated pages), `skills/` (not
   `references/messages-*.md`), `action.yml` comments, MSG-4's docstring.
   TRY-1 and TRY-6 first (ruled: the caveat in `docs/fragments.md` and
   `skills/sbom-validate/SKILL.md`, suggesting `--no-merge` for several
   files, saying an enrichment fragment fails on its own, and that no
   `FILE=... STATUS=valid` line is printed when only the merged check
   fails, `docs/cli.md:364`), TRY-2's example
   (`add_validation_dataset()`, and the new `use_model()` rule), CLI-7's
   page text, then the docs batch above. DOC-5 (splitting
   `docs/python-api.md`) last, since DOC-1, REG-1, TRY-2, TRY-11 and DOC-7
   edit that page; the split breaks `docs/id-registry-keys.md:13`
   (`python-api.md#tracking-decorator`). Budgets: `sbom-enrich` body 12
   bytes spare, `sbom-generate` body 16,188 of 16,384 bytes and description
   3 characters.
5. **PR D, the 0.25.0 bump** (the user tags): SKL-2, SKL-1, HOOK-6, the
   bump cautions; extend `tests/test_licenseid_floor_docs.py` to the prose
   form "LicenseID 0.x.y".

Order: the review PR; A and B in parallel; E after B; C after A, B and E;
D last. Then Gate A and Gate B on the release commit and the release
checklist (policy step 7).

## Fix status: catalogue batch (#559)

All seven items fixed; each has a regression test that fails on the
review's base tree. Files outside the written fence, both needed by the
fix: `scripts/message_reference/sections.py` (HOOK-4: the generated
"exit 1" comes from its `ERROR_RULE_OVERRIDES`, not from the entry) and
`cli/commands/utils.py` (CLI-3: passes the validated paths to the relay;
three lines).

- **LIB-6**: `generate_git_sbom(sbom_kind=)` and `generate_pypi_sbom(kind=)`
  refuse through `require_choice_argument` (`one-of-sbom-kind`,
  `one-of-pypi-kind`): `CodedTypeError` for a non-string,
  `CodedValueError` for an unknown string. The URL of both, and of
  `generate_git_project_sbom()`, goes through `require_text_argument`:
  `None` is `CodedTypeError`, `""` and blank `CodedValueError`, all
  `option-invalid` (an Opus second opinion preferred this to letting the
  `url` field write an empty value: the precedent of every other empty
  argument, and the field is free text). A PyPI URL is parsed before any
  option warns against it. PR C: `docs/python-api-remote.md:113-114` (an
  empty URL is `option-invalid`, not `pypi-url-invalid`) and
  `docs/api.md:25-28` (a Git URL of the wrong type is now checked by the
  generators; `fetch_git_project()` still is not).
- **MSG-1**: as ruled; the mechanism is in
  [message-consistency-rescan.md](../design/message-consistency-rescan.md)
  section 6.1: the reader-unsafe line, both usage hints and (found by the
  first review round) the two `credentials-unsafe` library lines, which
  said `credentials=CredentialPolicy(...)` on the embed route.
  `option-no-effect`'s bare names stay (section 8 there).
  PR C: `docs/ai-model-scan-limits.md:167`, `docs/python-api.md:160-163`
  and the by-surface table of `docs/url-credentials.md:254` give only the
  keyword form (`set trust_model_files=True`,
  `credentials=CredentialPolicy(...)`); add the `embed_wheel_sbom()` form
  (`ConfigOverrides.trust_model_files`, `ConfigOverrides.credentials`).
- **MSG-6**: `set BuildOptions.allow=True`.
- **LIB-7**: the line's `option` value is picked per surface
  (`ALLOW_SIGNED_NAMES`, as `ALLOW_BUILD_NAMES`): `allow_signed_wheel=True`
  in the library. Not a `Twins` with the flag in the template: the
  20-character `--allow-signed-wheel` would then read as catalogue text in
  the CLI's own option declarations (`test_drift_sources`).
- **MSG-2**: summary and `did` say `TypeError (CodedTypeError)` for a
  wrong type, `ValueError (CodedValueError)` for a refused value.
- **HOOK-4**: the reference says the build fails (hook only). The page
  quote (`docs/hatchling-build-hook.md:131-134`) is PR C's.
- **CLI-3**: each validated path, and each `names` entry, is written into
  the validator's text escaped (`escape_controls`, one longest-first
  pass) before the text is split: `bad\nERROR: forged.json` stays on its
  line, as the coded `FILE=` line shows it.

Gates of this batch: the full suite, every CI linter, the message checks,
branch coverage of the changed files, two fresh-context Opus review rounds
(round 1: the credential lines and three stale tests; round 2: catalogue
prose only), 26 mutants of the selection logic (all killed after two added
tests and one redundant check removed), a Windows dry run (no new test
creates a file name with a line break; disk tests are `platform`) and the
manual CLI checks (`-j 8`). One manual check, `O1/src/fresh-loom` (the
loom SDK's dataset key sets), failed once under `-j 8` and passed alone
on this tree and on the base: load-dependent, in code this batch does not
touch; a rerun does not prove it gone.

## Rulings (user, 2026-11-27)

Not decisions: LIB-1, LIB-2, CLI-1 and the TRY-1 caveat block the release
by the review's definition; SKL-2 is the tracked cut sweep.

1. **TRY-1**: caveat plus handoff. Keep the merged check; the caveat goes
   in PR C; spdx3-validate gets the prompt below; it is not edited here.
2. **MSG-1**: library-specific wording naming the `ConfigOverrides`
   fields; no API change (PR B).
3. **TRY-2**: `loom.add_dataset()` inside a `use_model()` run records the
   dataset as `testedOn`, not `trainedOn`: a 0.25.0 code fix (PR A), the
   example in PR C.
4. **CLI-7**: a target that is neither a local path nor a Hub repository
   the Hub knows is an error, no SBOM, exit 1, naming the local path as
   not found too: a 0.25.0 fix (PR E).
5. **TRY-7, TRY-8**: next release.
6. **CLI-7, 401**: always refuse. A target that is no local path and that
   the Hub answers "not found" (an anonymous 401 included, which a private
   model asked for without a token also gets) is an error; the line names
   the local path as not found, says the Hub knows no such model, and adds
   that a private one needs `HF_TOKEN` or `hf auth login`. A bare id and a
   URL alike (the URL line names no local path: a URL is none).
7. **CLI-7, legacy page URL**: fixed in the same PR:
   `https://huggingface.co/gpt2/tree/main` reads as the model `gpt2`, so the
   new error cannot fire on a real model with a one-part id.

## PR A, argument checks: what was done

Branch `review-argument-fixes`, #560. Every PR A item is fixed; the rulings
below had an Opus second opinion, whose amendments were taken unless noted.

- LIB-1, LIB-4: one helper, `pitloom._sbom_io.refuse_empty_path()` (type,
  then `""`), at the start of `generate()`, `generate_project_sbom()`,
  `generate_wheel_sbom()` (before a PyPI download),
  `generate_wheel_sbom_with_metadata()`, `embed_wheel_sbom()`,
  `resolve_registry()`, `refuse_empty_output()` and `IdRegistry`;
  `_loom_args` shares its predicate (`is_named_path`). It lives in
  `_sbom_io` (the fence); `pitloom.core` would fit better (follow-up).
- LIB-2: the loom `name` rule refuses empty or blank on every call taking it
  (`set_model`/`use_model` too: no model is named blank).
- LIB-5, REG-3: `IdRegistry(path=, project_root=)`, `new()`, `save()`,
  `generate()` (paths, root, exclude), `import_sbom()` and `register()`
  (types; empty or blank type name; empty name) refuse with
  `option-invalid` (an empty path in `generate()`'s *paths* is
  `input-not-found`, as `loom id generate ''`); a `str` path is held as a
  `TypedPath`, so `load("./r.json")` names `./r.json` as typed; `save()` over a
  directory is `file-unwritable` naming the path given (`coded_write` in
  `write_registry_file`); `_mint_id`'s empty prefix is an `InternalError`.
- LIB-8: `configure_logging()` in `IdRegistry.__init__`/`load()` (every
  method runs on such an object), `resolve_registry()`,
  `find_embedded_sbom()` (which now refuses an empty `wheel_path`,
  `input-not-found`) and `fetch_git_project()`.
- LIB-10: a Git URL with no host is refused before git runs, with the
  existing `url-unsafe/host-spelling` line (its text does not name a
  missing host: a catalogue follow-up for PR B).
- CLI-1, CLI-2, CLI-9 (`''`): `type=` in `cli/parser.py` refuses an empty
  or blank `--creator-name`, `--creator-email`, `--creation-tool` at parse:
  `argument --x: must be a non-empty string`, `option-invalid`, exit 2.
- TRY-2 (ruled): `_emit_model_dataset_relationships()` relates every
  `add_dataset()` dataset `testedOn` when the run's model was declared with
  `generated=False` (`use_model()`), once even when also a validation
  dataset; `None` (not given) stays training, as `generates` reads it.
- LIB-9: the CHANGELOG bullet now names what is checked.

Gates: Gate A full suite 31,493 passed, 0 failed (main merged in); ruff,
flake8, mypy (1,668 files), pyright, pyrefly 0 errors, pylint 10.00 (exit 0),
bandit; message inventory and reference `--check`; changed lines 100%
branch-covered; every new regression test fails on 1ebf0201. Mutation: 42
mutants of the new checks, all killed. Two fresh-context Opus review rounds
(round 2 found no bug), each with a Windows dry run. Gate B:
`manual_cli_checks -j 8 --network` 671 pass, 0 fail, 29 known (the tracked
order-matrix item). Changed `SKILL.md`s: none.

Left for later (next-release list): `IdRegistry` methods not on the
findings list (`lookup`, `get`, `has_name`, `reserve_id`,
`promote_alias`, `require_project_root`) still raise uncoded errors for a
wrong type; `set_model(path="")` warns `model-file-missing` at exit rather
than refusing; `generate_pypi_sbom(project_dir="")` only warns
(`_generators_pypi.py`, PR B's fence); a `list-of-paths` EXPECTED id;
`id_registry/_registry.py` is 690 lines (over the soft limit); a blank
`email` in `[[tool.pitloom.creator]]` or `Creator(email="")` is still dropped
silently (the CLI flag now refuses it); `extract.remote.pypi.fetch_pypi_file`
(public) never calls `configure_logging()`. For PR C: `docs/api.md:16` says
"choice arguments" are checked (true once LIB-6 lands); the no-host Git URL
refusal and the blank creator/tool refusal are not on the Git URL and CLI
flag pages.

## PR E, Hub "repository not found" (CLI-7): what was done

Branch `hub-repository-not-found`. The Hub's answers, measured on
2026-11-27 with `huggingface_hub` 2.2.0, anonymous (no token was at hand;
the private rows are huggingface_hub's own comment in `hf_raise_for_status`
and the Hub's documentation; an Opus second opinion measured the case and
rename rows):

| Repository | `model_info()` | Files (`resolve`) |
|---|---|---|
| missing (`h/nope`, an owner with no account) | `RepositoryNotFoundError`, 401 "Invalid username or password." | 401 |
| public (`gpt2`, `mistralai/Mistral-7B-v0.1`) | 200 | 200 |
| gated (`meta-llama/Llama-2-7b-hf`, `google/gemma-2b`) | 200, `gated=manual` | card 200; `config.json` 401 `X-Error-Code: GatedRepo` |
| missing, an invalid token sent | as anonymous (the Hub ignores the token) | - |
| public or gated, an invalid token sent | 200 | - |
| another case or a moved name (`GPT2`, `gpt2`) | 200 after a 307 to the current id | - |
| private, no token (or an expired one) | believed: as missing (401) | - |
| private, a token without / with access | believed: 404 `RepoNotFound` / 200 | - |

`GatedRepoError` is a subclass of `RepositoryNotFoundError` (1.x and 2.x)
and is sent for files only; `DisabledRepoError` is not one.

The rule (ruling 6): only `model_info()` decides, the first request. A
`RepositoryNotFoundError` that is no `GatedRepoError`
(`_hub_api.is_repository_not_found`) raises `RemoteSourceError`
`huggingface.repository-not-found`, catalogue `input-not-found/hub`, before
any file is fetched: no SBOM, exit 1, on `loom generate`, `loom model`,
`generate()` and `generate_model_sbom()`. Two lines: an id (`target not
found: 'h/nope' is no local path, and the Hugging Face Hub knows no model
<page>; if it is private, set HF_TOKEN ...`) and a URL (`URL=<page>: the
Hugging Face Hub knows no such model; ...`); the page is the Hub asked
(`HF_ENDPOINT`). Every other failure keeps its `WARNING:`. A dataset a card
lists is not the target: `dataset_info()` not found still warns. An id
`huggingface_hub` refuses before any request (`HFValidationError`:
`a/b--c`, `h/no pe`) is refused the same way: no model can have it. A
mirror (`HF_ENDPOINT`) that answers a bare 404 without the Hub's
`X-Error-Code: RepoNotFound` is no "not found" answer: it still warns
(an http mirror is refused before any request).

Also: `loom model <url>` now gives the library the URL as typed, as
`loom generate` does (it gave the id, so a URL's refusal would have named
a local path, and `gpt2/tree/main` was read as a local file `gpt2`); the
URL-rewrite `INFO:` is said by `read_huggingface` alone, before the offline
check. A page URL `<id>/<page>/<part>` with a page kind (`tree`, `blob`,
`resolve`, `commit`, `commits`, `discussions`, `edit`, `raw`, `blame`) and
a part that is none names the one-part id (ruling 7); `org/tree/tree/main`
stays the model `org/tree` (`settings` is a page kind too, measured). A
page kind with nothing after it is read as the two parts
(`https://huggingface.co/gpt2/settings` is refused naming
`gpt2/settings`): nothing tells it from a model of that name. Measured on
the Hub: bare `gpt2/tree` and `gpt2/commits` are 401 there too (no page),
`gpt2/settings` is a page that needs a login, `gpt2/discussions` is read
as before (no refusal). A retry as the one-part id was tried and dropped:
it named the output file and the rewrite `INFO:` after an id the run then
did not read. An id-shaped target that is a dangling symbolic
link is a local path (`os.path.lexists`), so "is no local path" stays true.

The other items: `fetch_git_project()` checks its URL argument
(`require_text_argument`) when the block is entered, before the temporary
directory; a Git URL with no host has its own `git-url-invalid` line ("the
URL names no host"; a line of an existing code rather than a new
`url-unsafe/host-missing`, as the catalogue rules ask); `IdRegistry.generate()`
says "a list or tuple of paths" (`list-of-paths`).

For PR C: `docs/ai-model-formats-hugging-face.md` and `docs/cli.md:168-178`
(a model the Hub does not know, or private without a token, is
`input-not-found/hub`; a page of a one-part id; a dangling link is a local
path), `docs/python-api-remote.md` (the `huggingface.repository-not-found`
code; the no-host `git-url-invalid` line beside `url-unsafe/host-spelling`
at line 49), `docs/git-urls.md:114-125` (the no-host refusal),
`docs/api.md:25-28` (`fetch_git_project()` now checks its URL).

Follow-ups (next release): `docs/message-codes-targets.md` is 163 bytes
under its 30,000-byte cap: the next `targets` entry needs a topic split; a
one-part URL with no page (`https://huggingface.co/gpt2`) is still
`hf-url-invalid`; the model id kept is the one typed, not the Hub's current
one (`info.id`: `gpt2`, not `openai-community/gpt2`); a page URL's revision
(`tree/v1.0`) is not read, the revision `model_info()` states is;
`https://huggingface.co/gpt2/discussions` is read as the model
`gpt2/discussions`, whose `model_info()` answer is no model's
(`hub-response-invalid`, an SBOM, exit 0, as before); a URL without its
scheme (`huggingface.co/gpt2`) is read as an id and refused naming
`https://huggingface.co/huggingface.co/gpt2`, with no hint to add
`https://`.

## PR C, docs and skills, and the sweep: what was done

Branch `release-docs-sweep`: every item fixed or ruled out with its reason,
and the sweep's removals, in [docs-batch-done.md](pre-release-review-0.25.0/docs-batch-done.md).

## Handoff prompt for spdx3-validate (TRY-1)

For a session in the spdx3-validate repository (`bact/spdx3-validate`); the
pin Pitloom tests is `0e2e3562` (`pyproject.toml`, `conformance` group):

> `spdx3_validate.validate(paths, check_merged=True)` builds the merged
> graph as `merged = rdflib.Graph()` then `merged += doc.graph` per
> document (`src/spdx3_validate/core.py:719-722` at the pinned
> commit). A blank node label is scoped to its own JSON-LD document, but the
> union keeps the labels, so two documents that both use `_:CreationInfo0`
> (every Pitloom SBOM does) share one `CreationInfo` node in the merged
> graph. With different `created` values it then fails
> `sh:MaxCountConstraintComponent` on `Core/created` ("More than 1 values
> on ... _:CreationInfo0"), though each document is valid on its own.
> Repro: two SPDX 3 JSON-LD files, each with `{"@id": "_:CreationInfo0",
> "type": "CreationInfo", "created": ...}` and different `created`; the
> merged check fails, `--no-merge` passes. Fix: rename each document's
> blank nodes apart before the union (for example map every `BNode` of
> document *i* to a fresh `BNode()`, or skolemise per document), keeping
> IRIs shared. Add a regression test with two such documents; check that a
> blank node a document references twice still resolves to one node within
> that document. Do not change how a single document is validated.
