---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SBOM fragment fixtures

This directory (`tests/fixtures/fragments/`) contains minimal hand-crafted
SPDX 3 JSON-LD fragment files used to test the `merge_fragments` merge pipeline
and verify that AI- and dataset-profile fields are not dropped during
the stitch step.

| Path | Content | Purpose |
| :--- | :--- | :--- |
| `ai-model-fragment.spdx3.json` | One `ai_AIPackage` with hyperparameters, metrics, domain, energy consumption | Tests that all AI-profile fields survive `merge_fragments` |
| `dataset-fragment.spdx3.json` | One `dataset_DatasetPackage` with type, size, availability | Tests that dataset-profile fields survive `merge_fragments` |
| `training-run-fragment.spdx3.json` | `ai_AIPackage` + 2 `dataset_DatasetPackage` + `trainedOn`/`testedOn` relationships | Tests that provenance relationships from a simulated `loom.shoot()` output survive |

All fragment fixtures are licensed CC0-1.0.
Tests that exercise these fixtures live in `tests/test_fragments.py`.
