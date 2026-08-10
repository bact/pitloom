---
Created: 2026-07-08
Last-Modified: 2026-08-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

<!-- markdownlint-disable-next-line MD041 -->
{% include nav.html %}

# Metadata provenance

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

Pitloom checks these in order and uses the first hit:

1. `project.license` in `pyproject.toml` (a literal SPDX expression, or a
   `{file = "..."}`/`{text = "..."}` table).
2. If that's absent or not directly usable, a `LICENSE`/`LICENSE.*` file
   in the project directory, matched against known SPDX licenses via
   `licenseid` (`method: licenseid_detection`).

**Current limitation:** if both a declared value (step 1) and a detected
`LICENSE` file (step 2) are present *and disagree*, Pitloom does not
flag the conflict -- the declared value silently wins, and there is no
provenance marker recording that a detected alternative existed. This is
a known, documented gap (tracked as "G2" in the design docs), not yet
implemented.

For the full design rationale, current implementation status, and code
citations behind both sections above, see
[`annotation-provenance.md`](https://github.com/bact/pitloom/blob/main/working-docs/implementation/annotation-provenance.md)
in the Pitloom repository.
