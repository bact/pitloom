---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# NumPy fixtures

File details for `numpy/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## numpy/example-model-bundle.npz

| Property | Value |
| :--- | :--- |
| Format | NumPy NPZ archive (`.npz`) |
| Arrays | 1: `weights` - shape `(2, 2)`, dtype `float32` |
| Data | `weights`: `[[1.0, 2.0], [3.0, 4.0]]` |
| Size | 284 bytes |
| SHA-256 | `dc19291ff85cbe795eba48c2c84bd31cf32263b3219bc53a97128467070ae3b5` |
| License | CC0-1.0 |
| Source | Generated for testing purpose |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `inputs` lists 1 array: `{"name": "weights", "shape": [2, 2], "dtype": "float32"}`
- `properties` does not contain `npy_format_version` - NPZ archives do not
  expose a per-file NPY version at the archive level
- `name`, `description`, `version` are all `None`

---

## numpy/example-model-v1.npy

| Property | Value |
| :--- | :--- |
| Format | NumPy v1.0 (`.npy`) |
| NPY version | 1.0 - 2-byte LE uint16 header length, latin1 header encoding |
| Shape | `(2, 2)` |
| dtype | `float32` |
| Data | `[[1.0, 2.0], [3.0, 4.0]]` |
| Size | 144 bytes |
| SHA-256 | `e8072b61f5d81a3cc4dc59b9d5e14187b20b5d8a3ddd8e6d0bc5128bda5f27aa` |
| License | CC0-1.0 |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `properties["npy_format_version"]` = `"1.0"`
- `properties["header_encoding"]` = `"latin1"`
- `inputs[0]` = `{"shape": [2, 2], "dtype": "float32"}`
- `name`, `description`, `version` are all `None`

---

## numpy/example-model-v2.npy

| Property | Value |
| :--- | :--- |
| Format | NumPy v2.0 (`.npy`) |
| NPY version | 2.0 - 4-byte LE uint32 header length, latin1 header encoding |
| Shape | `(2, 2)` |
| dtype | `float32` |
| Data | `[[1.0, 2.0], [3.0, 4.0]]` |
| Size | 144 bytes |
| SHA-256 | `f133b24fb6c1a4cd7dff975636fdc2d93616bb40afa0e2e6ce59e4bbf34e18e1` |
| License | CC0-1.0 |
| Source | Generated for testing purpose |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `properties["npy_format_version"]` = `"2.0"`
- `properties["header_encoding"]` = `"latin1"`
- `inputs[0]` = `{"shape": [2, 2], "dtype": "float32"}`
- `name`, `description`, `version` are all `None`

---

## numpy/example-model-v3.npy

| Property | Value |
| :--- | :--- |
| Format | NumPy v3.0 (`.npy`) |
| NPY version | 3.0 - 4-byte LE uint32 header length, UTF-8 header encoding |
| Shape | `(2,)` |
| dtype | `[('π_weights', '<f4', (2,))]` (structured dtype with Unicode field name) |
| Data | `[([1., 2.],), ([3., 4.],)]` |
| Size | 144 bytes |
| SHA-256 | `8cd3ec2addd4446899352d1408a4849762e4d453d584c56e375216fce3344dd8` |
| License | CC0-1.0 |
| Source | Generated for testing purpose |
| Required library | `numpy` (`pip install pitloom[numpy]`) |

Notable metadata extracted by the NumPy extractor:

- `properties["npy_format_version"]` = `"3.0"`
- `properties["header_encoding"]` = `"utf-8"` - required for the Unicode field
  name `π_weights` (Greek letter π); version 1.x/2.x latin1 encoding would
  reject this header
- `inputs[0]["dtype"]` contains `"π_weights"` - confirms UTF-8 round-trip
- `name`, `description`, `version` are all `None`
