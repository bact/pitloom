---
Created: 2026-07-08
Last-Modified: 2026-08-09
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
`comment` form kept alongside for back-compat. Controlled by
`[tool.pitloom.provenance]` in `pyproject.toml`:

```toml
[tool.pitloom.provenance]
format = "both"                    # "annotation" | "comment" | "both" (default)
detail = "minimal"                 # "minimal" (default) | "full"
preserve-source-metadata = "auto"  # "auto" (default) | "always" | "never"
```

By default (`detail = "minimal"`), a field only gets a provenance
Annotation when it adds something the native SPDX value can't already
convey -- e.g. the value was inferred or detected rather than read
verbatim. A value with a real native SPDX home (the license itself, the
package version, a dependency edge) is never restated in the Annotation;
only *how it was determined* is. Set `detail = "full"` for an exhaustive
per-field source map instead.

## Provenance examples

An `Annotation` on a package whose license was detected (not
author-declared):

```json
{
  "type": "Annotation",
  "annotationType": "other",
  "contentType": "application/json",
  "subject": "https://spdx.org/spdxdocs/mypackage-.../#Package-1",
  "statement": "{\"schema\":\"https://pitloom.dev/provenance/1\",\"fields\":{\"license\":{\"source\":\"LICENSE\",\"method\":\"licenseid_detection\"}}}"
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

## What the `method` values mean

The `method` field in a provenance entry says *how* Pitloom arrived at a
value, not just where it read it from. Values in use today:

| `method` | Meaning |
| --- | --- |
| `dynamic_extraction` | Read from a Python file at build time (e.g. a `__version__` or `__about__.py` variable), not from `pyproject.toml` directly. |
| `licenseid_detection` | License text matched against a known SPDX license using the [`licenseid`](https://pypi.org/project/licenseid/) library -- detected, not author-declared. |
| `inferred_from_authors` | Derived from the `authors` list (e.g. a copyright statement), not read verbatim from any single field. |
| `file_directive` | A `pyproject.toml` dynamic field pointed at a file (`{file = "..."}`); the value was read from that file. |
| `attr_directive` | A `pyproject.toml` dynamic field pointed at a Python attribute (`{attr = "..."}`); the value was imported and read from code. |
| `inspect_caller` | Recorded automatically by the `pitloom.loom` tracking SDK via Python stack inspection -- identifies which script/function called the SDK. |
| `synthetic` | The element itself was synthesized by Pitloom (e.g. a placeholder), not extracted from any source file. |

A field with **no** `method` -- just a `source` -- was read verbatim from
the named file with no interpretation involved (e.g. `project.name` from
`pyproject.toml`). In `detail = "minimal"` (the default), these
no-`method` entries are dropped entirely when the source is a
well-known, re-readable manifest (`pyproject.toml`, `setup.cfg`/`setup.py`,
wheel metadata, the Hugging Face Hub API) -- they add no signal beyond
what's already implied by the native field. Set `detail = "full"` to see
every field's source regardless.

## How a license source is chosen

For the project's own declared license (`project.license` in
`pyproject.toml`), Pitloom also independently checks the project
directory for a second opinion -- `CITATION.cff`, then `codemeta.json`,
then a `LICENSE`/`LICENSE.*` file -- checked regardless of whether a
declared value was already found. A `CITATION.cff`/`codemeta.json` value
that's already a bare SPDX id is used as-is; anything else (typically a
`LICENSE` file's full text) is matched against known SPDX licenses via
`licenseid` (`method: licenseid_detection`). Either way counts as
Pitloom's own independent-detection procedure. Both sides are normalized
before comparison -- not just casing (a declared `"mit"` and a detected
`"MIT"` are recognized as the same license), but also equivalent compound
expressions written differently (`"MIT AND MIT"` and plain `"MIT"`;
`"MIT OR Apache-2.0"` and `"Apache-2.0 OR MIT"` all normalize to the same
value) -- so none of these are misreported as a conflict.

- If only one of the two exists, only that one is recorded, as
  `hasDeclaredLicense` or `hasConcludedLicense` respectively.
- If both exist and **agree**, both `hasDeclaredLicense` and
  `hasConcludedLicense` are recorded, pointing at the same license.
- If both exist and **disagree**, both are still recorded -- pointing at
  two different licenses -- and Pitloom adds a `conflict` Annotation
  (`field: "license"`) on the package listing both candidates and where
  each came from, so the disagreement is visible rather than one value
  silently overriding the other:

  ```json
  {
    "schema": "https://pitloom.dev/provenance/conflict/1",
    "kind": "conflict",
    "field": "license",
    "candidates": [
      {"value": "MIT", "role": "declared", "source": "Source: pyproject.toml | Field: project.license"},
      {"value": "Apache-2.0", "role": "detected", "source": "Source: LICENSE | Method: licenseid_detection | Tool: licenseid==0.3.0"}
    ]
  }
  ```

  `role` says *whose* determination each candidate is: `declared` is the
  project's own stated claim; `detected` is Pitloom's own independent
  directory-search procedure's result. (Two further roles,
  `externalReported` and `inferred`, are
  reserved for future candidate sources -- a linked GitHub/Hugging Face
  Hub API, or an AI agent's inference -- not built yet.)

For the full design rationale, current implementation status, and code
citations behind both sections above, see
[`annotation-provenance.md`](https://github.com/bact/pitloom/blob/main/working-docs/implementation/annotation-provenance.md)
in the Pitloom repository.

## See also

`[tool.pitloom.provenance]` is read the same way regardless of entry
point -- see [Command line](cli.md#configuration), [Hatchling build
hook](hatchling-build-hook.md), and [Python API](python-api.md) for where
to set it.
