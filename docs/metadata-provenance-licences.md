---
Created: 2026-10-15
Last-Modified: 2026-10-23
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
`licenseid` (`method: licenseid_detection`). The text is matched as
written and without its copyright notice lines; the better-scoring of
the two decides. When two licences match almost equally (a modified variant scores
just above the licence it modifies), the one the project states wins; with
none stated, there is no detection. A GPL-family `-only`/`-or-later` pair,
which the text cannot tell apart, is not such a tie, nor is a licence the
text fits measurably worse: matched less closely, or of which the text
holds less (MIT's text is a quarter of `FSL-1.1-MIT`). Either way counts as
Pitloom's own independent-detection procedure. Both sides are normalised
before comparison -- not just casing (a declared `"mit"` and a detected
`"MIT"` are recognised as the same licence), but also equivalent compound
expressions written differently (`"MIT AND MIT"` and plain `"MIT"`;
`"MIT OR Apache-2.0"` and `"Apache-2.0 OR MIT"` all normalise to the same
value) -- so none of these are misreported as a conflict.

- If the project states no licence, the directory's value is recorded as
  `hasDeclaredLicense`: a `CITATION.cff`, `codemeta.json` or `LICENSE` file
  in the project is the project's own statement, however it was read.
- If both exist and **agree**, both `hasDeclaredLicense` and
  `hasConcludedLicense` are recorded, pointing at the same licence. A
  licence name that is the SPDX License List name of the other value's id
  (a classifier's `MIT License` and a detected `MIT`) agrees too: two
  elements, no conflict.
- If both exist and **disagree**, both are still recorded -- pointing at
  two different licences -- and Pitloom adds a `conflict` Annotation
  (`field: "license"`) on the package listing both candidates and where
  each came from, so the disagreement is visible rather than one value
  silently overriding the other:

  ```json
  {
    "candidates": [
      {"role": "declared", "source": "Source: pyproject.toml | Field: project.license", "value": "MIT"},
      {"role": "detected", "source": "Source: LICENSE | Method: licenseid_detection | Tool: licenseid==0.3.0", "value": "Apache-2.0"}
    ],
    "field": "license",
    "kind": "conflict",
    "schema": "https://pitloom.dev/provenance/conflict/1"
  }
  ```

  `role` says *whose* determination each candidate is: `declared` is the
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
| Anything else (a licence text, `Apache2`) | a `SimpleLicensingText`, as written less its leading blank space and final line breaks |
| `NOASSERTION`, `UNKNOWN` (any case) | no element: the relationship points at the `NoAssertionLicense` individual |
| `NONE` (any case) | no element: the relationship points at the `NoneLicense` individual |
| Absent or blank | nothing: no licence relationship at all |

A deprecated id ending `+` becomes its `-or-later` successor (`GPL-2.0+` is
`GPL-2.0-or-later`). A bare deprecated `GPL-2.0` stays as written, because
whether `-only` or `-or-later` was meant is unknown. Text that has an
operator or parenthesis and a known id, so looks like a broken expression
(`MIT OR`), is kept as text with one `WARNING:` per value.

Three provenance keys record what changed, in the entry's `license` field:

| Key | Meaning |
| --- | --- |
| `Normalized-From` | The value as the source wrote it, when recording changed it (`mit`, `UNKNOWN`, `GPL-2.0+`). |
| `Normalizer` | The `py-spdx-license` version that parsed it; present with `Normalized-From` only when a parse took place (not for `UNKNOWN`/`NONE`). |
| `Deprecated-License-Id` | A deprecated id kept as written, with the successors it could mean (`GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)`). |

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
are one `LicenseExpression`, the AND of `LicenseRef-pitloom-classifier-<name>`
terms sorted by classifier, whose `customIdToUri` maps each term to a
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
