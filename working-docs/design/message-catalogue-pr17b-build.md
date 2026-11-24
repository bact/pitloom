---
Created: 2026-11-23
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 17b: authors, the loom SDK, the SBOM base name (build notes)

See also: [message-catalogue-pr17-plan.md](message-catalogue-pr17-plan.md)
(the plan and rulings), [message-catalogue-finish-plan.md](message-catalogue-finish-plan.md).

PR number #527 is a guess until the PR is opened.

(V) verified by running or reading; (I) inferred.

## 1. What was built (V)

- Step 0, the page split: `files` keeps the file and size-cap families;
  a new `text` topic ("Text and documents") takes `card-malformed`,
  `json-malformed` and `text-malformed` (`pitloom.messages.text`). New
  topics `authors` and `datasets` ("Datasets and loom runs").
- New entries (`since` 0.25.0): `author-ambiguous`, `author-invalid`,
  `project-unreadable`, `caller-info-unreadable`, `model-file-missing`,
  `reference-not-found/dataset` (on the `fragments` page, with its family),
  `sbom-name-invalid` (on `options`).
- New lines on shipped entries: `option-missing` (no model set),
  `registry-hash-missing` (a model with no `path=`, or not a file at exit,
  while a registry is loaded), `metadata-conflict` (an embed's project
  directory names another project).
- Q7: the ` -- only authors listed in pyproject.toml ...` hint left every
  author line; its text is now the entries' advice.
- Q8: a loom model not a file at exit says `registry-hash-missing` when a
  registry is loaded, else `model-file-missing`.
- Q11: an sdist's `pyproject.toml`, read for authors, relays the reader's
  coded error (`config-malformed`, `file-unreadable/not-utf8`, `over-cap`)
  as its `WARNING:` twin.
- D3: the library raises take `loom SDK: ` (`LOOM_SDK_PREFIX`, a literal
  in `messages/_loom_sdk.py`); a `croissant=` URL is `option-invalid` on
  its own line `loom SDK: croissant: must be ..., got ...`
  (`LOOM_SDK_VALUE_LINE`, `loom_sdk_invalid_value`); an `enrich_model()`
  Hugging Face source is `option-invalid` (`EXPECTED` gains `local-file`,
  `local-model`); `LIBRARY_PAT` became `LIBRARY_EXC = {"_no_active_run"}`
  plus `LIBRARY_SITES`, one function by file and name
  (`_loom_dataset_meta._declared_licence`, its `TypeError`): a new
  `raise TypeError` elsewhere stays counted. The reach of every
  `raise TypeError` site equals the base's.
- Ratchet 27 to 15.

## 2. Probes (V)

- P3, before: with no registry loaded, a model whose `path=` was gone at
  exit printed `loom: model 'm': gone.pt is not a file at exit; not hashed,
  looked up by name only`: no lookup happens without a registry, so the
  claim was false. After: `loom SDK: model 'm': path= ... is not a file at
  exit; not hashed [model-file-missing]`.
- With a registry: base printed the uncoded `loom:` line and then a coded
  `registry-entry-missing` line; now a coded `registry-hash-missing` line
  says the ungated lookup, still followed by `registry-entry-missing`.
- No `path=` and no registry: silent before and after (control).
- Hook: the `sbom-basename` warning prints without the hook frame, so
  `HOOK_STEP_FRAME` is unchanged. The hook reads `[project].authors` one by
  one, so it prints no author line.

## 3. Decisions and deviations

- The embed line says `not the wheel's %(wheel_value)s` rather than the
  plan's `the wheel's METADATA`: that 20-character core matched the
  `embed_wheel.py` help string in the drift-quotes test.
- `set_model_hyperparameters()` (and siblings) without a model raised an
  uncoded `RuntimeError("No model set ...")`; it is now coded
  `option-missing`. A scope extension: `_no_active_run` stays uncoded and
  library-exempt.
- The `enrich_model()` Hugging Face raise became `option-invalid`: needed
  to drop its `LIBRARY_PAT` text.
- `TypeError` in `INTERNAL_EXC`, not a new `INTERNAL_PAT` text (that list
  does not grow).

## 4. Review fixes (two fresh reviews, no blockers)

- `package` (`free_name_text`) and `entity` (`cut_entity_text`) are masked
  then cut to 500 characters: a 1 MB package name gave a 1,000,599
  character line no reader could take back. `entity_text` itself stays
  uncut: `namespace_conflict_line` compares two written values.
- The two other uncut values of 17b lines got fields of their own:
  `project_value` (the embed line, now quoted as `wheel_value` is) and
  `base_name` (the `sbom-name-invalid` lines, cut).
- `embed_wheel_sbom(sbom_basename=...)` names `sbom_basename`, in its
  warning and in its `option-invalid` refusal (was `--sbom-basename`);
  `embed-wheel --sbom-basename` names the option, once: the command hands
  the checked base to the library.
- A dataset declared without a name shows as `None`, as the base did.
- A family under two topics raises `InternalError` at import
  (`family_topics`).
- A non-scalar GGUF field cannot reach `scalar_text` from
  `gguf.py:233`: the header reader yields `int`, `float`, `bool` or `str`
  scalars, and an array becomes a derived length (an `int`). No code needed.

## 5. Out of scope, found while building

- Hatchling raises an uncoded `ValueError("Invalid addr_spec ...")` for a
  bad email in `[project].authors`, before Pitloom reads it.
- `_publish_input_ids` returns early when a run has no input datasets, so
  an output naming an undeclared input is unlinked silently.
- A `path=` or `FILE=` value is not cut (the shared path writers): a
  caller's 1 MB model `path=` prints a 1,000,088-character
  `FILE=...: could not read for the model hash; File name too long
  [file-unreadable]` line (probed).

## 5b. Post-PR review fixes (PR 527 review, 2026-11-24)

- `config-malformed` and `file-unreadable/not-utf8` say what an sdist
  `pyproject.toml` read only for its declared authors costs (authors from
  `PKG-INFO`, order lost), not "no fields".
- A non-text `input_datasets` item is shown as `a value of type X`, never
  `str()` of it (it may raise or be huge).
- The messages' author keys are `AUTHOR_FIELD_KEYS` (four), apart from
  `pitloom.extract.authors.AUTHOR_KEYS` (the project route's two); a test
  pins the subset.
- The registry variants of the model lines read `loom model ...`, so a
  reader can tell a loom call; the two prefixes stay (the registry frame
  matches `ID registry: `).
- `local-model` expectation names no library function (test pins it).
- Author split lines by a `(dependency, named)` table; `entity` and
  `package` share `cut_and_escaped`.

## 6. Lessons

- A fail-on-base run in this repository needs `-o pythonpath=`: the
  `pythonpath = ["src"]` setting in `pyproject.toml` wins over
  `PYTHONPATH`, so a base run silently tests the tree.
- A new template's 20-character cores can collide with any quoted string
  in `src/` (a help text); pick the wording after the drift test, not
  before.
