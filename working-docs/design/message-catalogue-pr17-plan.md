---
Created: 2026-11-23
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 17 (the last family PR): counts, sites, split, design, rulings

See also: [message-catalogue-pr17-plan-steps.md](message-catalogue-pr17-plan-steps.md)
(steps, tests, gates, risks),
[message-catalogue-pr16-plan.md](message-catalogue-pr16-plan.md) (the shape this
plan follows; it handed over `_embed_overlay.py:117`, `_embed_wheel.py:438`
and `utils.py:199`),
[message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md)
(section 1.3, `_author_warnings.py:168`; ruling 11, row 57),
[message-catalogue-pr12-18-rulings.md](message-catalogue-pr12-18-rulings.md)
(ruling 11),
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md)
(row 17), [message-frames-forward.md](message-frames-forward.md) ("PR 17",
ruling 2: `loom SDK: `).

Status (2026-11-23): planned, not built. Read-only plan by Opus against
`main` at dd31412b (#515 merged; ratchet 44). Every line number is from that
tree. Rulings (user, 2026-11-23): three PRs (17a, 17b, 17c); Q4 validate at
construction; Q6 probe P1 then drop the safety nets (keep as a coded WARNING
if a probe input reaches one); Q11 WARNING with a new code. Every other Qn
takes the planner's recommendation unless the user vetoes at review. Tags: (V) verified by reading the source or running the
inventory; (I) inferred, not run.

## 0. Counts and ratchet

`in_scope` and not `coded` over the inventory gives exactly the **44** sites
of section 1, which sum to the baseline (V). **Target after PR 17: 0** (every
site has a ruling). That needs three inventory scope rules (section 4.5). If
all three are turned down, the floor is 4: `_sbom_io.py:70,79`,
`utils.py:199` and `pytorch.py:204`.

Found while reading; not in the 44, but user-visible and hidden by a wrong
scope:

- H1 (V): `extract/env.py:18` `_shape_error` is in `DETAIL_EXC`
  (`_scope.py:76`). No wrapper adds a line around it, so `loom env` prints
  `ERROR: loom env: Unexpected pipdeptree output: ...` uncoded (5 calls).
  PR 17a codes it and takes `_shape_error` out of `DETAIL_EXC`.
- H2 (I, probe P2): `[tool.pitloom.provenance] schema = "x"` is only
  type-checked (`core/_config_parse.py:150`). It reaches
  `_provenance_encoders.py:143` `Unknown provenance schema`, exempt by
  `INTERNAL_PAT`, but it is a user's value: `config-invalid` (Q4).
- H3 (V): `deps_originator.py:181-184` and `deps_pypi.py:106-111` swallow
  network failures with no line. Roadmap, not this PR.

## 1. Sites and triage

Surfaces: CLI, hook (H), library (L), loom API (S), skill quote (K). Kinds:
(a) a user-reachable catalogued message; (b) a programming error or library
misuse, coded or `InternalError`; (c) exempt by an inventory rule, or
removed with no message. `<n>` is a new code with `since="0.25.0"`.

| # | file:line | Lvl | Who | Kind | Ruling | PR |
| - | - | - | - | - | - | - |
| 1 | `_embed_overlay.py:117` | W | CLI embed-wheel, `wheel --embed` `--project-dir`, L | a | `metadata-conflict` new line (DIR=) | b |
| 2 | `_embed_wheel.py:438` | E | L only (the CLI refuses an empty `--sbom` first) | b | `invalid_value(Parameter("sbom_content"), "sbom-content")`: `option-invalid` VALUE_LINE, new EXPECTED id | a |
| 3 | `_loom_active_run.py:389` | W | S | a | new variant `reference-not-found/dataset` (W, thinner, caller) | b |
| 4,5 | `_loom_caller.py:119,156` | W | S | a | new `caller-info-unreadable`, 2 lines (`inspect.stack` failing) | b |
| 6 | `_loom_dataset_meta.py:190` | W | S | c | safety net: `read_dataset_card` already warns for every read problem (`enrich/readme.py:217-232`); drop the `except Exception` after probe P1 (Q6) | a |
| 7 | `_loom_dataset_meta.py:280` | W | S | a | new `text-unsafe` (dataset line) | c |
| 8 | `_loom_model.py:127` | W | S | a | split by registry (Q8): registry loaded, `registry-hash-missing`; none, new `model-file-missing`. Today it says "looked up by name only" with no registry (V: `_digest` hashes always, `:240`) | b |
| 9 | `_loom_model.py:283` | W | S, K | a | `registry-hash-missing` new W line; prefix `ID registry: ` | b |
| 10,11 | `_sbom_io.py:70,79` | E | via `say_save_failure` (`id_registry/_persist.py:207`, `file-unwritable`) | c | OS error rebuilt to name the path given: detail by errno shape (rule R-a) | a |
| 12 | `assemble/_generators.py:89` | W | L | a | `warn_option_no_effect` (`option-no-effect`) | a |
| 13 | `_ai_package.py:390` | W | CLI, H, L | a, K | `text-unsafe` (model line) | c |
| 14 | `_ai_package.py:421` | W | CLI, H, L | a | new `model-field-invalid`; text unchanged | c |
| 15 | `creation_info.py:157` | E | L (a `Creator.type` set after `__post_init__`; `core/creation.py:115` checks at construction) | b | `invalid_value(Parameter("Creator.type"), "creator-type")`, the construction line | a |
| 16 | `deps_originator.py:171` | E | nobody: raised and caught by its own `except ... ValueError` (`:181`) | c | early `return locator, ctype, None`; no raise, no message | a |
| 17,18 | `provenance.py:335,345` | W | CLI, H, L (`--max-source-metadata-bytes`) | a | `warn_over_cap` MODEL_LINE with `Cap(n, "byte", "max-source-metadata-bytes", model_format=fmt)`; two outcomes | c |
| 19 | `provenance.py:417` | E | nobody (encoders are Pitloom's) | b | `InternalError` | a |
| 20,21 | `provenance.py:444,449` | E | L (`ProvenanceConfig(format="x")`, `PitloomConfig(provenance_format=...)`); config files are checked at `_config_parse.py:147` | b | check in `ProvenanceConfig.__post_init__` and `PitloomConfig.provenance`; the two raises become `InternalError` (Q4) | a |
| 22 | `cli/commands/utils.py:199` | E | CLI wheel commands | c | relay rule R-b, plus wrap uncoded `OSError` at the three `(ValueError, OSError)` handlers (`utils.py:257`, `verify_wheel.py:119`, `_embed_wheel_batch.py:263`) into `file-unreadable` (Q9) | a |
| 23 | `core/dataset_merge.py:102` | W | CLI (GGUF, HF model datasets) | a | new `dataset-conflict` | c |
| 24 | `core/dataset_names.py:92` | I | CLI, S | a | new variant `dataset-conflict/spelling` | c |
| 25 | `core/file_names.py:94` | W | CLI, H, L | a | new `sbom-name-invalid` (W, none, none), config and parameter lines (Q10) | b |
| 26 | `core/iri.py:145` | E | L (`IdRegistry(namespace=...)`); CLI only as the detail of `argument --namespace:` (`cli/id.py:110`, already `option-invalid`) | b | `option-invalid` new lines `namespace %(namespace)s %(namespace_problem)s` and an empty twin | a |
| 27 | `enrich/__init__.py:54` | W | CLI, H | c | safety net: the only enricher (`ReadmeEnricher`) says its own failures; drop the catch-all after a fuzz probe (Q6) | a |
| 28 | `_author_warnings.py:128` | W | CLI, H, L, K | a | new `author-ambiguous` (split) | b |
| 29 | `_author_warnings.py:140` | I | CLI, H, L, K | a | `author-ambiguous` (one author, INFO) | b |
| 30 | `_author_warnings.py:156` | W | CLI, H, L, K | a | new `author-invalid` | b |
| 31 | `_author_warnings.py:168` | W | sdist route (`sdist.py:271`), embed overlay (`_embed_overlay.py:111`) | a | sdist: `load_project_toml_bytes` + `relay_coded_warning` (the `config-malformed` / `file-unreadable/not-utf8` WARNING twins, as PR 12 planned); overlay: new `project-unreadable` (Q11) | b |
| 32 | `_author_warnings.py:188` | W | CLI (dependency authors) | a | `author-ambiguous` (dependency line) | b |
| 33 | `_extract_utils.py:261` | E | S (an absent `croissant=`), L (`read_croissant(url)`); `deps_pypi.py:106` swallows | a | split: URL, `download-network-failed` (or `download-timeout`); absent, `input-not-found` with new INPUT_KINDS `Croissant document` | c |
| 34 | `extract/ai_model/pytorch.py:204` | W | CLI, H (relayed under RELAY_FRAME, `scanner.py:255-270`) | c | fickling's own words: prefixed relay `fickling: ` (rule R-c; Q12) | a |
| 35 | `croissant.py:266` | E | S, L | a | new `dataset-malformed` (exception type only) | c |
| 36 | `croissant.py:281` | E | S, L | a | `dataset-field-invalid` ERROR line | c |
| 37 | `croissant.py:286` | E | S, L | a | new `dataset-name-missing` (sibling of `project-name-missing`) | c |
| 38-41 | `extract/dataset/values.py:96,207,231,267` | W | CLI (HF dataset cards, GGUF), S | a | new `dataset-field-invalid`, 4 W lines | c |
| 42,43 | `extract/env.py:92,96` | E | CLI `loom env`, L `generate_env_sbom` | a | new `environment-unreadable` (+ H1's shape lines) | a |
| 44 | `extract/scanner.py:467` | I | CLI, H, K (`manual_cli_checks/_checks_config.py:226`) | a | `Summary` (a hint), text unchanged | a |

Kept exempt, untouched: `_loom_dataset_meta.py:70,74` (`^loom: ` library
raises, `LIBRARY_PAT`).

## 2. Probes to run at step 1 (not run; read-only plan)

- P1. A loom dataset directory whose card has a deep `tags` list (10,000
  levels), a `version` of 10**5000, a `license` of each YAML type, and
  aliases. Does anything reach `_loom_dataset_meta.py:188`? Same through
  `ReadmeEnricher` for `enrich/__init__.py:54`. Q6 depends on the answer.
- P2. H2: `schema = "bogus"` in a project `[tool.pitloom.provenance]`
  through `loom generate`. Is the ERROR uncoded?
- P3. `loom.Run` with `set_model(path="gone.pt")` and no registry: confirm
  the false "looked up by name only".
- P4. `loom env` with `pipdeptree` missing (`PYTHONPATH` shadow) and with a
  stub printing `{}`.
- P5. `--max-source-metadata-bytes 8` on a GGUF model with metadata: both
  over-cap outcomes.
- P6. Before and after stderr of every probe, for the sweep.

## 3. Split: three PRs

Each PR leaves `--check` green and lowers the baseline.

| PR | Theme | Sites | Ratchet |
| - | - | - | - |
| 17a | Library misuse, scope rules, safety nets, `loom env`, hint | 2, 6, 10, 11, 12, 15, 16, 19, 20, 21, 22, 26, 27, 34, 42, 43, 44 (17) | 44 to 27 |
| 17b (built, #527 guessed; [build notes](message-catalogue-pr17b-build.md)) | Authors, the loom SDK, `sbom-basename` | 1, 3, 4, 5, 8, 9, 25, 28-32 (12) | 27 to 15 |
| 17c | Datasets, display text, metadata budget | 7, 13, 14, 17, 18, 23, 24, 33, 35-41 (15) | 15 to 0 |

17a holds the inventory-tool changes (`_scope.py`, `_relay.py`) and the
API-behaviour changes (Q4, Q6): the risky rulings, reviewed alone. 17b holds
every author line and every loom SDK line (the `loom SDK: ` and
`ID registry: ` renames). 17c holds the attacker-text dataset readers and the
display-text escape. Each is about 1,200 to 2,000 changed lines with tests
(I). Two PRs (17a+17b, then 17c) is possible; rejected because 17a's scope
rules deserve their own review round.

## 4. Design

### 4.1 New codes (`since="0.25.0"`; templates are proposals for step 1's `template_problem`)

| Code | Lvl | Effect / actor | Template |
| - | - | - | - |
| `author-ambiguous` | W, I | weaker / user | W `AUTHOR=%(authors)s: split into %(entries)s next to an address; a name field is never cut between names`; W `AUTHOR_EMAIL=%(authors)s: split into %(entries)s on ',' or ';'; an address field cannot tell a list from one name holding a comma`; I `AUTHOR=%(authors)s: read as one author; it may list several`; W x2 `PACKAGE=%(package)s AUTHOR[_EMAIL]=%(authors)s: split into ...; %(number)s dependencies split in all` |
| `author-invalid` | W | thinner / user | `AUTHOR_EMAIL=%(authors)s: not an email address; %(entries)s not recorded`, and an `AUTHOR=` twin |
| `project-unreadable` | W | thinner / user | `DIR=%(dir)s: project metadata not read; authors from the wheel METADATA; %(failure)s` (Q11) |
| `caller-info-unreadable` | W | thinner / none | `loom SDK: caller info not determined: %(failure)s` plus today's `field_loss_suffix`; and the script-path twin |
| `model-file-missing` | W | thinner / caller | `loom SDK: model %(entity)s: path= %(path)s is not a file at exit; not hashed` |
| `sbom-name-invalid` | W | none / none | `%(config_key)s: %(got)s is not a bare file name (white space or a trailing .spdx3.json); using %(value)s`; `%(option)s: ...` twin |
| `text-unsafe` | W | weaker / user | `FORMAT=%(format)s FILE=%(file)s: invisible or bidi control characters written as \uXXXX in %(properties)s`; `loom SDK: DATASET=%(dataset)s: ...` |
| `model-field-invalid` | W | thinner / user | `FORMAT=%(format)s FILE=%(file)s: release time is not ISO 8601; left out` |
| `dataset-field-invalid` | W, E | thinner (E: not-written) / user | W `dataset metadata: SOURCE=%(dataset_source)s FIELD=%(dataset_field)s: of type %(value_type)s, not text; skipped`; `...: not a URL; skipped`; `...: version of type %(value_type)s, not text; quote it to keep it as written; skipped`; `...: not a whole number of zero or more; skipped`; E `FILE=%(file)s: Croissant name is of type %(value_type)s, not text; not read` |
| `dataset-name-missing` | E | not-written / user | `FILE=%(file)s: Croissant document has no name; not read` |
| `dataset-malformed` | E | not-written / user | `FILE=%(file)s: not a Croissant document Pitloom can read (%(exception_type)s); not read` |
| `dataset-conflict` | W | weaker / user | `DATASET=%(dataset)s FIELD=%(dataset_field)s: references differ; kept the first` |
| `dataset-conflict/spelling` | I | none / none | `DATASET=%(dataset)s: %(name)s names it too; kept the first spelling` |
| `reference-not-found/dataset` | W | thinner / caller | `loom SDK: add_output_dataset(%(dataset)s) names input_datasets=%(dataset_input)s, which no add_input_dataset of this run declared; not linked` |
| `environment-unreadable` | E | not-written / user | `pipdeptree exited %(exit_code)s; %(failure)s`; `could not run pipdeptree; %(failure)s`; `pipdeptree output is not its --json list: %(why)s` (closed `why` from `_validated_node_list`) |

Lines added to shipped families (additive, unreleased):

- `metadata-conflict`: `DIR=%(dir)s: names project %(name)s, the wheel's
  METADATA %(wheel_value)s; authors from the wheel METADATA`.
- `registry-hash-missing`: `ID registry: model %(entity)s has no path=; looked
  up ungated: not hashed`, and `... path= %(path)s is not a file at exit;
  looked up ungated: not hashed` (both W).
- `option-invalid`: two namespace lines; new EXPECTED ids `sbom-content`.
- `over-cap`: no new line; the advice gains `max-source-metadata-bytes` as a
  fourth setting cap.
- `input-not-found`: INPUT_KINDS `Croissant document`.
- `download-network-failed`, `download-timeout`: reused unchanged.
- Summary: the scanner hint (`extract/scanner.py:95`), topic `models`.

### 4.2 Fields

New: `authors` (`shown_list`, masked, cut, escaped; attacker text); `entries`
(a new `entry_count` if the shipped field's shape does not fit `N entries`);
`dataset` (`quoted_name_text`); `dataset_source` (quoted label or URL,
masked); `dataset_field` (closed: `DatasetMetadata` names plus `name`);
`dataset_input` (quoted); `properties` (closed: the names
`escape_element_display_text` returns, comma-joined).

Reused: `file`, `dir`, `format`, `failure`, `exception_type`, `value_type`,
`entity`, `path`, `option`, `config_key`, `got`, `value`, `name`, `package`,
`number`, `exit_code`, `why`, `namespace`, `namespace_problem`,
`wheel_value`.

New modules: `messages/_fields_authors.py` (authors, entries),
`messages/_fields_datasets.py` (dataset*, properties). The `values` page
grows about 1.5 KB (I).

### 4.3 Modules (after `_wheels.py` and `_fields_wheels.py`)

- `messages/_authors.py`, `_authors_say.py`: the `author-*` entries and
  `project-unreadable`, plus `warn_author_split(kind, ...)` with a closed kind.
- `messages/_datasets.py`, `_datasets_say.py`: the `dataset-*` entries and
  the `stated_*` warners.
- `messages/_loom_sdk.py`: `LOOM_SDK_PREFIX = "loom SDK: "` (frames-forward
  ruling 2, a literal, not a Frame), `caller-info-unreadable`,
  `model-file-missing`.
- `messages/_text_unsafe.py`, `_environment.py`, `_sbom_name.py`.
- Public topic modules re-export each entry (the `_topics.py` contract).

No new Frame. `HOOK_STEP_FRAME` gains the codes of the hook's own WARNING
lines (step 1 reads its code set). Expected: `sbom-name-invalid`, `author-*`,
`text-unsafe`, `model-field-invalid`, `over-cap` (already there).

### 4.4 Topics and pages (bytes now, V; growth I)

| Page | Now | Adds | Estimate |
| - | - | - | - |
| new `authors` ("Authors") | 0 | `author-ambiguous`, `author-invalid`, `project-unreadable` | about 9 KB |
| new `datasets` ("Datasets and loom runs") | 0 | `dataset-*`, `caller-info-unreadable`, `model-file-missing` | about 12 KB |
| `model-fields` | 8,347 | `model-field-invalid`, `text-unsafe` | about 12 KB |
| `options` | 12,525 | `sbom-name-invalid`, option-invalid lines | about 15.5 KB |
| `dependencies` | 9,670 | `environment-unreadable` | about 12 KB |
| `fragments` | 20,330 | `reference-not-found/dataset` | about 21.6 KB |
| `id-registry-ids` | 20,492 | two lines | about 21 KB |
| `metadata` | 17,181 | one `metadata-conflict` line | about 17.4 KB |
| `files` | 28,433 | over-cap advice | about 28.6 KB (watch) |
| index `message-codes.md` | 21,433 | about 17 rows | about 23 KB |

Each page and its two skill twins are checked against `MAX_BYTES` and 800
lines. `mkdocs.yml` gains two pages.

### 4.5 Inventory scope rules (17a; keyed on code shape, never on text)

- R-a (`_scope._raise_reach`): an `OSError`-family raise whose first
  positional argument is `errno.<NAME>` or `<name>.errno` is `detail` (the
  OS's own error, named for the caller's wrapping line).
- R-b (`_relay.py`, new kind `exception-param`): a function whose only
  statement is `print_error(str(p), code=code_of(p))` of its own exception
  parameter `p` (PR 16 Q16's alternative).
- R-c (`_relay.py` `prefixed`): also `one_line(<param>, <NAME>)`, where
  `NAME` is a module int constant bound once.
- `DETAIL_EXC` loses `_shape_error` (H1).

Each rule gets a positive and a negative fixture in
`tests/test_message_ratchet.py`.

### 4.6 Skills and docs that quote these lines (grep on dd31412b, V)

- `skills/sbom-generate/references/id-registry-log-lines.md:116-118` and
  `id-registry.md:336`: `loom: model X has no path=` becomes `ID registry: ...`.
- `skills/sbom-generate/references/known-limitations.md:61` (INFO author
  line) and `:218` (bidi).
- `docs/metadata-provenance-authors.md:45-103`, `docs/wheel-sbom.md:165`,
  `docs/metadata-reading-back.md:83`, `docs/ai-model-scan-limits.md:147`
  (fickling).
- `docs/python-api.md:95` (project_metadata), `:337-338` (path=, the "matched
  by name only" fix), `:416-424` (card and Croissant), `:461`
  (input_datasets).
- `scripts/manual_cli_checks/_checks_config.py:226` (the hint, text
  unchanged).
- No `description` or flag change, so no `_matrix_plan.py` entry.
- Step 1 greps `tests/` for each old text. Known: `tests/core/test_loom_model.py`,
  `tests/id_registry/test_loom_miss_warnings.py`,
  `tests/extract/dataset/test_{card,licence}.py`,
  `tests/extract/remote/test_huggingface_dataset.py`,
  `tests/extract/ai_model/test_model_bounds.py:151`.

### 4.7 CHANGELOG (`[Unreleased]`)

- Added: fold into the catalogue bullet; PR links.
- Changed: the SDK's `loom: ` WARNING prefix becomes `loom SDK: `; the model
  registry lines say `ID registry: `; the author lines lose the ` -- only
  authors listed ...` hint (Q7); the metadata-budget lines become `over-cap`;
  the fickling line becomes `fickling: <text>`; `ProvenanceConfig` refuses a
  bad `format` or `detail` when built (Q4).
- Fixed: a loom model gone at exit no longer claims a name-only lookup
  without a registry; an absent `croissant=` file and an unreachable
  Croissant URL carry codes; `loom env`'s pipdeptree output errors carry
  codes (H1); H2 if probed true.

## 5. Rulings (Qn: the recommendation, then the alternative)

User decision needed: Q4, Q6, Q7, Q9, Q11 (behaviour or stderr a script may
parse); Q1-Q3, Q8, Q10, Q12 (names, shape); Q13 (pages).

- **Q1. Author families.** [Recommended: `author-ambiguous` (W split, I one
  author, W dependency split) and `author-invalid` (not an address); one
  literal-key line per `AUTHOR=` and `AUTHOR_EMAIL=`, because `subject_key`
  must be literal.] Alternative: one `author-ambiguous` for all, with "not an
  address" as a line (it is not ambiguous).
- **Q2. Dataset subject.** [Recommended: keep the `dataset metadata: `
  literal (frames-forward) plus a new subject `SOURCE=`. The source is a card
  path, a Croissant label, a Hub URL or a dataset name
  (`assemble/spdx3/dataset.py:104`), so no single shipped key fits.]
  Alternative: per caller `FILE=`, `URL=` or `DATASET=`, threading a kind
  through `stated_*` (about 15 call sites).
- **Q3. Display text.** [Recommended: a new `text-unsafe` (bidi and invisible
  controls are valid text, a reading hazard).] Alternative: a variant
  `text-malformed/controls` on the `files` page, at 28,433 B.
- **Q4. Provenance validation.** [Recommended: `ProvenanceConfig.__post_init__`
  and `PitloomConfig.provenance` refuse `format`, `detail` and `schema` (H2)
  as `option-invalid`, so a library caller fails at construction, not
  mid-generation. The config file's `schema` becomes `config-invalid` at
  parse. The `emit_provenance` checks become `InternalError`.] Alternative:
  code `:444,449` in place (a later raise; H2 stays hidden). Irreversible-ish:
  a public API timing change.
- **Q5. Library misuse.** [Recommended: code as `option-invalid`
  (`invalid_value(Parameter(...))`), as `core/creation.py:110-135` does.]
  Alternative: add texts to `LIBRARY_PAT` (stays out of the ratchet, but the
  code is lost for library callers).
- **Q6. Safety nets.** [Recommended: drop `except Exception` at
  `_loom_dataset_meta.py:188` and `enrich/__init__.py:52`, if and only if P1
  shows no input reaches them; a bug then fails the run like any other.]
  Alternative: keep them as a coded WARNING (`card-malformed`-like `failure`
  text). Drops a degrade path: ask before building.
- **Q7. Author hint.** [Recommended: move ` -- only authors listed in
  pyproject.toml ... are read one by one` from the line into the entries'
  advice; halves the lines, and ` -- ` is not the grammar.] Alternative: keep
  it as `; only authors ...`, using twin lines.
- **Q8. A model gone at exit.** [Recommended: with a registry, the
  `registry-hash-missing` line; without one, the new `model-file-missing`.
  Both WARNING, while the dataset twin `UNGATED_LINE` is INFO, because an
  entry recording a hash is not reused.] Alternative: one line in
  `registry-hash-missing` for both (false with no registry).
- **Q9. `report_error_line`.** [Recommended: rule R-b, plus wrap uncoded
  `OSError` at the three per-wheel handlers into `file-unreadable`.]
  Alternative: leave the site counted (floor 1), or raise `InternalError` on
  an uncoded exception (would abort a batch on a bug).
- **Q10. `sbom-basename` normalised.** [Recommended: `sbom-name-invalid`
  (effect none, actor none), on the `options` page.] Alternative: stage-split
  variants `config-invalid/...` and `option-invalid/...` (effect differs from
  those families' `not-written`, so they need variants).
- **Q11. Project not read for authors.** [Recommended: the sdist route relays
  the coded TOML or UTF-8 WARNING twin, and the overlay route gets
  `project-unreadable`.] Alternatives: make `embed-wheel --project-dir`
  unreadable an ERROR (CLAUDE.md: a read failure is one), a behaviour change;
  or `project-unreadable` for both routes (the inner code is lost).
- **Q12. fickling.** [Recommended: the prefixed relay `fickling: `, needing
  rule R-c.] Alternative: code it as a `model-field-unreadable` line. Its
  words are fickling's, and nothing is lost.
- **Q13. Pages.** [Recommended: new `authors` and `datasets` ("Datasets and
  loom runs") topics.] Alternative: authors on `metadata` (about 26 KB), or a
  separate `loom-sdk` page (about 4 KB).
