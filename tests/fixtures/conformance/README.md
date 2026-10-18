---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Conformance fixtures

Data for `tests/conformance/` (G7 SBOM for AI, CISA 2026 and FSCT 2024 coverage,
checked with `ntia-conformance-checker`).

See also: [fixtures README](../README.md).

| File | What it is |
|---|---|
| `g7ai-expected.tsv` | Expected outcome of every G7 rule for each scenario SBOM (`present`, `missing`, `not-applicable`, `out-of-scope`). Edit it in the same commit as the change that moves a cell. |
| `g7ai2026-to-spdx30.sssom.tsv` | Snapshot of the [G7 -> SPDX 3.0.1 SSSOM mapping](https://bact.github.io/bom/mapping/g7ai2026-to-spdx30.sssom.tsv), CC0-1.0 per its header. `test_g7ai_sssom_gaps.py` checks its sha256. |
| `cisa2026-expected.tsv`, `fsct3-expected.tsv` | The same for CISA 2026 and FSCT 2024 (`fsct3` is the checker's id). |
| `cisa2026-to-spdx30.sssom.tsv`, `fsct2024-to-spdx30.sssom.tsv` | Snapshots of the matching mappings (CC0-1.0 per their headers), byte-identical to the published files. |

Regenerate an expected table with
`python scripts/g7_coverage_report.py [--standard cisa2026|fsct3] --write-expected`,
then review the diff.
