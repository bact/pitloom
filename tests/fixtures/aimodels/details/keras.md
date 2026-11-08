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
| Architecture | `Sequential`: `InputLayer` -> `Dense(32, relu)` -> `Dense(1, sigmoid)` |
| Task | Binary classification (10 features -> 1 output) |
| Input | float32 `[None, 10]` |
| Output | float32 `[None, 1]` (sigmoid probability) |
| Keras version | 3.13.2 (`metadata.json` `keras_version`) |
| Model name | `Binary_Classifier_v1` |
| Size | 19 215 bytes (0.02 MB) |
| SHA-256 | `d0941f8de74c5afdfdcb93e395bb1e3538b6029eac4001a31dd283d95e979fde` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | None (uses stdlib `zipfile` + `json`) |

Archive members: `metadata.json`, `config.json`, `model.weights.h5`.

Metadata extracted by the Keras extractor:

- `format_info.framework_version` = `"3.13.2"` (`metadata.json`
  `keras_version`, the Keras library version; the model has no version)
- `properties["date_saved"]` = `"2026-03-29@08:51:08"` (`metadata.json`;
  no time zone, so no release time)
- `type_of_model` = `"Sequential"` (`config.json` `class_name`)
- `name` = `"Binary_Classifier_v1"` (`config.json` `config.name`)
- `hyperparameters`: `trainable=True` (the scalar entries of `config`;
  `dtype`, a dtype policy in Keras 3, is excluded)
- `properties["layer_count"]` = `"3"` (the `InputLayer` counted, as the HDF5
  reader counts it)
- `inputs[0]["shape"]` = `[None, 10]` (the `InputLayer`'s `batch_shape`)
- `properties["archive_contents"]` = `"metadata.json, config.json,
  model.weights.h5"` and `properties["archive_member_count"]` = `"3"` (the
  ZIP structure)

Not extracted:

- `compile_config` is `{}` in this file: no optimizer, loss or metrics.
- The top-level `metadata` object of `config.json` (`description`,
  `author`, `model_version`, `license`) is a convention of this fixture's
  generator, not a field Keras writes: it is not mapped to the description,
  the version or the licence.
- `model.weights.h5` is not opened: no parameter count.
