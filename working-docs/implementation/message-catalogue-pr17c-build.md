---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-24
Last-Modified: 2026-11-27
---

# Catalogue PR 17c: datasets, display text, the metadata budget (build notes)

See also: [message-catalogue-pr17c-plan.md](message-catalogue-pr17c-plan.md)
(the plan and rulings), [message-catalogue-pr17b-build.md](message-catalogue-pr17b-build.md).

PR #534. (V) verified by running or reading; (I) inferred.

## 1. What was built

Core (messages package and the attacker-text sites 1, 2, 9-15):

- New entries (`since` 0.25.0): `dataset-field-invalid` (four lines, all
  starting `dataset metadata: SOURCE=<dataset-source> FIELD=<dataset-field>: `),
  `dataset-name-missing` (two `ERROR` lines), `dataset-conflict` and
  `dataset-conflict/spelling` (`messages/_datasets.py`, topic `datasets`);
  `text-unsafe` (a model line, wording unchanged, and a loom dataset line,
  `messages/_text_unsafe.py`, topic `text`); `model-field-invalid`
  (`_model_field.py`, topic `model-fields`). (V)
- Helpers: `warn_dataset_field`, `warn_dataset_conflict`, `say_one_dataset`
  (`_datasets_say.py`), `warn_text_unsafe` (`_text_unsafe_say.py`: an entry
  module may not import `_emit`, which imports the catalogue). (V)
- Fields: `dataset_source` (free, masked, cut to 500, escaped:
  `free_name_text`), `dataset_field` (shape check), `dataset_value_type`
  (exact-type table, `object` otherwise; never raises), `dataset_spelling`
  (quoted, masked, cut) in `_fields_datasets.py`; `properties` (closed
  label and property tables) in `_fields_text.py`. (V)
- `over-cap` advice: "Four caps", adding `max-source-metadata-bytes`.
  `INPUT_KINDS` gains `Croissant document`. The `download-*` summaries and
  `did` name a library `read_croissant` URL. (V)
- `escaped_properties(elements)` in `_display_text.py` (sorted, once each)
  replaces the two hand-copied comprehensions; `LABELS` and `PROPERTIES`
  there are public for the drift test against `_fields_text.py`. (V)
- `_model_where` no longer calls `loggable`: its value reaches the `file` or
  `name` field, whose writer escapes it. (V)
- The Croissant reader's catch-all is an `InternalError` naming the
  exception's type only. (V)
- Removed: `NOT_TEXT_WARNING`, `UNQUOTED_VERSION_WARNING`,
  `NOT_A_COUNT_WARNING`, `NOT_A_URL_WARNING` (and `licence.py`'s
  re-export), `CONTROL_CHARACTERS_WARNING`. (V)
- `scripts/generate_message_reference.py`: `MODEL_OUTCOMES` gains
  `model-field-invalid` (a thinner model-field entry must be in the model
  table; `test_generated_reference` holds it). (V)

## 2. Probes (V)

- Site 1 does not fire for a loom dataset declared by name only: with no
  source (`declared_license=`, `croissant=`, a card) the run writes no
  metadata, so nothing is escaped, and the raw U+202E stays in the SBOM's
  `name` (coordinator's before-capture, scenario 5). With
  `declared_license="MIT"` the package is written and the line fires:
  `WARNING: loom SDK: DATASET='evil\u202etxt': invisible or bidi control
  characters written as \uXXXX in dataset name [text-unsafe]`.
- Site 2 on the before-capture GGUF printed `... in dataset name,
  description, name`: no repetition. `dataset name` is the dataset
  package's, `name` the model's own (the label `""` prints the property
  bare). The set already deduplicated; `escaped_properties` keeps that.
- Sites 12-14 on the before-capture cards and GGUF print, for example,
  `WARNING: dataset metadata: SOURCE=corpus2/README.md FIELD=version: a
  value of type bytes, not text; skipped [dataset-field-invalid]`.

## 3. Decisions and deviations

- Site 14: the quoting advice is printed only for a value YAML read from
  an unquoted scalar (`bool`, `int`, `float`, `date`, `datetime`); a
  `!!binary` (`bytes`), `!!set` (`set`) or a list or mapping gets the plain
  not-text line. The plan kept the advice for every type.
- The site 14 line names its field from the caller's `field` argument
  (`version` by default), as the other kinds do.
- `text-unsafe` effect `weaker`: the SBOM states the text, escaped, not as
  read.
- `warn_dataset_field` takes the logger first, as every helper does.
- Sites 10-11 name the document by `FILE=` as given (`source`), not by its
  provenance label, as the base did.

## 4. Review fixes

Round 1 (fresh-context Opus, 9 findings; 2026-11-24):

- **F1** `build_source_metadata_annotation` built its `Cap` before any
  check that the budget was exceeded, so a library caller with a
  `source_format` that is no model format (`"My-Format"`, `""`) and a budget
  that dropped nothing got an `InternalError`. Now `Cap.of_model` leaves a
  format of the wrong shape out (the line names `FILE=` only); a test calls
  it with such a format.
- **F2** `SOURCE=` was free text before `FIELD=`: a source holding ` FIELD=`
  forged a pair, and an empty label printed `SOURCE= FIELD=url`. The field
  is now quoted (`quoted_name_text`, as `DATASET=`): `SOURCE='corpus/README.md'`
  (a ruling 4 change, made before the key freezes at 0.25.0).
- **F4** this doc showed a raw U+202E where the code prints the escape.
- **F5, F6** the `download-network-failed` summary now says a Croissant URL
  gets any HTTP error, a 404 included; the `dataset-name-missing` `did` no
  longer claims no SBOM is written (a caller that catches the exception
  inside `loom.run` still writes one).
- **F8** `Last-Modified` of `model-stub-diagnosis.md`.
- **F3, F7, F9** recorded in section 5.

Round 2 (fresh-context Opus, the round-1 fixes re-checked and a second pass
on the loom SDK routes, merge and fold paths and docs; no high finding):

- `where` of `build_source_metadata_annotation` is documented; the `format`
  field is bounded (`[a-z][a-z0-9_]{0,31}`), so a library caller's 10,000
  character `source_format` is left out of the line, as the other odd shapes.
- `dataset-conflict/spelling` was said once per spelling: at a second
  version the same other spelling folded with no line. Now once per
  (kept, spelling) pair (present before this PR); a test.
- The `text-unsafe` summary says "when it has a Croissant document or
  dataset card"; `docs/python-api.md` is back under 30,000 bytes.
- Recorded in section 5: a repeated `croissant=` re-declaration repeats the
  `dataset-field-invalid` lines; a plain `ValueError` from a field writer's
  shape check passes `read_croissant` uncoded (only a programming error
  reaches it); `SOURCE=` on the `-v` option lines means where the option's
  value came from (kept: `docs/cli.md` documents that key); the partial
  branch `_loom_dataset_meta.py:218->220` is uncovered on `main` too.

## 5. Out of scope, found while building

- A loom dataset declared with a bidi or invisible character in its name
  and no source keeps the raw character in the SBOM's `name` and prints
  nothing (escape runs only on written metadata). A hardening candidate
  (escape the name whenever the package is written), and a format-gap
  question for the ledger (SPDX has no "display text escaped" marker).
- A `FILE=` value is still not cut (17b's finding): a 1 MB `croissant=`
  path prints whole in `dataset-name-missing`.
- A wheel scan names the temporary copy in `SOURCE=` (`SOURCE='1.gguf'` for
  `demo/m.gguf`): the record is not relayed through `_relog_reader_records`,
  so the copy's name is never replaced. Present on `main` too; the key is
  frozen with that value (a follow-up, with the same fix as the other relays).
  Fixed in sweep A (#536).
- `stated_count` (a `byte_size` count) warns for `""`, `[]`, `[None]`,
  `"unknown"` and `"N/A"`, where version and text stay silent for the same
  placeholders. Documented behaviour of 0.24.0, unchanged here; a placeholder
  is not a claim, so a candidate for the sweep.
- `download-timeout` rounds the limit up (`max(ceil(t), 1)`, as
  `_http_errors.py` does): "within 3 seconds" for a 2.4 s limit, "1 seconds"
  for 0.2 s. The template is shared; fix with a singular form in the sweep.
- `failure_reason` masking can eat the closing `>` of a `URLError` text
  (`<urlopen error weird https://***:***@h/?token=***; not read`), and
  `read_croissant("HTTPS://h/x")` (upper-case scheme) is read as a path
  (`input-not-found`). Both present on `main`.
- `SOURCE=` is also the key of the `-v` option lines (`OPTION=... SOURCE=...
  VALUE=...`, where an option's value came from): one key, two meanings, in
  different message families.
- Re-declaring a loom dataset with the same `croissant=` repeats each
  `dataset-field-invalid` line (`text-unsafe` is said once); a follow-up under
  "repeated input said once".
- A `ValueError` from a field writer's shape check (`dataset_field_text`)
  passes the `except ValueError: raise` of `read_croissant` uncoded; only a
  programming error reaches it. Candidate: raise `InternalError` there.
- `_loom_dataset_meta.py:218->220` (`merge_metadata`, a stated field with no
  provenance entry) is an uncovered branch on `main` too (full suite).
- A wheel-scanned GGUF dataset's provenance in the SBOM still names the
  temporary copy (`Source: 0.gguf | Field: general.dataset.0.name`, annotation
  `"source":"0.gguf"`): `_restore_source_name` rewrites only the model's own
  `meta.provenance`, not each dataset's (found in sweep-a; `SOURCE=` in the
  log line is fixed). Fixed in #540: each dataset's provenance names the
  wheel member.
- `fetch_json` follows redirects with plain `urlopen` and no host policy
  (library `read_croissant(url)` only).

## 6. Lessons

- An entry module cannot import `_emit` (`_emit` imports the catalogue):
  a helper goes in a `_say` module.
- A `Write` tool call can turn a `\u202e` escape in test source into the
  character itself; pylint's `bidirectional-unicode` catches it. Grep new
  files for non-ASCII before linting.

## 7. Reference page sizes (bytes, lines; skill twins in brackets)

| Page | Size |
| - | - |
| datasets | 8,336, 147 (8,300) |
| text | 11,889, 188 (11,853) |
| model-fields | 9,518, 163 (9,482) |
| files | 20,387, 305 (20,351) |
| network | 17,824, 291 (17,788) |
| values | 26,806, 159 (26,775) |
| index | 22,911, 274 (22,119; 22,075) |
| targets (largest, unchanged) | 27,547, 432 |

## 8. Mutation pass

335 mutants (187 AST operators, 148 hand-written regex, table and keyword
edits) of the lines this PR changed, in 14 files: 274 killed at first, 61
survived. 44 survivors are equivalent (an `except InternalError` widened to
`ValueError`, a dropped `line=` keyword the level already selects, the order
of type names under `fullmatch`, an unused value argument, the kind strings,
`str` never reaching a helper). 17 were test gaps, now killed (16; one regex
variant of the `dataset_field` shape is equivalent: `aname` already
matches): the `TimeoutError` classification and the failure text of
`fetch_json` (a refused or reset connection is `download-network-failed`),
`max(ceil(t), 1)` for a 0.5 s limit, `from None` and `from exc` on the
`InternalError` and the missing-file route, the kept spelling named in
`dataset-conflict`, the `dataset_field` shape and the writers' type check
(`None`, `bytes`, a number), the type-name shape (`tuple`), the quoting advice
for a `datetime`, the property order of `text-unsafe` for a loom dataset, the
`where` of the emptied annotation and the silent partial drop, the
`_model_where` fallback chain, `release_time=""` silent, `FORMAT=` and
`FILE=` not swapped. New files: `tests/extract/test_fetch_json_failures.py`,
`tests/extract/dataset/test_croissant_internal_error.py`,
`tests/messages/test_datasets_mutation_gaps.py`,
`tests/assemble/test_budget_and_model_lines.py`.
