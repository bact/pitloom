---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Enriching or checking an SBOM generated from a PyPI URL

Companion to `../SKILL.md`. The field-by-field reading of the record is in
`sbom-generate/references/pypi-url.md` (a sibling skill; on GitHub, under
https://github.com/bact/pitloom/blob/main/skills/sbom-generate/references/).

An SBOM from `loom wheel <url>`, `loom project <url>` or `loom generate <url>`
on `https://pypi.org/project/<name>/[<version>/]` (Pitloom 0.24.0 or later) is
the SBOM of a wheel or an sdist, plus one provenance record on the main
package saying how the file was obtained (an `Annotation`, and the same
entries in the package `comment` after `Metadata provenance:`). What follows
for this skill:

- **No merge.** Neither a wheel nor an sdist base merges a registered fragment,
  silently. Do steps 1-7 or a standard's steps a-b, report the gaps and hand
  the drafted fragment over, saying it was not merged. Do not run `loom
  generate --enrich` on the URL (a `WARNING: Options:` line says it has no
  effect), and do not run `loom enrich` for it: the downloaded file is gone, so there is
  no model file to read.
- **The record is not an enrichment target.** Never edit it, restate it in a
  fragment or mark it `inferred`: it is Pitloom's own measurement and PyPI's
  own declaration. Its `sha256` (`Evidence: measured_read`) and
  `sha256_declared` (`Evidence: declared`) are equal in every SBOM that
  exists (a mismatch is refused), so equal values are not a finding.
- **Hash elements (NTIA, FSCT, CISA 2026, BSI "Component Hash").** The
  archive's SHA-256 is only in that record, which a checker does not read as a
  hash. A wheel's main package has a Merkle root over its payload files
  (`verifiedUsing`, not an artefact hash); an sdist's has none. Report the
  element as a gap with that cause, and do not copy the digest into a fragment
  you cannot merge.
- **The platform shapes the SBOM.** A wheel is picked for the Python and
  platform Pitloom ran on (`wheel_tags`, `compatible_wheels_skipped`,
  `Method: running-environment`): the gaps found are those of that wheel
  there. Say so in the report; a different machine can give a different
  payload. An sdist SBOM does not depend on the platform.
- **Pins and status.** `Method: latest-release` means the URL named no version:
  for a repeatable base and a repeatable fragment match, regenerate from the
  versioned URL. `release_status` `prerelease` or `yanked` is a fact about the
  release, not a gap to fill.
- **Prose and outside sources.** The file was downloaded into a temporary
  directory that is removed, so a README or model card is not on disk. The
  PyPI page, the project's repository and the file's URL are outside sources:
  step 5 applies (ask first; non-interactive: use none and list them as "not
  used -- needs consent"). The project's own PyPI metadata that the SBOM
  already holds is not an outside source.
- **A dependency's licence or originator from the PyPI JSON API** (a
  `Source: PyPI JSON API` entry on a dependency) is Pitloom's lookup for a
  dependency, not this record; leave it as it is.
- **Nothing to do is a valid result.** On an SBOM that already meets the
  standard asked for, the answer is "no gaps", with no fragment.
- **After enrichment or a gap report**, `sbom-validate` applies to the file
  as to any SBOM. Its `verify-wheel` and `validate-wheel` take a local `.whl`
  only, never a PyPI URL.
