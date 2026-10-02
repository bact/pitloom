---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# PyTorch PT2 fixtures

File details for `pytorch_pt2/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## pytorch_pt2/example-model.pt2

| Property | Value |
| :--- | :--- |
| Format | PyTorch PT2 Archive (ExecuTorch on-device format) - ZIP archive |
| Architecture | `nn.Linear(10, 1)` (linear regression) |
| Task | Linear regression (10 features -> 1 output) |
| Description | A serialized PT2 model for metadata extraction test. |
| Version | 1.0.0 |
| Input | `x`: float32 `[batch, 10]` |
| Output | `linear`: float32 `[batch, 1]` |
| Author | Pitloom |
| Tags | regression |
| Size | 8 800 bytes |
| SHA-256 | `7f057931a7094fd88dcc1a9331a73b5a2fe0769e285ea8b63e1d31a8372319f5` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | None (uses stdlib `zipfile` + `json`) |

Notable metadata extracted by the PT2 extractor:

- `version` = `"1.0.0"` (from `extra/model_version`; takes precedence over `archive_version`)
- `description` = `"A serialized PT2 model for metadata extraction test."`
  (from `extra/description`)
- `license` = `"CC0-1.0"` (from `extra/license`)
- `properties["author"]` = `"Pitloom"` (from `extra/author`)
- `properties["tags"]` = `"regression"` (from `extra/tags`)
- `inputs` = `[{"name": "x"}]`, `outputs` = `[{"name": "linear"}]` (from `models/model.json`)
- `type_of_model` = `None` - PT2 extractor does not inspect pickle data
- `name` = `None` - no `extra/name` or `METADATA.json` with name in this fixture
