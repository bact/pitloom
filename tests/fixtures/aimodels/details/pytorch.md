---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# PyTorch classic fixtures

File details for `pytorch/`. See also: [AI model fixtures](../README.md)
(summary, licences, hostile files).

## pytorch/example-model.pt

| Property | Value |
| :--- | :--- |
| Format | PyTorch classic (`.pt`) - full model (`torch.save(model, ...)`) |
| Architecture | `nn.Linear(10, 1)` (linear regression) |
| Task | Linear regression (10 features -> 1 output) |
| Input | `x`: float32 `[batch, 10]` |
| Output | float32 `[batch, 1]` |
| Size | 2 637 bytes |
| SHA-256 | `38c9cf8d5d491fd9a85e8e311e172406f6edda0d961fa9aa6ec04f249a002186` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | `torch` (`pip install pitloom[pytorch]`) |

Notable metadata extracted by the PyTorch extractor:

- `format` = `AiModelFormat.PYTORCH` (detected via ZIP magic bytes)
- `type_of_model` = `None` - class name extraction requires the optional
  `fickling` library
- `name`, `description`, `version` are all `None` - PyTorch classic format
  embeds no model metadata

---

## pytorch/example-model.pth

| Property | Value |
| :--- | :--- |
| Format | PyTorch classic (`.pth`) - weights-only (`torch.save(model.state_dict(), ...)`) |
| Architecture | `nn.Linear(10, 1)` (linear regression) |
| Task | Linear regression (10 features -> 1 output) - weights-only save (no class info) |
| Input | `x`: float32 `[batch, 10]` |
| Output | float32 `[batch, 1]` |
| Size | 2 005 bytes |
| SHA-256 | `748f37e6fc24a5ec7b77aa5186cb7cff662e5635317f65a4f2b800a6bd7f14d2` |
| License | CC0-1.0 |
| Source | Generated for testing purposes |
| Required library | `torch` (`pip install pitloom[pytorch]`) |

Notable metadata extracted by the PyTorch extractor:

- `format` = `AiModelFormat.PYTORCH` (detected via ZIP magic bytes)
- `type_of_model` = `None` - state-dict saves contain only tensors, no class name
- `name`, `description`, `version` are all `None`
