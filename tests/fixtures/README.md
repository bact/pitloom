---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Test fixtures

1. Project fixtures (`projects/`)
    - For project metadata extraction testing
    - For build-backend hook testing
    - [Details](./projects/README.md)
2. SBOM fragments fixtures (`fragments/`)
    - For SBOM aggregation testing
    - [Details](./fragments/README.md)
3. AI model fixtures (`aimodels/`)
    - For AI model metadata extraction testing
    - [Details](./aimodels/README.md)
4. Hugging Face Hub fixtures (`huggingface-hub/`)
    - For AI model metadata retrieval from HG Hub testing
    - [Details](./huggingface-hub/README.md)
5. Croissant fixtures (`croissant/`)
    - For Dataset metadata extraction testing
    - [Details](./croissant/README.md)
6. Real-world project fixtures (`real-world-projects/`)
    - Vendored sdist archives of real, published PyPI packages, one per
      build backend, for wheel-file-discovery regression testing
    - [Details](./real-world-projects/README.md)
7. pipdeptree output fixtures (`pipdeptree/`)
    - Captured `pipdeptree --json` / `--json-tree` output for `loom env`
      testing
    - [Details](./pipdeptree/README.md)
8. Licence text fixtures (`license-texts/`)
    - Real `LICENSE` files that `licenseid` alone ranks wrong or misses,
      for licence-detection regression testing
    - [Details](./license-texts/README.md)
9. Real-world extras fixtures (`real-world-extras/`)
    - Real `pyproject.toml` files of published packages that declare
      extras, one or more per build backend, for extras-reader testing
    - [Details](./real-world-extras/README.md)
10. SPDX model snapshot (`spdx-model/`)
    - Unmodified SPDX 3.0.1 context, SHACL model and JSON schema
      (Community-Spec-1.0), for offline `spdx3-validate` runs
    - [Details](./spdx-model/README.md)
11. Conformance fixtures (`conformance/`)
    - Expected G7 SBOM for AI, CISA 2026, FSCT 2024 and BSI rule outcomes per
      scenario and snapshots of their SPDX 3.0 mappings, for
      `tests/conformance/`
    - [Details](./conformance/README.md)
12. Git LFS pointer fixtures (`lfs-pointers/`)
    - Real Git LFS pointers from the Hugging Face Hub (pointer text only),
      for Git LFS pointer detection testing
    - [Details](./lfs-pointers/README.md)
