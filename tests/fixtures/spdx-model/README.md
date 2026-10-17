---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# SPDX model snapshot (offline validation)

Unmodified copies of the SPDX 3.0.1 machine-readable model, in the layout
`spdx3-validate` expects for `model_dir` (`<model_dir>/v3.0.1/`). Tests
validate SBOMs against them without network access.

See also: [fixtures README](../README.md).

## Files

| File | Source |
|---|---|
| `v3.0.1/spdx-context.jsonld` | <https://spdx.org/rdf/3.0.1/spdx-context.jsonld> |
| `v3.0.1/spdx-model.ttl` | <https://spdx.org/rdf/3.0.1/spdx-model.ttl> |
| `v3.0.1/spdx-json-schema.json` | <https://spdx.org/schema/3.0.1/spdx-json-schema.json> |

`v3.0.1/SHA256SUMS` records the checksums; tests compare the files to it.
Never edit the files by hand: `spdx-json-schema.json` uses CRLF line endings,
kept by `-text` in `.gitattributes`.

## Copyright and licence

```text
SPDX-FileCopyrightText: 2010-2024 The Linux Foundation and its Contributors
SPDX-License-Identifier: Community-Spec-1.0
```

The SPDX Specification, including these files, is provided under the
Community Specification License 1.0 (`v3.0.1/LICENSE`). Portions of the
specification from copyright holders who did not contribute under that
licence are provided under CC-BY-3.0; see the upstream
[LICENSE](https://github.com/spdx/spdx-spec/blob/development/v3.0.1/LICENSE).

The files are excluded from the sdist. This README and `SHA256SUMS` are
Pitloom's own and are CC0-1.0.
