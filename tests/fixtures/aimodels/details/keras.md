---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Keras v3 fixtures

File details for `keras/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## keras/example-model.keras

| Property | Value |
| :--- | :--- |
| Format | Keras v3 native format (`.keras`) - ZIP archive |
| Architecture | `Sequential` (`nn.Linear(10, 1)` equivalent - Dense(1, sigmoid)) |
| Task | Binary classification (10 features -> 1 output) |
| Input | float32 `[None, 10]` |
| Output | float32 `[None, 1]` (sigmoid probability) |
| Version | 3.13.2 (Keras version) |
| Model name | `Binary_Classifier_v1` |
| Size | 19 215 bytes (0.02 MB) |
| SHA-256 | `d0941f8de74c5afdfdcb93e395bb1e3538b6029eac4001a31dd283d95e979fde` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | None (uses stdlib `zipfile` + `json`) |

Notable metadata extracted by the Keras extractor:

- `version` = `"3.13.2"` (from `metadata.json`)
- `type_of_model` = `"Sequential"` (from `config.json`)
- `name` = `"Binary_Classifier_v1"` (from `config.json`)
- `inputs[0]["shape"]` = `[None, 10]`
- `hyperparameters`: `trainable=True`
- `properties["date_saved"]` contains the save timestamp
