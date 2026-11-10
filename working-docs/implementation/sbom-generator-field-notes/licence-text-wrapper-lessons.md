---
Created: 2026-11-11
Last-Modified: 2026-11-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a licence text behind a wrapper (#471)

See also: [README.md](README.md) (index of these notes),
[spdx-modelling.md](spdx-modelling.md) (SPDX 3 claims and licences),
[free-text-wrapper decision record](../license-free-text-wrapper.md) (what was
built), [process-lessons.md](process-lessons.md).

Lessons from fixing an SBOM generator that pointed `hasDeclaredLicense` at a
plain `Element` (Pitloom, 2026-11-10 to 2026-11-11). Evidence is Pitloom's: an
SPDX 3.0.1 JSON-LD generator. Counts are from the merged tree: 21396 tests
passed, 100% branch coverage on the changed files, three review rounds.

## 1. A schema validator may not check relationship end types

- **Evidence.** `hasDeclaredLicense` and `hasConcludedLicense` accept only an
  `AnyLicenseInfo` (or a subclass) at `to`, and a package, file or snippet at
  `from`. Pitloom pointed them at a `SimpleLicensingText`, a plain `Element`.
  Its own tests and `spdx3-validate` (SHACL for 3.0.1) passed: neither checks
  those ends.
- **Do:** write the range from the specification's bindings into a test, and
  enforce it where untrusted graphs enter (a fragment merge), not only where
  your own builder writes.

## 2. A wrapper whose ref is derived from content

- **What was built.** A free-text licence is a `SimpleLicensingText` plus a
  `LicenseExpression` of one `LicenseRef-<prefix>-text-<16 hex>`, mapped to the
  text by `customIdToUri`. The 16 hex are the SHA-256 prefix of the stripped
  text (64 bits: about 3 in 10^14 for two of 1,000 texts in one document).
- **What broke in review.** A merge that keyed a wrapper on its ref string
  unified two hand-written wrappers that both said `LicenseRef-custom` for
  different texts, so the second package declared the wrong licence.
- **Do:** unify on a ref only when its spelling proves it was derived from the
  content; keep every other ref apart.

## 3. One copy of a fact

- The wrapper has no name and no provenance. The text carries the single
  provenance `Annotation`; a reader follows `customIdToUri` to it. A second
  copy states one fact twice and can drift.
- **Do:** put a fact on the element that owns it; make a reader follow the link.

## 4. Review rounds find the previous round's fixes

- Rounds 1 and 2 found real bugs (an escape missed on the mapped text, a
  blank classifier name, a test that no longer covered the blank case). Round 3
  found the shared-ref unification above, in code round 2 had added.
- **Do:** after a fix, re-review the delta; stop when a round finds only
  wording or test-strength points.
