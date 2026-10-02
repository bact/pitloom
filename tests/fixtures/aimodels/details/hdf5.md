---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# HDF5 (legacy Keras) fixtures

File details for `hdf5/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## hdf5/example-model.h5

| Property | Value |
| :--- | :--- |
| Format | HDF5 - legacy Keras v2 format (`.h5`) |
| Magic bytes | `\x89HDF\r\n\x1a\n` (HDF5 signature) |
| Architecture | `Sequential` (`nn.Linear(10, 1)` equivalent - Dense(1, sigmoid)) |
| Task | Binary classification (10 features -> 1 output) |
| Input | float32 `[None, 10]` |
| Output | float32 `[None, 1]` (sigmoid probability) |
| Version | 3.13.2 (Keras version) |
| Model name | `Binary_Classifier_v1` |
| Size | 23 352 bytes (0.02 MB) |
| SHA-256 | `587004a95c71efffd650977f9530deab113e5017a04a8af91403011a4302be59` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | `h5py` (`pip install pitloom[hdf5]`) |

Notable metadata extracted by the HDF5 extractor:

- `version` = `"3.13.2"` (from `keras_version` attribute)
- `type_of_model` = `"Sequential"` (from `model_config.class_name`)
- `name` = `"Binary_Classifier_v1"` (from `model_config.config.name`)
- `inputs[0]["shape"]` = `[None, 10]`
- `hyperparameters`: `trainable=True`
- `properties["backend"]` contains the Keras backend name
