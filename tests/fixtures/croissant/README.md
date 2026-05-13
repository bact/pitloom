---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Croissant fixtures

Synthetic JSON-LD files in [Croissant](https://mlcommons.org/croissant/) format,
used by [tests/test_extract_croissant.py](../../test_extract_croissant.py) to test
dataset metadata extraction via `pitloom.extract._croissant`.

## Fixtures

| File | Purpose |
| - | - |
| `minimal.json` | Bare-minimum valid Croissant document — only `@context`, `@type`, and `name`. Tests graceful handling of absent optional fields. |
| `full.json` | Complete Croissant document with all commonly extracted fields: `name`, `description`, `version`, `license`, `url`, `keywords`, `creator`, RAI fields (`rai:dataCollection`, `rai:dataBiases`, `rai:dataPreprocessingProtocol`, `rai:personalSensitiveInformation`), and a `cr:recordSet` with typed fields. |
| `prefixed.json` | Croissant document where schema.org terms use explicit `sc:` prefix (e.g. `sc:name`, `sc:license`) instead of bare keys. Tests that prefix normalization works correctly alongside `cr:` and `rai:` prefixes. |

## Context variants covered

| Pattern | File | Notes |
| - | - | - |
| Bare `@vocab` context | `minimal.json`, `full.json` | `@vocab` set to `https://schema.org/`; schema.org keys unprefixed |
| Explicit `sc:` prefix | `prefixed.json` | `sc` mapped to `https://schema.org/`; all schema.org keys use `sc:` |
| RAI extension | `full.json`, `prefixed.json` | `rai` mapped to `http://mlcommons.org/croissant/RAI/1.0/` |
| `cr:recordSet` | `full.json`, `prefixed.json` | Record set with typed fields and item counts |
