---
Created: 2026-10-29
Last-Modified: 2026-10-29
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
the plumbing, schema and ratchet, is #390 (in review).

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
2. `over-cap` (36 sites, 8 edit points; `warn_over_cap` moves into
   `pitloom.messages` with it).
3. The model-stub causes in `extract/scanner.py`: `model-unreadable`,
   `library-missing`, `model-gated`, `not-a-model` (condition
   `wrong-format`).
4. `file-unreadable` and `dir-unlistable`, paired with the evidence reasons of
   the same names.
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
  prints nothing new, since the line has no code yet.
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
