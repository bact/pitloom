---
Created: 2026-09-29
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Complete a standard's minimum elements: step detail

See also: `../SKILL.md` ("Complete a standard's minimum elements", steps
a-g, which hold the rules) and `minimum-elements.md` (the checklists,
field mappings and question bank).

## Step d: ranking the questions

Lead with effort-to-impact, not checklist order. Before asking, rank the
remaining gaps: quick answers (a plain yes/no, a fact the user obviously
already knows) and answers that resolve multiple elements or multiple
standards at once go first (e.g. setting `[[tool.pitloom.creator]]` closes
both `SBOM Author` and `Component Producer` for the main package in one
step -- see `minimum-elements.md`'s NTIA "Supplier Name" row for why). Say
up front which few answers would close most of the remaining gap, so the
user can judge where their time actually pays off -- don't just work a
flat list top to bottom.

The user can stop with "stop", "that's enough", "skip the rest" or
equivalent. That is not a failure, and there is no need to insist on an
answer first.

## Step g: why `NOASSERTION`

An element the user leaves unknown is written as `NOASSERTION`/"unknown"
in the fragment, following CISA 2026's "Explicitly Identifying Unknown
Information" practice: a stated unknown is a decision, a missing field
is indistinguishable from an oversight.

For a licence the user says is unknown, write a `Relationship` with
`relationshipType` `hasDeclaredLicense` (or `hasConcludedLicense`), `from`
the package's id and `"to": ["expandedlicensing_NoAssertionLicense"]`. No
licence element is created, and never a `SimpleLicensingText` reading
"NOASSERTION". Pitloom itself writes no licence relationship for a licence
nobody stated.

## Optional cross-check

`minimum-elements.md` also lists a manual cross-check
(`ntia-conformance-checker`) for NTIA/CISA targets -- not a required step,
and not wired into this skill.
