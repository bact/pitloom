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

## Fix status: catalogue batch (PR B, branch `review-catalogue-fixes`)

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
  PR C: `docs/ai-model-scan-limits.md:167` says only the keyword form.
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
