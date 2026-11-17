---
Created: 2026-11-17
Last-Modified: 2026-11-17
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue: review rounds and what is left open

See also: [message-catalogue-families.md](message-catalogue-families.md) (the
families built), [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(the design), [roadmap.md](../design/roadmap.md).

A round is a set of read-only reviews of the merged catalogue, its docs, its
skills and the code comments, each finding checked against the code before it
is fixed. Findings not fixed are listed here, so the roadmap keeps one line.

## Round 1 (2026-11-16, after #492)

Two reviews of the registry save, file-set and summary lines. Fixed in #494:
"already written" (the SBOM is built before the registry save and written
after it), "left the file as it was" (`replace_text_lf` writes in place where
the directory refuses a temporary file), the Action inputs in the credential
advice, `registry-file-missing` said once, a memory address in `sbom-invalid`
text, a `MemoryError` filed as an invalid SBOM.

## Round 2 (2026-11-17, PRs #480 to #494)

Six reviews (docs, working-docs, code comments in two parts, skills, the whole
catalogue). Fixed in #494: stale "refused by default" wording in
three docs, the Action example for a tag without the inputs, `url-credentials`
missing from the `loom.run` key list, `embed-wheel` missing from the flag
lists, the `option-conflict` text for `loom id import`, quoted lines of the
skills that dropped their frame, ten stale or false docstrings, four broken
cross-references, drift-test markers for 44 unguarded quotes.

### Open: catalogue behaviour

- `library-missing` under `--allow-build`: the coded `CodedImportError` is
  caught in `core/_models_wheel_build_and_read.py` and relayed as an uncoded
  `WARNING: Build: build-and-read discovery failed ...`, so the text shows
  without `[library-missing]`. Needs a WARNING line on the entry, or a
  forwarded code. Same pattern: `assemble/spdx3/fragments.py` relays a coded
  `json-malformed` / `file-unreadable` text without its code.
- `failure_text` drops memory addresses only for the `failure` field; about
  30 sites print `one_line(exc)` directly. `MemoryError` is still filed as an
  input fault by `assemble/spdx3/fragments.py:393` and
  `cli/commands/fragment.py:126,135` (the latter uses a block `pylint:
  disable=`).
- `CREDENTIALS_UNSAFE_ACCEPTED`'s summary names no Action input; the drift
  markers `<input> not found: `, `archive not found: ` and `path not found: `
  match no template, so they guard nothing.
- `text-malformed` names an SBOM element under `FILE=` (`export/spdx3_json.py`,
  `warn_lone_surrogates(log, file=min(changed))`); it wants an `ELEMENT=` line.
- `credentials-unsafe/git-userinfo` shows its URL quoted (`URL='...'`); its
  siblings do not. `docs/git-urls.md` and the git-url skill reference quote it.
- In the `refuse` mode the `weak` and `accepted` lines are said before a
  refusal (`export/_spdx3_credentials/_check.py`); a test pins the order.
- `SBOM_NOT_VALID_LINE` says "no wheel was written", every `did` "no wheel is
  changed"; `_field_tables.py:114` and `extract/_license_detect.py:255` say
  "license" in message text; `_sbom_format.py:202` says "recognized".
- Rule R1 (INFO decisions code as actor none, effect none) is not applied to
  `reader-unsafe`, `field-not-recordable`, `usage-unparseable/mention`,
  `release-unpinned*`, `release-unusable` and `file-ambiguous`; record R1 as
  forward-only, or move `reader-unsafe` to WARNING.
- Twenty lines are reached only by catalogue-generic tests: the registry
  save-reread WARNING twins, `json-malformed` "not a JSON object", the Hub
  redirect WARNING, `temp-dir-unusable`.
- A `since` per line: lines new since 0.24.0 under an older code carry the
  entry's `since`.

### Open: code shape

- `resolve_registry(..., refuse_credentials=<cfg>.credential_policy.refuse)` is
  hand-copied at eight sites (`_embed_generate.py`, `assemble/_generators*.py`,
  `_model_generator.py`, `plugins/hatch.py`): one helper taking the config.
- `_embed_generate.py` imports `check_graph_credentials` from the private
  `export._spdx3_credentials`; re-export it from a public `pitloom.export`
  module.
- `require_key_without_credentials` and `registry_key_for_path` are exported
  and have no caller outside tests.
- `id_registry/_harvest/__init__.py` lists underscore names in `__all__`.
- `generate` settles the build flags after its existence check, `loom project`
  before it: a missing target prints the build-flag WARNING under `project`
  only.
- `_ai_package.py:197` passes `loggable(where)` into a `file` field.

- The masker's linear-time tests are timing ratios (growth bound 64, ratio
  bound 15, widened after CI flakes): a scan whose quadratic part is under a
  quarter of its time at the smaller size passes them. A deterministic
  complement: wrap the compiled patterns of `core/url_masking/` with a
  counting proxy that sums `len(text) - pos` per search, and assert the
  count is linear.
- `test_models_wheel_dispatch_lock.py` (`*_is_not_serialized`) overlaps four
  threads inside a 50 ms sleep (use an `Event` or `Barrier`);
  `test_models_wheel_build_kill.py` counts `killpg` calls in a 0.3 s poll.

### Open: docs, skills, size

- Skills and `docs/agent-skills.md` name `pitloom >= 0.24.1`, a release that
  does not exist; raise it with the 0.25.0 cut (roadmap, "0.25.0 cut sweep"),
  with `.claude-plugin/plugin.json` and a CHANGELOG line.
- No skill covers the GitHub Action or `loom merge` / `loom fragment list`
  (known deferrals); the three skill descriptions sit at 999 to 1021 of 1024
  characters, so a trigger needs a trim first.
- Over the 30 KB limit: `roadmap.md` (36 KB), `skills-trigger-coverage.md`,
  `file-map.md`, `docs/git-urls.md` (crossed in this range), `docs/cli.md`,
  `docs/ai-model-formats.md`, `docs/ai-model-scan-limits.md`,
  `docs/configuration.md`, `skills/sbom-enrich/references/minimum-elements.md`.
  Near it: `id-registry-followups.md`, `credential-leak-fixes.md`,
  `docs/id-registry.md`, `docs/python-api.md`.
- Built plans still in `design/`: `credential-detect-and-refuse.md` (move with
  `credential-leak-fixes*.md` into an `implementation/credential-leak-fixes/`
  folder), `message-catalogue-pr6-pr7-plan.md`.
- CLAUDE.md rules whose detail docs are missing: "Write the key the lookup
  used", the `provenance_source` rule, the pyrefly interpreter note.
- CHANGELOG bullets over 160 characters (with the PR links): seven; `CHANGELOG.md`
  itself is 60 KB.
- Out of scope of catalogue PRs 10 and 11 (2026-11-17): `loom fragment list` reading lock files (only to work out a document id), and a requirements file with `--generate-hashes` that is ignored; both in [message-catalogue-pr10-11-lock-plan.md](../design/message-catalogue-pr10-11-lock-plan.md).
