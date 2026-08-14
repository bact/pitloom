---
Created: 2026-07-06
Last-Modified: 2026-08-12
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Wheel-embedded SBOM verification

## Why this exists

The Hatchling-hook rewiring and code-review fixes (name/dependency
canonicalization parity, Poetry fallback, PURLs, file hashes -- see
[hatchling-build-hook.md](hatchling-build-hook.md)) had only
been checked against local dogfood builds and unit/integration tests
before this pass. This document records independent checks against
**actual published releases** on PyPI -- the real, externally-built
artifacts -- so the result is durable evidence, not just a one-off chat
answer that disappears with the session that produced it.

As of 2026-08-11 this check is part of the standard
[release checklist](release-checklist.md) (step 3, post-publish
verification) -- run it for every release, not just the ones below that
happened to prompt a closer look.

## Verification of v0.13.3 (2026-08-11)

The actual release cut from v0.13.0-rc1 below -- v0.13.0 final, then
patches v0.13.1/.2/.3 landed a default-SBOM-filename change (PR #130,
`sbom.spdx3.json` -> `<name>-<version>.spdx3.json`) and a
missing-dependency-metadata fix (PR #131, per-dependency author
`Person` + PURL). Re-verifying against this filename/content change, not just
repeating the rc1 check.

### Method

Same as rc1 below, against `https://pypi.org/pypi/pitloom/0.13.3/json`.

### Findings

- **Location (PEP 770), filename changed.** File now at
  `pitloom-0.13.3.dist-info/sboms/pitloom-0.13.3.spdx3.json` -- the
  `<name>-<version>` filename (not the fixed `sbom.spdx3.json` seen in
  every earlier verification in this doc) reflects PR #130's default
  filename change. Still exactly where PEP 770 expects it.
- **Element count.** 197 elements (`Relationship: 89, software_File: 67,
  Annotation: 13, software_Package: 11, Person: 10,
  simplelicensing_SimpleLicensingText: 3, CreationInfo: 1,
  SpdxDocument: 1, software_Sbom: 1, Tool: 1`) -- up from rc1's 176,
  driven by PR #131: all 10 non-main dependencies (`spdx-python-model`,
  `tomli`, `auditwheel`, `hatchling`, `licenseid`, `pipdeptree`,
  `py-spdx-license`, `pyproject-metadata`, `pyyaml`, `rfc8785`) now carry
  their own author `Person` and PURL, where rc1 was missing this for
  dependencies.
- **spdxId coverage.** 0 non-`CreationInfo` elements missing a `spdxId`
  (same spec-correct exception as rc1).
- **License relationships.** 1 `hasDeclaredLicense` (the main `pitloom`
  package only -- Pitloom only declares its own project's stated
  license) + 11 `hasConcludedLicense` (main package plus all 10
  dependencies, each independently detected). Main package's `comment`
  still shows `license_concluded: Source: codemeta.json`.
- **File hashes.** 67 `software_File` elements, 59 with a SHA-256
  `verifiedUsing` hash (8 directory entries, same pattern as every prior
  verification). Recomputed from actual extracted bytes: 0 mismatches.
  Cross-checked against the wheel's own `RECORD`: 0 mismatches across all
  59. Only `RECORD`-only entries are the `.dist-info/` metadata files
  themselves, as expected.
- **Wheel SHA-256 vs PyPI's published digest.** Exact match
  (`67285cda8e27637badb3f1bbe6d59baee7b9d180fb3c0b7a57af77ea426fe19f`).
- **Schema and SHACL conformance.** `spdx3_validate` -- both passed,
  exit code 0.
- **Creator identity and Tool version.** `createdBy` a real `Person`
  (matches `[[tool.pitloom.creator]]` config, as in rc1); `Tool.summary`
  = `"Pitloom 0.13.3"`, matching the release version.

---

## Verification of v0.13.0-rc1 (2026-08-11)

### Method

1. Resolved the wheel URL via `https://pypi.org/pypi/pitloom/0.13.0rc1/json`
   and downloaded it; verified its SHA-256
   (`4fe6e7fe419d385f988a9a1129ece5a9723603554854b31920dcd6108a6574f7`)
   against the digest PyPI's own API publishes for that file (exact match).
2. Unzipped the wheel and inspected `pitloom-0.13.0rc1.dist-info/sboms/
   sbom.spdx3.json` directly -- the actual bytes a consumer would get,
   not a regenerated copy.

### Findings

- **Location (PEP 770).** File found at exactly
  `pitloom-0.13.0rc1.dist-info/sboms/sbom.spdx3.json`, matching PEP 770
  and Pitloom's `sbom-basename = "sbom"` config, same as prior releases.
- **Fields.** `CreationInfo.specVersion` = `"3.0.1"`; `createdBy` is a
  real `Person` (Arthit Suriyawongkul, with an `email` `ExternalIdentifier`)
  rather than the default "Pitloom" `SoftwareAgent` seen in earlier
  verifications -- confirms `[[tool.pitloom.creator]]` config is honored
  on the actual PyPI-published build, not just in local tests. `Tool`
  (`createdUsing`) reports `summary: "Pitloom 0.13.0-rc1"`, matching the
  release version. The main `pitloom` `software_Package` carries
  `software_packageVersion: "0.13.0rc1"`, `software_packageUrl:
  "pkg:pypi/pitloom@0.13.0rc1"` (PURL), and both `hasDeclaredLicense` and
  `hasConcludedLicense` relationships (Apache-2.0 from both `pyproject.toml`
  and an independent `codemeta.json` scan -- they agree, so no
  `provenance/conflict/1` Annotation fires, per that mechanism's own
  "only when candidates disagree" rule).
- **Element count and shape.** 176 total elements in `@graph`
  (`Relationship: 79, software_File: 67, Annotation: 12,
  software_Package: 11, simplelicensing_SimpleLicensingText: 2,
  CreationInfo: 1, SpdxDocument: 1, software_Sbom: 1, Person: 1, Tool: 1`)
  -- roughly 30% more elements than v0.11.0's 138, driven by the
  provenance-as-Annotation work (PR #102) and native SPDX3 backfill
  (N1-N6, PRs #105-#109) that landed between v0.11.0 and this release.
  All 12 `Annotation` elements use the structured `provenance/fields/1`
  schema (`kind: "fields"`), e.g. `copyright_text` (`method:
  inferred_from_authors`) and `license_concluded` (`source:
  codemeta.json`) on the main package.
- **spdxId coverage.** Every `Element`-derived node has a non-null
  `spdxId` except the single `CreationInfo` node, which is correctly
  absent one -- `CreationInfo` is referenced by other elements'
  `creationInfo` property (here via blank node `_:CreationInfo0`), not an
  independently-addressed `Element` subtype under the SPDX 3 model, so
  this is spec-correct, not a gap. (Earlier entries in this doc phrased
  the check as "all elements have a spdxId" without this caveat --
  worth keeping in mind for future verifications too.)
- **File hashes.** 67 `software_File` elements; 59 carry a SHA-256
  `verifiedUsing` hash and 8 don't -- the 8 are directory entries
  (`pitloom`, `pitloom/core`, `pitloom/enrich`, etc.), which never carry
  file hashes, same pattern as prior verifications. Verified two ways:
  (a) recomputed each of the 59 file hashes from the actual extracted
  bytes -- 0 mismatches; (b) cross-checked against the wheel's own
  `RECORD` file (re-encoding `RECORD`'s urlsafe-base64 digests to hex) --
  0 mismatches across all 59 shared entries. The only entries in `RECORD`
  but not the SBOM are the `.dist-info/` metadata files themselves
  (`METADATA`, `WHEEL`, `entry_points.txt`,
  `licenses/LICENSE` -- note the `licenses/` subdirectory, a Wheel-spec
  path change since v0.11.0's plain `LICENSE` -- and the SBOM file
  itself) -- expected, same as prior verifications.
- **Schema and SHACL conformance.** Ran `spdx3_validate` (`jsonschema` +
  `pyshacl` + `rdflib`) directly against the real SPDX 3.0.1 JSON Schema
  and SHACL model: schema validation and SHACL check both passed (exit
  code 0), no errors reported.

---

## Verification of v0.11.0 (2026-07-09)

### Method

1. Resolved the wheel URL via `https://pypi.org/pypi/pitloom/0.11.0/json`
   and downloaded it; verified its SHA-256 (`69dfae20490491f2cc4d872db64b278e2cb5748d54f9f2efbd86061df4bc9f52`)
   against the digest PyPI's own API publishes for that file (exact match).
2. Unzipped the wheel and inspected `pitloom-0.11.0.dist-info/sboms/
   sbom.spdx3.json` directly -- the actual bytes a consumer would get,
   not a regenerated copy.

### Findings

- **Location (PEP 770).** File found at exactly
  `pitloom-0.11.0.dist-info/sboms/sbom.spdx3.json`. PEP 770 (status: Final)
  reserves `.dist-info/sboms/` and does not mandate a filename; Pitloom's
  own choice matches its `sbom-basename = "sbom"` config.
- **Fields.** `CreationInfo.specVersion` = `"3.0.1"`; a `createdBy`
  SoftwareAgent ("Pitloom", the default when no creator is named) +
  `createdUsing` Tool; the main `pitloom` `software_Package` carries
  `name`/`version` sourced from Hatchling, a `pkg:pypi/pitloom@0.11.0`
  PURL, and declared+concluded license relationships. All 138 elements in
  `@graph` have a non-null `spdxId`.
- **File hashes.** All 49 non-directory `software_File` elements carry a
  SHA-256 `verifiedUsing` hash. Verified two ways: (a) recomputed each
  hash from the actual extracted file bytes -- 0 mismatches; (b)
  cross-checked against the wheel's own `RECORD` file (re-encoding
  `RECORD`'s urlsafe-base64 digests to hex) -- 0 mismatches across all 49
  shared entries. The only entries in `RECORD` but not the SBOM are the
  `.dist-info/` metadata files themselves (`METADATA`, `WHEEL`,
  `entry_points.txt`, `LICENSE`, the SBOM file itself) -- expected, since
  those aren't part of the package's source tree the SBOM documents.
- **Hash algorithm vs. the governing spec.** PyPA's **Binary Distribution
  Format (Wheel)** spec states verbatim: *"The hash algorithm must be
  sha256 or better; specifically, md5 and sha1 are not permitted."*
  Pitloom hardcodes SHA-256 with no weaker fallback.
- **File-collection algorithm.** `get_wheel_files()` does not independently
  walk the filesystem -- it instantiates Hatchling's own
  `hatchling.builders.wheel.WheelBuilder(project_dir)` and iterates
  `builder.recurse_included_files()`, the same API Hatchling itself uses
  to decide what goes into the real wheel. Directory entries in the SBOM
  are derived purely by splitting each file's own `distribution_path` --
  there is no second, independently-drifting directory walk.
- **Schema and SHACL conformance.** Ran the same validation engine
  `spdx3-validate` uses internally (`jsonschema` + `pyshacl` + `rdflib`)
  directly against the real SPDX 3.0.1 JSON Schema and SHACL model
  (`spdx.org/schema/3.0.1/spdx-json-schema.json`,
  `spdx.org/rdf/3.0.1/spdx-model.ttl`): **0 schema errors, SHACL
  `conforms: True`**, 821 triples parsed cleanly.

---

## Verification of v0.9.0 (2026-07-06)

### Method

1. Resolved the wheel URL via `https://pypi.org/pypi/pitloom/0.9.0/json`
   and downloaded it; verified its SHA-256 against the digest PyPI's
   own API publishes for that file (exact match).
2. Unzipped the wheel and inspected `pitloom-0.9.0.dist-info/sboms/
   sbom.spdx3.json` directly -- the actual bytes a consumer would get,
   not a regenerated copy.

### Findings

- **Location (PEP 770).** File found at exactly
  `pitloom-0.9.0.dist-info/sboms/sbom.spdx3.json`. PEP 770 (status:
  Final) reserves `.dist-info/sboms/` and does not mandate a filename;
  Pitloom's choice matches its `sbom-basename = "sbom"` config.
- **Fields.** `CreationInfo.specVersion` = `"3.0.1"`; a `createdBy`
  SoftwareAgent ("Pitloom", the default when no creator is named) +
  `createdUsing` Tool; the main `pitloom` `software_Package`
  carries `name`/`version` sourced from Hatchling (confirmed via its own
  provenance `comment`, e.g. `"Source: Hatchling build backend | Field:
  project.name"` -- not a stale re-parse), a `pkg:pypi/pitloom@0.9.0`
  PURL, and declared+concluded license relationships. All 132 elements in
  `@graph` have a non-null `spdxId`.
- **File hashes.** All 46 non-directory `software_File` elements carry a
  SHA-256 `verifiedUsing` hash. Verified two ways: (a) recomputed each
  hash from the actual extracted file bytes -- 0 mismatches; (b)
  cross-checked against the wheel's own `RECORD` file (re-encoding
  `RECORD`'s urlsafe-base64 digests to hex) -- 0 mismatches across all 46
  shared entries.
- **Hash algorithm vs. the governing spec.** PyPA's **Binary Distribution
  Format (Wheel)** spec states verbatim: *"The hash algorithm must be
  sha256 or better; specifically, md5 and sha1 are not permitted."*
  Pitloom hardcodes SHA-256 with no weaker fallback
  (`src/pitloom/core/models.py:134`, `:99` for the Merkle-root
  aggregation; `src/pitloom/assemble/spdx3/document.py:209`).
- **File-collection algorithm.** `get_wheel_files()`
  (`src/pitloom/core/models.py:107-159`) does not independently walk the
  filesystem -- it instantiates Hatchling's own
  `hatchling.builders.wheel.WheelBuilder(project_dir)` and iterates
  `builder.recurse_included_files()`, the same API Hatchling itself uses
  to decide what goes into the real wheel. Directory entries in the SBOM
  are derived purely by splitting each file's own `distribution_path`
  (`_add_package_files()`, `document.py:152-227`) -- there is no second,
  independently-drifting directory walk. This is why the hash
  cross-check matched exactly: the file *set*, not just the hash
  *algorithm*, is guaranteed by construction to match what Hatchling
  actually built.
- **Schema and SHACL conformance.** Ran the same validation engine
  `spdx3-validate` uses internally (`jsonschema` + `pyshacl` + `rdflib`)
  directly against the real SPDX 3.0.1 JSON Schema and SHACL model
  (`spdx.org/schema/3.0.1/spdx-json-schema.json`,
  `spdx.org/rdf/3.0.1/spdx-model.ttl`): **0 schema errors, SHACL
  `conforms: True`**, 821 triples parsed cleanly.
- **Comparison to other tooling.** Most mainstream Python SBOM generators
  don't do per-file hashing at all -- checked the CycloneDX v1.6 schema
  (hashes are modeled at the whole-Component level, no per-file concept)
  and the official `cyclonedx-python` generator's `environment.py`
  (zero hash-related logic; `Component`s carry no hash by default).
  Pitloom's per-file, build-backend-verified approach is more granular
  than the norm, not just adequate.
- **One flagged non-issue.** `tomli` (a `python_version < "3.11"`
  marker-gated dependency) shows `software_packageVersion: "unknown"` and
  no PURL in the released wheel, because whatever Python version built
  that release didn't have `tomli` installed to resolve a real version
  from. This is honest, correct degradation (the SBOM's own `comment`
  documents the declared constraint) -- not a defect.

## Conclusion

The wheel-embedded SBOMs are valid per SPDX 3.0.1 (schema + SHACL), correctly
located per PEP 770, and every field is present and correct in the actual
published artifacts -- confirmed against the real files, not just against
source or local test fixtures. Holds across releases spanning significant
internal redesigns (v0.9.0 through v0.13.3): the CLI/API rewrite, the
provenance-as-Annotation system, the native SPDX3 backfill, and the
default-SBOM-filename change (`sbom.spdx3.json` ->
`<name>-<version>.spdx3.json`, PR #130) all landed without breaking this
guarantee.
