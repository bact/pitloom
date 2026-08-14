---
Created: 2026-08-12
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Per-file metadata extraction (SPDX-File\* header tags)

See [provenance/annotation-provenance.md](provenance/annotation-provenance.md)
and [provenance/metadata-provenance.md](provenance/metadata-provenance.md)
for the intrinsic/extrinsic role vocabulary this document's "Provenance:
intrinsic vs. extrinsic" section reuses.

Pitloom extracts metadata at the project level (`pyproject.toml`,
`codemeta.json`, `CITATION.cff`) and the dependency level (installed
package metadata). Individual `software_File` elements, however, carried
only a name and a SHA-256 hash until this feature -- nothing about who
wrote a file, under what license, or what kind of file it is, even when
the file itself declares that information in its own header comment.

Many source trees (including Pitloom's own, and REUSE-compliant projects
generally) already carry this as machine-readable
[SPDX File Tags](https://spdx.github.io/spdx-spec/v2.3.1-dev/file-tags/)
in a leading comment block:

```
# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
```

Pitloom reads this (plus a bare `Copyright (c) YYYY Name` fallback for
files that predate SPDX tagging) and records it against each
`software_File` element.

**v1 scope:** `loom project`/`loom generate`/the Hatchling build hook
only. `loom wheel` (a standalone `.whl` with no accompanying
`pyproject.toml`) needs a second, structurally different implementation
(zip-entry reads instead of real filesystem paths) and has no config
file to read a default from -- not yet built. `loom model`/`loom env` do
not scan file headers either; there is no per-file source tree to scan
in those modes.

**What is extracted:** `copyright_text` (SPDX tag preferred, bare
`Copyright (c) ...` line fallback only when no tag exists -- never
both), `file_contributors` (one raw string per `SPDX-FileContributor:`
line, kept opaque -- no name/email sub-parsing; the tag's own spec
doesn't promise that structure), `file_type` (the raw `SPDX-FileType:`
value, only when the tag is explicitly present -- never guessed),
`spdx_license_identifier` (the raw `SPDX-License-Identifier:`
expression). No attempt to regex-parse "author name + email" separately
out of `copyright_text` -- SPDX's own tag vocabulary doesn't define a
separate author tag; whatever name is in the copyright string is the
author, full stop.

## Native vs. non-native mapping

| Extracted field | SPDX 3 destination |
| :--- | :--- |
| `copyright_text` | `software_File.software_copyrightText` (native -- shared with `Package` via `software_SoftwareArtifact`) |
| `spdx_license_identifier` | `hasDeclaredLicense` Relationship + `simplelicensing_SimpleLicensingText` element (native; never `hasConcludedLicense` -- see below) |
| `file_type` | `software_File.software_primaryPurpose`, when the raw tag maps cleanly to `SoftwarePurpose`; `File.summary` for the raw tag value whenever it doesn't map |
| `content_type` (new, not from the header -- see below) | `software_File.contentType` -- a real IANA media type, detected independently of whatever `SPDX-FileType:` said |
| `file_contributors` | `File.summary` -- no dedicated native slot exists, but `summary` (on the base `Element` class) is a legitimate free-text home, not an Annotation workaround |

### `primaryPurpose` and `contentType` are independent axes

They are two separate, independently-populated facts on the same
element, not alternatives for the same one. A `README.md` can get
`software_primaryPurpose = "documentation"` (from its own declared
`SPDX-FileType: DOCUMENTATION`) **and** `contentType = "text/markdown"`
(detected independently) at the same time -- that is a more complete
SBOM, not a redundant one.

**`primaryPurpose`/`additionalPurpose` are never inferred from a
detected `contentType`.** Per the SPDX 3 spec, "Software Purpose is
intrinsic to how the Element is being used rather than the content of
the Element." A `text/markdown` file could be a `README.md`
(`documentation`) or a data file a program parses at runtime (`data`);
content-type detection has no way to know which. Only the file's own
declared `SPDX-FileType:` tag (or real project context Pitloom doesn't
have) can answer that. This is guarded by a regression test
(`test_build_file_primary_purpose_never_inferred_from_content_type`).

`primaryPurpose` is set only via this translation table, applied to the
raw `SPDX-FileType:` tag value:

| SPDX 2.x `FileType` | `software_primaryPurpose` |
| :--- | :--- |
| `SOURCE`, `ARCHIVE`, `APPLICATION`, `DOCUMENTATION`, `OTHER` | `source`/`archive`/`application`/`documentation`/`other` |
| `SPDX` | `bom` (an SPDX document describes a bill of materials) |
| `BINARY`, `AUDIO`, `IMAGE`, `TEXT`, `VIDEO`, or anything unrecognized | no `SoftwarePurpose` equivalent -- `primaryPurpose` left unset; the raw value still goes to `File.summary` |

`contentType` is detected from the file's own bytes/filename,
independent of any tag -- via [`magika`](https://github.com/google/magika)
(Google's ML-based content-type detector) first, falling back to stdlib
`mimetypes.guess_type(filename)` when `magika` isn't installed or
inconclusive. Never the raw `SPDX-FileType:` tag text itself, which
isn't MIME-shaped (`"AUDIO"` is not a valid `contentType` value; a real
MIME type like `"audio/mpeg"` is). Detection can simply fail (no
extension match, inconclusive `magika` result) -- `contentType` is then
left unset, same as any other absent field.

## Config: independently-gated toggles, in separate tables

Header-tag parsing and content-type detection are genuinely independent
features -- a binary file with no text header at all (e.g. an AI model
file) still gets a `contentType` when detection is on, regardless of
whether header scanning ran -- so they live in separate config
locations, not one bundled table. `extract-file-header` has exactly one
setting, so it's a flat top-level key; content-type has more than one
(whether detection runs, and which detector resolves it), so it keeps
its own table -- the same "fold a single-key table, keep a multi-key one"
rule applied across `[tool.pitloom]` generally (see
[Configuration](../../docs/configuration.md) for the full reference):

```toml
[tool.pitloom]
extract-file-header = true   # tag/copyright/license/contributor/file_type extraction

[tool.pitloom.content-type]
enabled = false               # magika/extension-guess contentType detection
method = "auto"                # "auto" | "magika" | "extension"
```

- **`extract-file-header` defaults on.** Header-tag parsing is pure
  regex over bytes already read into memory for the SHA-256 hash -- no
  extra I/O, no extra file open, negligible per-file cost, the same cost
  class as work Pitloom already does unconditionally elsewhere (e.g.
  `_license.py`'s LICENSE/CITATION.cff/codemeta.json scanning, which has
  no gate at all).
- **`[tool.pitloom.content-type] enabled` defaults off.** `magika`
  inference is a real, measurable wall-clock cost -- Google's own
  figures put it around 5ms/file, which adds up fast across a large
  project's file count. Same "opt-in until proven" treatment
  `[tool.pitloom] enrich` already has.
- **`method` defaults `"auto"`.** `"auto"` and `"magika"` behave
  identically per file (try `magika`, fall back to a filename-extension
  guess on an inconclusive result); the difference is that `"magika"`
  raises a clear error up front, before any file is scanned, if the
  `magika` package isn't installed at all -- you asked for it
  explicitly, so silent full-degradation would hide that every
  `contentType` in the SBOM is lower-quality than requested. `"extension"`
  skips `magika` entirely, resolving purely from the filename.

`magika` is an optional dependency, extras-gated:
`pip install pitloom[content-type]`. Unavailable with `method = "auto"`
(the default) means silent fallback to the extension guess, never an
error; unavailable with `method = "magika"` is a hard `RuntimeError`.

### Content-type overrides

A config-only table pre-empts detection for specific files the project
author already knows the content type of -- everything under `vendor/`,
every `*.woff2` font, a generated `*.min.js` -- both to save the
per-file detection cost and to get a deterministic value regardless of
what `magika` would have guessed:

```toml
[tool.pitloom.content-type]
enabled = true

[[tool.pitloom.content-type.override]]
pattern = "*.woff2"
content-type = "font/woff2"

[[tool.pitloom.content-type.override]]
pattern = "vendor/*"
content-type = "application/octet-stream"
```

Matching: `pattern` is a plain shell-glob, matched case-sensitively
(`fnmatch.fnmatchcase`, not `fnmatch.fnmatch` -- the latter case-folds on
Windows via `os.path.normcase`, which would make the same config behave
differently across platforms) against each file's `distribution_path`
(the canonical in-package path -- the same string that becomes the
`software_File`'s own `name`). `*` matches any characters including
`/`, so `vendor/*` matches everything under `vendor/`, not just direct
children -- there is no `.gitignore`-style negation or
directory-boundary distinction, since a value-mapping table doesn't need
exclusion-set semantics. First match wins, in declaration order.

**Overrides are a per-file refinement *within* the `[tool.pitloom.content-type]
enabled` gate, not a bypass of it.** When `enabled` is off, overrides
never fire -- no file gets a `contentType` at all, identical to today's
behaviour whether or not any are configured. When it's on, each file is
checked against the table first: a match sets `contentType` directly and
detection never runs for that file; a non-match still goes through the
normal detection path exactly as before. So overrides only ever save
cost/add determinism for the specific patterns configured -- they never
change whether the feature runs at all.

Role is `sbomAuthorSupplied`, not `detected` -- the config author is
asserting the value directly, Pitloom isn't deriving anything for a
match. Provenance: `Source: <file> | Role: sbomAuthorSupplied` (no
`Tool:` segment -- there's no detector to attribute).

**Config-only, deliberately.** No CLI flag (a glob -> MIME-type mapping
isn't a good fit for a scalar flag) and no Python API parameter (a
caller who wants this constructs their own `PitloomConfig`). No new
GitHub Action input either -- the Action already inherits
`[tool.pitloom.content-type]` from the project's `pyproject.toml`.

**Known limitation:** the generated SBOM records that a file's
`contentType` came from a config override (role `sbomAuthorSupplied`),
but not *which* pattern matched -- an auditor can tell a config assertion
fired, but has to check `pyproject.toml` to see which rule. Not
currently planned to change; adding a matched-pattern field would touch
every layer of the pipeline for a debugging convenience, not a
correctness gap.

### Surfaces

| Surface | How to opt in |
| :------ | :------------ |
| CLI -- `loom project`/`loom generate` | `--extract-file-header`/`--no-extract-file-header`, `--content-type`/`--no-content-type`, `--content-type-method {auto,magika,extension}` (each defers to config when omitted) |
| Python API -- `generate_project_sbom()`/`generate()` | `extract_file_header=True/False`, `content_type=True/False`, `content_type_method="auto"/"magika"/"extension"` keywords (`None` defers to config) |
| Hatchling build hook | Inherits the project's `[tool.pitloom]`/`[tool.pitloom.content-type]` automatically -- no separate hook-level key |
| GitHub Action | `extract-file-header: "true"/"false"`, `content-type: "true"/"false"`, `content-type-method: "auto"/"magika"/"extension"` inputs, mapped to the CLI flags; empty (default) defers to config |
| Content-type overrides | Config-only (`[[tool.pitloom.content-type.override]]`) -- no CLI flag, API parameter, or Action input; see above |

## Provenance: intrinsic vs. extrinsic

Everything read verbatim from a file's own header is *intrinsic* --
role `declared`, full stop, using the established shape
(`annotation-provenance.md`'s role vocabulary): `Source: <this file's
own path> | Field: SPDX-FileCopyrightText` / `SPDX-License-Identifier` /
`SPDX-FileType` / `SPDX-FileContributor` (the bare-copyright-line
fallback uses `Field: bare Copyright line` instead).

`contentType`, however it was resolved, is *extrinsic* -- Pitloom's own
procedure examining bytes or a filename, not a claim the file's header
makes -- role `detected`, using the established shape: `Source: <this
file's own path> | Method: magika_content_detection | Tool:
magika==<version>` when `magika` did the detection, or `Source: <this
file's own path> | Method: extension_guess` (no `Tool:` segment --
stdlib, not a separately-versioned dependency) when it fell back.

A file can carry both a `declared` `primaryPurpose` entry and a
`detected` `contentType` entry at once (the README.md case) -- because
who actually assessed the content type depends on gating, the
provenance line differs between an `extract-file-header`-only run (no
`contentType` entry at all) and a run with
`[tool.pitloom.content-type] enabled = true` too (a `detected`-role
entry naming whichever tool actually resolved it).

`File.summary` aggregates every fact with no dedicated native slot --
`file_contributors` (every one, every time) and any not-independently-
captured `file_type` value (the `BINARY`/`AUDIO`/`IMAGE`/`TEXT`/`VIDEO`
bucket) -- in one deterministic string per file: `"<Key>: <value>; <Key>:
<value>; ..."`, entries sorted by key alphabetically, then by value
alphabetically within a key, e.g. `"Contributor: Alice; Contributor:
Bob; FileType: AUDIO"`.

**A file's `SPDX-License-Identifier` is never `hasConcludedLicense`.**
`build_license_elements()` picks declared-vs-concluded via whether the
field's source string is in `TRANSPARENT_SOURCES` -- a file's own path
is never in that set, so calling it as-is would silently misclassify
every file's own tag as `hasConcludedLicense`. There's exactly one
candidate at file granularity and its role is `declared` by
construction, so `build_file_declared_license()` (`assemble/spdx3/deps.py`)
skips the classification heuristic entirely.

**Nothing is emitted when a file's header scan finds nothing.** No
`NOASSERTION` license/copyright per file -- a project can have thousands
of files; only files that actually said something get an entry.
Different from the dependency-completeness `NOASSERTION` policy, which
applies to a handful of packages, not every source file.

## Known limitations

- `loom wheel` does not scan file headers (v1 scope, above).
- `file_contributors` is stored as opaque strings, not split into
  name/email.
- `contentType` detection quality depends entirely on `magika`
  (when installed) or the `mimetypes` stdlib table (when not); neither
  is infallible, and a wrong or missing `contentType` is not treated as
  an error.
