---
Created: 2026-10-10
Last-Modified: 2026-10-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Extras, edge kind and authors on every route

See also: [extra-lifecycle-scope.md](../design/extra-lifecycle-scope.md)
(optional scope setting, not built),
[author-entity-recognition.md](../design/author-entity-recognition.md)
(NLP / NER candidate),
[roadmap-completed.md](roadmap-completed.md#bugs-fixed-in-0210),
field notes [spdx-modelling.md](sbom-generator-field-notes/spdx-modelling.md)
sections 4 and 5.

**Status:** built on branch `optional-dependencies-parity`
([#300](https://github.com/bact/pitloom/pull/300)); docs, skills and
CHANGELOG done. Open items are listed [below](#open-questions) only.

## Why

PyThaiNLP v5.4.0: the Action's SBOM (wheel route) had 79 packages, 78
`dependsOn`, 82 `Person`; `loom project .` had 3 packages, 2 `dependsOn`,
3 `Person` (files and AI models identical). The wheel and sdist routes keep
every `Requires-Dist` (152 of 154 carry `extra ==`); the directory route read
`[project].dependencies` only.

## What was decided and built

- **Extras on every route**, tagged `; extra == "x"` as a wheel writes them
  (one helper, `core/requirements.py`); Poetry `[tool.poetry.extras]` and
  setuptools `[tool.setuptools.dynamic]` requirement files included.
- **Edge kind:** an extra's edge is `hasOptionalDependency` with **no**
  lifecycle scope (an extra's name cannot back one); a required edge is
  `dependsOn` + `runtime` (`assemble/spdx3/_dep_scope.py`).
- **Self-reference** (`demo[dev]`) adds no package; the including extra goes
  into the comments of the requirements it pulls in.
- **Lock pins** for the project's own extras' direct requirements (uv,
  Poetry, PDM; no transitive closure; `extract/lock/_extra_pins.py`). An
  extra-only dependency the lock also resolves **stays optional**: a lock
  reaches the document as a flat `name==version` list, not who needs whom
  (`time-machine` in the `pendulum` fixture is in Poetry's `main` group yet
  only a `test` extra and group need it).
- **Authors:** all of them, in declared order, as `originatedBy` and in the
  copyright text; maintainers are out; Persons are minted last so no id
  renumbers; copyright holders follow the `originatedBy` identity, with the
  email only where two identities share a name (`_main_authors.py`).
- **One author reading by field kind, not by surface**
  (`extract/authors.py`, `_author_parts.py`): an address field
  (`Author-email`, `author_email`) splits on `,` and `;` outside quotes and
  `<...>`, never on `and`, with one `WARNING:` per document when a cut follows
  a name; a name field (core-metadata `Author`, `setup.cfg` `author`,
  `setup.py` `author=`, a dependency's record) is cut only next to an address,
  so `Doe, Jane` and `Ann and Bob` are one author each and a project's own
  name field holding `,`, `;` or `and` gets one `INFO:`; a structured entry
  (`[project].authors`, a Poetry `authors` string, a quoted `Author-email`
  display name) never splits. The rule as users see it is in
  [metadata-provenance-authors.md](../../docs/metadata-provenance-authors.md).
  No heuristic: see
  [author-entity-recognition.md](../design/author-entity-recognition.md).
  Dependencies are read as a package's own wheel is (`Author` names beside
  `Author-email`); their splits give one summary line per document; an
  unusable dependency address is dropped silently. `embed-wheel
  --project-dir` warns only when the wheel's own authors are used.
- **setuptools dynamic requirement files**, as setuptools 84 reads them
  (measured): files joined and parsed once, no `-r`, strict UTF-8, a missing
  file warns. Pitloom adds a 1 MiB cap and confinement to the project
  directory (`extract/project/_setuptools_dynamic.py`).

## Measured limits worth keeping

- Hatchling 1.32 expands a self-reference and sorts requirements;
  setuptools 84 keeps `demo[dev]`; poetry-core 2.5 keeps it and writes the
  **first author only**. A non-optional dependency listed in
  `[tool.poetry.extras]` is written extra-only.
- `METADATA` splits `Author:` (names) from `Author-email:`, so declared
  author order is unrecoverable from a bare wheel; a name-only plus an
  email-only author is indistinguishable from a legacy `author`/
  `author_email` pair; `Doe, Jane` stays one author (a name field is cut only
  next to an address).
- pdm-backend and pyproject-metadata write `Unknown <a@x>` for an
  email-only author; Pitloom reads `Unknown` there as no name.

## Fixed after the 2026-10-10 reviews

Code, then tests: a test must not pin what a backend or the spec contradicts.

- Warnings: extras name their real source and honour `quiet`; an unparsable
  dependency warns once; an unreadable or over-cap `pyproject.toml` read for
  authors warns on the sdist route as on `embed-wheel --project-dir`.
- Poetry: a 2.x project without `tool.poetry.name` keeps its dependencies and
  extras; an empty `[project]` list defers to Poetry's own (poetry-core tests
  truthiness; a non-empty list still ignores `[tool.poetry.extras]`); a
  list-form dependency is read table by table (the required entry stays);
  git-sourced dependencies warn truthfully.
- Authors: `Author-email` entries are checked as written (`a@b c` is not
  recorded as `a@bc`); an `<addr>` inside a free-text `Author` is an address,
  never a name; "and" inside a word does not split; a trailing "and others" /
  "et al." stays one group on every free-text surface, as in a table; a
  `setup.py` `UNKNOWN` author no longer wipes `setup.cfg`'s, and a bare
  `UNKNOWN` gives no authors and no provenance.
- Copyright: `copyrightText` is never generated (SPDX 3.0.1: the notices
  found). The main package gets the notice lines found in its LICENSE /
  LICENCE / COPYING / COPYRIGHT files on every route (one shared extractor,
  `extract/copyright_notices.py`; templates and prose such as "the copyright
  holder" are not notices), else `NOASSERTION`, never `NONE`; provenance
  `copyright_notice_lines`. The authors feed `originatedBy` only.
- Identity: the agent type is part of an agent's identity (`agent_key()`): a
  creator Organization and a same-named Person are two Agents; a padded
  creator name merges with the author. A non-PEP 508 dependency string named like the project is a
  non-reader again, so harvest still pins the main package.
- setuptools dynamic: a file is opened as written (a `..` through a missing
  directory is "not found" on POSIX, as in setuptools); a blank extra marker
  part warns and skips.
- Fixtures and tests: `readeckbot` removed (no licence); `-text` and
  `.editorconfig` exceptions keep vendored bytes; the real-world extras test
  compares extra names with the raw table and pins exact strings
  (`etils`: 66 raw entries expand to 123, pinned as the expansion); limits
  are named `*-limit`.

Review of the final tree (security, performance, correctness):

- Denial of service: self-reference expansion is iterative and capped
  (100,000 entries; 64 nested markers), the closure is computed once, author
  splitting is one pass (a wheel `Author` of `"a,"*80000` took 50 s, now
  0.03 s), the copyright placeholder check is linear, setuptools dynamic
  files are read once with a 4 MiB total budget.
- Every cap warns through ONE helper (`logging_config.warn_over_cap`, `Cap`);
  `tests/test_cap_warnings.py` fails when a `MAX_*`/`*_CAP`/`*_LIMIT`
  constant neither uses it nor has an allow-list reason.
- Licence files are read only inside the project (symlinks out refused with a
  warning); the FSF notice inside a GPL/LGPL/AGPL text is not the project's
  and is dropped (`dulwich` => `NOASSERTION`); the sdist route reads
  `[tool.poetry].authors`; `<addr>` plus a trailing "and others" and
  Hatchling's joined `Author` read per part; extras and file names in
  warnings are escaped; a lock warning prints once.

A required dependency that an extra also lists keeps its plain required edge
(`dependsOn` + `runtime`, no `also in extras` comment; decided 2026-10-11):
the edge already states the full fact, the extras stay in `declared_constraint`
provenance, and a wheel's `Requires-Dist` cannot reproduce the comment.

A contributor group ("Ann and others", "J. et al.") stays whole as an
Organization. Decided 2026-10-11 and since narrowed: Hatchling's joined
`Doe, Jane, Ann and others` was read per comma-separated part (Person Doe,
Person Jane, Organization "Ann and others"); a name field is now cut only next
to an address, so that string is one `Organization`
([metadata-provenance-authors.md](../../docs/metadata-provenance-authors.md)).

Edge scope by source (decided 2026-10-11): declared required, locked
transitive and phantom dependencies are `dependsOn` + `runtime` (a declared
requirement or bundled code is needed to run); `loom env` edges stay a plain
`Relationship`: an installed package gives a version, not evidence that
something is used at runtime (it may be a development tool or an extra the
environment pulled in), and a scope there waits for a user-stated mapping.

`loom env` lists no extras and no root authors (decided 2026-10-11): it has
a synthetic root, not a project, so nothing there declares them. Each
installed package's authors are read as dependency originators, and its
`Provides-Extra` names extras the distribution defines, not extras the
environment installed; the installed graph already holds the real edges.

An extra-only direct dependency that a lock also resolves **stays
optional**: the lock is a flat `name==version` list, and a Poetry package in
`groups = ["main", "test"]` with `optional = false` (`time-machine` in the
`pendulum` fixture) is not proven runtime-required.

Third review round (2026-10-11), fixed: splitters tested uncapped for
linear time; `Ann <a@b c>` keeps the name; GNU/GFDL title forms (markdown,
RST, mixed case); author cap warns only where the read is used, once per
whole field; `<...>` commas stay whole; typographic quotes; one confinement
helper (`core/path_confine.py`) for licence and setuptools-dynamic reads;
licence cap through `Cap`; one extra-gate rule (`core/extra_gate.py`);
self-reference cycle warns once. Pitloom's expansion differs from Hatchling
1.32.3 (marker kept, no sort, cycle dropped) by design; edges agree.
Known gaps: embed path with `pitloom_config=` skips adopted-author
warnings; `authors.py` ~544 lines; `deps.py`/`_license.py` ~505 lines;
`_models_wheel_setuptools.py:120` textual parents check; dynamic reader
dedups by resolved path (letter-case symlink spellings read twice).

Fixed 2026-10-12: those two gaps (`is_inside`; read-once by the file opened,
so `missing/../a.txt` is not served `a.txt`); the setuptools `file`
version/text reader is confined and capped (1 MiB); an outside
`project.license.file` or `project.readme` file is dropped with a `WARNING:`
(only a shape pyproject-metadata reads a file for, so its own errors stay);
a `project.license.file` `Source:` is project-relative. Not confined by
design: the model-card enricher (a Hugging Face cache `README.md` is a
symlink into `blobs/`) and the Hatchling hook (Hatchling reads the readme
itself). The model-card read is capped at 1 MiB (`MODEL_CARD_MAX_BYTES`),
not confined; a frontmatter closed within the cap is used.

Fixed 2026-10-14: deeply nested markers (every packaging `Requirement` and
`Marker` parse goes through `core/pep508.py`: a nesting over 64 is refused
with one cap `WARNING:` before parsing, a stray `RecursionError` takes the
same path, a guard test forbids direct calls); a field's bad
addresses are one warning per field (first three shown, an ellipsis when
cut, singular and plural counts).

Fixed 2026-10-14 (second batch): a Poetry dependency's version, extras,
`git`/`url` source and `python`/`markers`/`platform` keys are written as
poetry-core writes them (its own code converts them; combined keys keep
poetry-core's order, same environments); `[tool.poetry.dependencies]` is
ignored, with a `WARNING:`, when poetry-core ignores it; the `[tool.poetry]`
gap-fill applies only to a Poetry backend (or none declared); a `path`
dependency is skipped with a `WARNING:`. `Author-email` splits exactly like
`Author`; `Two names, two addresses` is a documented limit, not paired by
position; an `Author-email` entry is never split on `and` (one author on
every route); an entry with no `<`, `>` or `@` is a name. A requirement
with its own extra condition inside an extra is
`hasOptionalDependency` (`extras: dev, x`) with one `WARNING:`; the author
warning helpers moved to `extract/_author_warnings.py`.

Every cap warns through `warn_over_cap` (decided 2026-10-12): the model
scan bounds, labels, names and per-wheel budget, the wheel/sdist header
block and the sdist config member read `<KEY>=…: larger than the <limit>-
<unit> <purpose> cap; <outcome>`. `Cap.after("FORMAT=x")` keeps a model's
key order; `ModelOverCap` and `HeaderBlockOverCap` carry the `Cap`, a
reader's record carries it for the scanner's relay (`over_cap_of`). The
frame (`FORMAT=… FILE=…`, `metadata not read`, `identity unknown`,
`no label recorded`) is kept; the inner phrases were unified. An archive
member is `FILE=<archive>:<member>`, as the licence cap already was. The
guard (`tests/test_cap_warnings.py`) follows a `Cap` across modules
(holders, carrier assignments, returns) and has no pending list.

Fixed 2026-10-14 (third batch): a name-field `Author` is one author, cut
only after a closed `<address>` or a bare address (never after a plain name;
`Author-email` cuts after any `,`/`;` outside quotes and brackets, never on
`and`); a one-author reading of a value holding `,`, `;` or `and` gives one
`INFO:` on the core-metadata routes. `setup.cfg` `install_requires` and
`extras_require` `file:` are read by one shared reader (also the pyproject
dynamic one). No `build-backend` (or no `build-system`) uses setuptools file
discovery, as PEP 517 says. Every route shows the PEP 503 name for a
dependency (`loom env` too), the joined `declared_constraint` is sorted, the
main package keeps its declared name with a canonical PURL; `doc_uuid` changes
for non-canonically spelt projects. Dynamic version files, a dependency's
`License-File` from `RECORD`, and `[project].readme` are confined; a
`requirements.txt` the project names is not also read as a lock; an invalid
dynamic requirement line is skipped like an extras one; an invalid
requirement warning shows an excerpt. A present but unreadable dependency
`Author` no longer falls back to the Maintainer. The pylock fixtures are
exercised by `tests/extract/lock/test_pylock_real_world.py`.

Fixed after the 2026-10-14 delta review: several mailboxes joined by
`and`/`&`/newline in a name field are cut after each closed `>`; a bare
address after a name is its own author; setuptools' deprecation text for the
target project goes to DEBUG; the `attr` version reader reads parenthesised,
`;`-joined, annotated and chained assignments again (still capped); a
transitive lock package is named canonically (all six lock formats);
poetry-core's internals are resolved lazily with a drift-guard test.

Decided 2026-10-14: an empty licence file keeps its provenance (the raw key
was present: the convention); a structured author never splits; sorted joins
and canonical names accepted.

## Open questions

One line each; the long form is here only (known-bugs.md points here).
Lifecycle-scope questions are in
[extra-lifecycle-scope.md](../design/extra-lifecycle-scope.md#open-questions).
Ambiguities that need research, not a fix, are in
[open-research-questions.md](sbom-generator-field-notes/open-research-questions.md).

Decided earlier: a creator Organization and a same-named Person are
different agents (the agent type is part of the identity); PDM
`dynamic = ["optional-dependencies"]` pins nothing (silent on every
backend, documented); no per-lock "reaching path" flag now (only `uv.lock`
has a root walk; promoting an extra-only dependency from a lock stays
rejected, `time-machine`).

Reader gaps:

1. `pylock.toml` has no extras-pin extractor: `uv export` and `pip lock` write
   no `extras` keys or `'x' in extras` markers, only the selected packages
   (real fixtures under `real-world-locks/pylock/`), so a pin exists only
   when the exporter selected the extra. The extractor design needs the PEP
   751 keys from a producer that writes them (`pdm export -f pylock`
   untried: PDM is not installed).
2. An archive with no `PKG-INFO` leaves `dynamic` fields unresolved (now
   warned, not resolved); a `setup.cfg`-only archive is not read and gets
   the name `unknown`.
3. A wrapped `setup.cfg` `file:` value reads both files with no warning where
   setuptools fails the build; `long_description`/`classifiers` `file:` still
   treat a missing file silently.
4. A poetry-core wheel's `idna (>=3)` form is parsed only where packaging
   validates it.
5. `[tool.poetry]` without a `build-backend`: metadata is read from it, while
   file discovery is now setuptools (no longer PEP 517); a `setup.py` passing
   `packages=[...]` itself, and a flat layout with several top-level
   packages (three warnings in a row), still fall back.
6. An empty extra (`etils` `epath-no-tf`) has no representation in the flat
   dependency list.
7. A `uv export` with default groups folds dev tools in unmarked, so they read
   as required runtime dependencies; a lock pinning one name at two versions
   (flask `click`) is skipped with a warning and the SBOM then showed 8.5.0
   from the running environment (cause not checked; an explicit pin must not
   fall back to local introspection); every export with a project entry
   warns that its own directory entry is skipped.

Structure and tests:

8. At the soft limit: `deps.py` (500), `_embed_build_sbom.py` (500),
   `authors.py` (498). `extract/lock/uv.py` was split into `_uv_graph.py`.
9. A dependency's unusable `Author-email` entry is dropped without a trace
    (a per-document summary like the split one is the option).
10. `NOTICE*`, `license-files` and `license.file` are not read for the notice;
    a notice with no marker or no year does not match; a wheel's licence is
    METADATA-only; `loom env` has a synthetic root (copyright `NOASSERTION`).
11. `extract/_license.py` is 505 lines; `apply_in_package_license_files`
    cannot move to `copyright_notices.py` (import cycle).
12. SBOM text from new sources (`copyrightText`, Agent names, the `extras:`
    comment) carries display controls unescaped, as existing package fields do.
13. `embed-wheel` reads the project three times; the directory route reads
    every licence file four times.
14. `cli_error_handler` prints exception text raw; the `_dep_scope`
    "declared as %r" warnings and the `core/pep508.py` cap warning still print
    whole or unescaped text.
15. Third-party parsers Pitloom cannot screen for deeply nested markers or
    crafted modules: Hatchling's `core.dependencies` (a plain build crashes
    too), setuptools discovery, flit-core's whole-module parse (bounded only
    by size), `loom env`'s pipdeptree subprocess (untested).
16. Flit and PDM version files are check-then-delegate (a file swapped between
    the check and the backend's open is not caught) and read twice;
    `read_listed_file` still lives in `_setup_cfg_directives.py`; the
    setuptools `file` provenance keeps the raw value; PDM raises `TypeError`
    on a non-string `path` with no `source`; the line-based `attr` reader can pick up a
    `__version__ = "x"` inside a docstring, and skips a non-string first
    assignment where setuptools stops at it.
17. `ProjectMetadata.readme` holds pyproject-metadata's joined, often absolute
    path on the directory route (it never reaches the SBOM).
18. `requires_python` from `[tool.poetry.dependencies] python` uses the old
    caret/tilde converter (`^3.8` gives `>=3.8,<4.0.0`, poetry-core writes
    `<4.0`; same meaning).
19. Hatchling joins name-only authors into one `Author:` header, so a bare
    wheel cannot recover the declared structure (the `INFO:` says so); the
    directory route and the hook keep each declared name.
20. Author edge cases: an escaped quote inside a partly quoted name records
    nothing, with a warning; `Ann <a@x.org> and Bob <b@x.org>` gives `[]`
    in `Author-email` (the `and` cut is name-field only); an `Author` cut
    warns while the same text cut in `Author-email` does not;
    a Poetry `path` dependency is skipped on the directory route while the
    wheel carries a `file://` URL.
21. `tests/extract/project/test_setuptools_dynamic.py` is 504 lines and
    `tests/core/models_wheel/test_models_wheel_setuptools.py` 549.
