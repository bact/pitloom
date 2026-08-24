---
Created: 2026-08-14
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Provenance implementation notes

Shipped provenance-mechanism history and rationale, grouped here since
they cross-reference each other heavily (shared N1-N6/A1-A2/G1-G4/E1-E2/P1
taxonomy codes, shared role/method vocabulary). Still-open/future
provenance questions live at
[working-docs/design/provenance-enrichment-vocabulary.md](../../design/provenance-enrichment-vocabulary.md)
instead.

| File | Covers |
| :--- | :----- |
| [annotation-provenance.md](annotation-provenance.md) | Canonical design rationale and current status: goal, design decisions, statement schema, implementation, tests, acceptance criteria, security hardening. Start here. |
| [annotation-mechanism.md](annotation-mechanism.md) | When/how to use the `Annotation` mechanism at all: boundary principle, extrinsic-assertion test, high-signal test, config, statement-envelope convention. |
| [role-vocabulary.md](role-vocabulary.md) | The `role` vocabulary (`declared`/`detected`/`externalReported`/`inferred`/`sbomAuthorSupplied`): definitions, decision rule, source-recording convention, role-to-native mapping. |
| [use-case-catalog.md](use-case-catalog.md) | Why an Annotation earns its place: the G1-G4/A1-A2/E1-E2/P1 use-case catalog, and the Phase 2 N1-N6 backfill checklist. |
| [multi-source-conflict.md](multi-source-conflict.md) | G2 (multi-source disagreement) implementation depth: license-conflict schema, normalization logic, what's built, real-world validation, future candidate sources. |
| [metadata-provenance.md](metadata-provenance.md) | Implementation detail behind `docs/metadata-provenance.md`: the Core/Annotation mechanism, comment-attribute back-compat, the `Source: X \| Field: Y` format spec, tracked-field list. |
| [annotation-provenance-full-plan.md](annotation-provenance-full-plan.md) | Archived, fuller original Phase 1 plan -- historical reference, not a live task list. |
| [phase2-native-backfill-handover.md](phase2-native-backfill-handover.md) | Status/next-steps summary for the N1-N6 native-first backfill (now complete). |
| [demo-provenance.md](demo-provenance.md) | Worked CLI walkthrough of provenance output (historical, pre-Annotation framing but still-accurate `comment` examples). |
