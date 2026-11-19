---
Created: 2026-11-19
Last-Modified: 2026-11-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence variants (-only, -or-later): declared as read, concluded only on evidence

See also: [licence-resolution-provenance.md](licence-resolution-provenance.md)
(T14, the per-operand mapping), [evidence-levels.md](evidence-levels.md),
[roadmap.md](roadmap.md), [sbom-format-gaps.md](sbom-format-gaps.md).

## 1. Decision (user, 2026-11-19): option G, for now

LicenseID 0.9.0 reads a bare `GPL-2.0` (an SPDX tag in text, or a value) as
`GPL-2.0` as written, with `variant_stated` false, where 0.8.4 answered
`GPL-2.0-only`. It adds `detect(variant=auto|as-written|only|or-later)`. The
full GPL v2 text still answers `GPL-2.0-only` with `exact` and `variant_stated`
both false (measured with 0.9.0, 2026-11-19). `resolve()` has no `variant`.

Pitloom writes what an artefact says as the **declared** licence and a variant
only when something supports it, and then only as a **concluded** licence:

- Declared values (manifest, `License` field, classifiers, `License-Expression`,
  SPDX tag, PyPI or lock data) keep the value as read, `GPL-2.0` included, with
  the existing deprecated-ID note.
- A licence text matched with `variant_stated` false (strictly `False`;
  `None` means the licence has no variants) is written as the bare deprecated
  ID taken from `resolve(<family>)`, never as an invented `-only`.
- No default `-only` conclusion. A concluded variant comes from a stated twin
  (the existing stated-wins rule), the SBOM author, or a named rule that
  records its rationale in the relationship `comment`.
- A dependency's licence is never concluded (the 2026-11-16 ruling).

Why: SPDX 3.0.1 defines `hasDeclaredLicense` as the licence information
actually found in the artefact and `hasConcludedLicense` as the creator's
conclusion from analysing it and other information. A variant the text does not
state was never found in it. A guessed `-only` also makes a `conflict`
Annotation against a `GPL-2.0` classifier or `license` value that the author
never made (the known bug in
[known-bugs/licences-and-licenseid.md](known-bugs/licences-and-licenseid.md)).

Open, not yet ruled: (1) whether a deprecated ID in `hasDeclaredLicense` on the
text path is acceptable to consumers (the value path already writes one; both
forms pass `spdx3-validate`); (2) what a text-only match writes for the six
GFDL invariants and no-invariants families, which have no bare deprecated ID;
(3) LicenseID 0.9.0 answers `GPL-2.0-only` with `variant_stated` false for the
GPL text plus an "or (at your option) any later version" notice beside it: if
that is not intended, an upstream handoff.

Consequences (the code stage, after the LicenseID 0.9 bump): the pin moves to
`licenseid>=0.9.0,<0.10`; `docs/metadata-provenance-licences.md`,
`tests/fixtures/license-texts/expected.json` and
`test_license_detection_ties.py` expect `-only` for an unstated text, a reversed
reading that needs a before/after sweep.

## 2. Later: find more evidence for the variant

A licence text alone, or a licence expression alone, cannot say whether the
author meant `-only` or `-or-later`. Other files in the repository often do: a
grant in a source header ("either version 2 of the License, or (at your option)
any later version"), a `COPYING` or `NOTICE` statement, per-file
`SPDX-License-Identifier` tags, a README sentence. That text is not what Pitloom
first hands to LicenseID, so it never reaches it; a later scan can read it.

Direction, not built, not ruled: a user may ask Pitloom to look for this
evidence (an opt-in, like the other enrichment steps; the `sbom-enrich` skill
and the provenance flags item in the roadmap are the places to decide), and to
use it, with or without LicenseID's help, to judge `-only` against
`-or-later`. Rules to keep when it is designed:

- The result is a **concluded** licence with its evidence named: which files
  and which statement, at which evidence level
  ([evidence-levels.md](evidence-levels.md): measured, declared, lower bound).
  The declared licence stays as read.
- A grant that sits next to the full licence text counts only for its own
  licence (LicenseID 0.9 applies the same rule to a tool's "or later").
- Evidence that disagrees (one file says `-only`, another `-or-later`) is
  reported as a conflict, not resolved silently.
- Scanning is bounded like every other read (caps bound reading, never
  reporting) and never runs without the user's opt-in.
