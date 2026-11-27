---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-24
Last-Modified: 2026-11-27
---

# Message catalogue PR 17c: plan

See also: [message-catalogue-finish-plan.md](message-catalogue-finish-plan.md),
[message-catalogue-pr17-plan.md](message-catalogue-pr17-plan.md),
[message-catalogue-pr17-plan-steps.md](message-catalogue-pr17-plan-steps.md),
[message-catalogue-pr17a-build.md](message-catalogue-pr17a-build.md) and
[message-catalogue-pr17b-build.md](message-catalogue-pr17b-build.md) (the
patterns and lessons this PR follows). The build record is
`message-catalogue-pr17c-build.md`, written during the build.

Built and merged as #534. Planned by Opus (read-only) against `main` at
beefc13c on 2026-11-24. Goal:
the uncoded-site ratchet goes from 15 to 0. The last tag is v0.24.0, so
every new entry has `since="0.25.0"`.

## 1. Sites

Paths are under `src/pitloom/`. Reach: CLI, H (Hatchling hook), L (library),
S (loom SDK).

| # | file:line | Now | Condition and reach | Proposed | Lvl | Topic | Fields (writer) |
| - | - | - | - | - | - | - | - |
| 1 | `_loom_dataset_meta.py:286` | W `loom: dataset %r: invisible or bidi ... in %s` | Bidi or invisible characters escaped in a loom dataset's elements. S (`_loom_dataset.py:296`). No test. | new `text-unsafe`, line `loom SDK: DATASET=%(dataset)s: invisible or bidi control characters written as \uXXXX in %(properties)s` | W | `text` | `dataset` (`quoted_name_text`), `properties` (new, closed) |
| 2 | `assemble/spdx3/_ai_package.py:395` | W `FORMAT=%s FILE=%s: invisible or bidi ...` | Same, for a model and its related elements. CLI, H, L. Quoted by skills and docs. | `text-unsafe`, model line, wording unchanged | W | `text` | `format`, `file` (`file_text`), `properties` |
| 3 | `_ai_package.py:426` | W `FORMAT FILE: release time is not ISO 8601; left out` | A stated release time is dropped (Hub revision, or a library `AiModelMetadata`). | new `model-field-invalid`, text unchanged, no value printed | W | `model-fields` | `format`, `file` |
| 4 | `assemble/spdx3/provenance.py:352` | W `Artifact-metadata Annotation for %r dropped entirely: max-source-metadata-bytes=%d ...` | The cap is too small even for an empty envelope. | merge into `over-cap`: `MODEL_LINE` through `warn_over_cap`, `Cap(n, "byte", "max-source-metadata-bytes", model_format=source_format)`, outcome `artifact-metadata annotation left out` | W | `files` | existing |
| 5 | `provenance.py:362` | W `... had all %d metadata keys dropped ...` | Every key dropped; the annotation is written empty. | `over-cap`, same line, outcome `every metadata key left out of the artifact-metadata annotation` | W | `files` | as 4 |
| 6 | `core/dataset_merge.py:102` | W `FIELD=%s: references to dataset %s differ; the first is kept` | Two references to one dataset state different values. | new `dataset-conflict`, `DATASET=%(dataset)s FIELD=%(dataset_field)s: references differ; kept the first` | W | `datasets` | `dataset`, `dataset_field` (new) |
| 7 | `core/dataset_names.py:92` | I `dataset %s and %s name one dataset; ...` | Two spellings folded into one dataset. | new `dataset-conflict/spelling`, `DATASET=%(dataset)s: %(dataset_spelling)s names it too; kept the first spelling` | I | `datasets` | `dataset`, `dataset_spelling` (new) |
| 8 | `extract/_extract_utils.py:254` | E raise `Cannot read {subject} {where}: {why}` | A missing local file (S, L) or a URL failure (L only). | split: missing file `input-not-found` (new `INPUT_KINDS` entry `Croissant document`); URL `download-timeout` when the reason is a `TimeoutError`, else `download-network-failed` | E | targets / network | `path`; `url` through `url_text`; `failure`; `seconds` |
| 9 | `extract/dataset/croissant.py:264` | E catch-all `Croissant source ... cannot be read` | Not reached by 60,000 fuzz inputs. | raise `InternalError` (a `ValueError`, so the contract holds); print the type and source only | E | none | n/a |
| 10 | `croissant.py:279` | E `field 'name' is of type X, not text.` | Name present but not text. | `dataset-name-missing`, `FILE=%(file)s: no dataset name: the Croissant name is a value of type %(dataset_value_type)s, not text; not read` | E | `datasets` | `file`, `dataset_value_type` (new) |
| 11 | `croissant.py:284` | E `has no 'name' field.` | Name absent. | `dataset-name-missing`, `FILE=%(file)s: Croissant document has no name; not read` | E | `datasets` | `file` |
| 12 | `extract/dataset/values.py:96` | W `dataset metadata: %s field %s is of type %s, not text; skipped` | A value is not text. | new `dataset-field-invalid`, `dataset metadata: SOURCE=%(dataset_source)s FIELD=%(dataset_field)s: a value of type %(dataset_value_type)s, not text; skipped` | W | `datasets` | `dataset_source` (new; masked, cut to 500, escaped), `dataset_field`, `dataset_value_type` |
| 13 | `values.py:207` | W `... is not a URL; skipped` | Croissant `url`; GGUF `repo_url`. | same family, `...: not a URL; skipped` | W | `datasets` | as 12 |
| 14 | `values.py:231` | W `... version is of type %s, not text; quote it ...` | A YAML card version that is not quoted. | same family, `...: a value of type ..., not text; quote it to keep it as written; skipped` | W | `datasets` | as 12 |
| 15 | `values.py:267` | W `... is not a whole number of zero or more; skipped` | Library only (`DatasetMetadata(byte_size=)`). | same family | W | `datasets` | `dataset_source` (a dataset name), `dataset_field` |

Nothing becomes DEBUG or is deleted. `log_one_dataset` stays unprefixed (it
is shared between the CLI and loom). No frame changes; confirm that
`HOOK_STEP_FRAME` does not touch `pitloom.extract.dataset.values` in step 1.

New fields: `dataset_source`, `dataset_field`, `dataset_value_type` and
`dataset_spelling` in `messages/_fields_datasets.py` (`dataset_field`: a
plain-text shape check, roughly `[A-Za-z_@][A-Za-z0-9_.:@-]*( name)?`;
`dataset_value_type` takes the value and maps it through the lock file's
`VALUE_TYPES` plus `bytes`, `set` and `tuple`, falling back to `object`, so a
warning cannot raise). `properties` in a new `messages/_fields_text.py` (a
regex over label and property, with a drift test against
`_display_text.py`'s labels and `_FIELDS`/`_ENTRY_FIELDS`; the messages
package cannot import `assemble`). `_model_where` (`_ai_package.py:194`)
stops calling `loggable`: the writers mask before they escape.

## 2. Rulings (planner's recommendations, taken)

1. `text-unsafe` is a new family on the `text` page.
2. The `croissant.py:264` catch-all becomes an `InternalError`.
3. A non-text Croissant name is a line of `dataset-name-missing`.
4. The `values.py` lines keep the `dataset metadata: ` literal and add
   `SOURCE=` and `FIELD=` (`SOURCE=` freezes at the release).
5. The metadata budget is `over-cap`: `build_source_metadata_annotation`
   gains a keyword `where: str | None` (the `FILE=` value; default
   `subject_spdx_id`); `FORMAT=` comes from `source_format`; the advice says
   "Four caps", adding `max-source-metadata-bytes`; a partial drop stays
   silent on stderr (the SBOM marks it `truncated`).
6. `fetch_json`'s `subject=` becomes a keyword `input_kind=` (an
   `INPUT_KINDS` value); URL failures reuse the `download-*` lines.
7. The fold INFO line is coded `dataset-conflict/spelling`, not a `Summary`.
8. Removed public constants: `NOT_TEXT_WARNING` and its three siblings, and
   `CONTROL_CHARACTERS_WARNING` (`licence.py:44,54` re-exports one; nothing in
   `tests` uses them).

## 3. Skills and docs impact

- `skills/sbom-generate/references/known-limitations.md:227` and
  `docs/metadata-reading-back.md:83` quote the model `text-unsafe` line; the
  wording is kept; append ` [text-unsafe]` to both.
- `docs/metadata-provenance-artifact-metadata.md:162-167` ("a `WARNING` is
  logged"): optionally add `[over-cap]`. `docs/python-api.md:427-432`:
  optionally name `input-not-found`.
- No `SKILL.md` description or flag change; no `_matrix_plan.py` entry.
  `skills/{sbom-enrich,sbom-generate}/references/messages-*.md` are
  regenerated by `--write`.
- `tests/messages/test_drift_quotes.py`: `_MARKERS` for `text-unsafe`,
  `model-field-invalid`, `dataset-conflict`, `dataset-field-invalid`,
  `dataset-name-missing`; the four with no quote go to `_NOT_QUOTED`
  (`text-unsafe` stays out). Choose marker wording after the drift test has
  run (the 20-character cores can collide with help strings).

## 4. Tests

A fail-on-base run needs `-o pythonpath=`. Each site gets a regression test
asserting `pitloom_code`, `None` on `main`:

| Sites | Test |
| - | - |
| 1 | A loom run with dataset name `evil<RLO>txt` (U+202E); one line, `[text-unsafe]`; new test in `tests/messages/test_loom_sdk.py`. |
| 2 | Extend `tests/assemble/test_display_text_escape.py:186` with a code assert and a sorted-properties mutation target. |
| 3 | Extend `test_ai_package_revision.py:77`. |
| 4, 5 | Extend `test_annotation_metadata_truncation.py:104,130` with the code, `FORMAT=gguf FILE=...`, and a direct library call naming the subject id. |
| 6 | Extend `test_dataset_merge.py:119` and `test_gguf_datasets.py:525-559`. |
| 7 | Extend `test_dataset_names.py:79` and `test_loom_dataset_dedup.py:330`. |
| 8 | Flip `test_extract_utils.py:137`; mocked `urlopen` cases `HTTPError` 404, `TimeoutError`, `URLError(TimeoutError)`, `IncompleteRead`; text tests at `:140,234,296` and `test_json_malformed.py:112,119`. |
| 9 | `test_loom_dataset_sources_rules.py:399`: match changes, add `isinstance(InternalError)`. |
| 10, 11 | `test_loom_dataset_sources.py:226-233`. |
| 12-15 | `test_card.py:64,156-165`, `test_licence.py:146,194`, `test_values.py:146`, `test_huggingface_dataset.py:318,329`; a library case `DatasetMetadata(byte_size=-1)`. |

Adversarial cases, one table-driven file `tests/messages/test_datasets_hostile.py`:
a name or source `https://u:pw@h/d?token=x` masked in the record; `a\nWARNING: x`,
ANSI and U+202E give one line and no forged `[code]` (`trusted_message`); a 1 MB
name or source is cut to 500 characters plus `...`, a credential at the end
masked before the cut; quote characters; tri-state (absent, `""`, `[]`,
`[None]` and a placeholder silent; `0` counts; `-1`, `true`, `1.9` warn);
`version: !!binary aGk=` gives `bytes`, `!!set` gives `set`; each emitter once
with a repeated input. The croissant net test asserts the exception type
only. New fixtures that create missing paths or touch `errno` go through
`pytest <file> -m platform --collect-only -q`; mark when nothing is collected.

## 5. Files and sizes

- Over the soft limit: `assemble/spdx3/provenance.py` (520) and
  `_ai_package.py` (504): every change there is net non-positive (each
  `log.warning` block becomes one helper call). `messages/_fields.py` (493):
  no new fields there.
- New modules: `messages/_datasets.py` (four `dataset-*` entries),
  `_datasets_say.py` (`warn_dataset_field(kind, source, field, value=None)` with
  a closed kind, `warn_dataset_conflict`, `say_one_dataset`), `_text_unsafe.py`
  (entry plus `warn_text_unsafe`), `_fields_text.py`. Changed: `_model_field.py`
  (`MODEL_FIELD_INVALID`), `_over_cap.py` (advice), `_field_tables.py`
  (`INPUT_KINDS`), `_topics.py`; public re-exports `datasets.py`, `text.py`,
  `model_fields.py`. Shared helper `escaped_properties(elements)` in
  `_display_text.py` replaces two hand-copied comprehensions.
- Page sizes now to after: datasets 3,232 to ~9,500; text 10,134 to ~12,500;
  model-fields 8,347 to ~9,800; files 20,210 (+150); index 22,357 to ~23,600;
  **values 25,681 to ~27,500 (highest risk; split before the PR if it passes
  29 KB)**; targets 27,547 (+100). Measure both skill twins.
- CHANGELOG `[Unreleased]`: Added (append "dataset" to the catalogue bullet);
  Changed ("Dataset field, Croissant name, display-text and metadata-budget
  lines carry codes; dataset lines name `SOURCE=` and `FIELD=`"); Fixed ("A
  missing `croissant=` file is `input-not-found`; an unreachable Croissant URL
  is `download-network-failed` or `download-timeout`"); link the PR number.

## 6. Steps, agents, gates, risks

- **Step 0 (Opus): probes and the before-capture** on base: a GGUF model with
  bidi text and bad dataset fields; an HF dataset card with a bad version;
  `--max-source-metadata-bytes 8`; a loom run with a bidi dataset name and a
  missing `croissant=`.
- **Step 1 (Opus), fence `src/pitloom/messages/**` and
  `tests/messages/test_datasets*.py`:** entries, fields, `SAMPLES`, say-helpers,
  drift markers; `--write` then measure pages; an import-cycle test in both
  orders for `core.dataset_names` and `extract._extract_utils`. Opus also keeps
  the attacker-text writers and their sites (`values.py`, `croissant.py`, both
  `text-unsafe` sites, `_loom_dataset_meta.py`, `_display_text.py`).
- **Sonnet A (conversions), fence the remaining source files:**
  `dataset_merge.py`, `dataset_names.py`, the `_release_time` emit, the
  `provenance.py` `where=` keyword and `_emit_source_metadata` caller, the
  `_extract_utils.py` split, `deps_pypi` and `croissant` passing `input_kind`.
- **Sonnet B (docs and tests):** the test-text updates, the two quotes,
  CHANGELOG, the hostile test file from Opus's spec.
- **Haiku:** grep `tests/` and `scripts/` for each old text ("first spelling
  is kept", "references to dataset", "Cannot read", "Croissant source",
  "dataset metadata:", "dropped entirely", "release time is not") and update
  them; no `src/` change.
- **Step 4 (Opus): integrate**: `--write`, `--write-baseline` (no module lines
  left), page sizes, stderr before and after, a fresh-context review with the
  Windows notes, mutation, Gates A and B, the build doc.
- **Gate A:** ruff format and check, pylint (`examples/ src/ tests/
  tests/*/`), mypy, pyright, pyrefly, bandit, flake8; `message_inventory
  --check`; `generate_message_reference.py --check`; the drift tests
  (`test_drift_quotes`, `test_drift_sources`, `test_drift_records`,
  `test_message_ratchet`, `test_generated_reference`); full `pytest -n 4`; each
  new test failing on base; branch coverage of touched modules;
  `scripts/manual_cli_checks --only 17,19,20,21,22,24`.
- **Gate B:** mutation (the `fetch_json` classification, `_count_of` routing,
  the `escaped_properties` sort, the `where` default, the type-name fallback),
  `manual_cli_checks -j 8`, the Windows dry run, a fresh read of
  `known-limitations.md`, the `test-all-os` label.

Risks, ranked: the `values` page size; the two files over 500 lines growing; a
cut breaking masking (the `file` and `url` writers do not cut, `url` does not
mask: pass `url_text`); `SOURCE=` freezing at 0.25.0; drift marker collisions;
the `InternalError` contract for library callers matching on the text.

Out of scope, for the sweep: `fetch_json` follows redirects with plain
`urlopen` and no host policy (library `read_croissant(url)` only); `values.py`'s
coded `warn_over_cap(f"{source} {field}")` uses the `name` field (`free_text`),
which neither masks nor cuts.
