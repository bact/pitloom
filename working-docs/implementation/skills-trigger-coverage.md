---
Created: 2026-09-18
Last-Modified: 2026-10-28
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
- **Id-management triggers (2026-10-15, registry v3, PR #305).** User
  decision: when the user asks to pin ids or to create or update an ID
  registry, the agent runs `loom id generate`/`loom id import` itself and
  reports the command; the "never pass a registry the user did not name"
  rule stays for unasked runs. `sbom-generate`'s description gained "pin
  ids", "keep ids stable", "create or update an ID registry" and "loom id
  generate/import" and went from 1021 to 1008 of 1024 characters (YAML
  parsed): "gen SBOM" stayed, "SBOM of this project", "create PEP 770
  SBOM", "embed SBOM to python wheel", "wheel is signed / has RECORD.jws"
  (now "signed wheel / RECORD.jws") and the "owns combined asks, generating
  first" wording were trimmed or shortened. A v2 registry file now fails
  with an `ERROR:`; the skill relays it and deletes the file only if the
  user agrees (non-interactive: change nothing).
- **Five standards (2026-10-18).** User decision: the skills name every
  standard the pinned `ntia-conformance-checker` checks on SPDX 3: NTIA 2021
  (`ntia`), FSCT 2024 (`fsct3`), CISA 2026 (`cisa2026`), G7 SBOM for AI 2026
  (`g7ai`) and BSI TR-03183-2 v2.1 (`bsi`). New trigger phrasings:

  | Skill | Phrasing added | Covers |
  | :--- | :--- | :--- |
  | enrich | standard list "NTIA 2021, FSCT 2024, CISA 2026, G7 SBOM for AI 2026, BSI TR-03183-2" | all five by name |
  | enrich | "is this SBOM CISA 2026/FSCT compliant" | FSCT, CISA 2026 |
  | enrich | "does it meet BSI TR-03183" | BSI |
  | enrich | "check this SBOM against NTIA/CISA/G7 AI" | NTIA, CISA, G7 |
  | enrich | "make this SBOM meet NTIA minimum elements" | NTIA |
  | generate | "SBOM meeting NTIA/FSCT/CISA 2026/G7/BSI minimum elements" | combined ask, all five |
  | validate | "Not for NTIA, FSCT, CISA 2026, G7 AI or BSI completeness (sbom-enrich)" | routing away from validate |

  Lengths (YAML parsed, of 1024): enrich 987 to 1005, generate 1008 to
  1017, validate 976 to 999. Phrasings no longer literally present in
  enrich: "make this SBOM meet NTIA standard" (now "...NTIA minimum
  elements"), "what's missing for CISA/NTIA compliance" (now "what's
  missing for compliance"), "check this SBOM against NTIA/CISA minimum
  elements" (now "...NTIA/CISA/G7 AI"); "complete the minimum elements" and
  "help filling minimum elements" are kept as "complete/help filling the
  minimum elements". The `sbom-generate` hand-off table row names all five;
  its body is 24,554 of the 24 KiB ratchet (the duplicate "`loom` and
  `pitloom` are one console-script entry point" line was dropped to fit), so
  its next addition must move text to `references/` first. Verify (structural)
  vs validate (schema/SHACL) stays in `sbom-validate`'s description; its body
  now says a named-standard completeness ask is `sbom-enrich`'s. No CLI
  subcommand changed (`add_parser(` list as before). Each element's SPDX 3
  field, what Pitloom fills and whether the checker checks it:
  `skills/sbom-enrich/references/minimum-elements.md`; the checker recipe
  (install pointer to the user page "G7 SBOM for AI", so the pinned commit
  lives in `pyproject.toml` and that page only; `sbomcheck -c <id>`; reading
  `ruleResults`; what to do per `missing` rule; a non-interactive fallback
  that installs nothing) is in `minimum-elements-workflow.md`. Every recipe
  was run on 2026-10-18 (Pitloom 0.20.2, checker `34c00ba`): `loom model` on
  the ONNX, Safetensors and GGUF fixtures and `loom generate` on a small
  Hatchling project and the `uv/flask-3.1.3` lock fixture, each through all
  five `-c` ids; the `missing`-rule one-liner prints nothing on a report with
  no missing rule. Findings recorded there: the checker has no `table`
  report (`-r print` is the text table); exit 0 is conformant, 1 not; BSI
  declared no `reach_via` at checker `34c00ba`, so `bsi` did not judge a
  dataset linked only by `trainedOn` (superseded: every standard follows
  `trainedOn`/`testedOn` by default since `151460c`); a fragment adding
  `hasConcludedLicense`, a `dependsOn` to `NoneElement` with `completeness`,
  a distribution `software_File` with SHA-512 and `hasDistributionArtifact`,
  and `software_additionalPurpose` `container` took the test project to
  conformant under `fsct3` and `bsi` (validated with `loom fragment
  validate`).
- **Sweep (2026-10-19, after #309 and #310).** No subcommand changed
  (`add_parser(` lists `generate`, `project`, `wheel`, `embed-wheel`,
  `verify-wheel`, `validate-wheel`, `model`, `enrich`, `env`, `merge`,
  `fragment` (`validate`, `list`) and `id` (`generate`, `import`); each has
  trigger phrasing except `merge` and `fragment list`, see "Deferred"). Run on a small Hatchling project, a built wheel and the
  `gpt2-tiny-decoder.onnx` fixture, Pitloom 0.20.2, checker `82a63b9`: `loom
  generate`/`project`/`model`/`env`, `loom generate --enrich`, `loom
  generate FILE` without `-o` (an `ERROR:`), `verify-wheel` before and after
  `embed-wheel --verify --validate`, `validate-wheel`, `loom fragment
  validate` on a valid and on a broken document (`ERROR:` lines on stderr), the
  standalone `spdx3-validate --json` (report on stdout, only the header line
  `ERROR:`-tagged), `sbomcheck -s spdx3 -c` each of `ntia`, `fsct3`,
  `cisa2026`, `g7ai`, `bsi` with `-r json` (exit 1 not conformant) and `g7ai`
  also with `sarif`, `html` and `print` (the last two list no `out-of-scope`
  rule), and the
  `missing`-rule one-liner (it lists the rules of each report and prints
  nothing on a report edited to have none). The checker pin is the same in
  `pyproject.toml` and `docs/g7-sbom-for-ai.md`; the skills name none. The cross-check recipe
  now points at Lumina (a web UI for the same results).
- **Release sweep (2026-10-28, 0.21.0, after #359 and #360).** No
  subcommand changed (`loom --help` and `add_parser(` list the same twelve,
  with `fragment validate`/`list` and `id generate`/`import`); every one has
  trigger phrasing except `merge` and `fragment list` (still "Deferred").
  Descriptions unchanged (generate 1018, enrich 1005, validate 999 of 1024):
  no new command or ask needed a phrasing. Every subcommand's `--help` was
  diffed against the skills: `--describe-relationship`,
  `--max-source-metadata-bytes`, `--no-build-isolation` and `--project-dir` on
  `wheel`/`project <sdist>` (registry keying) were in no `SKILL.md` body and
  now are, one line each; `id generate --namespace` was already in
  `id-registry.md`. Run on a scratch Hatchling project (licence `Apache2`, an
  extra, a `LICENSE` copyright line), its built wheel, the
  `real-world-locks/uv/fastapi-cli-0.0.32` fixture, the ONNX, Safetensors and
  GGUF model fixtures and a project shipping a Safetensors model with a
  frontmatter README, all `--offline --creation-datetime
  2026-01-01T00:00:00Z`, Pitloom 0.21.0, checker `2355afc`: `project`
  (default name), `generate` without `-o` (exit 1), `wheel`, `env`, `model`,
  `id generate` (with `-e`, `--namespace`, `-o -`, a missing `PATH`), `id
  import --project-dir`, `project --id-registry`, `verify-wheel` before and
  after `embed-wheel --project-dir --verify --validate`, `validate-wheel`,
  `wheel --embed`, `embed-wheel --sbom`, `--sbom-basename foo.spdx3.json`,
  `--output` with two wheels, a non-ZIP wheel, the signature `unzip` check,
  the whole `sbom-enrich` recipe (`loom enrich --project-dir`, the agent
  fragment, the pre-merge deserialiser one-liner, registration, re-run,
  `loom fragment validate`), `loom fragment list`, `loom merge`, every
  `spdx3-validate` recipe, and `sbomcheck -s spdx3` with all five `-c` ids
  and every `-r` type. Legitimate-input checks: the `missing`-rule one-liner
  prints nothing on a report with no missing rule; the stale-`ai_AIPackage`
  one-liner printed a blank line on a clean fragment (now a list
  comprehension: nothing) and the stale id on a stale one; the `RECORD.`
  `unzip` check exits 1 on an unsigned wheel. Fixed from the runs: the
  `licenseid update` requirement (`Requirements`, with `uvx --from
  "licenseid>=0.6.0"` and `--source packaged`, both run) and the resolver's
  provenance keys (`Method: licenseid_resolution`, `Resolution-1`,
  `Expansion-1`, `Tool`; a classifier's `INFO:` has no `FIELD=`); a base
  `ai_hyperparameter` entry beats a fragment's with a `WARNING: Merge:
  conflicting ...` since #357, not silently (`examples.md`,
  `minimum-elements.md`); `embed-wheel --verify --validate` prints nothing on
  a pass and embeds before it fails; `validate-wheel`'s `ERROR:` lines name a
  temporary copy, not the wheel; `sbomcheck` exits 2 on an unknown `-c`/`-m`
  and only `fsct3` takes `-m 1`/`2`; the `INFO: ... no SPDX 3.0.1 property:
  model-architecture (written in ai_typeOfModel)` line is expected. Checker
  stamps say `2355afc` where the repository's expected tables were
  regenerated unchanged (#360; `tests/conformance` passes on this tree).
  `sbom-generate`'s body is 24,556 of the 24,576-byte ratchet after the
  name/label-cap wording, the wheel-refusal detail and the AGENTS.md link
  moved behind `references/known-limitations.md` pointers; `sbom-enrich`'s is
  24,553, unchanged: the next addition to either must move text first. The
  plugin manifest is 0.21.0 (`scripts/check_version_consistency.py` OK); its
  and the marketplace's description now name wheels, Git URLs and the five
  standards; `claude plugin validate` passes with one warning (no icon). The
  plugin ships no `hooks/`, `commands/` or `agents/` and references none.
- **Long topics move to `references/`.** `sbom-generate`'s lock-file and ID
  registry detail (what a registry pins, creating one, which log lines are
  expected) moved to `references/lockfile-discovery.md` and
  `references/id-registry.md`, keeping the declared-only rule, the
  ask-or-fall-back-to-none step and the hard rules in `SKILL.md`, which was
  514 lines and is now about 410.

## Portability across clients (2026-09-29, PR #235)

Review against the Agent Skills specification (agentskills.io) and other
clients (Codex, Gemini CLI, GitHub Copilot / VS Code, claude.ai). Decisions:

- **No `argument-hint`.** It is a Claude Code extension outside the
  specification (allowed keys: `name`, `description`, `license`,
  `compatibility`, `metadata`, `allowed-tools`); claude.ai and Skills API
  upload and `skills-ref validate` reject it. Cost: no placeholder in the
  Claude Code palette. Each body says what argument it takes.
- **`compatibility` declared** (at most 500 characters), tailored per skill:
  shell, Python 3.10+, `pitloom >= 0.20.0` by pip/`uvx`/`pipx`, the extras
  each needs (`ai`, `validate`, `build`, `content-type`), network, and "not
  usable where packages cannot be installed" (e.g. Claude API code
  execution).
- **Version floor: 0.20.0** (raised to 0.20.2, then to 0.21.0 for registry
  format 3 and Git URL targets; every `compatibility`, Requirements section
  and example under `skills/` and `docs/` reads `>=0.21.0`, checked
  2026-10-28). The skills use `--id-registry`,
  `--update-id-registry`, `loom id ...` and `--build-timeout`, absent from
  0.19.0 (PR #235 ships in 0.20.0). The floor appears in each
  `compatibility`, each Requirements section, `docs/agent-skills.md` and
  every `uvx --from`/`pipx run --spec`/`pip install` example
  (`"pitloom>=0.20.0"`, extras `"pitloom[validate]>=0.20.0"`). It must move
  with any later breaking CLI change the skills rely on: grep
  `>=0.20.0` under `skills/` and `docs/`. `uvx --from` fetches the newest
  matching release, not the user's installed `loom`; `sbom-generate` says
  to pin `pitloom==X.Y.Z` (the number `loom --version` prints) where ids
  must reproduce. Not automated: `scripts/check_version_consistency.py`
  checks only structured version fields, and could also assert the
  skills' floor is at most `__about__.__version__` (it would fail until
  the release bump lands).
- **Install paths.** `docs/agent-skills.md` leads with `.agents/skills`
  (project) and `~/.agents/skills` (user); `.claude/skills` stays for
  Claude Code and the Agent SDK; a table lists Codex, Gemini CLI and Copilot
  folders; claude.ai takes a zipped skill folder. The three skills are
  installed together: they cross-refer to each other's sections, and
  `id-registry.md` lives only in `sbom-generate` (each intro says so; a
  GitHub URL is the fallback).
- **Pre-merge fragment check.** The `spdx_python_model` snippet fails under
  `uvx`/`pipx` installs and on Windows. It is now one line (no multi-line
  `-c`), lives only in `sbom-enrich`'s step 7, and is run with Pitloom's
  own interpreter: `uvx --from "pitloom>=0.20.0" python -c ...` or
  `pipx run --spec "pitloom>=0.20.0" python -c ...` (both run from a
  scratch project: exit 0, no `.venv`/`uv.lock` written).
  `uv run --with pitloom python` was dropped: in a project directory it
  creates `.venv` and `uv.lock` and builds the project (build-backend
  code, against the `--allow-build` hard rule; the new `uv.lock` then
  feeds lock-file discovery). `uv run --no-project --with ...` is safe but
  redundant. The bare-`pipx install` venv path is right only after
  `pipx install`, not after `pipx run` (hashed cache venv).
  `references/examples.md` points there. The deserialiser check catches
  malformed JSON, an unknown property on a known type, a wrongly typed
  value, a missing `spdxId` and a misspelled type carrying properties; a
  bare unrecognised type with no other key, not even `spdxId`, passes
  (extensible object),
  and a missing required property is left to the SHACL post-merge check.
  Snippets are POSIX shell; each skill says so in `SKILL.md` and in its
  `references/examples.md`.
- **Invocation syntax** (`/sbom-*`) differs by client (`$sbom-*` in Codex);
  one clause says so, occurrences were not rewritten.
- **Size.** Bodies above the recommended ~5,000 tokens moved detail to
  `references/` (whole-file sizes): `sbom-generate` 21.1 KB to 20.3 KB
  (`known-limitations.md`), `sbom-enrich` 23.4 KB to 20.8 KB (`dangling-references.md`,
  `deterministic-pass.md`, `minimum-elements-workflow.md`). Hard rules,
  step lists and fallbacks stay in the body; each reference holds only
  what the body omits (why, extra detail) and points back to the rule, so
  no fact lives in two places.
- **Internal links.** No shipped skill file points into `working-docs/`;
  public `bact.github.io/pitloom` pages replace them.
- **Guard.** `tests/test_skill_frontmatter.py` checks per skill: frontmatter
  keys, `name`, `description`, `compatibility`, body size (at most 500
  lines, the specification's number, and a 24 KiB byte ratchet towards
  ~20 KB), markdown links, skill files named in code spans (all current
  references are spans, so a link check alone passes vacuously; the
  sibling-skill `id-registry.md` mention resolves against `sbom-generate`),
  one-level `references/`, and no orphan reference. Descriptions were not
  touched (951, 987, 976 of 1024).

## Deferred (need design; tracked in the roadmap)

`loom merge` and `loom fragment list` have no trigger phrasing. `loom id
generate` and `loom id import` gained theirs in `sbom-generate` on
2026-10-15 (see above). Open questions: which skill owns the rest, and which
phrasings separate "pin ids before a first run" from "import ids from an
SBOM" without colliding with plain generate/enrich asks.

Possible drift guard (not built): a test asserting every CLI subcommand
name appears in some `skills/*/SKILL.md` description, with an explicit
allowlist for the commands above that still have no trigger.
