---
Created: 2026-10-29
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue: the contract between Pitloom and the skills

See also: [roadmap.md](roadmap.md) (the summary bullet),
[diagnostics-logging-followups.md](diagnostics-logging-followups.md),
[debug-logging.md](../implementation/debug-logging.md),
[skills-trigger-coverage.md](../implementation/skills-trigger-coverage.md),
`git-lfs-pointers.md` in `../implementation/` once #378 is merged (the case
that showed the gap).

Status: decided 2026-10-29 (the four decisions, then decisions A to L of
the review of #390, then M proposed, at the end); scope split between 0.22.0 and 0.23.0
below. The inventory (step 1) is done; its results and the printed form it
settled are in "Inventory results". Step 3a, the `lfs-pointer` families with
the plumbing, schema and ratchet, is #390 (merged); migration step 2, the
`over-cap` family, is #396 (decisions in "The `over-cap` family"); step 3,
the model-stub causes, is #404 (PR 1a; decisions in "The model-stub causes");
step 4, unreadable files and directories, is #408 (PR 2a; decisions in "The
unreadable files and directories").

## Core idea

**The message catalogue is the contract between Pitloom and the skills.** A
skill reads Pitloom's stderr and stdout, decides what to do and tells the user
what happened. Today that contract is implicit: each skill copies message text
by hand, and nothing fails when the code changes. The catalogue makes it
explicit: one list of messages (level, subject, condition, meaning, advice) that
the code emits from, the skills quote from, and tests hold together.

## Why now

Measured 2026-10-29 on the Git LFS branch (#378):

- About 233 `warning` and 84 `info` call sites in `src/pitloom`, 2 `ERROR`
  prints; 56 sites use the shared helpers (`warn_once`, `log_once`,
  `warn_over_cap`); the rest are free text.
- The skills quote about 157 `WARNING:`, `ERROR:` or `INFO:` messages by hand.
- Tests pin the wording of single families (`test_cap_warnings`,
  `test_messages_quote_paths`). None compares the skills with the code.
- The same condition has several shapes. The LFS refusal prints
  `ERROR: model command failed: ...`, `ERROR: SBOM generation failed: ...` or
  `ERROR: enrichment fragment generation failed: ...` for one sentence. The
  advice differs by source: `run 'git lfs pull'` for a directory, `clone with
  git lfs` for a Git URL.
- `SKILL.md` bodies are 24.5 KB (about 480 lines, roughly 6,000 tokens): under
  our byte test, above the Agent Skills guidance of about 5,000 tokens.

## Goals

1. Skill bodies stay within the recommended size, so they are read in full.
2. Everything important or safety-related is in the body, so it is always read.
3. Every useful detail is kept: in the body, or in `references/` linked at the
   exact step that needs it.
4. A skill can explain what Pitloom did, and what it found in the environment.
5. Pitloom's messages are easy to digest: predictable, consistent, mechanical.

## Pitloom side

1. **Inventory (read-only). Done 2026-10-29**, see "Inventory results".
2. **Grammar, written down and ratcheted.** Shape:
   `LEVEL: [SUBJECT=value: ]CONDITION[ (detail)][; ACTION] [code]`. Advice is a
   catalogue field, not parsed from the line (see the results). A grammar test
   fails any new message that breaks it; existing outliers sit in an allow-list
   that only shrinks (as licenseid's `check_diagnostic_grammar` does), fed by
   the lines the tests actually produce.
3. **One helper per family** wherever a pattern is hand-copied at three or more
   sites (extends the over-cap helper).
4. **A closed condition vocabulary for new and touched messages only**
   (`lfs-pointer`, `over-cap`, `not-a-model`); no rewrite of existing text. The
   code is printed as a trailing ` [code]` and travels on the log record and on
   exceptions, not in the message text.
5. **State the environment decision.** Offline, static or real build, which cap
   applied, which registry: each is an `INFO:` or `WARNING:` with its cause. The
   inventory shows where one is missing.
6. **Optional: `--report FILE`**, one JSON line per message (code, level,
   subject, fields), human lines unchanged. A new CLI, Action and matrix
   surface: only if 1 to 5 do not suffice.

## Skills side

1. **Body budget** below today's ceiling (target 16 to 18 KB, 400 lines),
   ratcheted down.
2. **The body holds**: triggers and hand-offs, the decision flow, every safety
   rule and mandatory check, every non-interactive fallback, and one short
   section on reading Pitloom's output (explain and relay; never run the fix).
   Everything else moves to `references/`.
3. **Every reference is linked at its step with a condition** ("if Pitloom
   reports X, read `references/Y.md`"). Tests: no orphan reference page; every
   body pointer states a condition.
4. **One shared message reference, generated from the catalogue**, not written
   by hand: meaning, what Pitloom did, what to tell the user. A drift test:
   every message a skill quotes must match a catalogue pattern.
5. **A "what Pitloom did" reference** mapping each decision point to its
   messages and to more detail (`PITLOOM_DEBUG`, `-v`).
6. **Behaviour checks**: static tests, plus a few scenarios (Pitloom output in,
   expected explanation out) run with an agent during development.

## Inventory results

Measured 2026-10-29 on `main` b18e2cce by an AST extraction of every emission
site, then a classification; every count is from a script. (The scripts move
into the repo with the first catalogue PR.)

- **983 sites; 718 user-visible lines** (WARNING, INFO, ERROR) with 517 distinct
  templates, in **62 families using 35 condition words**. Top 10 families hold
  43% of sites, top 20 hold 65%, **31 reach 80%**, 41 reach 90%; 11 families
  have 1 to 3 sites. 37% of sites already use a helper or shared constant; 568
  places to edit.
- **Not catalogued (265 sites):** internal invariants 37, pass-through
  `str(exc)` 49, KEY=VALUE data 16, DEBUG 46, reader-detail raises 97 (their
  text is the detail of a catalogued line), `loom.*` library raises 19, one
  traceback.
- **Printed form: a trailing `[code]`**, after a space, parsed by
  `^(ERROR|WARNING|INFO): (.*) \[([a-z][a-z0-9/-]*)\]$` (dots dropped by
  decision A). Example: `WARNING: FILE=demo/model.gguf: Git LFS pointer,
  content not read; run 'git lfs pull' for the content [lfs-pointer]`.
  The message text is unchanged, so the 453 `in caplog` and 46 `caplog.messages
  ==` assertions and all 46 matched skill quotes still pass; about 47 full-line
  stderr tests can break, one family at a time. Rejected: a `CODE=` pair after
  the subject (155 of 545 templates name a path with no KEY subject) and a
  leading condition word (rewrites every line; licenseid can use it because its
  subjects are a closed set of words).
- **Advice is a catalogue field.** 211 templates contain `; `, and another
  tool's own `; ACTION` can sit inside a detail, so the advice cannot be parsed
  from the line.
- **Wording drift:** 170 sites break six mechanical rules (83 ` -- `, 72
  trailing periods, 22 two-sentence messages, 16 pipe suffixes, 12 contractions,
  7 "Please") across 75 modules; "failed to read" has 12 variants over 18 sites;
  "could not" (32) competes with "cannot" (20).
- **Skill quotes:** 46 of the 168 quotes match exactly; the 7 unmatched and the
  approximate one are live (none stale), three need small corrections, and one
  comes from spdx3-validate, so the drift test needs an allow-list for external
  tools. About 94 of the 109 bare-tag quotes could cite a code.
- **Licence families** (8 classification sites plus 3 DEBUG) wait for the
  licenseid 0.7.0 adoption; 5 licence-file-read sites probably survive it.

**Migration order** (cost against benefit; one family per PR, code first,
wording later; revised by the #390 review, family names after decisions B
and C):

1. `lfs-pointer`, `lfs-pointer/shipped`, `lfs-pointer-malformed`: the
   plumbing, the schema and the ratchet (#390).
2. `over-cap` (#396): 33 `warn_over_cap` calls in 23 modules (one inside
   the `warn_field_cap` wrapper, so 33 inventory sites) and 3 raises (an
   sdist's config file, a Git URL's checkout and `git` output). The helper,
   `Cap` (46 calls in 27 modules) and `over_cap_of` moved into
   `pitloom.messages`: 35 modules and 2 tests import them from there.
3. The model-stub causes (#404, PR 1a): `library-missing`,
   `reader-unsafe`, `model-unreadable`, `model-wrong-format`,
   `parameter-count-invalid`, `hyperparameter-conflict` (not `model-gated`,
   a response, nor `not-a-model`, merged into `wrong-format`). The model
   fields a reader reads in part follow in PR 1b.
4. `file-unreadable` and `dir-unlistable`, paired with the evidence reasons of
   the same names (#408, PR 2a; the cards and `fetch_json` follow in 2b).
5. `option-no-effect`: the first entry whose actor is the `caller`.
6. Frames: the uniform `loom <command>:` prefix of an `ERROR:` (its own PR;
   the `FRAMES` table holds today's strings).
7. The registry file codes, then `input-not-found` (a helper first).
8. `lock-file-*`, then `lock-entry-*`; then `config-*`; then `timeout` and
   `network-failed`.
9. The licence families, after the `licenseid` 0.7.0 adoption.

**Ratchet.** A runtime check on every captured stderr line (one tag, one line,
no trailing period, no "Please", a `[code]` must be in the catalogue) plus a
static, shrink-only allow-list keyed by module and normalised template.
Capitalisation, a path with no KEY subject, "could not" against "failed to", and
the wrapper wording need a decision before they become rules.

## Scope by release

**0.22.0** (with the `licenseid` 0.7.0 adoption, which is already planned for
this release): correct reporting on the existing infrastructure, and better
message language and pattern.

- Steps 1 to 4 below: inventory, grammar and ratchet test, catalogue in code
  with the emit helper, generated skills reference and drift test, outliers
  fixed family by family.
- The skill size PR (step 2).
- Order with the adoption: the licence families are rewritten by the adoption
  (`resolve()` replaces Pitloom's own classifier and its messages), so fix
  those families after it lands, not before.

**0.23.0**: `--report FILE` (JSON Lines, SARIF-compatible field names), the
SARIF 2.1.0 export, and the licence resolver's result nested in a record
(`licenseid`'s `Resolution` as it is, not re-modelled). Deferred so that the
nested shape is real, not guessed.

## Order

| Step | Work | Agent | Release |
| - | - | - | - |
| 0 | Finish #378, then the ceilings PR | in progress | 0.22.0 |
| 1 | Inventory and outlier report (read-only): **done 2026-10-29** | Sonnet extract, Opus classify | 0.22.0 |
| 2 | Skill size PR: move detail to references, conditional pointers | Sonnet, Opus review | 0.22.0 |
| 3a | **`lfs-pointer` family first, with the plumbing** (code on the record and on exceptions, formatter and `print_error`, the catalogue module, the drift test), then the #390 review's schema (decisions A to L): **in review (#390)** | Opus design, Sonnet | 0.22.0 |
| 3b | Remaining families in the migration order above, grammar ratchet, generated skills reference | Opus design, Sonnet | 0.22.0 |
| 4 | Fix outliers family by family, smallest first (licence families after the adoption) | Sonnet | 0.22.0 |
| 5 | `--report` JSON Lines, SARIF export, resolver detail, scenario checks | decide after step 3 | 0.23.0 |

Steps 1 and 2 are independent. Compatibility is not a constraint (alpha).

## Decisions

Decided 2026-10-29 (the maintainer took the recommendations; SARIF and the
resolver JSON deferred to 0.23.0):

1. **Condition token.** Every catalogued message has a stable code. In 0.22.0
   the printed line carries it only for catalogued messages, as a trailing `
   [code]` (settled by the inventory; see the results) so `LEVEL:` stays first
   and the existing text is unchanged. A message without a token is "not
   catalogued yet"; the ratchet shrinks that set. `--report` (0.23.0) will give
   every record a code, `uncatalogued` where there is none. (A code was first
   to hold dots, as `RemoteSourceError` codes do, `git.too-large`; decision A
   replaced them with `/`.)
2. **`--report`.** JSON Lines first, SARIF-compatible names (`ruleId`, `level`,
   `message`, a location from `FILE=`); SARIF export and the licence
   resolver's nested result follow. All 0.23.0.
3. **Skill body size.** Target 16 KB and 400 lines; hard limits 20 KB and 500
   lines (the Agent Skills guidance is under 500 lines and about 5,000 tokens,
   roughly 20 KB). Ratchet down from today's 24.5 KB.
4. **Catalogue location.** In code, the source of truth: the emit helper formats
   the line; docs and the skills' message reference are generated; the drift
   test checks that every message a skill quotes matches an entry.

Decided 2026-10-29 by the maintainer on the #390 review ("go with your
recommendations"; SARIF and `licenseid` codes get room only, no scheme):

- **A. Variant separator `/`.** A code is a family or `family/variant`; each
  part kebab ASCII, `[a-z][a-z0-9]*(-[a-z0-9]+)*`; at most one `/`; at most 40
  characters. A reader takes `[a-z][a-z0-9/-]*`, so a dotted TOML table
  (`[tool.poetry.dependencies]`) never reads as a code.
- **B. Subject first.** `[subject-]condition` (`file-unreadable`,
  `dir-unlistable`); the bare condition when it does not depend on the
  subject (`over-cap`, `timeout`, `network-failed`, `lfs-pointer`,
  `not-a-model`, `interrupted`).
- **C. Name by cause**, never by Pitloom's response (`skipped`, `ignored`,
  `new-id`, `left-out`) or by a module.
- **D. Split a code only when the advice or the SBOM effect differs**
  (`over-cap` stays one code).
- **E. One code for ERROR and WARNING** of one condition; the reference
  states the ERROR outcome by rule (the command stops for that input and
  writes nothing for it, exit 1); each printed line carries its level. One
  condition per family; a variant never changes it.
- **F. Causes only** in the condition vocabulary (23 words): `malformed`,
  `timeout`, `network-failed`, `needs-build`, `not-recordable`, `ambiguous`,
  `unsafe`, `missing` added; `refused`/`rejected`, `not-this-format`/
  `not-a-model` (now `wrong-format`), `id-collision`/`mismatch` (now
  `conflict`) merged; `decision`, `summary`, `usage`, `wrapper` and `licence`
  moved out (a message kind, an actor, a frame, a domain).
- **G. Advice by actor.** `user`: an agent relays it ("Tell the user ... Do
  not ... for them"); `caller`: the program that ran the command may fix
  its own command.
- **H. Named values owned by the catalogue.** A line is `%(name)s`
  templates; `emit(..., file=..., count=...)` and `CodedValueError(M,
  path=...)` write each value through its field (a quoted path, an escaped
  `FILE=`, `N bytes`), each with a tight shape (an `oid` is 64 hex digits).
- **I. Frames** are a table (`FRAMES`): the CLI handler's and the hook's
  `<what> failed:`, and the relay's `FORMAT=... FILE=...:`. The uniform
  `loom <command>:` frame is its own PR.
- **J. Ratchet**: per module and in total, falls only; a programming error
  is out of scope by its class (`InternalError`), never by raising a count;
  a reader's raise is detail.
- **K.** `warn_over_cap` moves into `pitloom.messages` with the `over-cap`
  family PR, deferred: moving it alone touches 24 modules (35 calls) and
  prints nothing new, since the line has no code yet. Done in #396, measured
  then: 33 calls in 23 modules; 35 modules and 2 tests imported a moved name.
- **L. Stability.** A code is stable from the release that first prints it:
  never renamed, reused or removed while its condition can occur; variants
  may appear in any release; a code that can no longer occur is marked
  retired and stays; after a release a rename carries `replaces` for one
  minor release. Tool names are reserved family names (`pitloom`,
  `licenseid`, `lumina`, `spdx`, `sbom`, `sarif`, `bom`); no producer prefix
  in a printed code.
- **M. (Proposed after #390 merged.) A trusted line proves its code, not its
  values.** `trusted_message` matches a line against the entry's templates,
  and a free field (`FILE=`, shape `.+`) can hold any text, even
  `; run 'git lfs pull'; FILE=x`. The advice a skill acts on comes from the
  catalogue entry of the code, never from the line; a free value is data.
  Stated in `docs/messages.md` ("What a trusted line does and does not
  prove").

**Room for SARIF and `licenseid`** (a note, no design): the charset keeps the
door open; a `/` variant maps to a SARIF hierarchical `ruleId`
(`CA5350/md5`); a family is a `rule.id`, a code a `result.ruleId`, the
reference's section of a code a `helpUri`; `Message` is keyword-only, so
`rule_id` or `tags` can be added. Lumina's SARIF ingest refuses a rule id
that does not start `BOM-`: Pitloom and `licenseid` diagnostics reach it
through its Notification path instead.

## The `over-cap` family

Decided 2026-10-29 for #396 (the maintainer took the recommendations):

1. One code, `over-cap`, no variant. The advice differs only between a cap
   a setting sets and a fixed one, and the line names the setting (its
   purpose is the setting's name), so one advice states both; a variant per
   setting would be a stability promise (decision L).
2. `Cap`, `warn_over_cap` and `over_cap_of` live in `pitloom.messages`:
   `Cap` renders and checks itself through the catalogue's fields. The
   logging module imports nothing of the catalogue.
3. Two warning shapes: the input after its key (`FILE=`, `DIR=`, `FIELD=`,
   `DATASET=`, `MARKER=`, `REQUIREMENT=`), or a model's `FORMAT=<format>
   FILE=<file>`, chosen by `Cap.model_format` (set by `model_cap`, which
   replaced `Cap.after`), not one shape whose key holds `FORMAT=x FILE`.
4. The outcome after the semicolon stays free text (30 shapes in the suite);
   a closed outcome table is a wording PR.
5. Coded now: the sdist's config file over its cap (`CodedValueError`), a Git
   URL's checkout over `max_clone_bytes` (`git.too-large`) and a `git`
   call's output over its cap (`git.output-too-large`); `RemoteSourceError`
   gained `pitloom_code`, its `code` and text unchanged (and became
   copyable and picklable). Deferred: the three `fetch_json` raises (a URL's
   response or a file over the size cap, JSON over the nesting cap), since
   Croissant rewrites their text into its own (steps 4 and 8 rework that
   prefix for `over-cap`, `file-unreadable` and `network-failed` at once).
6. The evidence reason `over-cap` stays a literal in `core.evidence`, as
   `lfs-pointer` does: a reason is SBOM data, a code a stderr token that may
   gain variants. The drift test holds them equal.
7. The quote drift test reads a quoted line by its values (a value given has
   its field's shape; a free value never holds the family's marker), so the
   30 cap quotes in the docs and skills are checked.
8. Later PRs: the `max-source-metadata-bytes` truncation lines
   (`assemble/spdx3/provenance.py`: a user's budget, named by `spdxId`; a
   wording PR) and the lock-file `over N bytes` text (the detail of `Cannot
   read`; the lock-file PR).

Not `over-cap`: `git.too-many-redirects` (its advice is to give the final
URL), the build-timeout and `MAX_ID_NUMBER` ranges (invalid input). The
`Git source: <reason>` warning that repeats a Git URL's refusal before its
`ERROR:` stays uncoded: its prefix is no frame yet (step 6).

## The model-stub causes

Decided 2026-10-30 for #404 (PR 1a of row 1; the maintainer took the
recommendations D1 to D12 of its plan):

1. **Six codes, named by cause (D1, decision B)**: `library-missing`
   (`missing`), `reader-unsafe` (`unsafe`), `model-unreadable`
   (`unreadable`), `model-wrong-format` (`wrong-format`),
   `parameter-count-invalid` (`invalid`) and `hyperparameter-conflict`
   (`conflict`). A test holds every family to its condition, or a subject
   and `-<condition>`.
2. **`library-missing` owns its text (D2)**: `required library not
   installed: <module>; install pitloom[<extra>]`, the extra a closed field,
   never a bare `pip install <package>`; actor `user` (D3), since an extra
   changes the environment and runs native parsers on the files. It covers
   every optional library a step imports (`pitloom.core.optional_libraries`):
   the model readers, the Hugging Face Hub client, `spdx3-validate`, PyPA
   `build` and `magika`. `CodedImportError` stands beside `CodedValueError`,
   both copyable and picklable through one mixin. No field may share a name
   with a parameter of `emit` or of a coded exception (a field `extra` was
   swallowed by `emit`'s own; tested).
3. **One `model-unreadable`, no variant (D4)**: a reader's failure
   (`<error>`, free) and a bound check's (`<reason>`, a closed table of six
   texts the readers raise from `pitloom.messages`, D5; an AST test holds
   every `ModelLimitExceeded` raise to it).
4. **A closed field may repeat in a line (D6)**: `FORMAT=<format>
   FILE=<file>: header is not <format>; ...`; a free one may not.
5. **`read_ai_model()` refuses a file no reader reads as `not an AI model
   file of a supported format` (D7)**, the single-file commands' words, not
   "Unsupported model format ... Supported extensions": one code,
   `model-wrong-format`, on every surface; its effect is `thinner` (D8).
6. **A model reader's raise is detail (D9, decision J)**: a raise in
   `extract/ai_model/` but the dispatch `reader.py` is out of the ratchet by
   where it is, since only the scanner calls the dispatch and only the
   dispatch names a reader (both tested): 25 sites. With 15 sites coded, the
   ratchet fell from 556 to 516 (172 to 163 modules).
7. **Row 1 is split (D10)**: PR 1a is this one (the 18 covered sites and the
   detail rule); PR 1b, also 0.22.0, takes the 27 sites of model fields read
   in part (`model-field-unreadable`, `model-field-conflict`,
   `model-field-invalid`, `field-not-recordable`; fickling's own stderr
   stays a relay). Six sites move: `git.not-found` and the interpreter to
   PRs 13 and 14, poetry-core's "API not found" (installed, its API moved:
   `unusable`) to PR 12, and the model command's URL, the project's Hub
   model and the usage hint (actor `caller`) to PR 3. The migration plan's
   row 1 follows once it is merged.
8. **The generated catalogue has its own page (D11)**:
   `docs/message-codes.md`; `docs/messages.md` keeps the grammar, the
   guarantees and the trust rule. The generator writes it, both skills'
   `references/messages.md` and, behind a second marker, the model table of
   `model-stub-diagnosis.md` (what each code leaves of a model; tested
   complete).
9. **Parked (D12)**: the stub's cause in the SBOM (`Reason:` on a
   format-only entry). No field carries it; it needs three more reason
   codes, a carrier on `AiModelMetadata`, merge semantics and edits to the
   frozen scan-limits page. After 0.22.0.

Left open: the `Build:` warning reporting a missing PyPA `build` keeps no
code, its prefix being no frame (step 6); an import that is found but fails
is reported as not installed, as before (the readers raise
`missing_library()` from any `ImportError`); `hyperparameter-conflict` is
the first entry whose actor and effect are `none`.

## The unreadable files and directories

Decided 2026-10-30 for #408 (PR 2a of row 2; the maintainer took the
plan's recommendations, PR 2a then 2b):

1. **Two families**: `file-unreadable` (`unreadable`), with the variants
   `file-unreadable/not-utf8` and `file-unreadable/outside-project`, whose
   advice differs (decision D), and `dir-unlistable` (`unlistable`). The
   codes equal the evidence reasons, which PR-D now writes for a `loom`
   dataset (`_loom_dataset_keys.digest_evidence` reads any reason).
2. **The exception picks the entry**: `warn_file_unreadable` and
   `warn_dir_unlistable` (named after `warn_over_cap`; the plan's
   `say_unread` is taken by the scanner's model-stub helper) take the
   exception, never a text: `OutsideRootError` is `/outside-project`, a
   `UnicodeDecodeError` `/not-utf8`. An absent path raises `InternalError`:
   absent is quiet, so every caller asks `is_missing_errno` first, and a
   file gone since it was found now says nothing (a dataset member, a
   registry file, a usage source).
3. **New fields**: `use` (a closed table, `READ_USES`; a test holds every
   call's `use=` to it, and each use live), `field` (a project setting),
   `dir` (written as `file`) and `failure`, which writes an `OSError`'s
   `strerror` and never its text: the raw-exception bug (an absolute path,
   `[Errno 13] ... '/home/...'`) is fixed at every site by construction,
   and `dir`'s escaping ends a newline-forged line.
4. **Text kept but the detail** ("code first, wording later"): the
   not-UTF-8 lines of a `setup.cfg` directive and of the usage scan gain
   the variant's `not UTF-8:` prefix; the model hash's `(no verifiedUsing,
   registry lookup not gated)` moved to the entry's `did`; a licence file
   is named relative to its project (a dependency's by its `RECORD` entry).
5. **Not this family, uncoded**: a listed requirements file not found and
   a name an ID registry cannot hold (each on a line of its own, allowed
   by name in `tests/messages/test_file_unreadable.py`), the `setup.cfg`
   parser's `RecursionError` (reworded), a lock file refused or unparsable,
   a wheel member, and the ID registry's explicit `PATH` error, whose
   `ERROR` form waits for the registry PRs (no `ERROR` line is catalogued
   before a site prints one).
6. **The ratchet counts a catalogue helper's calls**: a function of
   `pitloom.messages` that says its message through `emit` codes each
   caller (the inventory's second round), as `warn_over_cap` does by name.
   511 to 498 uncoded sites, 160 to 155 modules.

Left for PR 2b: the cards (`card-malformed`, the card read joining
`file-unreadable`, `find_card_file`'s silent listing), `fetch_json` (its
local read, and `over-cap` for its caps, with Croissant passing a code
through) and the lone-surrogate warning (`text-malformed`, effect `weaker`
by the maintainer's ruling).

## The `AGENTS.md` rule

Added with #390 ("CLI output"): the catalogue is the contract; a message is
said through `pitloom.messages`, its code rides on the record and on any
exception as `pitloom_code`, and a message, the catalogue, the generated
reference and what a skill quotes change together.

## Risks

- A message rewrite breaks tests that pin wording. Touch a family at a time.
- The grammar test is only as good as the extraction: start with the shared
  helpers, then the free-text sites.
- The families are rule-based over a static extraction and raise reach is a
  heuristic: build the ratchet on lines the tests produce.
- One condition prints in several shapes by surface; the code must travel on
  exceptions or it is lost on two of three surfaces.
- Moving text to references can make a rule unread. Safety and fallbacks stay in
  the body; recipes are run before and after.
