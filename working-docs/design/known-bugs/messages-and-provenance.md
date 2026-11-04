---
Created: 2026-11-02
Last-Modified: 2026-11-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Known bugs: messages, catalogue and provenance

See also: [known-bugs.md](../known-bugs.md) (index, severity scale,
rules for adding an entry), [roadmap.md](../roadmap.md),
[message-catalogue-migration-plan.md](../message-catalogue-migration-plan.md),
[evidence-levels.md](../evidence-levels.md).

Message wording and codes, the message catalogue migration, and provenance
strings and annotations. Entries are ranked by priority tier, then by size
tag; see the severity scale in the index. Open entries come first; fixed
entries stay in the last section for history.

## Open

### P3: after 0.20.0

- [ ] **`Source: Pitloom generator | Method: ...` is hand-written at 3
  sites (S).** Found in the #292 review (then 7 sites): `core/ai_metadata.py`
  (`FILE_NAME_STEM_PROVENANCE`) and two in `extract/env.py`. Add one helper in
  `core/provenance.py` (e.g. `generator_provenance(method)`) and use it at
  each; `generator_provenance` does not exist yet.
- [ ] **AI model usage hint names CLI flags in library messages (S).**
  `_USAGE_HINT` (`extract/scanner.py`) says `pass --scan-model-usage` from
  `generate_project_sbom()` and the hook too; the setting text differs per
  producer. Word it per surface through one helper.

### Found in review rounds, not yet prioritised

- [ ] **`file-unreadable` is not in the generated model table (S), decided
  2026-10-30: later (0.22.x or 0.23.0).** The model header line drops the
  model, and the model hash leaves no `verifiedUsing`; add the code to the
  generated table so both are said.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [ ] **A base element holding both a value and a `not_measured` entry loses the
  entry when a fragment folds into it for an unrelated field (S).** Needs a
  forged entry, which sanitising now blocks; ruling it out means tracking which
  side of each fold supplied the entry.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [ ] **An import that is found but fails is reported as "not installed"
  (S).** A reader library that is present but raises on import gets the
  missing-extra message, which hides the real cause.
  Recommendation: add the variant code `library-missing/import-failed` with
  the error line `required library failed to import: %(module)s: %(cause)s;
  reinstall %(requirement)s` and the warning line `FORMAT=.. FILE=..:
  required library failed to import: %(cause)s`. Add one helper,
  `optional_libraries.import_failed(requirement, exc)`, that returns
  `missing()` only when `isinstance(exc, ModuleNotFoundError)` and
  `exc.name` is `requirement.module` (or a submodule of it), and the failed
  variant otherwise. Route the 11 or so sites through it (onnx, fasttext,
  gguf, safetensors, hdf5, numpy, `huggingface.py:192`, `_get_magika`,
  `spdx3_validate` in `cli/commands/utils.py`, the build subprocess) and
  `say_unread` in `extract/_scanner_messages.py`. The scanner's
  `require_library` uses `find_spec` and never imports, so the failure must be
  caught at read time. Touches `messages/_model_stub.py`, the generated
  reference, `tests/messages/test_drift_quotes.py`, the skill quotes and the
  ratchet. Target: 0.23.0.
  *Found 2026-10-30, from #404 (model stub, catalogue 1a).*
- [ ] **Catalogue 1b is not coded (S).** The 27 "model fields read in part"
  sites (`model-field-unread`) keep their free text; 0.23.0.
  *Found 2026-10-30, from #404 (model stub, catalogue 1a).*
- [ ] **The `--allow-build` `Build:` warning is uncoded (S).** It needs the
  frames PR (catalogue 4).
  *Found 2026-10-30, from #404 (model stub, catalogue 1a).*
- [ ] **A card frontmatter that is valid YAML but no mapping is silent (S).**
  `---\n- a\n---` states none of the keys read, so nothing is said; a reader
  cannot tell it from a card without frontmatter. Kept quiet in 2b (H9).
  *Found 2026-11-04, catalogue 2b plan.*
- [ ] **Wheel-member, listed requirements file and registry-unstorable-name
  lines use the unreadable family's wording for another cause (S).**
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [ ] **The Hatchling `file discovery failed` warning has no `[code]` (S).**
  Seen when a project name matched no package directory.
  *Found 2026-11-02, PyPI 0.22.0 verification (a 0.22.1 candidate).*
- [ ] **19 in-scope message sites pass another message through with no code
  (S).** Their text is another message, not a template of their own,
  so no code of the inner message is forwarded or checked: `scanner_wheel.py` 2
  (1b), `croissant.py` and `path_confine.py` (2b, fixed in #444), 11 in the CLI
  (`cli/commands/utils.py` 3, `cli/id.py` 3, `cli/options.py` 3,
  `_sbom_io.py` 2; PR 4), `id_registry/import_keys.py` (6),
  `setuptools_cfg.py` (12), `archive_member_names.py` (16) and
  `_loom_active_run.py` (17). Each goes with its family in the migration plan;
  none is fixed alone. The relay of `licenseid` warnings
  (`extract/_licenseid_relay.py`, `say`) is the same shape, left out of the
  ratchet by its `%s` template. Target: 1b and 2b in 0.23.0, the rest in
  0.24.0.
  *Found 2026-11-04, catalogue plan refresh (measured 19 at 54f79c57).*
- [ ] **`provenance.py:414` raises a plain `ValueError` for a programming
  error (S).** `assemble/spdx3/provenance.py` wraps a failure of the
  provenance encoder or of `spdx3.Annotation` as `Invalid Annotation for
  provenance schema ...`; a failure there is Pitloom's own bug (ruling R7), so
  it should raise `pitloom.core.internal_error.InternalError` (decision J),
  which leaves the line out of the ratchet by its class (one of the 498
  sites).
  One line; it can go in any catalogue PR (PR 17 in the plan). Target: 0.24.0.
  *Found 2026-11-04, catalogue plan refresh.*

## Fixed

Kept for history, with the PR. A fixed entry moves to
[roadmap-completed.md](../../implementation/roadmap-completed.md) once its
release ships.

### Fixed, Found in review rounds, not yet prioritised

- [x] **Where the `ERROR` template of the unreadable family first lands was
  open (S), fixed (#444).** It landed in `fetch_json`: a Croissant document
  that cannot be read raises `file-unreadable` with the `ERROR` form of the
  warning's template.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [x] **The lone-surrogate message was uncatalogued (S), fixed (#444).** It
  is `text-malformed` (effect `weaker`), said through
  `pitloom.messages.warn_lone_surrogates`.
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [x] **A card that does not parse had free text (S), fixed (#444).** It
  says `card-malformed`; a card read failure says `file-unreadable`.
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [x] **`fetch_json` size and nesting raises were not `over-cap` (S), fixed
  (#444).** Its JSON parse failures are `json-malformed`.
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [x] **Croissant re-raised a plain `ValueError` and dropped the code (S),
  fixed (#444).** The rewrite is gone; the code passes through.
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [x] **`find_card_file` dropped a card silently when the model directory
  could not be listed (S), fixed (#444).** It says `dir-unlistable`; an
  absent directory stays quiet.
  *Found 2026-10-30, from #408 (unreadable files, catalogue 2a; 2b and later).*
- [x] **Untagged setuptools lines on stderr (S).** Cloning
  `zzzeek/sqlalchemy` with `loom project <url>` printed
  `warning: no files found matching '*.js' under directory 'doc'` and
  `no previously-included files found matching …` with no level tag (CLI
  output rule). Not a build child: setuptools' in-process manifest step
  (`include_package_data` in static file discovery) logs through
  `distutils.log`, the root logger, which with no handler falls to
  `logging.lastResort` on stderr; `distutils.text_file` writes there itself.
  A local checkout, `--allow-build`, `embed-wheel --project-dir` and the
  library did the same; the Hatchling hook never runs setuptools discovery.
  Fixed (#356): discovery captures this thread's
  stderr and relays each line as one `DEBUG:` record (`WARNING:` for an
  `error:` line), beside #300's banners. See
  [backend-file-discovery-validation-flit-pdm.md](../../implementation/backend-file-discovery-validation-flit-pdm.md).
  *Found 2026-10-23.*
- [x] **A failed setuptools file discovery is followed by a second, wrong
  warning (S).** Fixed in 0.21.1 (#365): a per-thread flag set by every
  discoverer that logs a failure (`warn_discovery_failed`,
  `mark_discovery_failed`) makes the fallback line say the discovery failed.
  Was: after `Setuptools file discovery failed for ...` (any cause,
  e.g. a bad `%` in `[flake8]`), `_models_wheel_dispatch` also says `No static
  setuptools config resolvable ... (packages only resolvable via an
  imperative setup.py build)`, as if the config were absent. Found in the
  #357 review; `discover()` returns `None` for both.
  *Found 2026-10-27, combined review of #352 to #357.*
- [x] **After a comment merge the second `Metadata provenance:` block is not
  found by the drop helpers (S), fixed (#386).** `_merge_comment`
  joined comments with `"; "` (`_fragments_props.py`);
  `provenance_comment_parts` strips the prefix only at the start of a line. A
  provenance line now starts a line of its own on either side of the join, and
  a `not_measured` entry goes when the merged element gains the value
  (`_fragments_evidence.py`).
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [x] **An unreadable project file is logged with the raw exception (S),
  fixed (#408).** The skip in `core/_models_wheel.py` logged `exc`, and an
  `OSError` text holds an absolute path. Every unreadable-file and
  unlistable-directory line now says the system's description only
  (`file-unreadable`, `dir-unlistable`), and a directory's name is escaped.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [x] **Provenance `Source:` strings built from a file or label name outside
  `assemble/spdx3` were not sanitised (S), fixed (#389).** A `|` in the name
  added a segment (a forged `Evidence:` or `Method:`). Every provenance
  string is now built by `provenance_source`/`provenance_segment`
  (`core/provenance.py`): the setup.cfg/pyproject directives, the installed
  dist-info label, licence and copyright file and archive names, the dataset
  labels (Croissant, card, licence), the lock-file cascade, the merged
  setuptools and optional-dependency sources, `Normalized-From` and the
  `Resolution-1`/`Expansion-1` steps, a dependency marker in
  `declared_constraint` (a real forge: `os_name == "x | Evidence: ..."`),
  the loom caller and the AI-model readers. The pdm, Poetry, setuptools,
  Hugging Face and README-card sites interpolated constants only (defence in
  depth). `tests/test_provenance_builders_lint.py` keeps it so.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [x] **A project file whose name is not valid UTF-8 crashed generation (S),
  fixed (#402).** For `src/demo/\xff.py` the provenance Annotation passed (the
  sanitiser escapes the lone surrogate), but
  `export/spdx3_json.py::_graph_sort_key` raised an `rfc8785` error on the
  element's own `name`, on every surface (`loom project`/`generate`, the
  library on a directory or an sdist, the hook, a loom dataset). `to_json`
  now escapes every lone surrogate of the graph, with one `WARNING:` naming
  the first element. A model file was already escaped by its reader.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
- [x] **A plain-text provenance value with a `:` read as a key (S), fixed
  (#402).** `declared_constraint` holds requirement text, but `emit_provenance`
  parsed every value as `Key: value`: `pkg @ https://x/p.whl` gave the key
  `pkg @ https`, a marker holding a `:` one too, as did the AUTHORS URL
  (`fetched from authors at https`) and the version note (`version
  resolved`). `parse_provenance_value` now reads only its closed key set
  (the segment keys, `Source`, `Evidence`, `Reason`, the numbered ones);
  any other segment is a note. `provenance_note` writes requirement text
  and the AUTHORS sentence after `Note:` when they hold a `:`.
  *Found 2026-10-29, Opus review of the provenance code against evidence-levels.md.*
