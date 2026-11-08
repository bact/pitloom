---
Created: 2026-10-15
Last-Modified: 2026-11-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance: licences and copyright

See also: [Metadata provenance](metadata-provenance.md) for the
provenance annotations and the `method` values, and the other parts:
[Preserved artefact metadata](metadata-provenance-artifact-metadata.md),
[Authors](metadata-provenance-authors.md).

## How a licence source is chosen

For the project's own declared licence (`project.license` in
`pyproject.toml`), Pitloom also independently checks the project
directory for a second opinion -- `CITATION.cff`, then `codemeta.json`,
then a `LICENSE`/`LICENSE.*` file -- checked regardless of whether a
declared value was already found. A `CITATION.cff`/`codemeta.json` value
that's already a bare SPDX id is used as-is; anything else (typically a
`LICENSE` file's full text) is matched against known SPDX licences via
LicenseID (`method: licenseid_detection`). The text is matched as
written and without its copyright notice lines; the better-scoring of
the two decides. When two licences match almost equally (a modified variant
scores just above the licence it modifies), the one the project states wins;
with none stated, there is no detection. A GPL-family `-only`/`-or-later` pair,
which the text cannot tell apart, is not such a tie, nor is a licence the text
fits measurably worse: matched less closely, or of which the text holds less
(MIT's text is a quarter of `FSL-1.1-MIT`). Either way counts as Pitloom's own
independent-detection procedure. Both sides are normalised before comparison --
not just casing (a declared `"mit"` and a detected `"MIT"` are recognised as the
same licence), but also equivalent compound expressions written differently
(`"MIT AND MIT"` and plain `"MIT"`; `"MIT OR Apache-2.0"` and `"Apache-2.0 OR
MIT"` all normalise to the same value) -- so none of these are misreported as a
conflict.

- If the project states no licence, the directory's value is recorded as
  `hasDeclaredLicense`: a `CITATION.cff`, `codemeta.json` or `LICENSE` file
  in the project is the project's own statement, however it was read.
- If both exist and **agree**, both `hasDeclaredLicense` and
  `hasConcludedLicense` are recorded, pointing at the same licence. A
  licence name LicenseID reads as the other value's id (a classifier's
  `MIT License` and a detected `MIT`, both `MIT`) agrees too: one element, no
  conflict.
- If both exist and **disagree**, both are still recorded -- pointing at
  two different licences -- and Pitloom adds a `conflict` Annotation
  (`field: "license"`) on the package listing both candidates and where
  each came from, so the disagreement is visible rather than one value
  silently overriding the other:

  ```json
  {
    "candidates": [
      {"ref": "...#License-1", "role": "declared", "source": "Source: pyproject.toml | Field: project.license", "value": "MIT"},
      {"ref": "...#License-2", "role": "detected", "source": "Source: LICENSE | Method: licenseid_detection | Tool: licenseid==0.7.3", "value": "Apache-2.0"}
    ],
    "field": "license",
    "kind": "conflict",
    "schema": "https://pitloom.dev/provenance/conflict/1"
  }
  ```

  `ref` is the `spdxId` of the candidate's licence element. `role` says
  *whose* determination each candidate is: `declared` is the
  project's own stated claim; `detected` is Pitloom's own independent
  directory-search procedure's result; `sbomAuthorSupplied` is asserted
  directly by the human operating Pitloom (e.g. a
  `[[tool.pitloom.content-type.override]]` match, or a value the
  `sbom-enrich` Skill records on the SBOM author's direct say-so).
  `inferred` isn't emitted by Pitloom's own deterministic code, but is
  what the `sbom-enrich` Skill's agent-authored fragments use for a value
  the agent derived itself rather than one the SBOM author stated.
  `externalReported` remains reserved for a future candidate source (a
  linked GitHub/Hugging Face Hub API) -- not built yet.

- A `NOASSERTION` (or `UNKNOWN`) candidate is not a disagreement: it only
  says "not known". Both relationships are still recorded and no `conflict`
  Annotation is added. `NONE` against a real licence is a conflict.

The same rule applies where a project's static metadata is checked against
its installed metadata: an agreeing pair, or a `NOASSERTION`/`UNKNOWN` on
either side, is no conflict, and a real installed licence replaces a
`NOASSERTION`/`UNKNOWN` static one.

The check runs where Pitloom reads a project's own files: `loom project`
or `generate_project_sbom()` on a directory or an sdist, and the Hatchling
build hook. In an sdist it reads the root `LICENSE`, `CITATION.cff` and
`codemeta.json` of the directory holding `PKG-INFO`, as for the unpacked
directory. When the project's metadata states no licence, the detected
one is its declared licence instead. An SBOM of a wheel records only the
licence the wheel's metadata states, with no `hasConcludedLicense` second
opinion.

## How a licence value is recorded

Every licence value goes through one classification, whichever source it
came from:

| Value | Recorded as |
| --- | --- |
| A valid SPDX expression (`mit`, `Apache-2.0 OR MIT`) | a `LicenseExpression`, in canonical form (listed id case, operators upper-case, terms sorted) |
| A single-line value [LicenseID](https://pypi.org/project/licenseid/) reads as one licence (`Apache2`, `MIT License`, `GPLv3+`), or several of them joined by `AND`, `OR` or `WITH` (`Apache2 OR MIT`) | a `LicenseExpression` of the licence it names (`Apache-2.0`), see below |
| Anything else (a licence text, `BSD`, `MIT -`) | a `SimpleLicensingText`, as written less its leading blank space and final line breaks |
| `NOASSERTION`, `UNKNOWN` (any case) | no element: the relationship points at the `NoAssertionLicense` individual |
| `NONE` (any case) | no element: the relationship points at the `NoneLicense` individual |
| A whole Git LFS pointer (a licence file not pulled, read as its text) | nothing, as for an absent value: a pointer is no licence text |
| Absent or blank | nothing: no licence relationship at all |

Every expression is read by LicenseID, the one reader of a declared
value. A deprecated id ending `+` becomes its `-or-later` successor
(`GPL-2.0+` is `GPL-2.0-or-later`). A bare deprecated `GPL-2.0` stays as
written, because whether `-only` or `-or-later` was meant is unknown; so does
the id of a re-spelt one (`GPLv3` is `GPL-3.0`, `LGPL v3` is `LGPL-3.0`).
Both note the successors they could mean. A licence's prose name (`BSD
3-Clause License`) and a classifier's name (`GNU General Public License v3
(GPLv3)`) read as their id. Licences joined by `;` (`MIT; Apache-2.0`) name
no operator, so no expression: text, as written. Text that has an operator
or parenthesis and an id as written, so looks like a broken expression
(`MIT OR`), is kept as text with one `WARNING:` per value; the reason in it
is LicenseID's (`parse failed: Unexpected 'OR'`).

A value that is not an SPDX expression is read by LicenseID (`resolve`),
in any field. It is accepted when it names exactly one licence, or several
joined by an operator (`Apache2 OR MIT`): another spelling of an id
(`Apache2`, `CC BY 4.0`, `GPLv3+`, `licenseref-foo` as `LicenseRef-foo`), the
licence's List name (`MIT License`), a stated qualifier (`GPL 3.0 or later`,
`MIT or later` as `MIT+`) or a renamed id. It is never a guess: a bare
`GPL-3.0` stays as written. A value naming several licences with no operator
(`BSD`) or none stays text. So does a value with a character the reading
would drop (`Apache 2.0?`), one of several lines, and one LicenseID refuses
because a licence is not all it holds: a stray mark (`-MIT`, `.GPL-3.0-only`,
`MIT -`, `MIT...`), a list number (`1. MIT`, `iv. MIT`), a comment word
(`REM MIT`) or a plus after a space (`GPLv3 +`). A reading that changed more
than the case, white space, brackets or a `+` is said once per value per run,
and kept in the provenance:

```text
INFO: FIELD=project.license LICENSE='Apache2': read as Apache-2.0 (separator, version_spelling)
```

The reading uses the SPDX License List the `licenseid` wheel ships, not the
LicenseID database: the same value gives the same reading with or without
one. Only licence-text detection needs the database (`licenseid update
--source packaged`), and only for a text long enough to be a licence: a
declared name such as `New BSD` never looks it up, and says nothing. When
the project declares a licence and the database is only missing,
`licenseid database not found` is said once at `INFO:`: only the
`LICENSE`-file check is skipped. A declared full licence text warns
`licenseid database cannot be used` once, as it is kept as written, and so
does a `LICENSE` file with no declared licence. An empty, invalid or
unreadable database warns whenever a lookup is needed (a `LICENSE` file,
a long text, or no declared licence). A warning of LicenseID itself is
said once, after `licenseid: ` (`WARNING: licenseid: database: build v2
outdated: current v3; run 'licenseid update'`; `INFO:` for `variant not
stated`, a guess it records on a detection). `too few words for text`
(LicenseID 0.7.2 on: a text too short to match has no licence) is
`DEBUG` only.

Some fields hold an SPDX expression only. A value there that is not one
Pitloom reads (`Acme-Terms`, `MIT OR Foo`, a licence text) is still recorded
as text, as written, and gets one `WARNING:` per value per run, naming the
field:

```text
WARNING: FIELD=project.license LICENSE='Acme-Terms': not read as an SPDX license expression (not found: Acme-Terms); recorded as license text
```

| Field | Read from |
| --- | --- |
| `project.license` (a string, PEP 639) | `pyproject.toml` of a directory or an sdist with no `PKG-INFO`; the Hatchling build hook |
| `License-Expression` | a wheel's `METADATA`, an sdist's `PKG-INFO`, installed metadata |
| `license_expression` | a dependency's PyPI record |
| `SPDX-License-Identifier` | a file's header tag |
| `general.license` | a GGUF model file |

The value shows on one line, control characters escaped, cut after 120
characters. A field that may hold free text (`License`,
`project.license.text`, `[tool.poetry] license`, a Hugging Face card's
`license`) gets no such warning. Whether an id is known comes from the SPDX
License List packaged with LicenseID, so a missing database turns no id
unknown. Hatchling refuses an unknown id in `project.license` itself; the
hook warns only for an id newer than that packaged list.

These provenance keys record what changed, in the entry's `license` field:

| Key | Meaning |
| --- | --- |
| `Normalized-From` | The value as the source wrote it, when recording changed it (`mit`, `UNKNOWN`, `GPL-2.0+`). |
| `Deprecated-License-Id` | A deprecated id kept as written, with the successors it could mean (`GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)`). |
| `Method` | `licenseid_resolution` when LicenseID respelt or renamed the value; absent when only its case, white space, brackets or `+` changed. |
| `Resolution-1` | The value, what it was read as and the steps: `Apache2 -> Apache-2.0 (separator, version_spelling)`. |
| `Expansion-1` | A qualifier written out, apart from the respelling: `plus_to_or_later` (`GPLv3+`), `stated_qualifier` (`GPL 3.0 or later`, `MIT or later`). |
| `Tool` | The LicenseID version that read it. |

These notes are kept at the default `detail = "minimal"`. They land on the
licence element when this source created it. When the element already
existed (an earlier package had the same licence), the note lands on that
source's own `hasDeclaredLicense`/`hasConcludedLicense` relationship
instead, as a `comment` and in the relationship's provenance Annotation. A
named individual cannot carry a comment or an Annotation, so its notes
always land on the relationship.

A dependency's licence is looked up in order: installed
`License-Expression`/`License`, installed `License ::` classifiers, then the
PyPI JSON API. `NOASSERTION`/`UNKNOWN` is weak in that order: a later source
that states a licence wins, and the `NoAssertionLicense` individual is
recorded, with the first source's provenance, only if none does. `NONE`
ends the lookup.

The project's own `License ::` classifiers are read the same way: after
`project.license` in `pyproject.toml` (`Field: project.classifiers`, also in the
Hatchling build hook), `license` in `setup.cfg` (`Field: metadata.classifiers`),
`license` in `setup.py` (`Field: setup(classifiers=...)`), or
`License-Expression`/`License` in a wheel, an sdist or installed metadata
(`Field: Classifier`). A Poetry project's classifiers are not read: Poetry
writes the licence classifier from `license` itself. `License :: OSI Approved`
is a category, not a licence: it is left out, alone or beside a more specific
classifier under it, as if absent. `setup.cfg` `classifiers` are listed as
setuptools lists them (one per line, else comma-separated). When `setup.py`
and `setup.cfg` both state a licence, see
[setuptools projects](cli.md#setuptools-projects-setuppy-and-setupcfg).
A multi-line licence text in a wheel, an sdist or installed metadata is read
without the indent the build tool folded it with. Several licence classifiers
are one `LicenseExpression`, the AND of terms sorted by classifier: the id for
a name LicenseID reads as one licence (`MIT License` is `MIT`), else a
`LicenseRef-pitloom-classifier-<name>` whose `customIdToUri` target is a
`SimpleLicensingText` of the name as written; AND is assumed, with one
`WARNING:`, as they may offer a choice. So a directory, its sdist, its wheel and
the build hook record the same declared licence, except a licence file or text
that Pitloom identifies as a listed licence: the directory and the build hook
record its id, the sdist and the wheel the text. A directory, an sdist and
the build hook add the concluded second opinion above (a wheel only through
`embed-wheel --project-dir`). A directory's `[project].license` `file`, or
`[project].readme` file, outside the project directory (`..`, an absolute
path or a symlink out) is not read: the field is dropped with a `WARNING:`
naming it. So is a file a dynamic `version` names (`[tool.hatch.version]
path`, a setuptools `attr` or `file`, Flit's module, PDM's `path`), or one
over 1 MiB: no version is read from it.

Whose statement a licence is decides the relationship. The package's own --
its manifest, a file it ships, an AI model file's own metadata, a model card,
its own installed metadata (the project, or a `loom env` package) -- is
`hasDeclaredLicense`. A third-party record -- the PyPI JSON API, or a
dependency's installed copy read for a project SBOM -- is
`hasConcludedLicense`, as is the directory's second opinion above.

## How the copyright text is found

A package's `copyrightText` is the text of the copyright notices *found*
for it, never generated. For the main package these are the notice lines
of its own licence files: `LICENSE`, `LICENCE`, `COPYING` and `COPYRIGHT`
(bare, or `.txt`, `.rst`, `.md`) at the project root, at the sdist's
root, or in the wheel's `.dist-info/licenses/` (else its `.dist-info`
itself) -- the files the licence detection reads, in its order. A
dependency's are those of the `License-File`s its installed metadata
lists.

A notice line is `Copyright` with `(c)`, `©` or a year, or `(c)`/`©`
with a year (`Copyright (c) 2019, Brett Cannon`, `© 2020 Acme`), kept as
written with the rest of its line (`All rights reserved.`). Prose about
copyright (`the copyright holder`) is not a notice, nor is a licence
template's placeholder (`Copyright [yyyy] [name of copyright owner]`),
nor the Free Software Foundation's own notice heading a GNU licence
document (between its title line -- `GNU ... GENERAL PUBLIC LICENSE` or
`GNU Free Documentation License`, any case, alone on its line, a Markdown
heading or an underlined reStructuredText title -- and `Version
N, <date>` lines and its `Everyone is permitted to copy and distribute
verbatim copies` line): a project notice before or after the licence text,
or under such a title written inside a sentence, is kept. Several notices
are joined by a line break in file order, a repeat left out; the
provenance names the files they came from (`method:
copyright_notice_lines`).

When no file holds a notice, the copyright text is `NOASSERTION`, with no
provenance: Pitloom does not say the package has none (`NONE`). A licence
file that exists but cannot be read, is over the 256 KiB cap, or resolves
outside the project directory (a symlink out of it) or, for a dependency,
outside its `.dist-info` (a `RECORD` entry with `..`), is skipped with a
`WARNING:` naming it.
