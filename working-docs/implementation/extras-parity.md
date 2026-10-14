---
Created: 2026-10-10
Last-Modified: 2026-10-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Extras, edge kind and authors on every route

See also: [extra-lifecycle-scope.md](../design/extra-lifecycle-scope.md)
(optional scope setting, not built),
[author-entity-recognition.md](../design/author-entity-recognition.md)
(NLP / NER candidate),
[roadmap-completed.md](roadmap-completed.md#bugs-fixed-in-0210-unreleased),
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
  (`extract/authors.py`): a free-text field (core-metadata `Author`,
  `setup.cfg` `author`, `setup.py` `author=`, a dependency's record) splits
  on `,` and `and` with one `WARNING:` per document; a structured entry
  (`[project].authors`, a Poetry `authors` string, a quoted `Author-email`
  display name) never splits. No heuristic: see
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
  `author_email` pair; `Doe, Jane` becomes two authors.
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

Free-text author fields read per comma-separated part: a part that is a
contributor group ("Ann and others", "J. et al.") stays whole as an
Organization; Hatchling's `Doe, Jane, Ann and others` gives Person Doe, Person
Jane and Organization "Ann and others" with one split warning (decided
2026-10-11).

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

## Open questions

One line each; the long form is here only (known-bugs.md points here).
Lifecycle-scope questions are in
[extra-lifecycle-scope.md](../design/extra-lifecycle-scope.md#open-questions).

Decided 2026-10-12 (a creator Organization and a same-named Person are
different agents, 2026-10-11: the agent type is part of the identity):

- PDM with `dynamic = ["optional-dependencies"]` pins nothing: accepted.
  Checked: `dynamic` `dependencies` and `optional-dependencies` are both
  silent on PDM, Hatchling and setuptools (no table), so it is consistent;
  documented in `dependency-sources.md`.
- No per-lock "reaching path" flag now: a lock-only package reached only
  through an extra keeps `dependsOn` + `runtime` (known limitation,
  documented without claiming more; only `uv.lock` has a root walk, so a
  one-format fix would break parity). Revisit with `pylock.toml` (item 1);
  promoting an extra-only dependency from a lock stays rejected
  (`time-machine`).

Reader gaps:

1. `pylock.toml` has no extras-pin extractor and, ranked first, blocks the
   uv/Poetry/PDM extras pins; needs a real `uv export --format pylock.toml
   --extra x` sample (PEP 751 `extras`, marker `'x' in extras`).
2. `setup.cfg` `install_requires = file:` / `extras_require` `file:` are not
   read; the sdist pyproject fallback reads no `dynamic` field.
3. Wheel/sdist dependency names are not canonicalised for non-Hatchling
   backends (poetry-core writes `idna (>=3)`).
4. No `build-backend` gets Hatchling file discovery ("Hatchling file
   discovery failed" on `dinglehopper`); PEP 517 means setuptools.
5. With `requirements.txt` as the dynamic source, the lock cascade also
   logs "isn't pinned -- ignoring requirements.txt".
6. The directory route expands self-references and canonicalises names
   where setuptools' wheel keeps `demo[x]` and the spelling (spelling only).

Structure and tests:

7. A dynamic `dependencies` file keeps an invalid line as required
   (assembly warns) while an extras file skips it; an empty extra (`etils`
   `epath-no-tf`) has no representation in the dependency list.
8. `extract/lock/uv.py` is over the soft limit (518); splitting out the
    extras pins needs a public accessor for three private helpers. At the
    limit: `assemble/spdx3/deps.py` (500), `_embed_build_sbom.py` (491).
9. A dependency's unusable `Author-email` is dropped without a trace
    (a per-document summary like the split one is the option); the pinned
    rows `name-only-merge-open-question` follow the name-only merge, now closed by the agent-key rule.
10. `NOTICE*`, `license-files` and `license.file` are not read for the
    notice, because licence detection does not read them; widening the shared
    discovery changes detection on every route.
11. A notice with no `Copyright`/`(c)`/`©` marker or no year
    (`Copyright Microsoft Corporation`) does not match; it cannot be told
    from prose such as "Copyright holders".
12. A wheel's licence is still METADATA-only; its licence files now feed the
    copyright only. `loom env` has a synthetic root (copyright
    `NOASSERTION`); the in-tree installed reconcile reads no `License-File`.
13. `extract/_license.py` is 505 lines; `apply_in_package_license_files`
    cannot move to `copyright_notices.py` (import cycle).
14. An installed dist's `RECORD` entry with `..` passes the dist-info check
    and its `License-File` reads outside it (predates this work; reach grew
    from 500 characters to 256 KiB).
15. SBOM text from new sources (`copyrightText`, Agent names, the `extras:`
    comment) carries display controls unescaped, as existing package fields do.
16. `embed-wheel` reads the project three times
    (`_adopt_project_authors`, `_embed_generate`, registry peek); the
    directory route reads every licence file four times.
17. The split hint names `--project-dir`, which `loom wheel` lacks;
    `cli_error_handler` prints exception text raw; `_parse_poetry_deps` and
    `deps_originator` docstrings are stale; `deps.py` (502) is over the soft
    limit and `_embed_build_sbom.py` is at 500 lines.
18. `[tool.hatch.version] path` (`pyproject_dynamic.py`) is read without
    project confinement; an absolute `path` holding `__version__` probably
    raises an uncaught `ValueError` in `relative_to(project_dir)`.
19. An empty licence file records `license_name` provenance while the value
    is `None` (predates this work).
20. `ProjectMetadata.readme` holds pyproject-metadata's joined, often
    absolute path on the directory route (`extract_readme`,
    `str(readme.file)`); it never reaches the SBOM today.
21. Third-party parsers Pitloom cannot screen for deeply nested markers:
    Hatchling's own `core.dependencies` raises `RecursionError` inside the
    build hook (a plain Hatchling build crashes too); setuptools file
    discovery parses `install_requires` itself, so its warned fallback
    depends on the Python version for nesting around 400 to 900; `loom env`
    runs pipdeptree in a subprocess (untested with a crafted `METADATA`).
    The `_dep_scope` "not a valid PEP 508 requirement" warning prints the
    whole text (about 1.8 KB for a crafted line).
22. `requires_python` from `[tool.poetry.dependencies] python` still uses the
    old caret/tilde converter (`^3.8` gives `>=3.8,<4.0.0`, poetry-core
    writes `<4.0`; same meaning); `format_python_constraint` is the follow-up.
23. A name-only structured author (`{name = "Ann and Bob"}` or `"Doe,
    Jane"`) is one author on the directory route and the hook, but two on
    the wheel, sdist and installed routes: backends write it into `Author`
    verbatim, where `setup.py` free text also lands, so the reader cannot
    tell them apart. Measured with Hatchling 1.32.3, setuptools 84,
    flit_core 4.0.2 and pdm-backend 2.4.9; `Author-email` (name and
    address) agrees everywhere. Needs a ruling: never split `Author` either
    (which un-splits `setup.py` free text too)?
24. A Poetry `path` dependency is skipped on the directory route while the
    wheel carries a `file://` URL (by design, not portable).
