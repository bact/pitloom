---
Created: 2026-09-18
Last-Modified: 2026-09-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Skill trigger coverage

See also: [roadmap.md](../design/roadmap.md) (the deferred items below),
[recurring-bug-patterns.md](recurring-bug-patterns.md).

Record of a 2026-09-18 audit of `skills/sbom-{generate,enrich,validate}/
SKILL.md` (shipped in 0.18.1, PR #223): does every CLI function have
trigger phrasing, and can the skills tell similar asks apart?

## How skills are discovered (the non-obvious part)

Only the frontmatter `description` decides whether a skill fires. A body
section that documents a command (e.g. `loom merge` under "Explicit Target
Subcommands") does not make it discoverable. The skills have no tests, so
drift is silent.

## Audit method

1. List CLI subcommands: `grep -rn "add_parser(" src/pitloom/cli/`.
2. For each, check a trigger phrasing exists in some skill's `description`.
3. Verify every flag and default a skill states against `cli/parser.py`,
   `cli/options.py`, `core/_config_parse.py` (e.g. `enrich`=off,
   `extract-file-header`=on, `use-lockfile`=on, `content-type`=off).
4. Verify every cross-referenced section heading and `references/*.md`
   file exists.
5. Ask "if the user says X, which skill fires?" for realistic phrasings,
   including ungrammatical ones (the maintainer is not a native English
   speaker, and so are many users: "is this wheel has an SBOM").

## Decisions

- **Wheel-embedded SBOM checks.** Pitloom's CLI splits *verify*
  (`verify-wheel`: present at the PEP 770 location, extension, name/version
  match) from *validate* (`validate-wheel`: schema + SHACL). Users treat
  the words as synonyms, so `sbom-validate` runs **both** (verify first) for
  a validity ask. A presence-only ask ("is SBOM in the correct location",
  "does this wheel have an SBOM") runs `verify-wheel` alone and must ask a
  follow-up, because presence says nothing about whether the JSON is
  well-formed or valid SPDX 3. In a non-interactive run: report presence,
  state that content was not checked, and do not silently run
  `validate-wheel` either.
- **Generate + named standard.** "Give me an SBOM with CISA 2026 minimum
  elements" spans two skills. `sbom-generate` gains "Combine with a named
  standard" (generate with `--enrich`, hand off to `sbom-enrich`'s minimum-
  elements workflow, which ends in the mandatory `sbom-validate` pass);
  `sbom-enrich`'s description points back. Neither skill alone covered it.
- **Loom ID registry.** Skills must understand the concept, not run the
  commands: `project`/`wheel`/`env` auto-harvest ids, so ids stay stable
  across reruns and fragments keep merging; a `--id-registry` mismatch between
  the base-SBOM run and an enrichment run is a second cause of dangling
  fragment references (besides a Pitloom upgrade changing file discovery).

## Deferred (need design; tracked in the roadmap)

`loom id generate`, `loom id import`, `loom merge`, `loom fragment list`
have no trigger phrasing. Open questions: which skill owns them, and which
phrasings separate "pin ids before a first run" from "import ids from an
SBOM" without colliding with plain generate/enrich asks.

Possible drift guard (not built): a test asserting every CLI subcommand
name appears in some `skills/*/SKILL.md` description, with an explicit
allowlist for the deferred commands above.
