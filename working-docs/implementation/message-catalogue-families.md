---
Created: 2026-11-05
Last-Modified: 2026-11-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue: the families built

See also: [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(the design, decisions A to M),
[message-catalogue-migration-plan.md](../design/message-catalogue-migration-plan.md)
(the PRs still to come).

The decisions each catalogue PR took for its families, in the order built.

## The `over-cap` family

Decided 2026-10-29 for #396 (the maintainer took the recommendations):

1. One code, `over-cap`, no variant. The advice differs only between a cap
   a setting sets and a fixed one, and the line names the setting (its
   purpose is the setting's name), so one advice states both; a variant per
   setting would be a stability promise (decision L).
2. `Cap`, `warn_over_cap` and `over_cap_of` live in `pitloom.messages`:
   `Cap` renders and checks itself through the catalogue's fields. The
   logging module imports nothing of the catalogue.
3. Two warning shapes: the input after its key (`FILE=`, `DIR=`, `FIELD=`,
   `DATASET=`, `MARKER=`, `REQUIREMENT=`), or a model's `FORMAT=<format>
   FILE=<file>`, chosen by `Cap.model_format` (set by `model_cap`, which
   replaced `Cap.after`), not one shape whose key holds `FORMAT=x FILE`.
4. The outcome after the semicolon stays free text (30 shapes in the suite);
   a closed outcome table is a wording PR.
5. Coded now: the sdist's config file over its cap (`CodedValueError`), a Git
   URL's checkout over `max_clone_bytes` (`git.too-large`) and a `git`
   call's output over its cap (`git.output-too-large`); `RemoteSourceError`
   gained `pitloom_code`, its `code` and text unchanged (and became
   copyable and picklable). Deferred: the three `fetch_json` raises (a URL's
   response or a file over the size cap, JSON over the nesting cap), since
   Croissant rewrites their text into its own (steps 4 and 8 rework that
   prefix for `over-cap`, `file-unreadable` and `network-failed` at once).
6. The evidence reason `over-cap` stays a literal in `core.evidence`, as
   `lfs-pointer` does: a reason is SBOM data, a code a stderr token that may
   gain variants. The drift test holds them equal.
7. The quote drift test reads a quoted line by its values (a value given has
   its field's shape; a free value never holds the family's marker), so the
   30 cap quotes in the docs and skills are checked.
8. Later PRs: the `max-source-metadata-bytes` truncation lines
   (`assemble/spdx3/provenance.py`: a user's budget, named by `spdxId`; a
   wording PR) and the lock-file `over N bytes` text (the detail of `Cannot
   read`; the lock-file PR).

Not `over-cap`: `git.too-many-redirects` (its advice is to give the final
URL), the build-timeout and `MAX_ID_NUMBER` ranges (invalid input). The
`Git source: <reason>` warning that repeats a Git URL's refusal before its
`ERROR:` stays uncoded: its prefix is no frame yet (step 6).

## The model-stub causes

Decided 2026-10-30 for #404 (PR 1a of row 1; the maintainer took the
recommendations D1 to D12 of its plan):

1. **Six codes, named by cause (D1, decision B)**: `library-missing`
   (`missing`), `reader-unsafe` (`unsafe`), `model-unreadable`
   (`unreadable`), `model-wrong-format` (`wrong-format`),
   `parameter-count-invalid` (`invalid`) and `hyperparameter-conflict`
   (`conflict`). A test holds every family to its condition, or a subject
   and `-<condition>`.
2. **`library-missing` owns its text (D2)**: `required library not
   installed: <module>; install pitloom[<extra>]`, the extra a closed field,
   never a bare `pip install <package>`; actor `user` (D3), since an extra
   changes the environment and runs native parsers on the files. It covers
   every optional library a step imports (`pitloom.core.optional_libraries`):
   the model readers, the Hugging Face Hub client, `spdx3-validate`, PyPA
   `build` and `magika`. `CodedImportError` stands beside `CodedValueError`,
   both copyable and picklable through one mixin. No field may share a name
   with a parameter of `emit` or of a coded exception (a field `extra` was
   swallowed by `emit`'s own; tested).
3. **One `model-unreadable`, no variant (D4)**: a reader's failure
   (`<error>`, free) and a bound check's (`<reason>`, a closed table of six
   texts the readers raise from `pitloom.messages`, D5; an AST test holds
   every `ModelLimitExceeded` raise to it).
4. **A closed field may repeat in a line (D6)**: `FORMAT=<format>
   FILE=<file>: header is not <format>; ...`; a free one may not.
5. **`read_ai_model()` refuses a file no reader reads as `not an AI model
   file of a supported format` (D7)**, the single-file commands' words, not
   "Unsupported model format ... Supported extensions": one code,
   `model-wrong-format`, on every surface; its effect is `thinner` (D8).
6. **A model reader's raise is detail (D9, decision J)**: a raise in
   `extract/ai_model/` but the dispatch `reader.py` is out of the ratchet by
   where it is, since only the scanner calls the dispatch and only the
   dispatch names a reader (both tested): 25 sites. With 15 sites coded, the
   ratchet fell from 556 to 516 (172 to 163 modules).
7. **Row 1 is split (D10)**: PR 1a is this one (the 18 covered sites and the
   detail rule); PR 1b, in 0.23.0, takes the model fields read in
   part (27 sites when decided, 19 at 54f79c57: `model-field-unreadable`,
   `model-field-conflict`, `model-field-invalid`, `field-not-recordable`;
   fickling's own stderr stays a relay). Six sites move: `git.not-found` and
   the interpreter to PRs 13 and 14, poetry-core's "API not found"
   (installed, its API moved: `unusable`) to PR 12, and the model command's
   URL, the project's Hub model and the usage hint (actor `caller`) to PR 3.
   The migration plan's table follows this split.
8. **The generated catalogue has its own page (D11)**:
   `docs/message-codes.md`; `docs/messages.md` keeps the grammar, the
   guarantees and the trust rule. The generator writes it, both skills'
   `references/messages.md` and, behind a second marker, the model table of
   `model-stub-diagnosis.md` (what each code leaves of a model; tested
   complete).
9. **Parked (D12)**: the stub's cause in the SBOM (`Reason:` on a
   format-only entry). No field carries it; it needs three more reason
   codes, a carrier on `AiModelMetadata`, merge semantics and edits to the
   frozen scan-limits page. After 0.22.0.

Left open: the `Build:` warning reporting a missing PyPA `build` keeps no
code, its prefix being no frame (step 6); an import that is found but fails
is reported as not installed, as before (the readers raise
`missing_library()` from any `ImportError`); `hyperparameter-conflict` is
the first entry whose actor and effect are `none`.

## The unreadable files and directories

Decided 2026-10-30 for #408 (PR 2a of row 2; the maintainer took the
plan's recommendations, PR 2a then 2b):

1. **Two families**: `file-unreadable` (`unreadable`), with the variants
   `file-unreadable/not-utf8` and `file-unreadable/outside-project`, whose
   advice differs (decision D), and `dir-unlistable` (`unlistable`). The
   codes equal the evidence reasons, which PR-D now writes for a `loom`
   dataset (`_loom_dataset_keys.digest_evidence` reads any reason).
2. **The exception picks the entry**: `warn_file_unreadable` and
   `warn_dir_unlistable` (named after `warn_over_cap`; the plan's
   `say_unread` is taken by the scanner's model-stub helper) take the
   exception, never a text: `OutsideRootError` is `/outside-project`, a
   `UnicodeDecodeError` `/not-utf8`. An absent path raises `InternalError`:
   absent is quiet, so every caller asks `is_missing_errno` first, and a
   file gone since it was found now says nothing (a dataset member, a
   registry file, a usage source).
3. **New fields**: `use` (a closed table, `READ_USES`; a test holds every
   call's `use=` to it, and each use live), `field` (a project setting),
   `dir` (written as `file`) and `failure`, which writes an `OSError`'s
   `strerror` and never its text: the raw-exception bug (an absolute path,
   `[Errno 13] ... '/home/...'`) is fixed at every site by construction,
   and `dir`'s escaping ends a newline-forged line.
4. **Text kept but the detail** ("code first, wording later"): the
   not-UTF-8 lines of a `setup.cfg` directive and of the usage scan gain
   the variant's `not UTF-8:` prefix; the model hash's `(no verifiedUsing,
   registry lookup not gated)` moved to the entry's `did`; a licence file
   is named relative to its project (a dependency's by its `RECORD` entry).
5. **Not this family, uncoded**: a listed requirements file not found and
   a name an ID registry cannot hold (each on a line of its own, allowed
   by name in `tests/messages/test_file_unreadable.py`), the `setup.cfg`
   parser's `RecursionError` (reworded), a lock file refused or unparsable,
   a wheel member, and the ID registry's explicit `PATH` error, whose
   `ERROR` form waits for the registry PRs (no `ERROR` line is catalogued
   before a site prints one).
6. **The ratchet counts a catalogue helper's calls**: a function of
   `pitloom.messages` that says its message through `emit` codes each
   caller (the inventory's second round), as `warn_over_cap` does by name.
   511 to 498 uncoded sites, 160 to 155 modules.

Left for PR 2b: the cards (`card-malformed`, the card read joining
`file-unreadable`, `find_card_file`'s silent listing), `fetch_json` (its
local read, and `over-cap` for its caps, with Croissant passing a code
through) and the lone-surrogate warning (`text-malformed`, effect `weaker`
by the maintainer's ruling).

## Cards, Croissant files and lone surrogates

Decided 2026-11-04 for #444 (PR 2b; the maintainer took the plan's
answers H1 to H9):

1. **Three new codes**, all `since="0.23.0"`, condition `malformed`:
   `text-malformed` (effect `weaker`; helper
   `pitloom.messages.warn_lone_surrogates`, which takes the name raw and
   escapes it),
   `card-malformed` (named by document, with a closed `card` field, the
   kinds of `CARD_KINDS`) and `json-malformed` (named by format, R4;
   `ERROR` only, effect `not-written`).
2. **Reused**: `file-unreadable` gains its first `ERROR` line (the same
   template as its warning) and four uses (the three cards, the Croissant
   document), raised through `file_unreadable_error`; `dir-unlistable` ends
   `find_card_file`'s silence; `over-cap` gains an `ERROR` line
   (`JSON-document` and `Croissant-nesting`). Every `fetch_json` line keys
   the document as `file-unreadable` does, `FILE=<file>: <condition> <use>`
   (`use` required, the PyPI fetch's included), so one call gives one key
   form and the line names the document; `FILE=` holds a path, a URL or a
   Hub dataset id, as the `file` field says (review of #444).
3. **Kept as given (H1, H4 to H6)**: the SBOM's surrogate line names an
   element under `FILE=` (code first); the `_loom_dataset_meta` card
   catch-all and the registry's unencodable name stay uncoded (PRs 17,
   5 to 7); a URL that cannot be fetched and an absent file stay one
   uncoded raise in `fetch_json`, its `Cannot read Croissant source` text
   kept through a `subject` argument; Croissant no longer rewrites the
   coded texts.
4. **Card lines drop `| Field(s) affected` (H8)**: the entry's `did` says
   what each kind loses. A frontmatter that is valid YAML but no mapping
   stays quiet (H9), and so does an absent card, as an absent file does
   everywhere (2a ruling 2).
5. `path_confine` raises `SymlinkLoopError`, the errno's own text: the
   resolver's text named the path.
6. 498 to 488 uncoded sites, 155 to 153 modules.

## Model fields and import failures

Decided 2026-11-05 for #446 (PRs 1b and 1c; the maintainer took the plan's
answers M1 to M10):

1. **Three new codes**, `since="0.23.0"`, in `pitloom.messages._model_field`:
   `model-field-unreadable` (condition `unreadable`, thinner; the planned
   `-invalid` folded in, M2; the PT2 tags kept as raw text too, M3),
   `model-field-conflict` (`conflict`, effect and actor `none`) and
   `field-not-recordable` (`not-recordable`, weaker, actor `none`; M4).
2. **Reader text kept (M7)**: one line per reader site, 15 for
   `model-field-unreadable`, each ending in `field_loss_suffix`; the scan's
   `RELAY_FRAME` names the model. New fields `entry`, `fields`, `part`,
   `number` and `elements`. A Keras or HDF5 problem is `ConfigProblem(part,
   error, lost)`: a template may not start with a free field.
3. **The raw `model_config` cut is `over-cap` (M8)** when the config
   parses but names no class or name: the 500-character `raw-model-config`
   cap, said by the HDF5 reader and again by the scan as the model's. A
   config that does not parse says its cut inside its
   `model-field-unreadable` line (ledger).
4. **Uncoded still**: fickling's own stderr (M5); the scan's usage hint is
   PR 3's (M9).
5. **`library-unusable`, a family of its own** (M1 as ruled on review: the
   maintainer renamed the planned variant of `library-missing`; a variant
   never changes its family's condition, decision E, and an installed
   library that fails to import is `unusable`, not `missing`).
   The code is final (decision L).
   `optional_libraries.import_failed(requirement, exc)` gives
   `library-missing` only for a `ModuleNotFoundError` naming the module
   itself (a `None` in `sys.modules` too); a submodule's name means the
   package imported, so it is `library-unusable`, naming what the import
   raised. Each optional import catches `Exception` (a broken shared library
   raises `OSError`), its body the import only: the five readers, NumPy
   (once, before any read: its helpers' `try` made an import error
   `model-unreadable`), the Hub client, magika (the failure cached, not
   `None`; in `auto` mode a broken one warns once per process and files
   take extension types) and `spdx3_validate` (a static code per branch: a
   code read from the exception counts as forwarded, uncoded). Not the build
   subprocess (`find_spec`; a child's failure is a build failure, PR 14),
   fickling (optional) nor the Hub dataset reader's own import (ledger).
6. **Drift test**: a family may list several markers (M6), and a quote in a
   table cell reads `\|` as `|`.
7. `scanner_wheel` raises `MemberReadError`, an `OSError` whose text is the
   detail of the scanner's line (`DETAIL_EXC`, M10).
8. 488 to 469 uncoded sites, 153 to 146 modules.
