---
Created: 2026-08-25
Last-Modified: 2026-08-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragments: design, standards alignment, and integration plan

Design notes for Pitloom's fragment system -- how partial SBOMs from
different teams, tools, and times get merged into one composite SBOM.
Split into topic files (2026-08-25, this file was 793 lines/30KB,
against this project's own 800-line/30KB hard cap) since it covers
several largely-independent sub-designs that only share a "future work"
status and cross-reference each other loosely.

**Status:** design/future work throughout, except the fragment-merge
callout in [fragment-merge-design.md](fragment-merge-design.md) noting
what has actually shipped (`merge_fragments` unification, the
`loom-ids.json` registry). Everything else in this cluster is unbuilt.

| File | Covers |
| :--- | :----- |
| [fragment-merge-design.md](fragment-merge-design.md) | Start here. Problem statement, vocabulary alignment with SPDX 3/CycloneDX/CISA, the core fragment-declaration and fragment-assembly (merge) redesign, `DocumentModel` extensions, CLI tooling. |
| [loom-sdk-and-notebooks.md](loom-sdk-and-notebooks.md) | The `pitloom.loom` tracking SDK redesign (MLflow-style `log_*` API) and Jupyter/notebook recording mode (persistent sessions, IPython magic). |
| [extractor-integrations.md](extractor-integrations.md) | New extractors for external tracking tools: W&B Weave, DVC, and MLflow extractor updates. |
| [roadmap-and-resources.md](roadmap-and-resources.md) | The phased implementation roadmap tying the above together, plus the existing-tools/community-resources table and references. |

See also [working-docs/design/mlflow-extractor.md](../mlflow-extractor.md)
(the existing, separate MLflow extractor design this cluster's MLflow
updates build on).
