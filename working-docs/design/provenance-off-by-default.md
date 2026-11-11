---
Created: 2026-11-11
Last-Modified: 2026-11-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Provenance off by default

Plan, not built; **deferred 2026-11-11** (too large for now, no release set).
Implements the ruling of 2026-11-05 in [roadmap.md](roadmap.md)
("Provenance and source-metadata flags"): provenance is off by default; a
flag turns it on. Target first asked for: 0.24.1. The planning agent
recommends 0.25.0 (see [Version](#version)).

See also: [licence-resolution-provenance.md](licence-resolution-provenance.md)
(rulings section), [../../docs/metadata-provenance.md](../../docs/metadata-provenance.md).

Written from a read-only planning pass at `fd063903` (`cbf44b05` plus #476).
**[V]** = verified in code by the planner; **[A]** = assumed. The author of
this file re-checked only that `ProvenanceConfig` has no `enabled` field and
that `Spdx3JsonExporter()` is built in five places (below); the rest is the
planner's reading and needs checking per PR.

## Design: one switch, applied once at serialisation

`ProvenanceConfig.enabled: bool` is the switch. It is not a new `format`
value: `format` (`annotation|comment|both`) and `detail` (`minimal|full`)
describe the shape and apply only when `enabled` is true. `--provenance`
alone gives today's output (`both` + `minimal`). Rejected: `format = "none"`,
which mixes "is it on" with "what shape".

| Surface | Spelling |
| :------ | :------- |
| Config | `[tool.pitloom.provenance] enabled = true`; add to `KNOWN_KEYS["provenance"]` (`_config_keys.py`), read in `_read_provenance_settings` (`_config_parse.py`) [V] |
| `PitloomConfig` | `provenance_enabled`, read by the `provenance` property (`_config_types.py`) [V] |
| Overrides | `ConfigOverrides.provenance_enabled: bool \| None`, applied in `apply_overrides` (`config_cascade.py`) after the whole-`ProvenanceConfig` override [V] |
| CLI | `--provenance/--no-provenance`, `BooleanOptionalAction`, `default=None`, `dest="provenance_enabled"`, in `_build_parent_parser` (`cli/parser.py`); `_SAME_NAME_OPTIONS`, `overrides_from_options` (`cli/options_config.py`); `PARAM_TO_FLAG` and inert rows (`core/inert_options.py`) [V] |
| Library | `provenance_enabled: bool \| None` on `generate_project_sbom` and every `generate_*_sbom` taking `max_source_metadata_bytes`; `generate()` and `embed_wheel_sbom` through `ConfigOverrides`. Not `provenance`: that parameter already takes a `ProvenanceConfig` [V] |
| Hatchling hook | no new code: it passes `pitloom_config.assemble_options` (`plugins/hatch.py` `_generate`) [V] |
| Action | input `provenance` (`true`, `false`, empty defers), mapped to the flag in the `run:` block, as `scan-model-usage` is [V] |

The cascade stays CLI > `pyproject.toml` > default.

**Record internally, strip once when writing.** Builders keep recording
provenance, as now. A fragment merge reads the base's provenance back
(`GeneratedValues` in `_fragments_generated.py` decides whether a fragment
replaces a generated `description`, `ai_domain` or
`ai_informationAboutApplication`, from `Method: generated_from_labels` /
`derived_from_format`) [V]. Skipping `emit_provenance`
(`assemble/spdx3/provenance.py`) would drop a fragment's value with a
`Merge: conflicting` warning at three in-process merge sites
(`_generators.py`, `hatch.py`, `_embed_build_sbom.py`) [V]. So:

- one helper `new_exporter(prov_cfg)` replaces the five bare
  `Spdx3JsonExporter()` calls (`document.py`, `_document_model.py` x2,
  `_document_deployed.py`, plus `_fragments_envelope.py` and
  `_loom_active_run.py`, which keep provenance: see Q4);
- `Spdx3JsonExporter.to_json` (`export/spdx3_json.py`) filters the `@graph`
  when `keep_provenance` is false; the filter lives in a new
  `export/_provenance_filter.py` (`spdx3_json.py` is 587 lines).
- `export` must not import from `assemble`: move `PROVENANCE_COMMENT_PREFIX`
  and the fields schema URL (`https://pitloom.dev/provenance/fields/1`) to
  `core/provenance.py`.

## What "off" means

Removed: every Annotation whose statement is a Pitloom `fields` statement
(`Method`, `Normalized-From`, `Resolution-n`, `Tool`, the PyPI acquisition
record, `Evidence` entries) and every `Metadata provenance: ` line in an
element's `comment` [V]. This matches the ruling: a default SBOM carries no
`Normalized-From`, `Resolution-1` or `Tool`.

Kept (to confirm, Q1): conflict, unification and enrichment Annotations;
artifact-metadata (its own flag); skill-written `Source: ... | Role:
inferred` markers (no prefix).

Unaffected: logic reading the in-memory provenance dict (stripping runs
after it): `is_license_concluded`, the lock cascade, setuptools readers,
`filter_high_signal` [V].

Degrades when provenance is absent:

1. A fragment merged later into an SBOM written without provenance cannot
   tell what was generated (`_fragments_generated`) [V].
2. The sbom-enrich stub diagnosis reads `Method: file_name_stem` and
   `Source: <model> | Field:`: the skill must pass `--provenance` [V].
3. `pypi-url-base.md` and `sbom-validate/SKILL.md` describe the acquisition
   record as always present [V].
4. Evidence levels: CLAUDE.md says a declared fact must never pass as
   measured and `not_measured` must be recorded. Off, a declared LFS hash or
   size reads as plain fact (Q2).
5. Annotation ids are per-document counters (`core/models.py`): stripping
   leaves gaps (deterministic, cosmetic) [V].
6. No writer was found that leaves a dangling reference to a stripped
   element [A]: run `spdx3-validate` on stripped output.
7. verify/validate commands do not generate, so are unaffected [A].

Format or detail set while `enabled` is false: one `WARNING:` (no silent
deviations); a new catalogue message (Q3).

## Tests

- One shared test default: `ProvenanceConfig.enabled` takes
  `default_provenance_enabled()`, and an autouse fixture in
  `tests/conftest.py` turns it on; a `provenance_default_off` fixture opts
  out. About 210 test files mention provenance and 109 call `main()`
  in-process [V]. Subprocess runs (about 10 test files with `-m pitloom`,
  `_harness.loom_argv`, the sweeps) need `--provenance` injected (Q5).
- Default-off asserted on each surface (no `fields` Annotation, no prefix
  line): CLI, library, hook, Action (`tests/scripts/action/
  test_generate_step_inputs.py` for `true`, `false`, empty); cascade:
  pyproject `enabled = true`, then `--no-provenance` wins.
- Regression: a fragment still replaces a generated description with
  provenance off, in-process and through the hook. Determinism/parity
  harness in both modes.
- The four coverage snapshots should not change (the checker reads no
  `annotation` or `comment`; `properties_written` counts keys with `_`) [V];
  re-run to confirm [A].
- `scripts/manual_cli_checks/_matrix_plan.py`: add the flag, else
  `M/completeness` fails [V]. Classify `merge` and `id` (maybe inert).
- Classify new tests with `-m platform --collect-only`.

## Docs, skills, CHANGELOG

- Docs: `configuration.md`, `metadata-provenance.md` (line 15 says
  provenance is tracked by default), `cli.md`, `api.md`, `github-action.md`,
  `hatchling-build-hook.md`, `metadata-provenance-*.md`.
- Skills: `sbom-generate/references/cli-flags.md`, `known-limitations.md`;
  sbom-enrich `SKILL.md`, `model-stub-diagnosis.md`, `pypi-url-base.md`
  (pass `--provenance`); `sbom-validate/SKILL.md`. Raise the floor.
- Messages: if Q3 adds one, update the catalogue and run
  `scripts/generate_message_reference.py`.
- CHANGELOG: "Changed" (**Breaking:** provenance off by default); "Added"
  (flag, config key, input, parameter).

## Version

Planner recommends **0.25.0**: every default SBOM loses content that the
skills and downstream readers parse, and the skills' floor must move; 0.24.0
was a minor bump for comparable breaks. 0.24.1 is defensible only if SBOM
content is ruled not to be a contract during the alpha. The user asked for
0.24.1: decide before PR 4.

## Risks and size

- `provenance=ProvenanceConfig(detail="full")` passed by a library caller
  silently gets provenance off (Q6).
- Hand-written fragments using the `fields` schema are stripped too.
- Soft size limit: `_config_parse.py` (505): move `_read_provenance_settings`
  to `_config_parse_provenance.py`, as `_config_parse_scan.py` did;
  `spdx3_json.py` (587): filter in a new module; `assemble/spdx3/
  provenance.py` (504): moving the constants down helps; `action.yml` (610)
  grows about 15 lines.
- Clean-up: the format and detail value sets exist twice
  (`_config_parse.py`, `_provenance_encoders.py`); keep one in
  `core/provenance.py`.

## Open questions

1. Does "off" also remove conflict, unification and enrichment Annotations?
   (Recommended: no.)
2. Evidence floor: keep `declared`, `lower_bound` and `not_measured` entries
   when off, or change the CLAUDE.md rule?
3. `format`/`detail` set without `enabled`: `WARNING:` or turn it on?
4. Do `loom merge`, SDK fragments and `loom.Run` keep provenance, or take
   the flag? (The plan keeps it: they feed a later run.)
5. Subprocess tests and sweeps: argv injection (recommended) or a test-only
   environment variable?
6. Should passing a `ProvenanceConfig` without `enabled` warn?
7. Version: 0.25.0 or 0.24.1?
8. Final flag name (`--provenance` is the roadmap's wording).

## PR order

1. **Mechanism, default still on** (about 250 source, 250 test lines):
   `enabled`, config key, cascade override, `new_exporter`,
   `_provenance_filter.py`, constants to core, library parameter, shared
   test-default fixture, merge regression test.
2. **CLI flag** (about 120 + 150): parser, `options_config.py`,
   `inert_options.py`, `_matrix_plan.py`, manual checks, harness injection.
3. **Action input** (about 40 + 80): `action.yml`, Action shell tests.
4. **Flip the default** (about 30 source, 200 test and docs): per-surface
   default-off tests, docs, skills, CHANGELOG, floor, snapshot re-run.
5. **Optional: `--preserve-source-metadata auto|always|never`, default
   `never`** (about 150 + 150), same plumbing (`_should_preserve_metadata`
   in `_ai_package.py` already takes three values); also
   `docs/metadata-reading-back.md` and `known-limitations.md`. Ship in the
   same release as a separate PR so default output changes once; it does not
   block PRs 1 to 4.
