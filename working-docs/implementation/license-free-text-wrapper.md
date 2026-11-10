---
Created: 2026-11-11
Last-Modified: 2026-11-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Free-text licences: a wrapper, and one provenance copy (#471)

See also: [license-pipeline.md](license-pipeline.md) (stage 3, where the
licence elements are built) and
[license-typing.md](license-typing.md).

`hasDeclaredLicense` and `hasConcludedLicense` accept only an
`AnyLicenseInfo` or a subclass at `to`, and a `SimpleLicensingText` is a
plain `Element`. A licence that is no SPDX expression is therefore two
elements: the `SimpleLicensingText` (text, `name`) and a
`simplelicensing_LicenseExpression` of one `LicenseRef-loom-text-<hash>`
whose `customIdToUri` maps that key to the text's `spdxId`. The relationship
targets the expression.

The hash is the first 16 hex digits (64 bits) of the SHA-256 of the stripped
text, so one text is one pair. A ref must be unique only within one document,
where two of 1,000 different texts share one with odds near 3 in 10^14 (32
digits were built first, then shortened). The text is indexed as `text-body`,
the expression as an expression. An existing expression of that
`LicenseRef-` counts as the wrapper only when it maps to a text: a user's own
expression spelled so does not. The merge unifies a wrapper by ref only when
the ref carries the `LicenseRef-loom-text-` prefix; two fragments that each
map a ref of another spelling to a different text stay apart.

The `License ::` classifier AND maps each `LicenseRef-loom-classifier-` term to
the text element directly, so a wrapper is made only for a text a relationship
targets.

**Provenance lives on the text only.** The wrapper is plumbing and has no
`name` and no provenance `Annotation`: a second copy would state the same
fact twice and could drift. A reader that starts from the relationship's
target follows `customIdToUri` to the text for its provenance. Rejected: the
same `Annotation` on both elements.

**Enforcement.** The fragment merge rejects a licence relationship whose ends
are of the wrong type (`_fragments_license_ranges.py`, the coded message
`license-relationship-invalid`): `from` a `software_SoftwareArtifact`, `to` an
`AnyLicenseInfo`, a subclass, or the `NoAssertionLicense`/`NoneLicense`
individual. A fragment of any origin, including one from an older Pitloom that
pointed a relationship at a bare text, keeps to this shape or fails the merge;
there is no repair. `spdx3-validate` (SHACL for 3.0.1) does not check these
ends.
