---
Created: 2026-07-11
Last-Modified: 2026-08-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI UX Analysis: Consolidating Generation Subcommands & Input-Centric Redesign

See [docs/cli.md](../../docs/cli.md) for the shipped subcommand
reference and worked examples -- this file covers the rationale behind
the redesign, not the current command surface itself.

> **Status:** Design Approved (2026-08-08) — Post-v0.12.0 Architectural
> Decision. Merged 2026-08-11 from a separate `cisa-sbom-lifecycle.md`
> draft of the same decision (Python API section and downstream-impact
> notes below came from there) — kept as one file since the two had
> near-total content overlap.

This document details the architectural evolution of Pitloom's CLI subcommands, from stage-centric names (`source`, `analyze`, `deployed`) to an **Input-Centric Surface** with CISA SBOM Types compliance.

## Specification reference & governance context

Pitloom's lifecycle data model is aligned with official CISA guidance:

- **CISA Specification**: [Types of Software Bill of Materials (SBOM) Documents (April 2023)](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf)
- **SPDX 3 Specification**: [SPDX 3.0.1 Model Standard](https://spdx.github.io/spdx-spec/v3.0.1/)
- **PEP Specification**: [PEP 770 — Embedding SPDX SBOMs in Python Packages](https://peps.python.org/pep-0770/)

---

## 1. Background & Evolution

### Initial State (post-v0.12.0 and pre-v0.13.0)

The CLI initially exposed subcommands named directly after CISA SBOM lifecycle stages:

- `loom source [project_dir]` (Source SBOM)
- `loom analyze <target>` (Analyzed SBOM — handles `.whl`, local model binaries, and Hugging Face URLs)
- `loom deployed` (Deployed SBOM — active environment)
- `loom ids ...` (Registry management)

---

## 2. Architectural Critique of Stage-Centric Subcommands

An architectural review post-v0.12.0 identified key friction points with stage-centric CLI subcommands:

1. **Mental Model Mismatch**: Developers think in terms of concrete **input targets** (`pyproject.toml`, `.whl`, `venv`, `.gguf` file, HF URL), not CISA procurement taxonomy (*"Analyzed"* vs *"Source"*).
2. **Subcommand Overloading in `loom analyze`**: `loom analyze` mixed three distinct operations:
   - Local `.whl` ZIP extraction (package binary analysis).
   - Local `.gguf`/`.safetensors`/`.onnx` magic-byte file header scans (AI model asset analysis).
   - Remote Hugging Face URL/ID HTTP network queries (external web metadata fetching).
3. **Hidden Network Side-Effects**: Running `loom analyze mistralai/Mistral-7B` triggered external HTTP network calls, while `loom analyze model.gguf` was offline local inspection. In sandboxed CI/CD or agent runners, hidden network calls cause unexpected failures.
4. **Grammatical Inconsistency**: `source` (noun), `analyze` (imperative verb), `deployed` (adjective/past participle).

---

## 3. Decoupling User UX from Internal CISA Data Model

The key resolution is to separate the **User Interface (UX)** from the **Emitted Data Model**:

- **Emitted SPDX 3 Data Model (100% Strict CISA Compliance)**:
  The generated SPDX 3 JSON-LD SBOM strictly sets `software_sbomType` (`source`, `build`, `analyzed`, `deployed`, `runtime`), `CreationInfo`, `build_datetime`, and element provenance per the official [CISA Types of Software Bill of Materials (SBOM) Documents (April 2023)](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf).
- **User Interface (Input-Centric Surface)**:
  Subcommands are named after clear input targets (`project`, `wheel`, `model`, `env`, `merge`), while Pitloom automatically maps those inputs to the appropriate CISA SBOM Type in the underlying assembly layer.

---

## 4. Input Target to CISA SBOM Type Mapping

| Subcommand | Input Target | Network | CISA SBOM Type | SPDX 3 `software_sbomType` |
| :--- | :--- | :--- | :--- | :--- |
| `loom project` | Directory or `.tar.gz`/`.zip` sdist | Offline | **Source** | `[source]` |
| `loom wheel` | Built `.whl` archive | Offline | **Analyzed** | `[analyzed]` |
| `loom model` | Local `.gguf`/`.safetensors`/`.onnx` file | Offline | **Analyzed** | `[analyzed]` |
| `loom model` | Hugging Face URL / Model ID | Online (unless `--offline`) | **Analyzed** | `[analyzed]` |
| `loom env` | Python `venv` / `site-packages` | Offline | **Deployed** | `[deployed]` |
| `loom merge` | Dynamic execution `.spdx3.json` fragments | Offline | **Runtime** | `[runtime]` |
| *Hatchling Hook* | `hatch build` wheel output | Offline | **Build** | `[build]` |

## 5. Downstream integration impact

1. **`pitloom.loom` Decorators**: `@loom.run` context managers emit CISA **Runtime SBOM fragments** without corrupting static build metadata. `loom merge` allows command-line stitching.
2. **`SKILL.md` Agent Recipes**: Simplifies LLM agent routing trees (`loom generate <target>` or explicit target commands).
3. **Claude Code Plugin**: `loom model --offline` protects network-sandboxed Claude Code tool calls from unexpected external HTTP errors.
