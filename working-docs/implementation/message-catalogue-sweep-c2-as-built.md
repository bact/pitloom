---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-27
Last-Modified: 2026-11-27
---

# Message catalogue sweep C2: as built

See also: [message-catalogue-sweep-c2-plan.md](message-catalogue-sweep-c2-plan.md)
(the plan, sections 1 to 9, and its rulings, which these sections record
the differences from).

## 10. C2a as built: deviations and known limits

- Helpers moved to `tests/_message_quotes.py` (`quote_kind`, anchored
  matcher); the generator's helpers to `scripts/message_reference/`
  (`frames`, `sections`, `snapshot`). The release step lives in
  `working-docs/implementation/release-checklist.md`, not `CONTRIBUTING.md`.
- `quote_kind` is stricter than section 4's table: a coded quote is matched
  on its longest literal run, a catalogued quote's 12-character run must be
  template text, a prefix quote's values match only as wildcards, a summary's
  run may not sit in a free value. The marker `": not valid JSON "` (not
  `"not valid JSON "`, which marked a value-only quote).
- One `whole_seconds()` rounds every time limit up to a whole second, at
  least 1 (git used `round`; production passes 600.0, unchanged).
- Known limits, not fixed: a stale word between two wildcards
  (`git <command> stale ... did not finish`) still reads as a piece of the
  line (matcher design); `test_count_plurals.py` checks only the word right
  after a count field (`%(number)s Python files` would pass); `quote_kind`
  requires a frame on an `ERROR` relay, `line_kind` does not (true today:
  the only `ERROR` relay is framed by the CLI command).

## 11. C2b as built: deviations and known limits

Branch `catalogue-sweep-c2b-wording`, cut from main 4bb8d266 after the
merges of #544, #545 and #546.

- **Scope.** W1 and W2 shipped in C2a (#546, ruling 1); R1's dedup shipped
  in C1a (#545, ruling 10: `_loom_active_run.py` says each missing name once
  per output); ruling 8 stays for the rescan. C2b is A1-A3, D1-D3, B1.
- **Section 9 re-checked against main.** C1a did not touch
  `extract/authors.py`: `Ann <a@x.org> extra` still records `Ann` with no
  address and is noted, so A1's wording applies unchanged.
- **A1.** The `author-invalid` summary names the three causes (no
  `local@domain` address, text after a valid address, two addresses in one
  mailbox); the advice says "not one valid email address". The code is new
  in 0.25.0, so no per-line `since`.
- **A3.** `author_pairs(..., package=)` carries the package in `_Report`
  to `warn_field_cap`, whose once-memo key is `repr((package, key,
  digest))`: the project and each dependency holding one field text are
  each said once. `author_pairs`' `address_warnings` flag went (pylint
  argument cap): a `package` set now implies no address warnings, which
  only the dependency route asked for.
- **A3 line.** `over-cap` gains `PACKAGE=%(package)s %(key)s=%(name)s:
  larger than ...; %(outcome)s` (since 0.25.0); `warn_over_cap(...,
  package=)` picks it and refuses a model cap with a package
  (`InternalError`).
- **D1.** `DatasetReference.said_conflicts` is set by one helper in the GGUF
  reader (`_trained_on`), the only route that folds references before the
  assembler; `merge_dataset_references` seeds its memo with the union over
  every reference of a name. Inventory: `enrich/readme.py` and
  `huggingface_field.py` never fold (distinct names), Croissant and Hub
  dataset metadata fill in place, the enrichment document carries the
  references through, the loom SDK builds no `DatasetReference`.
  A reader conflict for `d@1` (url a vs b) also covers the assembler's
  `d@1` vs `d@2` fold of that field: "once per dataset and field" is per
  field, not per pair of values. The reader's own memo is keyed by
  `dataset_key` (the assembler's key), not (name, version): the line names no release, so `d@1` url a/b
  and `d@2` url c/e said `download_url` twice until review round 1.
- **Model file, one rule.** `AiModelFormatInfo.shown_path` (physical path,
  else path in the package, else file name) names the model in the
  `FORMAT=`/`FILE=` warnings and in `dataset-conflict`.
- **D1, logger.** The reader now says the conflict on its own logger
  (`merge_dataset_into(..., say_on=)`), under `pitloom.extract.ai_model`, so
  a wheel scan relays it and `named_stably` rewrites the temporary copy's
  name to the model's path; the reader names the model by `file_name`
  (the value the relay rewrites).
- **D2.** Two lines: `FILE=%(file)s DATASET=... FIELD=...` and
  `MODEL=%(model)s DATASET=... FIELD=...`. `MODEL=` takes a new quoted
  `model` field (masked, cut), not the free `name` field of
  `usage-unparseable`. `assemble.spdx3.dataset.dataset_model()` names a
  model by `physical_path`, `file_path_relative`, `file_name`, else
  `resolve_name()`; so a Hub model's conflict says `MODEL=<name>` where its
  other lines fall back to the URL (ruling 6 as written). `SPELLING_LINE`
  (`dataset-conflict/spelling`, INFO, no effect) is unchanged: its
  conclusion does not depend on the model.
- **B1.** Four lines, not two: `Cap.of_model` drops a format that is no
  format (a library caller's label), so each line has a `FORMAT= FILE=`
  and a `FILE=` form; one helper `warn_metadata_budget(log, cap, where,
  keys)`. The `over-cap` `did` text reads "the line says which" (a
  `key(s)` line has no semicolon).
- **Gates.** Gate A: full suite, every CI linter with CI's commands, 100%
  branch coverage of the changed source files, manual checks
  `--only 5,7,17,20,22,25,B1,B6,B7`. Gate B: two fresh Opus review rounds
  (round 1: the reader's double line and the copied path rule, both fixed;
  round 2: docs only), 45 mutants (44 killed, the survivor `shown_path`'s
  `or None` then pinned by a test), the full manual run `-j 8` (620 pass,
  0 fail), a Windows dry run (the `file` field keeps backslashes; the relay
  replaces by callable; new tests that build archives are `platform`). No
  `SKILL.md` changed; the skills' generated references did.
- **Left open.** A Hub model's `dataset-conflict` says `MODEL=<name>`
  while its other model lines fall back to the URL (ruling 6 as written;
  revisit at the rescan if one subject per model is wanted). A direct
  `read_gguf()` call names the model by its file name in both conflict
  folds (the last `shown_path` fallback) and by its path in the reader's
  over-cap line and read error; every production route rewrites to the
  stable path. Kept: [C1b](message-catalogue-sweep-c1-as-built.md#c1b-as-built).
