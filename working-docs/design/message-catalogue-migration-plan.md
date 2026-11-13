---
Created: 2026-10-30
Last-Modified: 2026-11-13
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue: migration plan and release cuts

See also: [message-catalogue-and-skills.md](message-catalogue-and-skills.md)
(the design and decisions A to M), [roadmap.md](roadmap.md) (0.23.0 and
0.24.0 scope), [known-bugs.md](known-bugs.md),
[licenseid/adoption-plan.md](../implementation/licenseid/adoption-plan.md).

Status: plan, re-measured 2026-11-04 on `main` 54f79c57 (0.22.1 released; the
LicenseID 0.7 adoption merged, #437 to #440). Done: `lfs-pointer` (#390),
`over-cap` (#396), the model-stub causes (#404, PR 1a), unreadable files and
directories (#408, PR 2a) and, in 0.23.0 (2026-11-05), PR 2b (#444) and PRs 1b
and 1c (#446); the reference split (#480) and PR 4, the frames
([message-frames.md](../implementation/message-frames.md)), are built. Left:
PR 3 onward and T14. This file is the
reference for what remains and what ships in which release.

## Shipped in 0.22.0 (2026-10-30)

1. Catalogue PR 1a, the model-stub causes (#404).
2. Catalogue PR 2a, unreadable files and directories (#408).
3. The serious known bugs fixed: a file name that is not UTF-8 and a `:` in
   plain provenance text (#402), a direct-URL dependency looked up on PyPI
   (#405), a package key without a version (#407, ID registry format 4).
4. The path-in-message fix (#410): archives and licence files named by file
   name, not an absolute path.

Earlier in the release: `lfs-pointer` (#390, #395) and `over-cap` (#396).
The grammar ratchet keeps new uncoded messages out
(`tests/test_message_ratchet.py`).

## Release cuts (maintainer ruling 2026-11-04)

0.22.1 shipped on 2026-11-03 (#413 to #433). 0.23.0 is cut early:

- **0.23.0**: the LicenseID 0.7.0 adoption (built, #437 to #440), the
  adoption's final gate (stage E), this plan's refresh, PR 2b and PRs 1b and
  1c. The ratchet falls from 498 to 469 (2b: 10, #444; 1b: 19, #446).
- **0.24.0**: the uniform `loom <command>:` frame (PR 4), catalogue PRs 3 to
  18 (the licence families last), the licence provenance mapping (T14,
  [licence-resolution-provenance.md](licence-resolution-provenance.md)) and
  `--report` with SARIF.

The earlier decision of 2026-10-30 (everything in 0.23.0) is superseded.

## Sizes

The tool (`python -m scripts.message_inventory`) finds 1,017 emission sites
at 54f79c57: 575 in scope (a user-visible `WARNING:`, `INFO:` or `ERROR:`),
77 coded and 498 uncoded, in 155 modules. The ratchet baseline
`tests/fixtures/message-inventory/uncoded.txt` is the contract; it holds the
498. The adoption (#437 to #440) moved the licence text lines from
`_license.py` to `_license_text_match.py` and changed no total.
Families are the classifier's, over the uncoded in-scope sites (the
`classify.py` rules of the 2026-10-29 inventory, run on the tool's records);
a helper's text counts once. Skill quotes (20 of the 60 remaining families,
243 sites at the first inventory) are not re-measured: use `--quotes` in each
PR's plan.

## Remaining catalogue PRs, in order

Order (the maintainer's, C5 of the 2026-11-04 plan): doc refresh, 2b, 1b
and 1c, **the 0.23.0 cut** (these four done), then 4 (frames), 3, 5 to 7
(with the D7 remote registry entries first, or with 6), 10 and 11, 8 and 9,
12, 13 and 14, 15 and 16, 17, 18 (the licence families; unblocked, the
adoption is done), and T14. The precondition (split the generated references,
over the ~30 KB limit after #446) is built: one page per topic, the family ->
topic mapping in `src/pitloom/messages/_topics.py`. Each catalogue PR that adds
a family maps it there (a test fails until it does), and a page nearing 30 KB
is split in that file; the generator refuses an oversize file.

"Plan" is the count in the plan made on `bccaa747`; "Now" is measured on
54f79c57. Codes are PROPOSALS by the grammar (decisions A to M); each PR's
read-only Opus plan settles them. Actor and effect are as decision G.

| # | Cut | Families (uncoded now) | Codes to define (proposed) | Actor / effect | Ratchet, plan then now | Effort / agents |
| - | - | - | - | - | - | - |
| 1b | 0.23.0 | model-field-unread 19 (`extract/ai_model/` hdf5_config 5, pytorch_pt2 5, pytorch 3, fasttext 2, gguf, onnx, unrecordable; `_ai_package.py` release time); model-scan-decision 1 (`scanner.py`); passthrough in `scanner_wheel.py` 2 | `model-field-unreadable`, `model-field-conflict`, `model-field-invalid` (built folded into `-unreadable`), `field-not-recordable` (#404 D10) | user / thinner (conflict: none) | -25, now -22; built -19 (#446) | M; Opus plan and implementation, Sonnet tests |
| 1c | 0.23.0 | none (coded sites gain a code) | `library-unusable` (planned as a variant of `library-missing`; its own family on review, final), helper `optional_libraries.import_failed(requirement, exc)` for about 11 sites | user / thinner | 0; built 0 (#446) | S-M; Opus; may ride with 1b |
| 2b | 0.23.0 | card-unreadable 3 (`enrich/readme.py` 2, `_loom_dataset_meta.py` 1); source-unreadable 5 and over-cap 2 (`fetch_json`, `extract/_extract_utils.py`); croissant passthrough 1; `id_registry/_types.py` indexing read 1; `core/path_confine.py` passthrough 1; lone surrogate (`warn_lone_surrogates`, 6 callers, helper in `logging_config.py`, out of scope); `find_card_file` silent (adds a line) | `card-malformed`, `text-malformed` (weaker); reuse `file-unreadable` (first `ERROR` template), `dir-unlistable`, `over-cap`; JSON parse as `json-malformed` (R4) | user / thinner (`text-malformed`: weaker) | -13, now -13 (helper move: 0); built -10 (#444) | M; Opus |
| 3 | 0.24.0 | usage-error 16; input-not-found 25 (26 by the classifier; `_license_text_match.py:94` is PR 18's); sbom-input-invalid 7; option-no-effect 1 (helper body, about 7 calls); not-a-model 2; hf-input-invalid 1 | `input-not-found` (helper first); `option-no-effect`; `option-invalid`, `option-conflict`; `sbom-malformed` or `sbom-invalid`; `target-wrong-format` | caller (first use) / not-written | -52, now -52 | M-L; Opus plan, Sonnet helper and sites |
| 4 | 0.24.0 | command-failed-wrapper 1 (13 calls of `cli_error_handler`); command-summary 6; hook-status 6; env-decision 4; env-tool-failed 2; interrupted 1; CLI passthrough 11 (`cli/commands/utils.py` 3, `cli/id.py` 3, `cli/options.py` 3, `_sbom_io.py` 2) | `interrupted` (bare); env tool as `tool-unusable`?; summaries per R1; passthrough forwards the code (`relay_extra`, `code_of`) (R6) | per entry | about -31, now -31 | L (many stderr tests); Opus |
| 5 | 0.24.0 | registry-file-invalid 24 (`id_registry/_format.py` 20); the `PATH` error 1 (`_types.py:364`); unknown-key 2; escaped-text 3 (plan: 2) | `registry-malformed`, `registry-unknown-key`, `file-unreadable` `ERROR` form, `registry-invalid` (if the advice differs) | user / not-written | -29, now -30 | M; Opus |
| 6 | 0.24.0 | registry-collision 7; registry-miss-new-id 7; registry-key-decision 20 (INFO); `import_keys.py` passthrough 1 | `registry-conflict`; `registry-entry-missing`; decisions per R1; D7's unpinned `INFO` born coded (`unpinned`) | user / weaker | -35, now -35 | M; Opus |
| 7 | 0.24.0 | registry-not-saved 5; registry-left-out 6; registry-summary 4 | `registry-unwritable`? (`unusable`?); left-out as `registry-conflict/file-set`? | user / none | -15, now -15 | S-M; Sonnet, Opus review |
| 8 | 0.24.0 | config-invalid 46, all `ERROR` (`core/_config_parse.py` 19, `_config_read.py` 5, `iri.py` 4, `_config_parse_scan.py` 3, `_models_wheel_types.py` 3; 44 templates) | ONE `config-invalid` via a helper `say_config_invalid(key, value, expected)` with a closed `expected` table (helper first) | user (R3) / not-written | -46, now -46 | L; Opus helper, Sonnet sites |
| 9 | 0.24.0 | config-file-unusable 5; config-moved 6; config-unknown-key 2; config-value-ignored 1 | `config-unusable`, `config-moved`, `config-unknown-key`; value-ignored folds into `option-no-effect` | user / none or not-written | -14, now -14 | S-M; Sonnet |
| 10 | 0.24.0 | lock-file-ignored 20 (pylock 7, requirements 4, uv 3); lock-file-unreadable 1 (`_lock_io.py:104`) | `lock-file-malformed`, `lock-file-unusable`, `file-unreadable` reuse; the `over N bytes` text is detail | user / thinner | -21, now -21 | M; Opus |
| 11 | 0.24.0 | lock-entry-skipped 20 (`_uv_graph.py` 9, `_common_warnings.py` 5, pipfile 3); dependency-skipped 7 | `lock-entry-malformed` or `-invalid`; `requirement-invalid`; the direct-reference `INFO` "not looked up on PyPI" born coded | user / thinner | -27, now -27 | M; Sonnet, Opus review |
| 12 | 0.24.0 | project-metadata-unreadable 31; project-value-ignored 5; file-discovery-fallback 12 (incl. the Hatchling `file discovery failed`); poetry-core API moved 1; `setuptools_cfg.py` passthrough 1 | `metadata-malformed` vs `file-unreadable` (split by advice); `file-discovery-unusable`?; `poetry-core-unusable`; value-ignored by cause | user / thinner | -50, now -50 | L; Opus |
| 13 | 0.24.0 | git-fetch-failed 11; git-decision 11 (INFO); git-redirect 2; network-refused 4; `git` missing 1 (`_git_run.py:121`) | `timeout`, `network-failed` (bare); `git-redirect-invalid`; `tool-missing`; `RemoteSourceError` dotted codes map onto `pitloom_code` | user / not-written | -29, now -29 | M; Opus |
| 14 | 0.24.0 | hub-fetch-failed 5; hf-decision 1; hf-unpinned 1; hf-input-invalid 1; build-subprocess 8; temp-left-behind 1; interpreter missing 1 (`_models_wheel_build_subprocess.py:133`); HF licence-file reads 2 | `network-failed`, `timeout` reuse; `unpinned`; `build-failed`, `needs-build`; `temp-dir-unusable`? | user / thinner | -20, now -20 | M; Opus plan, Sonnet |
| 15 | 0.24.0 | fragment-unusable 13; merge-conflict-kept 9; source-conflict-kept 9 | `fragment-unusable` or `-malformed`; `fragment-conflict`, `source-conflict` (merged if the advice is equal) | user / weaker | -31, now -31 | M; Opus |
| 16 | 0.24.0 | wheel-sbom-check 13; wheel-embed-action 4; archive-member-refused 10; `archive_member_names.py` passthrough 1 | `wheel-sbom-missing`, `-invalid`; `archive-member-unsafe`; embed actions per R1 | user or caller / not-written | -28, now -28 | M; Sonnet, Opus review |
| 17 | 0.24.0 | author-split 6; escaped-text 5 (plan: 6); dataset-field-invalid 7; over-cap in `provenance.py` 2; library-api-misuse 4; `_loom_active_run.py` passthrough 1; internal 1 (`provenance.py:414`, becomes `InternalError`, R7) | `author-ambiguous`, `text-escaped`?, `dataset-field-invalid`, `over-cap`, `call-invalid` (caller) | mixed | -27, now -26 | M; Sonnet |
| 18 | 0.24.0 | licence 8 (`_license_classify.py` 3, `_license_text_match.py` 2, `_core_metadata.py` 1, `_license_resolve.py` 1, `pyproject.py` 1); the `licenseid database` lines | `expression-malformed` (redesigns the ported broken-expression warning, adoption D7), `licence-not-recordable`, `licence-ambiguous`, `licence-db-missing`? ("licence" is a domain, not a condition) | user / weaker | -8, now -8 | M; Opus; after the adoption (done) |
| T14 | 0.24.0 | none (the licence provenance mapping, [licence-resolution-provenance.md](licence-resolution-provenance.md); not a catalogue PR) | none | none | 0 | after PR 18 |

Sum of the rows: 498 (the plan's 501 counted three `raise _over_cap()` sites
of `core/model_parameters.py` that the tool treats as a reader's detail,
decision J; their cap line is already `over-cap` through `warn_over_cap`,
PR 1a). The ratchet total reaches 0 when all land.

Differences from the plan, by measurement:

- 1b: 22, not 25 (the three parameter-count raises are detail, above).
- 5: 30, not 29, and 17: 26, not 27: three of the eight `escaped-text` sites
  are the ID registry's key encoding (`_format.py` twice, `_registry.py`
  once), not two.
- 3: the classifier files `_license_text_match.py:94` ("licenseid database not
  found") under `input-not-found`; it belongs to PR 18, which keeps both lines
  of that module. `id_registry/_format.py:98` ("not found or not a file") is
  PR 3's by family, though PR 5 edits the same file.
- Passthrough sites: the tool counts 19 in scope, as in the plan (1b 2, 2b 2,
  4 11, 6 1, 12 1, 16 1, 17 1). The warning relay of the adoption
  (`extract/_licenseid_relay.py:81`, `say`) is a passthrough site too, but
  the scope rule leaves out a template that is only `%s`, so it adds no count.
  It says LicenseID's own message after the sub-prefix `licenseid:`; PR 18
  decides whether that line carries a code.
- 2b moves the lone-surrogate helper into `pitloom.messages` (decision K): its
  six callers then count as coded, while `logging_config.py` is out of scope,
  so the move changes no count.
- Counts of PR 4's "about 47" stderr tests changed are not re-measured.

## Evidence pairing

- PR-A (the `Fact` value type) and PR-D (`file-unreadable` and
  `dir-unlistable` reasons, #408) are done.
- PR-B: the stub's cause as `Reason:` on a format-only model entry. Parked by
  #404 D12. It would pair with 1b; it stays parked (R5).
- PR-C1: Hub failures write `Evidence: not_measured | Reason: timeout` or
  `network-failed`; pairs with PRs 13 and 14. `PENDING` in
  `tests/messages/test_drift_sources.py` empties then.
- Not paired (later): the declared size of a model over the cap,
  `Evidence: declared` on pointers, directory sizes.

## Rulings needed before the PRs

The recommendation is in brackets.

- R1 (before 4, 6, 13, 16): `INFO` decision and summary lines (57 sites).
  [Code a decision by the condition it answers (`unpinned`, `needs-build`;
  actor none, effect none); keep pure counts in a "summary" kind left out of
  the ratchet by kind, an explicit scope rule, never by raising a count.]
- R2: frames before PR 3. [Yes; it departs from the design doc, where
  option-no-effect came before frames.]
- R3 (8): the `config-invalid` actor. [One code, actor `user`; the flag form
  belongs to `option-invalid` in PR 3.]
- R4 (2b): the JSON parse code name. [`json-malformed`, subject first.]
- R5 (1b): pair evidence PR-B. [No, it stays parked.]
- R6 (4): the 11 CLI passthrough sites forward the code. [Forward.]
- R7 (17): `provenance.py:414` raises `InternalError`. [Yes; one line, it may
  go in any PR.]

## Per-PR gate and risks

Every PR: an Opus read-only plan (codes, fields, sites, quotes, ratchet delta,
rulings), the maintainer's go, a branch from fresh `origin/main`, the two test
gates, a before and after stderr sweep (identical except the trailing `[code]`
and the decided wording). Tests per surface: the CLI (stderr line, `[code]`,
exit code), the library (`pitloom_code` on the record or exception), the hook
(`staged_sbom` stderr) and the Action where the CLI covers it; a per-family
file in `tests/messages/`; the quotes pass `test_drift_quotes.py`.

Skills text that quotes each area (the generated references replace the
quotes; the drift test holds them): 1b, 1c, 2b: `model-stub-diagnosis.md`,
`deterministic-pass.md`; 3 and 4: `cli-flags.md`, `messages.md`,
`examples.md`; 5 to 7: `id-registry.md`, `known-limitations.md`; 8 and 9:
`cli-flags.md`, `lockfile-discovery.md`; 10 and 11: `lockfile-discovery.md`;
13 and 14: `git-url.md`, `build-timeout.md`; 15 and 16: `embed-wheel.md`,
`pre-merge-check.md`, `dangling-references.md`; 18: the preflight text in all
three skills.

Risks: full-line stderr tests pin wording, so change one family at a time;
the wide PRs (3, 4, 8, 12) conflict with open work, so take each from fresh
main and never run two catalogue PRs on the same modules in parallel; a new
code is a stability promise (decision L), so no code without its plan; the
classifier is heuristic, so re-list the sites by AST in each plan.

## Serious known bugs

"Serious" means a crash, silently wrong data or identity, or a leak. The
entries are in [known-bugs.md](known-bugs.md). List decided 2026-10-30:

- Shipped in 0.22.0: a project file whose name is not valid UTF-8 crashed
  generation (#402); a plain-text provenance value with a `:` read as a key
  (#402); a direct-URL dependency was looked up on PyPI by name (#405); a
  package key without a version gave every release one id (#407); an
  unreadable project file was logged with the raw exception (#408).
- 0.23.0 (with the LicenseID adoption, merged as #437 to #440): the
  Hatchling hook finds no licence database in an isolated build. Fixed in
  #437: a declared value needs none.
- To re-check against the merged adoption (stage E sweep, else T14 in 0.24.0):
  a top match that holds only part of its licence is concluded; two
  `SPDX-License-Identifier` tags, one stated, conclude only the stated one.

## Other items outside the cuts

Evidence work only where it pairs with a family (PR-D shipped with catalogue
PR 2a). The rest of the evidence plan (model over the cap, `Evidence:
declared` on pointers, Hub failures, directory sizes) and the roadmap items
that 0.23.0 left open (`loom` SDK dataset provenance, `pkg:git` identifiers,
support-tier gaps, `contentIdentifier`) are unscheduled.
