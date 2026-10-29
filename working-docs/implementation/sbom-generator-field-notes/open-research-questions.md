---
Created: 2026-10-14
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: ambiguities, anomalies and open research questions

See also: [README.md](README.md) (index of these notes),
[spdx-modelling.md](spdx-modelling.md) (section 4 and 5: extras and author
strings, the rules chosen),
[identity-and-archives.md](identity-and-archives.md),
[../extras-parity.md](../extras-parity.md) (the build record and the open
items of the extras, author and copyright work),
[../../design/author-entity-recognition.md](../../design/author-entity-recognition.md)
and [../../design/extra-lifecycle-scope.md](../../design/extra-lifecycle-scope.md).

Where the packaging formats cannot say what an SBOM generator needs, the
generator has to guess, refuse or warn. Each item below is a place where
Pitloom made a choice that the data does not prove. Each says what was
measured, what was chosen, and what research would settle it. Versions are
the ones measured (2026-10): Hatchling 1.32.3, setuptools 84, flit_core
4.0.2, pdm-backend 2.4.9, poetry-core 2.4.1, uv 0.10.4, pip 26.x. Items marked
*unverified* were reported by a review or a third party and not reproduced.

## 0. The general pattern: a string that may be one value or a list

The hardest cases share one shape: a free-text field where the format does
not say whether a separator splits values or belongs to one value. Every
guess is silently wrong for some input, so the generator either splits
(and may invent two entities from one), keeps whole (and may hide several),
or warns. Pitloom's rule: split only where the text proves a list, keep the
rest whole, and say once what was decided and where the declared structure
survives (`--project-dir`, the sdist).

| Field | Why it cannot be decided | Chosen |
| :--- | :--- | :--- |
| `Author` (name) | name-only structured authors and `setup.py` free text share one header; separator may belong to the name (`Doe, Jane`, `Ann and Bob`, `Simon and Schuster, Inc.`) | one author, unless several complete mailboxes |
| `Author-email` | RFC 5322 list, but backends leave "and" and legacy commas unquoted | split on `,` `;` outside quotes and brackets, never "and" |
| `Maintainer`, `Maintainer-email` | same as above | same rules as author |
| Copyright holders in a notice (`Copyright 2020 A, B and C`) | the holders are free text inside a line | verbatim, never split |
| `Keywords` (core metadata: one comma-separated header; `setup.py` accepts a string or a list) | a keyword may contain a comma or a space | *unverified*: not split by a rule of its own yet |
| `Project-URL` (`Label, URL`) | the label may contain a comma; the first comma is the spec's separator | first comma |
| `License` (free text) vs `License-Expression` | `A or B` and `GPL v2, or later` are a name, an expression or a list | expression only when the field says so |

The first four rows are decided and tested; the last three are listed so a
future change checks the same question. Open: a measured corpus study of
how often each guess is wrong, and whether a model-assisted step
([author-entity-recognition.md](../../design/author-entity-recognition.md))
beats the no-guess rule at an acceptable error rate.

## 1. The format cannot tell the author kind apart

- **A name-only author is written verbatim into `Author:`.** All four
  backends write a structured `{name = "Ann and Bob"}` as `Author: Ann and
  Bob`, and `setup.py` free text (`author="Jane, Bob"`) lands in the same
  header. A bare wheel cannot tell a list from one name that contains a
  comma or "and". Chosen: one `Author` value is one author, except where
  the text proves a list (several complete mailboxes). Open: how often does
  each reading occur in the wild? A corpus study of `Author:` values on PyPI
  would give the rate of wrong splits against wrong merges.
- **Hatchling joins name-only authors with `, `** into one `Author:` header,
  so a wheel loses the declared structure the directory route keeps.
  poetry-core writes the first author only. The declared order is
  unrecoverable from any bare wheel.
- **`Author-email` is a list, but the backends do not write it as RFC 5322.**
  A name with a comma is quoted (`"Doe, Jane" <j@x.org>`); a name with "and"
  is not (`Ann and Bob <t@x.org>`). Legacy data has unquoted commas
  (`Doe, Jane <j@x.org>`), which a list parser reads as two entries.
  Chosen: split on `,` and `;` outside quotes and brackets, never on "and".
  Open: the unquoted-comma legacy form is a guess either way.
- **Person or Organization** is not stated by any field. The only signals are
  contributor-group words (`others`, `et al.`) and the name text
  (`Simon and Schuster, Inc.`). Open: named-entity recognition, with an
  explicit error budget, as an optional step.
- **Agent identity.** An Organization and a Person with the same name are
  different agents; the agent type is part of the identity key. Open: does a
  downstream consumer expect them merged?

## 2. Extras and lifecycle scope

- **An extra's name proves no lifecycle scope.** `dev`, `test`, `lint`,
  `async` are all just extras to a packaging tool, so an extra-only
  requirement is `hasOptionalDependency` with no scope; a scope waits for a
  user-stated mapping. Open: a naming practice, and whether projects would
  adopt a convention.
- **A flat lock cannot say who needs a package.** A package a lock lists only
  because an extra needs it looks the same as a required one. Poetry's
  `groups = ["main", "test"]` with `optional = false` (`time-machine` in the
  `pendulum` fixture) is a real counterexample to promoting a package to
  required because a lock resolved it. Only `uv.lock` has a root walk that
  could answer it; the other formats do not. Open: a per-lock reaching-path
  flag, built with a second lock format that has structure.
- **`uv export` and `pip lock` write no PEP 751 extras features.** Neither
  writes `extras`, `dependency-groups` or `default-groups` or an
  `'x' in extras` marker; they resolve the chosen extras and groups at export
  and write only the selected packages. Only pipenv's file has the keys, and
  it has no `in extras` marker. The extras of a project can then be seen only
  by comparing exports of the same project made with different flags. Open:
  whether the PEP 751 keys are used by any producer for extras, and what a
  consumer should do for a lock exported with one extra.
- **An exporter's selection is invisible in the file.** A `uv export` of
  flask with its default groups folds the dev groups (mypy and the like) into
  the one package list with no marker, so they read as required runtime
  dependencies; the file keeps no trace of which group they came from. The
  same project exported with `--extra async` pins `asgiref`, which an export
  with `--no-default-groups` leaves out. The pin is right for the file; what
  it means for the project is not stated. Open: whether to warn when a lock's
  selection cannot be reconstructed.
- **A lock may pin one name at two versions** (flask's `click`, split by
  marker). Pitloom skips the pin with a warning, and the assembled SBOM then
  showed a version taken from the environment Pitloom runs in (8.5.0): an
  explicit pin of any kind should not fall back to local introspection.
  *Unverified:* the cause was not checked.
- **A uv or pip export with a project entry** (`[packages.directory]
  path = "."`) logs a warning that the project's own directory entry is
  skipped, on a valid file.
- **A dynamic `optional-dependencies` or `dependencies` is unknowable at the
  source stage** (a PDM or Hatchling plugin computes it at build time), while
  the built wheel carries it. Pitloom is silent for all backends, so the two
  routes disagree by design.
- **An extra with no requirements** (`etils` `epath-no-tf`) has no
  representation in a flat requirement list. The only faithful SPDX form seen
  is a `hasOptionalDependency` to `NoneElement`; not built.
- **A requirement carrying its own `extra ==` marker inside an extra**
  (`foo; extra == "x"` under `dev`) can never be installed unconditionally;
  recorded as optional with both extra names. Open: what the author meant.

## 3. Backends disagree on the same declaration

- **Self-reference** (`demo[dev]` inside `full`): Hatchling expands it,
  sorts, drops the marker and raises on a cycle; setuptools and poetry-core
  keep `demo[dev]`. Pitloom expands and joins the marker, so the assembled
  edges agree but the strings do not. Dense cycles are costly: 6, 8 and 10
  extras that each name all the others read 2,784, 23,552 and over 100,000
  entries, which is why the expansion has a cap.
- **Poetry:** poetry-core uses truthiness, not presence, for an empty
  `[project]` list; the `[tool.poetry.dependencies]` table is ignored under
  rules that depend on `dynamic`; the caret operator `^0.0.3` is `<0.0.4`,
  which a hand-written converter got wrong (`<0.1.0`); combined `python`,
  `markers` and `platform` keys are simplified and reordered. Chosen: call
  poetry-core's own code, and compare markers by evaluating both over 24
  environments, not by string. Open: poetry-core is a version-sensitive
  private-ish API surface.
- **No `build-system`** means setuptools legacy under PEP 517, but a generator
  built around one backend may pick another. (Being fixed in the same PR.)
- **Names:** wheels keep `Foo_Bar` where PEP 503 canonical is `foo-bar`, and a
  poetry-core wheel writes `idna (>=3)`. Open: the single display rule.

## 4. Copyright and licence text

- **`copyrightText` is only what is found.** A notice with no `Copyright`,
  `(c)` or `©` marker, or no year (`Copyright Microsoft Corporation`), cannot
  be told from prose such as "Copyright holders", so it is not matched.
- **GNU licence texts carry a Free Software Foundation notice that is not the
  project's.** It is filtered by the licence title in several forms (plain,
  Markdown heading, reStructuredText underline, GFDL, LGPL). Open: other
  licence texts with an embedded third-party notice.
- **`NOTICE*`, `license-files` and `license.file` are not read** for the
  notice, because licence detection does not read them; widening the shared
  discovery changes detection on every route.
- **An empty licence file** records provenance for a `None` value, which
  follows the "raw key present" convention; pyproject-metadata copies a file's
  text into `.text`, so a whitespace-only file is labelled `project.license.text`.

## 5. Hostile and pathological input

- **A parser's recursion limit is not a safe bound.** `packaging` raises
  `RecursionError` on about 900 nested parentheses; a 300,000-attribute
  Python expression segfaults `ast.parse` on Python 3.10 (a C-stack crash that
  cannot be caught) and raises `RecursionError` on 3.12 to 3.14. Chosen: a
  deterministic cap before parsing, and read only the line that assigns the
  attribute. Open: flit-core, Hatchling and setuptools parse the same input
  themselves and cannot be screened from outside.
- **Quadratic regex splitting.** Lookahead-based separators took 46 s on
  `'a,' * 80000`. A one-pass tokenizer fixed it. A regex holds the GIL, so a
  thread-based test timeout cannot interrupt it; the test must run the call
  in a child process.
- **Path confinement is a family of traps:** a textual `in .parents` check
  fails on a case-insensitive file system (the same directory spelled
  differently), so identity `(st_dev, st_ino)` is used with `st_ino == 0` as
  no identity (FAT, exFAT). On Windows with Python 3.12+ a path `stat` and a
  handle `fstat` can fill those fields from different APIs; the compare uses
  `fstat` on both handles, reasoned but untested on Windows. Flit and PDM are
  check-then-delegate: a file swapped between the check and the backend's own
  open is not caught (TOCTOU).
- **Warning floods are an attack surface too:** one crafted address field
  could print 1,000 per-entry lines; now one line per field.
- **Display controls** in SBOM text from new sources (`copyrightText`, Agent
  names, the `extras:` comment) are not escaped, as existing package fields
  are not. Open: one escaping rule for every text field.

## 6. What the installed environment can and cannot prove

- **Installed is not used.** A package in `site-packages` gives a version, not
  evidence that the project needs it at run time, so `loom env` edges stay
  plain `Relationship` and list no extras or root authors.
- **Reaching an installed file by `RECORD`** can walk outside the dist-info
  (`..`); confined, but the read size grew from 500 characters to 256 KiB
  before it was.

## 7. Third-party claims need checking

A list of "projects that use `pylock.toml`" supplied for fixture hunting was
wrong in several places when checked: one project's lock exists only on its
`main` branch, not at its release; an issue cited as adding a feature was
about something else; a scanner's own fixture was not valid PEP 751
(`[[package]]` instead of `[[packages]]`); another project had no lock at all.
Lesson: verify the producer, the file and the version before vendoring.
*Unverified:* whether a newer uv writes extras markers (only 0.10.4 was run).

## Keying an id registry: name or path?

Name keys collide and miss for one artefact in several ways: two model files
with one stem (`a/m.gguf`, `b/m.gguf`), a dataset package keyed by the caller's
raw string (`data/t.txt` and `../data/t.txt` miss each other while their files
hit), a src-layout file under two spellings (the one case where two keys share
an id), case and NFC/NFD on case-insensitive file systems, and a registry
rooted above the project (every file misses on `project`). A path key (the
artefact's path below the registry root, canonicalised) removes most of these,
but a wheel member, an sdist member and a `--allow-build` temporary file are
three spellings of one source path, anything without a file (a PyPI package, a
Hugging Face model) still needs a name key, and a rename becomes a new
identity. Built 2026-10-16 as a two-tier key (path where a file exists, name
otherwise); the decisions, rejected options and lessons are in
[id-registry-path-keys.md](../id-registry-path-keys.md) and
[path-keys-lessons.md](path-keys-lessons.md).
*Unverified:* how often users rename data files after pinning ids.

## Git LFS pointers: identity and the hook (#378)

*Open:* a project that contains an LFS pointer gets one document id from the
Hatchling hook (Merkle leaf = pointer-text hash, to match `RECORD`) and another
from `loom project` (leaf = oid). Does any flow combine the two, for example
enriching with fragments made from `loom project` output and then embedding the
hook's SBOM? An id derived from stated hashes on every route would also survive
`git lfs pull`, at the cost of a second identity input.

*Unverified:* how often real pointers use the older `hawser` or `git-media` URLs
or extension lines (none in five Hub samples), and whether a registry made on a
checkout is later used by archive routes often enough to matter.

*Open:* is a SHA-512 required where a pointer is listed? BSI TR-03183-2 hash
checks may want one; the sbom-enrich skill tells the user to pull and
regenerate.

*Open:* the registry key for a pointer. If the stored key is the `oid` on every
  route, an archive SBOM (which states the pointer-text digest) cannot be
  harvested back to the key without the file. Either the archive route also
  states the `oid` somewhere harvest can read, or harvest is given the project
  files. Not decided.
*Unverified:* the claim that `os.path.normcase` does nothing on macOS was
  checked against the Python documentation ("no effect under POSIX"), not on a
  Mac.

## Evidence, messages and skills (2026-10-29)

*Open:* how should an SBOM state the evidence level of a value, or that a
value was deliberately not computed? SPDX 3.0.1 and 3.1-dev have no property
for either (FG-13 in the format-gaps ledger); Pitloom writes `Evidence:` and
`Reason:` segments into its own provenance Annotation and comment, which no
other tool reads. A consumer cannot tell "no hash known" from "hash skipped
over the read cap" from SPDX alone. See
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md).

*Partly answered:* are catalogue codes the right unit for SARIF `ruleId`s?
The #390 review left room without a scheme: a family is a SARIF rule `id`,
a code a hierarchical `ruleId` (`lfs-pointer/shipped`, hence `/` and not
`.` for a variant), a code's reference section its help link. Still open:
a code names a condition (`lfs-pointer`) shared by several subjects and
surfaces, while a SARIF rule usually names one check; no SARIF output is
built (0.23.0). See
[message-catalogue-decisions.md](message-catalogue-decisions.md),
section 1.

*Partly answered:* how do you version a message contract whose consumers
are AI agents? Decision L promises a code stable from the release that
first prints it (never renamed, reused or removed while its condition can
occur; a retired code stays; a rename carries `replaces` for one minor
release), and the wording is not promised. The skills now point to a
reference generated from the catalogue rather than quoting wording by hand,
and the ratchet and the drift test hold code, reference and quotes
together. Still open: a skill body still quotes some wording, an agent may
key on either, and nothing measures whether an agent behaves the same after
a wording change, or after a new variant appears.

*Open:* a shared contract across Pitloom, `licenseid` and the conformance
checker that Lumina runs. `licenseid` words its diagnostics
`LEVEL: SUBJECT: CONDITION[: DETAIL][; ACTION]` with its own closed set of
conditions (`not found`, `download failed`) and no code; the checker's
notification ids are dotted (`spdx.parsing-error`); Pitloom's codes are
kebab words with `/` and no producer prefix, with tool names reserved as
families so a namespace stays possible. Lumina's SARIF ingest reads only
`BOM-` rule ids, so the other tools' diagnostics reach it as notifications.
Whether the three share one condition vocabulary, and how a code is
namespaced when one tool's diagnostic reaches the user through another, is
not designed; *session record:* the maintainer has the
`licenseid` 0.8.0 release in mind for it.

*Open:* does an agent that reads a `[code]` and the generated reference
behave better than one reading free text? Static tests hold the code, the
reference and the skill pointers together; none measures the agent. A
candidate evaluation: the same Pitloom output with and without codes, the
same scenarios, scored on whether the agent states the SBOM effect, relays
the advice to the right actor and does not run the fix itself.

*Open:* how do you measure whether progressive disclosure in a skill loses
behaviour? Static tests check size, orphan references and that each pointer
states a condition; the four kinds of loss in #385 were found by a read-only
agent review, not a test. Candidate: scenario evals (Pitloom output in, expected
explanation out), planned but not built.
