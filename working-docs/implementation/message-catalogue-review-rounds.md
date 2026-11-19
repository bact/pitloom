---
Created: 2026-11-17
Last-Modified: 2026-11-19
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
- Out of scope of catalogue PRs 8 and 9 (2026-11-18), found by review: (1) `read_pitloom_config` on a project `pyproject.toml` (CLI project route, hook) still raises an uncoded `TOMLDecodeError`/`UnicodeDecodeError` with no `FILE=` (same as before; belongs to PR 12, project metadata); an sdist's invalid TOML is also still `config file '...': ...` uncoded (PR 12); (2) an unknown config key is masked only by the CLI/hook log handler, not at source, for a library caller (same as before; `entry` is a shared free-text field); (3) a `[tool:pitloom]` `no-creation-tool` error in setup.cfg names `[tool:pitloom:creation]`, because the INI reader moves the key into the creation table before parsing (wrong at HEAD too); (4) the `config file '...'` wrapper in `load_config_file` still catches an uncoded `ValueError` from `parse_pitloom_config` (stays in the baseline, 1 site).
- Out of scope of catalogue PRs 8 and 9, second review (2026-11-18): (1) a hook error for a `hatch.toml` names `[tool.hatch.build.hooks.pitloom]` and no file, though that file spells it `[build.hooks.pitloom]` (Hatchling's `ProjectMetadata.hatch` lets a `hatch.toml` replace `tool.hatch` wholesale, so the source is knowable: name `FILE=hatch.toml`); (2) an offset time out of range as UTC says "must be an ISO 8601 date and time" (an "out of range" id would be exact), a date-only `2024-01-01` passes as a date-time, and Python 3.10 refuses fractional seconds of one digit and `+0000` that 3.11 and later accept, so one `pyproject.toml` is `config-invalid` on 3.10 only; (3) `sbom-basename = "con"` (a Windows device name) says "not a path"; (4) on `main` too: `SOURCE_DATE_EPOCH` after 2107 fails `embed-wheel` with an uncoded `ushort format requires ...` (`_embed_wheel.py` `_resolve_zip_timestamp` has the 1980 floor and no 2107 ceiling).
- Found by mutation testing of PRs 8 and 9 (2026-11-18): `id-registry = ""` in a `--config` file resolves to the config file's directory (`GivenPath(<dir>, "")`), not to unset; whether `""` means unset or is refused is a design call (`core/config_cascade.py`, `apply_overrides` path join).
- Possibly dead code found by mutation testing (2026-11-17): the `InvalidRequirement` branch at `src/pitloom/core/requirements.py:219` (flatten). `_parse_extras` already drops invalid requirements and joining a marker fails only as `InvalidMarker`, so no test reaches it. Remove it or prove it reachable.

## Round 3 (2026-11-19, PR 12: project metadata, #501)

One fresh-context review and a HEAD-versus-tree stderr sweep (46 inputs):
exit codes and whether an SBOM is written are identical; every text change
traces to a ruling; the only input that yielded a record and now yields none
is the intended `[build-system]`-only DEBUG case. Fixed in the PR: the
`config-malformed` `did` for an sdist `WARNING` (no PKG-INFO: the package is
named `unknown`), a structural test pinning the two writers of
`field_conflicts` and a probe test (every `[tool.pitloom]` key times four bad
values, through `load_config_file` and `read_sdist`) behind the two
`InternalError` residues, public names for the pin-check helpers, and a
non-table `[tool.poetry]` with a `poetry.lock` said twice (row 21's own
warning, then row 17's relay of the same error): said once, the relay skipped
for a non-table (the user revised D5 on 2026-11-19; with no lock row 21 is the
only say, as the caller returns quietly).

Resolved by the PR: round 2's item that `read_pitloom_config` raised an uncoded
`TOMLDecodeError`/`UnicodeDecodeError` on a project `pyproject.toml`.
Correction to round 2's `hatch.toml` item (read in Hatchling 1.32.3,
`hatchling/metadata/core.py:231-254`): `ProjectMetadata.hatch` copies
`tool.hatch` and shallow-updates it with `hatch.toml`, per top-level key; a
`hatch.toml` with `[build]` replaces all of `tool.hatch.build` (hooks
included), while `version`, `metadata` and the other keys survive. The hook
table is read from `hatch.toml` when it has a top-level `build` key, else
`pyproject.toml`; the fix (`FILE=hatch.toml`, `[build.hooks.pitloom]`) is still
open.

Mutation testing of the new and changed modules (144 hand-written mutants,
seven targets): 109 killed, 9 equivalent, 26 survivors, each now killed by a
test (`*_edges.py` files beside the area they test). One finding beyond the
survivors: `InternalError` is a `ValueError`, so the `except ValueError` of
`_try_read_poetry` dropped one quietly when there is no `poetry.lock`, and the
two residue handlers re-wrapped one; each now lets it through
(`except InternalError: raise`). A relay of an uncoded error in a handler
still raises `InternalError` itself. The `retry-refused` case of
`tests/messages/test_metadata.py` never reached the licence retry
(pyproject-metadata checks `license` after every other field); renamed
`bad-version-with-licence`.

### Open (found in round 3, not fixed)

- `FILE=` on the `--index-url` line (`RequirementsFiles`) and on the dynamic
  directive lines (`_setuptools_dynamic._warn_ignored`) names `pyproject.toml`
  or `setup.cfg` without the project path; sibling lines give the full path.
  The project directory is not at hand in `_warn_ignored`.
- The `backend` field means two things: dispatch passes the lower-cased
  top-level key, the Poetry line a declared build-backend "as written".
- The installed-metadata conflict line (row 50) names no directory and writes
  the raw values, where the setup.py/setup.cfg line uses `conflict_text`.
- `authors = [1]` reads "is an array, expected an array of strings".
- Row 47's `name` is not cut by `excerpt()`; row 48's `files` is quoted as a
  whole list, not per name.
- `tests/messages/test_metadata_relays.py` is 508 lines and
  `tests/extract/project/test_poetry_extras.py` 517 (soft limit 400 to 500).
