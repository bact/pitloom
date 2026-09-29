---
Created: 2026-09-18
Last-Modified: 2026-09-29
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
  elements" spans two skills. `sbom-generate` gains "Combine with enrichment
  or a named standard" (generate with `--enrich`, hand off to `sbom-enrich`'s
  minimum-elements workflow, which ends in the mandatory `sbom-validate`
  pass); `sbom-enrich`'s description points back. Neither skill alone
  covered it.
- **Loom ID registry (revised 2026-09-29, PR #235).** The first decision
  (skills explain the concept, never run the commands) is superseded: the
  skills now run `loom id generate`/`loom id import` to create a registry
  the user asked for. Kept from it: a registry is used only when declared
  (`--id-registry`, a project's own `id-registry` key, or a `--config`
  key), nothing is auto-discovered, and a skill never creates, edits or
  passes one the user did not name (non-interactive: use none and report
  the `loom id generate` command). Element ids are content-addressed, so
  a registry matters only to pin ids across runs whose inputs differ (a
  fragment merged after the source changed). Once declared, `project`
  (directory or sdist), `wheel`, `env` and `generate` write newly minted
  ids back; `model`, `enrich`, `embed-wheel`, `wheel --embed` and the
  Hatchling hook only read it. A different or missing declaration between
  the base run and an enrichment run is a cause of dangling fragment
  references (besides a Pitloom upgrade changing file discovery). The
  detail lives in `skills/sbom-generate/references/id-registry.md`.
- **Description length (2026-09-29).** The Agent Skills limit is 1024
  characters; the three descriptions were 2072, 1736 and 1598, and this
  harness's skill listing cut each at about 1535, silently dropping the
  wheel-embedding and `--allow-build` triggers (generate), the hand-off
  clause to `sbom-generate` (enrich) and the closing "`@graph` check is
  not a substitute" sentence (validate). Now 951, 987 and 976. Every "see
  X below" pointer was dropped (routing ignores it), near-duplicate
  phrasings were merged ("embed SBOM to the wheel" / "...to python
  wheel"), and the hand-off clauses and the verify-vs-validate split sit
  early. Phrasings no longer literally present (compared against the
  pre-change text; slash-merged forms such as "generate/create/give me an
  SBOM/BOM" count as kept): generate -- "get an SBOM for `<artifact>`",
  "can we have SBOM of this project", "list this project's dependency
  inventory", "create an SBOM and fill in information as much as
  possible", "embed SBOM to the wheel", "put the SBOM in the wheel", "add
  the SBOM to dist/*.whl", "create SBOM in the wheel", "limit the build to
  30 minutes", "how long should the build timeout be", "use
  --allow-build"; enrich -- "get more info into the SBOM", "fill in
  information to the SBOM", "make the SBOM comply with CISA", "SBOM
  minimum elements checklist", the G7 AIBOM phrasing ("make this AIBOM
  meet the G7 SBOM for AI minimum elements"); validate -- "check this
  SBOM's SPDX conformance", "validate the SBOM in this wheel", "is the
  SBOM inside this wheel valid", "check if wheel SBOM is valid", "is this
  wheel has an SBOM", "does this wheel have a SBOM". Restored after
  review, as room allowed: "check this SBOM against NTIA/CISA minimum
  elements" (enrich), "is it a valid SBOM", "validate wheel SBOM", "check
  if the wheel has an SBOM" (validate). The
  `--allow-build`/`--build-timeout` triggers survive as one clause.
- **Long topics move to `references/`.** `sbom-generate`'s lock-file and ID
  registry detail (what a registry pins, creating one, which log lines are
  expected) moved to `references/lockfile-discovery.md` and
  `references/id-registry.md`, keeping the declared-only rule, the
  ask-or-fall-back-to-none step and the hard rules in `SKILL.md`, which was
  514 lines and is now about 410.

## Deferred (need design; tracked in the roadmap)

`loom id generate`, `loom id import`, `loom merge`, `loom fragment list`
have no trigger phrasing (the skills do run the two `id` commands once a
registry is asked for; only the description triggers are missing). Open
questions: which skill owns them, and which phrasings separate "pin ids
before a first run" from "import ids from an SBOM" without colliding with
plain generate/enrich asks.

Possible drift guard (not built): a test asserting every CLI subcommand
name appears in some `skills/*/SKILL.md` description, with an explicit
allowlist for the deferred commands above.
