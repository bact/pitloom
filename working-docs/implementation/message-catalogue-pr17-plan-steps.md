---
Created: 2026-11-23
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 17 (the last family PR): steps, tests, gates, risks

See also: [message-catalogue-pr17-plan.md](message-catalogue-pr17-plan.md)
(counts, sites, split, design, rulings Q1 to Q13),
[message-catalogue-pr16-plan-steps.md](message-catalogue-pr16-plan-steps.md)
(the shape this follows).

## 6. Steps and agents (per PR)

Step 1, **Opus**. Fence: `src/pitloom/messages/**`, `scripts/message_inventory/`
(17a only), `mkdocs.yml`, `tests/messages/test_<topic>*.py`.

- Entries, fields, `SAMPLES`, say-helpers.
- `--write` the reference; measure the pages.
- The import-cycle test in both orders.

Opus also owns, because each has attacker text, relay or drop semantics, or a
public surface: every `_loom_*` site (loom API); the relay rules R-a to R-c;
the safety-net drops (after P1); `_author_warnings.py` (masking of author
text); `values.py` and `croissant.py` field writers; `text-unsafe`'s property
list; `utils.py:199` and its handlers; the `ProvenanceConfig` move (Q4).

Step 2, **two Sonnets**. Common brief as PR 16's: CLAUDE.md, British English,
ASCII, no `%r`, messages through `emit` or helpers only, no generated pages,
no baseline, no git writes, the Windows notes.

| Agent | Fence | Work |
| - | - | - |
| A (conversions) | the PR's non-loom source files | mechanical swaps to Step 1's helpers: `env.py`, `scanner.py` Summary, `_generators.py`, `creation_info.py`, `iri.py`, `deps_originator.py`, `values.py` calls, `croissant.py` raises, `dataset_merge.py`, `dataset_names.py`, `_ai_package.py:421` |
| B (docs, tests) | section 4.6 files, `CHANGELOG.md`, `tests/messages/test_*_surfaces.py` | quotes to the regenerated text with `[code]`; the surface tests of section 7 from Opus's spec |

Step 3, **Haiku sweep** (no `src/`): grep `tests/` and `scripts/` for each old
text of section 1. Update the tests and run each.

Step 4, **Opus integrate**: `--write`, `--write-baseline` (expect 27, 15, 0);
page sizes; the stderr sweep; a fresh-context Opus review of the diff with the
Windows notes; Gates A and B; working docs (migration row 17, frames-forward
"PR 17", a `-build.md` log).

## 7. Tests

- Catalogue: every line through `template_problem`; each `SAMPLES` value
  renders; `subject_key` literal; `HOOK_STEP_FRAME` codes drift test.
- Hostile inputs, one per writer. Each prints one line, masked, quoted, no
  forged `[code]` (`trusted_message`): an author field `a\nWARNING: x`, ANSI,
  `https://u:pw@h`, 1 MB, `'`, `"`; dataset names and sources likewise;
  pipdeptree stderr with a newline; fickling stderr with a newline and a URL;
  a Croissant exception's text (only the type shows).
- CLI: `loom generate` of an HF model and a GGUF model with bad dataset
  fields; an sdist with bad `pyproject.toml` TOML, and one not UTF-8; a wheel
  with split authors; `--max-source-metadata-bytes 8` on a model; a model with
  a bidi name and a non-ISO release time; `--sbom-basename x.spdx3.json` on
  `embed-wheel`; `loom env` with pipdeptree failing (monkeypatched
  `subprocess.run`); `id generate --namespace ''` (argparse line unchanged,
  code `option-invalid`); a wheel batch with an unreadable wheel
  (`file-unreadable`).
- Hook: `sbom-basename = "x.spdx3.json"` and split authors, through the
  hook's WARNING path.
- Library, each asserting `code_of`: `embed_sbom_in_wheel(w, b"  ")`; a
  mutated `Creator.type`; `ProvenanceConfig(format="x")` raises at
  construction; `IdRegistry(namespace="")`; `read_croissant(absent)` and
  `read_croissant(url)` with the network mocked (failure and timeout);
  `generate_project_sbom(project_metadata=...)`.
- loom API (each a `loom.run` block): `add_output_dataset(input_datasets=["x"])`
  with no input; `set_model` with no `path=` and a registry; a path gone at
  exit, with and without a registry (fails on base); a bidi dataset name; a
  Croissant with no name, and one with a name not text; `inspect.stack`
  raising (once per process).
- Fail-on-base: P3, H1, H2 (if true), Q4 timing, the Croissant absent-file
  code, the `report_error_line` uncoded `OSError`, the sdist relay code.
- Platform: mark the file and path tests `platform`; classify with
  `-m platform --collect-only`. Windows dry-run of the `errno` and
  `os.access` paths in `_sbom_io` (untouched code; the rule only).
- Ratchet: R-a to R-c fixtures, each positive and negative (an `OSError` with
  a literal text stays counted; a helper adding text stays counted;
  `one_line(x, 200)` with a literal is not a relay).
- Mutation targets (Gate B): the registry or no-registry choice in
  `_hash_model_file`; `_count_of`'s `cap`/`count` routing; `fetch_json`'s
  URL, absent and `HTTPException` classification; the `named` versus address
  line choice and the one or many entries count; the order in
  `ProvenanceConfig.__post_init__`; `sorted` in the `text-unsafe` property
  list; the R-a errno predicate and R-b's single-statement check.

Gate A: the PR 15 build log's command block (ruff, flake8, pylint incl.
`tests/*/`, mypy, pyright, pyrefly, bandit, `message_inventory --check`,
`generate_message_reference.py --check`, full pytest `-n 4`, coverage on the
touched modules, `manual_cli_checks --only` the author, dataset and env
checks).

Gate B: mutation testing; `manual_cli_checks -j 8` in full; the Windows
dry-run; a fresh-context sweep agent; a fresh read of
`skills/sbom-generate/SKILL.md` and its changed references; the `test-all-os`
label, with `Unit tests` and `Build wheels` on the head commit.

## 8. Risks and open unknowns (ranked)

1. **Q6 safety-net drops.** A crafted card or model card that today degrades
   to a WARNING could fail a run. P1 decides; if anything reaches the net,
   keep it and code it.
2. **Q4 timing.** A library caller holding a bad `ProvenanceConfig` that never
   emitted provenance now fails at construction. Public surface; CHANGELOG
   Changed.
3. **Scope rules hiding real lines.** R-b could pass an uncoded exception
   through unseen, which is why Q9 adds the `OSError` wrap. R-a must not match
   a Pitloom-texted `OSError` (negative fixture). `DETAIL_EXC` and
   `INTERNAL_PAT` already hid H1 and H2: audit both in a follow-up.
4. **Page sizes.** `files` at 28,433 B gets only the advice edit; `targets`
   (27,547 B) gets nothing (INPUT_KINDS lives on the `values` page).
   Remeasure every skill twin.
5. **Source file sizes.** `_ai_package.py` (499 lines), `provenance.py` (507)
   and `_loom_active_run.py` (518) are at or over the soft limit. Move helpers
   out rather than grow them (`_display_text.py` for the escape warning).
6. **Wording churn quoted by skills.** The `loom: model` to `ID registry:`
   change and the author lines are quoted in four skill or doc files (4.6). A
   missed quote leaves a skill explaining a line no longer printed.
7. **Q2 subject spelling.** `SOURCE=` is a new subject key; a later move to
   `FILE=` would be a rename after release.
8. **Hook frame.** Whether the hook's WARNING lines of these codes need
   `HOOK_STEP_FRAME` codes (unknown until step 1 reads `plugins/hatch.py`).
9. **H3.** Silent network swallows in `deps_originator` and `deps_pypi`. Out
   of scope; roadmap.

### Critical files

`src/pitloom/extract/_author_warnings.py`,
`src/pitloom/extract/dataset/values.py`, `src/pitloom/_loom_model.py`,
`scripts/message_inventory/_scope.py`, `src/pitloom/messages/_topics.py`.
