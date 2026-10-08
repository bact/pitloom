---
Created: 2026-07-08
Last-Modified: 2026-10-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Metadata provenance

> **Note:** This is reference documentation for auditing or debugging a
> generated SBOM -- not needed to just generate one. The schema described
> below is still in beta and can change without notice between releases.

Pitloom tracks the source of each metadata field in the SBOM, so questions
like "why does the SBOM say the concluded license is MIT?" or "where did
the version number come from?" have a traceable answer.

Provenance is recorded as SPDX 3 Core `Annotation` elements -- structured,
machine-readable JSON keyed by field name -- with the original human-readable
`comment` form kept alongside for back-compat. The `format`, `detail`,
`preserve-source-metadata` and `max-source-metadata-bytes` keys of
`[tool.pitloom.provenance]` control it; their values, defaults and flags are
in [Configuration](configuration.md#toolpitloomprovenance).

By default (`detail = "minimal"`), a field only gets a provenance
Annotation when it adds something the native SPDX value can't already
convey -- e.g. the value was inferred or detected rather than read
verbatim. A value with a real native SPDX home (the license itself, the
package version, a dependency edge) is never restated in the Annotation;
only *how it was determined* is. Set `detail = "full"` for an exhaustive
per-field source map instead. A field built from more than one file names
them all, comma-separated, with each `Field` in the same order (`Source:
setup.py, setup.cfg | Field: setup(url=...), metadata.url/project_urls`);
when every one is a manifest, `minimal` leaves it out like a single
manifest read.

## Provenance examples

An `Annotation` on a package whose license was detected (not
author-declared):

```json
{
  "type": "Annotation",
  "annotationType": "other",
  "contentType": "application/json",
  "subject": "https://spdx.org/spdxdocs/mypackage-.../#Package-1",
  "statement": "{\"fields\":{\"license\":{\"method\":\"licenseid_detection\",\"source\":\"LICENSE\"}},\"kind\":\"fields\",\"schema\":\"https://pitloom.dev/provenance/fields/1\"}"
}
```

The legacy `comment` form of the same information (present when `format`
includes `"comment"`, the default `"both"` does):

```json
{
  "type": "software_Package",
  "name": "mypackage",
  "software_packageVersion": "1.2.3",
  "comment": "Metadata provenance: version: Source: src/mypackage/__about__.py | Method: dynamic_extraction"
}
```

The provenance information shows:

- **Version**: Dynamically extracted from `src/mypackage/__about__.py`
- **License**: Detected from a `LICENSE` file, not author-declared

This transparency is crucial for:

- **Auditability**: Understanding where SBOM data comes from
- **Trust**: Verifying the accuracy of metadata, and distinguishing
  extracted facts from inferred/detected ones
- **Machine consumption**: Automated tools can parse provenance
- **Human review**: Manual inspection of data sources

## Preserved artifact metadata

`preserve-source-metadata` embeds an artifact's own metadata in one
`Annotation.statement` of kind `artifact-metadata`, keyed as the file
names it. The rule is the same for every model format:

- a collection in the file (a label list, an archive listing, a metrics
  list) is a JSON array, or a JSON object where the file has a mapping;
- a scalar is text: the same text as in the model's properties and in
  its `ai_hyperparameter` values, where a value appears there. A number
  or boolean is never a JSON number or boolean, since a JSON consumer may
  widen or round it (an integer above 2^53);
- the text of a scalar has one spelling: a boolean `true` or `false`; an
  integer in decimal, at any size; a float in the
  [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (ECMAScript)
  spelling, the shortest decimal that reads back as the same double
  (`0.00001`, `1e-7`, `100`, `1e+21`); NaN and the infinities, which RFC
  8785 has no spelling for, `NaN`, `INF` and `-INF` (the XSD `double`
  spellings). `-0.0` is `0`, as in RFC 8785: the value is equal, only the
  sign of the zero is lost;
- a GGUF `FLOAT32` value is spelt as the float32's own shortest decimal,
  not as the double it widens to: a stored `1e-5` is `0.00001`, not
  `9.999999747378752e-06`. The text reads back as the same float32. A
  `FLOAT64` value keeps its own spelling. Only GGUF declares a value
  float32; another format's float is spelt as the double it reads as;
- `valueTypes` maps each top-level `metadata` key whose value is a
  non-string scalar in the source to `integer`, `float` or `boolean`, so a
  consumer can read the text back as its type without knowing the format.
  A key not in it is a string, a collection or a GGUF array summary.
  `valueTypes` is left out when no key has a type;
- collection elements are text too, spelt the same way (`null` for a
  missing value): `true`, `false`, `null`, `1`, `0.5` (an HDF5 metric
  `{"acc": true}` is `{"acc": "true"}`; a PT2 tag `null` is `"null"`).
  Elements are not typed;
- a key the file holds no value for is left out, never `null`;
- a collection nested over 32 levels keeps its first 32 levels; the part
  below is its JSON text (or `<nested over 32 levels>` where even that
  nests too deeply), so a hostile nesting never stops the model being read;
- a GGUF array is a summary object of text, `{"length": "N", "type":
  "<element type>"}`, never its elements;
- text is kept as the file holds it, bidi and zero-width controls
  included: the annotation is data, its values JSON strings for a program
  to read. The properties shown to a reader have those controls escaped
  instead (see [Reading values back](metadata-reading-back.md)).

A fastText classifier:

```json
{
  "format": "fasttext",
  "kind": "artifact-metadata",
  "metadata": {
    "labels": ["__label__q", "__label__pos", "__label__neu", "__label__neg"],
    "lossName": "softmax"
  },
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2"
}
```

A CRFsuite tagger:

```json
{
  "format": "crfsuite",
  "kind": "artifact-metadata",
  "metadata": {
    "labels": ["I", "E"],
    "model_type": "FOMC",
    "num_attributes": "2",
    "num_features": "4",
    "num_labels": "2"
  },
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2",
  "valueTypes": {
    "num_attributes": "integer",
    "num_features": "integer",
    "num_labels": "integer"
  }
}
```

A GGUF model (`stories260K.gguf`, some keys left out here), whose
`llama.attention.layer_norm_rms_epsilon` is the `ai_hyperparameter` value
`0.00001` too:

```json
{
  "format": "gguf",
  "kind": "artifact-metadata",
  "metadata": {
    "general.architecture": "llama",
    "llama.attention.layer_norm_rms_epsilon": "0.00001",
    "llama.block_count": "5",
    "tokenizer.ggml.model": "llama",
    "tokenizer.ggml.tokens": {"length": "512", "type": "STRING"}
  },
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2",
  "valueTypes": {
    "llama.attention.layer_norm_rms_epsilon": "float",
    "llama.block_count": "integer"
  }
}
```

A Hugging Face model, which is no model file, follows the same rules
(`"format": "huggingface"`): its Hub and `config.json` scalars are text,
typed in `valueTypes`, its lists and objects arrays and objects.

An archive listing (`archive_contents` of a PyTorch or PT2 archive) holds
the first 20 member names, the same ones the property text shows;
`archive_member_count` beside it is the number of members in the archive.

## Size-bounded preservation

`preserve-source-metadata` can embed an artifact's verbatim original
metadata (e.g. a GGUF model's key/value header) into a single
`Annotation.statement`. For a real model this can be large -- a chat
template alone can be several KiB. `max-source-metadata-bytes` caps the
serialised `Annotation.statement`'s size in UTF-8 bytes; `0` (the default)
means unlimited. Valid values and its flag, Action input and API parameter:
[Configuration](configuration.md#toolpitloomprovenance).

When the budget is exceeded, whole metadata entries are dropped --
largest first, to keep as many entries as possible -- never a value
truncated mid-string, which would produce invalid JSON. A dropped key's
`valueTypes` entry goes with it. The reduction is
always marked explicitly in the same envelope, never silent:

```json
{
  "format": "gguf",
  "kind": "artifact-metadata",
  "maxMetadataBytes": 500,
  "metadata": {"general.architecture": "llama", "llama.block_count": "32"},
  "schema": "https://pitloom.dev/provenance/artifact-metadata/2",
  "truncated": true,
  "truncatedKeyCount": 1,
  "truncatedKeys": ["tokenizer.chat_template"],
  "valueTypes": {"llama.block_count": "integer"}
}
```

If the budget is too small to hold even an empty `metadata: {}` plus the
marker fields, no Annotation is emitted for that artifact at all (a
`WARNING` is logged) -- an Annotation whose own `maxMetadataBytes` field
claims a budget its own overhead violates would be worse than omitting
it. A budget that forces every key to be dropped, but still fits the
marker overhead, is emitted with `metadata: {}` and a `WARNING`.

A model file with more than 1000 metadata keys keeps its first 1000 (the
[entry cap](ai-model-scan-limits.md#size-and-count-caps)). The keys left
out are counted, not named -- listing them would cost what the cap saves
-- and `maxEntries` names the cap. For a Safetensors model of 1500
`__metadata__` keys (its 1000 kept keys left out here):

```json
{
  "maxEntries": 1000,
  "truncated": true,
  "truncatedKeyCount": 500
}
```

When the byte budget drops keys from the same annotation, `truncatedKeys`
and `maxMetadataBytes` are added and `truncatedKeyCount` counts both: the
keys named in `truncatedKeys` and those over `maxEntries`.

Every JSON text Pitloom writes -- each `Annotation.statement`,
`ai_informationAboutApplication`, and the text of a model property holding
a list or an object (fastText and CRFsuite `labels`, HDF5
`loss`/`metrics`) -- is serialised via RFC 8785 (JSON Canonicalization
Scheme, JCS), the same canonicalization the whole SBOM document uses: no
insignificant whitespace and a deterministic key order, so byte-for-byte
comparing or hashing it across runs with unchanged input is safe. A value
RFC 8785 has no spelling for is a string in it: NaN and the infinities
`NaN`, `INF` and `-INF`, an integer beyond +-(2^53 - 1) its full decimal
text.

## What the `method` values mean

The `method` field in a provenance entry says *how* Pitloom arrived at a
value, not just where it read it from. Values in use today:

| `method` | Meaning |
| --- | --- |
| `dynamic_extraction` | Read from a Python file at build time (e.g. a `__version__` or `__about__.py` variable), not from `pyproject.toml` directly. |
| `licenseid_detection` | License text matched against a known SPDX license using the [`licenseid`](https://pypi.org/project/licenseid/) library -- detected, not author-declared. |
| `inferred_from_authors` | Derived from the `authors` list (e.g. a copyright statement), not read verbatim from any single field. |
| `parsed_author_list` | Extracted multiple individual entities by splitting a single, comma-separated author string. |
| `file_directive` | A `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`); the value was read from that file. |
| `attr_directive` | A `pyproject.toml` dynamic field pointed at a Python attribute (`{attr = "..."}`); the value was imported and read from code. |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` tracking SDK via Python stack inspection -- identifies which script/function called the SDK. |
| `synthetic` | The element is Pitloom's own synthesized placeholder root package for an installed environment (`loom env`), not extracted from any source file. |
| `magika_content_detection` | Per-file content type resolved by the [`magika`](https://pypi.org/project/magika/) content-detection library. |
| `extension_guess` | Per-file content type resolved by a filename-extension fallback (no `magika`, or no confident result). |
| `file_name_stem` | An AI model's name is its file name without the last extension: the file names no model (or only an exporter default). |
| `semver_bit_packed` | An ONNX integer `model_version` decoded as bit-packed SemVer (`MAJOR.MINOR.PATCH`). |
| `array_length` | A GGUF array field: only its element count is recorded (property `<key>.length`); the elements are not recorded. |
| `crfsuite_model_type` | A CRFsuite model's type of model, `conditional random field`, derived from the header's model type (`FOMC`, a first-order Markov CRF, the only type CRFsuite writes). |
| `generated_from_labels` | A CRFsuite model's description, written by Pitloom from the model's labels (the file has no description): the label count and the first 20 labels, each cut to 64 characters. |
| `resolved_lockfile` | A dependency version pinned by a lock file (`pylock.toml`, `uv.lock`, `poetry.lock` and similar), not by the project's own requirement specifier. |
| `pinned_requirements` | A dependency version pinned with `==` or `===` in a `requirements.txt`; weaker evidence than a real lock file, so tagged separately. |
| `pdm_dynamic_version` | A PDM dynamic `version`, resolved from `[tool.pdm.version]` with PDM's own resolver; the tag ends with the declared source in parentheses, e.g. `pdm_dynamic_version(file)`. |
| `flit_dynamic_metadata` | A Flit dynamic `version` or `description`, read from the module's `__version__` and docstring with flit-core's own AST scan. |
| `member_count` | A ZIP-based model archive's member count (property `archive_member_count`), read from the archive's central directory. |
| `yaml_frontmatter` | Read from a local README/model card's YAML frontmatter block during enrichment. |

A field with **no** `method` -- just a `source` -- was read verbatim from
the named file with no interpretation involved (e.g. `project.name` from
`pyproject.toml`). In `detail = "minimal"` (the default), these
no-`method` entries are dropped entirely when the source is a
well-known, re-readable manifest (`pyproject.toml`, `setup.cfg`/`setup.py`,
wheel metadata, an sdist's `PKG-INFO`, the Hugging Face Hub API) -- they
add no signal beyond what's already implied by the native field. Set
`detail = "full"` to see every field's source regardless.

## How a license source is chosen

For the project's own declared license (`project.license` in
`pyproject.toml`), Pitloom also independently checks the project
directory for a second opinion -- `CITATION.cff`, then `codemeta.json`,
then a `LICENSE`/`LICENSE.*` file -- checked regardless of whether a
declared value was already found. A `CITATION.cff`/`codemeta.json` value
that's already a bare SPDX id is used as-is; anything else (typically a
`LICENSE` file's full text) is matched against known SPDX licenses via
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
`"MIT"` are recognised as the same license), but also equivalent compound
expressions written differently (`"MIT AND MIT"` and plain `"MIT"`;
`"MIT OR Apache-2.0"` and `"Apache-2.0 OR MIT"` all normalise to the same
value) -- so none of these are misreported as a conflict.

- If the project states no license, the directory's value is recorded as
  `hasDeclaredLicense`: a `CITATION.cff`, `codemeta.json` or `LICENSE` file
  in the project is the project's own statement, however it was read.
- If both exist and **agree**, both `hasDeclaredLicense` and
  `hasConcludedLicense` are recorded, pointing at the same license. A
  license name that is the SPDX License List name of the other value's id
  (a classifier's `MIT License` and a detected `MIT`) agrees too: two
  elements, no conflict.
- If both exist and **disagree**, both are still recorded -- pointing at
  two different licenses -- and Pitloom adds a `conflict` Annotation
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
  Annotation is added. `NONE` against a real license is a conflict.

The same rule applies where a project's static metadata is checked against
its installed metadata: an agreeing pair, or a `NOASSERTION`/`UNKNOWN` on
either side, is no conflict, and a real installed license replaces a
`NOASSERTION`/`UNKNOWN` static one.

The check runs where Pitloom reads a project's own files: `loom project`
or `generate_project_sbom()` on a directory or an sdist, and the Hatchling
build hook. In an sdist it reads the root `LICENSE`, `CITATION.cff` and
`codemeta.json` of the directory holding `PKG-INFO`, as for the unpacked
directory. When the project's metadata states no license, the detected
one is its declared license instead. An SBOM of a wheel records only the
license the wheel's metadata states, with no `hasConcludedLicense` second
opinion.

## How a license value is recorded

Every license value goes through one classification, whichever source it
came from:

| Value | Recorded as |
| --- | --- |
| A valid SPDX expression (`mit`, `Apache-2.0 OR MIT`) | a `LicenseExpression`, in canonical form (listed id case, operators upper-case, terms sorted) |
| Anything else (a license text, `Apache2`) | a `SimpleLicensingText`, as written less its leading blank space and final line breaks |
| `NOASSERTION`, `UNKNOWN` (any case) | no element: the relationship points at the `NoAssertionLicense` individual |
| `NONE` (any case) | no element: the relationship points at the `NoneLicense` individual |
| Absent or blank | nothing: no license relationship at all |

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
license element when this source created it. When the element already
existed (an earlier package had the same license), the note lands on that
source's own `hasDeclaredLicense`/`hasConcludedLicense` relationship
instead, as a `comment` and in the relationship's provenance Annotation. A
named individual cannot carry a comment or an Annotation, so its notes
always land on the relationship.

A dependency's license is looked up in order: installed
`License-Expression`/`License`, installed `License ::` classifiers, then the
PyPI JSON API. `NOASSERTION`/`UNKNOWN` is weak in that order: a later source
that states a license wins, and the `NoAssertionLicense` individual is
recorded, with the first source's provenance, only if none does. `NONE`
ends the lookup.

The project's own `License ::` classifiers are read the same way: after
`project.license` in `pyproject.toml` (`Field: project.classifiers`, also in the
Hatchling build hook), `license` in `setup.cfg` (`Field: metadata.classifiers`),
`license` in `setup.py` (`Field: setup(classifiers=...)`), or
`License-Expression`/`License` in a wheel, an sdist or installed metadata
(`Field: Classifier`). A Poetry project's classifiers are not read: Poetry
writes the license classifier from `license` itself. `License :: OSI Approved`
is a category, not a license: it is left out, alone or beside a more specific
classifier under it, as if absent. `setup.cfg` `classifiers` are listed as
setuptools lists them (one per line, else comma-separated). When `setup.py`
and `setup.cfg` both state a license, see
[setuptools projects](cli.md#setuptools-projects-setuppy-and-setupcfg).
A multi-line license text in a wheel, an sdist or installed metadata is read
without the indent the build tool folded it with. Several license classifiers
are one `LicenseExpression`, the AND of `LicenseRef-pitloom-classifier-<name>`
terms sorted by classifier, whose `customIdToUri` maps each term to a
`SimpleLicensingText` of the name as written; AND is assumed, with one
`WARNING:`, as they may offer a choice. So a directory, its sdist, its wheel and
the build hook record the same declared license, except a license file or text
that Pitloom identifies as a listed license: the directory and the build hook
record its id, the sdist and the wheel the text. A directory, an sdist and
the build hook add the concluded second opinion above (a wheel only through
`embed-wheel --project-dir`).

Whose statement a license is decides the relationship. The package's own --
its manifest, a file it ships, an AI model file's own metadata, a model card,
its own installed metadata (the project, or a `loom env` package) -- is
`hasDeclaredLicense`. A third-party record -- the PyPI JSON API, or a
dependency's installed copy read for a project SBOM -- is
`hasConcludedLicense`, as is the directory's second opinion above.

## How a dependency-version source is chosen

The same disagreement-detection mechanism also applies to a dependency's
resolved version, once a project lock file is in play (see [Dependency
sources and precedence](dependency-sources.md)). Unlike license, there's
no independent-detection procedure here -- both candidates are the
project's own stated claims, just from two different files, so **both are
`role: "declared"`**, not a `declared`/`detected` pair:

- A direct dependency pinned exactly (e.g. `requests==2.31.0`) whose
  pinned version doesn't match what the lock file separately resolved to.
- A direct dependency declared as a range or left unpinned (e.g.
  `requests>=2.0`) whose declared constraint the lock file's resolved
  version doesn't satisfy.

Either way, the resolved `software_packageVersion` still follows the
same "explicit pin beats local environment" precedence described in
[Dependency sources and precedence](dependency-sources.md#version-comparison-pep-440-not-semver)
(a declared exact pin always wins; otherwise the lock file's version
wins), and Pitloom adds a `conflict` Annotation (`field:
"dependency_version"`) on the dependency package recording both values:

```json
{
  "candidates": [
    {"role": "declared", "source": "Source: pyproject.toml | Field: dependencies", "value": ">=2.0"},
    {"role": "declared", "source": "Source: requirements.txt | Method: resolved_lockfile", "value": "1.5.0"}
  ],
  "field": "dependency_version",
  "kind": "conflict",
  "schema": "https://pitloom.dev/provenance/conflict/1"
}
```

Note the declared candidate's `value` is a PEP 440 specifier expression
(e.g. `">=2.0"`), not a version, when the dependency was declared as a
range rather than pinned exactly -- the exact-pin case instead has a
concrete version on both sides.

## See also

`[tool.pitloom.provenance]` is read the same way regardless of entry
point -- see [Command line](cli.md#configuration), [Hatchling build
hook](hatchling-build-hook.md), and [Python API](python-api.md) for where
to set it.

- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies and provenance.
- [Reading values back](metadata-reading-back.md) -- the layers a value
  passes through (caps, scalar text, display escape, RFC 8785) and the
  order to undo them.
