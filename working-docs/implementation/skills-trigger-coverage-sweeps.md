---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Skill trigger coverage: drift sweeps

See also: [skills-trigger-coverage.md](skills-trigger-coverage.md)
(how skills are discovered, the audit method and the standing
decisions; read it first), [agent-skill.md](agent-skill.md).

Each entry records a drift sweep of the three `SKILL.md` descriptions after
a CLI or release change, with what changed. Split out of the Decisions
list for size.

## Sweeps after a CLI change (2026-10-19 to 2026-11-16)

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
- **Usage-scan trigger (2026-11-02, PR #413).** A drift check found no
  phrasing for `--scan-model-usage` ("which files use this model") in any
  description. `sbom-generate` gained "the usage scan (\"which files use this
  model\")" and went from 1018 to 1015 of 1024 characters (YAML parsed).
  Room came from dropping "SPDX 3 document" (the same asks name an SBOM) and
  the bare "embed-wheel" (wheel embedding keeps its natural-language
  phrasings), and from shortening the hand-off sentence to "Checking:
  sbom-validate; enriching: sbom-enrich." "keep ids stable" and "loom id
  generate/import" stay (decision of 2026-10-15). `--no-scan-model-usage` has
  no phrasing of its own: the body line in `SKILL.md` covers it once the skill
  is open.

- **Model from a Git URL (2026-11-09).** No subcommand was added
  (`add_parser(` lists the same twelve; `loom model`'s, `loom project`'s and
  `loom generate`'s `--help` changed). `loom model <url>` now takes a Git URL
  and `loom generate <url>` picks a project or a model by what the URL names,
  so `sbom-generate`'s description names "Git URL (repo, folder or model file
  page)" (1020 of 1024 characters, YAML parsed; the room came from dropping
  "branch/" and "or"). The body gained three lines and the rest moved to
  `references/git-url.md` (the body ratchet is 16 KB: 16,078 bytes before,
  under 16,384 after). `loom project` stays project-only, so its refusal of a
  folder with models and no project names `loom model <url>` and `loom
  generate <url>`; the skill relays that, and a folder with several models
  (`model-ambiguous`) is a follow-up question with a non-interactive fallback
  (report the list, never pick a file). `[reader-unsafe/remote]` is relayed,
  never acted on: the skill does not clone unasked. The verify/validate split
  is unchanged. Legitimate-input checks not run (no skill test exists): the
  recipes in `references/examples.md` were checked against `loom model
  --help`, and the local ones (`loom model DIR`, `loom generate FILE.dat`)
  were run on the GGUF fixture.

- **PyPI URL targets (2026-11-10, PR #468).** No subcommand was added
  (`add_parser(` lists the same twelve); `loom wheel`, `loom project` and
  `loom generate` take a `https://pypi.org/project/<name>/[<version>/]` URL
  and `loom model` refuses one. `sbom-generate`'s description already named a
  "PyPI URL"; it now reads "PyPI URL (wheel/sdist)" so that "SBOM for
  https://pypi.org/project/requests/", "SBOM of the requests wheel from PyPI"
  and "sdist SBOM from PyPI" match on both words (1012 to 1021 of 1024
  characters, YAML parsed; the room came from "model file page" to "model
  page"). Its `compatibility` says 0.24.0 for a PyPI URL (the rest stays
  0.23.4: the floor of the other targets), and the body keeps 16,376 of the
  16,384-byte ratchet by holding one paragraph and moving the rest to
  `references/pypi-url.md` (refusals, the pick, over-cap, how to read the
  provenance record, follow-ups and the combined asks) and a recipe in
  `references/examples.md`. `sbom-enrich` (1005) and `sbom-validate` (999)
  descriptions are unchanged: the asks "enrich/validate the SBOM of
  <pypi-url>" with no file are `sbom-generate`'s to start (it hands off), and
  a file is a file. Their bodies gained a paragraph each (enrich: a PyPI base
  is an "other base", so no merge, no `--enrich`, outside sources gated; plus
  `references/pypi-url-base.md`; validate: an ordinary document, the record is
  nothing to fix, `verify-wheel`/`validate-wheel`/`embed-wheel` take a local
  `.whl` only). Hand-offs both ways are in `pypi-url.md` ("Follow-ups") with a
  non-interactive fallback for each question (which platform, the sdist after
  `[release-file-not-found...]`, relying on a yanked release, raising
  `--max-download-bytes`: report the line and the command, run nothing). The
  platform-dependent pick is stated in the body, the reference and the enrich
  reference. Drift found in the first draft of the skill reference and fixed:
  a sentence that read as if `files.pythonhosted.org` file links were refused
  as PyPI URLs (0.23.4 and earlier took them for Git and failed; the tree
  refuses them as `pypi-url-invalid`), and the
  provenance record described without where it lives (an `Annotation` plus
  the `Metadata provenance:` comment). Checked on 2026-11-10 against the tree:
  `loom wheel|project|generate` with `--offline`, `--embed`, `--allow-build`,
  `--allow-signed-wheel`, a `test.pypi.org` URL, an `http` URL, a user page
  and `--max-download-bytes 0`; `loom model <url>`; `verify-wheel`,
  `validate-wheel`, `embed-wheel`, `merge` and `enrich` given the URL (each a
  plain "not found"-style `ERROR:`); an SBOM made from a local server standing
  in for PyPI passed `loom fragment validate` (the legitimate input on which
  the validate paragraph must do nothing). The live download was later run
  for real: `loom wheel` and `loom project` on `six` 1.16.0, and the
  network-marked manual matrix cells (PyPI and a pinned GitHub tag), all
  passing.
  *Revised later on 2026-11-10 (after the #469/#470 merge):* a downloaded
  wheel's gated models now say `[reader-unsafe/remote]` (its PyPI line names
  the file), `--trust-model-files` lifts it, and a Git URL's fetch shares
  `--max-download-bytes` (512 MiB). No description or `SKILL.md` body changed
  (the asks are the same; `sbom-generate`'s body stays at 16,376 bytes); the
  references carry it: `pypi-url.md`, `git-url.md`, `cli-flags.md`,
  `known-limitations.md` and `sbom-enrich`'s `pypi-url-base.md`.
- **URL credential refusal (2026-11-16, credentials PR 2).** No subcommand
  was added; every generating command and `merge` gained
  `--accept-url-credential` and `--allow-url-credentials`, and an SBOM
  whose URL field holds a credential now fails (`[credentials-unsafe/refused]`,
  exit 1, no SBOM). A user meets it mid-run or pastes it from a build hook
  failure in CI, so `sbom-generate`'s description gained `"holds a
  credential" errors` (1021 to 1023 of 1024 characters, YAML parsed; the room
  came from dropping "; enriching: sbom-enrich", which the earlier "Combined
  asks (hand off to sbom-enrich)" and `sbom-enrich`'s own description already
  cover). `sbom-enrich` and `sbom-validate` descriptions are unchanged (the
  refusal is not an enrichment or a validity question; `loom fragment
  validate` does not check credentials). Body: four lines in `sbom-generate`'s
  "Check stderr" (16,332 of 16,384 bytes) carrying the two rules a move must
  not lose (never suggest `--allow-url-credentials`; offer the fingerprint
  only once the user confirms the value is no secret), and one sentence in
  `sbom-enrich` that hands the line to `sbom-generate`. The flow (which
  value and field, rotate because it is in history, then the fingerprint,
  which surface reads the flag or the `pyproject.toml` list, the
  non-interactive stop) is in the new `references/url-credentials.md`;
  `cli-flags.md` names the flags and `id-registry.md` the registry file
  refusal (it said the entry was dropped).
  **Revised the same day (warn by default):** `--allow-url-credentials` was
  removed; the default writes the SBOM with `WARNING: ...
  [credentials-unsafe/written]`, and `--refuse-url-credentials` or
  `url-credentials = "refuse"` restore the refusal. Descriptions unchanged
  ("holds a credential" matches both lines). The "Check stderr" lines now
  name the `written` warning and the `refused` error and point to the
  reference (rotate, offer `refuse` for CI, fingerprint only once the value
  is confirmed no secret); `sbom-enrich`'s hand-off names both codes; the
  reference's last step is "never suggest turning `refuse` off".
