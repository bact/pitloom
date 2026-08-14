---
Created: 2026-08-14
Last-Modified: 2026-08-14
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
| [annotation-provenance.md](annotation-provenance.md) | Canonical design rationale and current status: the Annotation mechanism, role vocabulary, G1-G4/A1-A2/E1-E2/P1/N1-N6 taxonomy. Start here. |
| [metadata-provenance.md](metadata-provenance.md) | Implementation detail behind `docs/metadata-provenance.md`: the Core/Annotation mechanism, comment-attribute back-compat, the `Source: X \| Field: Y` format spec, tracked-field list. |
| [annotation-provenance-full-plan.md](annotation-provenance-full-plan.md) | Archived, fuller original Phase 1 plan -- historical reference, not a live task list. |
| [phase2-native-backfill-handover.md](phase2-native-backfill-handover.md) | Status/next-steps summary for the N1-N6 native-first backfill (now complete). |
| [demo-provenance.md](demo-provenance.md) | Worked CLI walkthrough of provenance output (historical, pre-Annotation framing but still-accurate `comment` examples). |
