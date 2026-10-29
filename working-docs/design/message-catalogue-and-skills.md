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

Status: proposed 2026-10-29; the four decisions at the end are open.

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
  advice differs by source (`run 'git lfs pull'` for a directory, `clone with git
  lfs` for a Git URL).
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

1. **Inventory (read-only).** Extract every message template by AST and classify
   it: level, subject key, condition, advice, helper. Output: a draft catalogue
   and a list of outliers (second tags, untagged continuation lines, differing
   separators, wrapper wording).
2. **Grammar, written down and ratcheted.** Shape:
   `LEVEL: [SUBJECT=value: ]CONDITION[ (detail)][; ACTION]`, advice always after
   the semicolon. A grammar test fails any new message that breaks it; existing
   outliers sit in an allow-list that only shrinks (as licenseid's
   `check_diagnostic_grammar` does).
3. **One helper per family** wherever a pattern is hand-copied at three or more
   sites (extends the over-cap helper).
4. **A closed condition vocabulary for new and touched messages only**
   (`lfs-pointer`, `over-cap`, `not-a-model`); no rewrite of existing text.
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

## Order

| Step | Work | Agent |
| - | - | - |
| 0 | Finish #378, then the ceilings PR | in progress |
| 1 | Inventory and outlier report (read-only); **queued after #378** | Sonnet extract, Opus classify |
| 2 | Skill size PR: move detail to references, conditional pointers | Sonnet, Opus review |
| 3 | Catalogue, grammar ratchet, generated reference, drift test | Opus design, Sonnet |
| 4 | Fix outliers family by family, smallest first | Sonnet |
| 5 | Optional `--report`, scenario checks | decide after step 3 |

Steps 1 and 2 are independent. Compatibility is not a constraint (alpha).

## Open decisions

Recommended answers in brackets; none is decided.

1. Do new messages carry a stable condition token in the printed line? [yes,
   new and touched messages only]
2. Is `--report` wanted? [later]
3. Is the body target of 16 to 18 KB right? [yes]
4. Does the catalogue live in code and generate the docs? [yes, code is the
   source of truth]

## Risks

- A message rewrite breaks tests that pin wording. Touch a family at a time.
- The grammar test is only as good as the extraction: start with the shared
  helpers, then the free-text sites.
- Moving text to references can make a rule unread. Safety and fallbacks stay in
  the body; recipes are run before and after.
