---
Created: 2026-08-08
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Architecture Design: CISA SBOM Lifecycle Types & Input-Centric Interfaces

> **Status:** Design Approved (2026-08-08) — Post-v0.12.0 Architectural Decision.

This document records the architectural review and design decisions regarding Pitloom's adoption of the **CISA Types of Software Bill of Materials (SBOM) Documents** framework and the resulting **Input-Centric Surface Architecture** for CLI subcommands, Python API, Hatchling build hook, and LLM agent tooling.

---

## 1. Specification Reference & Governance Context

Pitloom's lifecycle data model is aligned with official CISA guidance:
- **CISA Specification**: [Types of Software Bill of Materials (SBOM) Documents (April 2023)](https://www.cisa.gov/sites/default/files/2023-04/sbom-types-document-508c.pdf)
- **SPDX 3 Specification**: [SPDX 3.0.1 Model Standard](https://spdx.github.io/spdx-spec/v3.0.1/)
- **PEP Specification**: [PEP 770 — Embedding SPDX SBOMs in Python Packages](https://peps.python.org/pep-0770/)

---

## 2. The 6 CISA SBOM Types & Pitloom Mapping

The CISA framework defines 6 distinct SBOM Document Types across the software lifecycle. Pitloom implements 5 automated generator modes (Design SBOMs are manual specifications outside generator scope):

```
+-----------------------------------------------------------------------------------+
|                            CISA SBOM LIFECYCLE TYPES                              |
+-----------+------------+------------+------------------+-------------+------------+
|  Design   |   Source   |   Build    |     Analyzed     |  Deployed   |  Runtime   |
| (Planned) | (Unbuilt)  | (Hatchling)| (Wheel/Model/HF) | (Installed) | (@loom.run)|
+-----------+------------+------------+------------------+-------------+------------+
```

| CISA Type | CISA Definition | Pitloom Input Target | Internal Generator Implementation | SPDX 3 `software_sbomType` |
| :--- | :--- | :--- | :--- | :--- |
| **1. Design** | Intended/planned architecture & dependencies before coding. | N/A (Spec phase) | *Out of scope for generator* | N/A |
| **2. Source** | Created directly from uncompiled source code files & repository metadata. | Repository root or `.tar.gz`/`.zip` sdist | `loom project [PATH]`<br>`generate_project_sbom()` | `[source]` |
| **3. Build** | Created during build execution; captures build tools, compiler, exact resolved wheel output. | Hatchling build hook | `pitloom.plugins.hatch`<br>(PEP 770 `.dist-info/sboms`) | `[build]` |
| **4. Analyzed**| Created by analyzing built release artifacts (wheels, model binaries) post-build. | Built `.whl` wheel archive,<br>Local model file (`.gguf`, `.safetensors`, `.onnx`),<br>Hugging Face model URL/repo ID | `loom wheel <WHEEL>`<br>`generate_wheel_sbom()`<br><br>`loom model <MODEL>`<br>`generate_model_sbom()` | `[analyzed]` |
| **5. Deployed**| Created by inspecting software installed in an operational environment. | Python virtualenv (`site-packages`) | `loom env`<br>`generate_env_sbom()` | `[deployed]` |
| **6. Runtime** | Created by monitoring dynamic software execution & loaded modules at runtime. | Python pipeline scripts | `@loom.run` decorators & `merge_fragments()` | `[runtime]` |

---

## 3. Core Architectural Decision: Decoupled Input-Centric Interface

### The Impedance Mismatch
An architectural review revealed that forcing CISA regulatory terms (`source`, `analyze`, `deployed`) directly as CLI subcommands and API functions creates cognitive friction:
1. **Mental Model Mismatch**: Developers think in concrete **input targets** (`pyproject.toml`, `.whl`, `venv`, `.gguf`, HF URL), not abstract procurement stages (*"CISA Stage 4 Analyzed Scanning"*).
2. **Subcommand Overloading in `loom analyze`**: `loom analyze` mixed local `.whl` ZIP extraction, local model binary header scans, and remote Hugging Face HTTP network requests.
3. **Hidden Network Side-Effects**: Running `loom analyze mistralai/Mistral-7B` triggered external network calls under a generic verb, threatening sandboxed CI/CD and LLM agent safety.

### The Resolution
Separate **Internal Data Model Compliance** from **External User Interface Ergonomics**:

- **Internal Data Model (100% CISA/SPDX 3 Compliant)**: Emitted JSON-LD graph strictly populates `software_sbomType`, `CreationInfo`, `build_datetime`, and element provenance nodes.
- **External User Interface (Input-Centric Surface)**: CLI subcommands (`project`, `wheel`, `model`, `env`, `merge`) and Python API functions (`generate_project_sbom`, `generate_wheel_sbom`, `generate_model_sbom`, `generate_env_sbom`) represent clear input targets.

---

## 4. Subcommand & API Specification

### CLI Surface (`src/pitloom/__main__.py`)
- **`loom generate [TARGET]`**: Smart entrypoint with automatic target detection.
- **`loom project [PATH]`**: Generates a CISA Source SBOM from a project directory OR an `.sdist` archive (`.tar.gz` / `.zip`).
- **`loom wheel <WHEEL_FILE>`**: Generates a CISA Analyzed SBOM from a built `.whl` file.
- **`loom model <FILE_OR_URL> [--offline]`**: Generates a CISA Analyzed AIBOM from a local model weight file or Hugging Face repository. `--offline` enforces no network calls.
- **`loom env`**: Generates a CISA Deployed SBOM from the active Python virtualenv.
- **`loom merge <FRAGMENTS_DIR>`**: Stitches CISA Runtime SBOM fragments generated by `@loom.run`.

### Python API (`src/pitloom/assemble/__init__.py`)
```python
import pitloom

# 1. Smart Unified Entrypoint
sbom_json = pitloom.generate(target=".")

# 2. Harmonized Explicit API (1:1 with CLI subcommands)
sbom_json = pitloom.generate_project_sbom(project_dir=Path("."))
sbom_json = pitloom.generate_wheel_sbom(wheel_path=Path("dist/pkg.whl"))
sbom_json = pitloom.generate_model_sbom(source="models/model.gguf", offline=True)
sbom_json = pitloom.generate_env_sbom()
```

---

## 5. Downstream Integration Impact

1. **`pitloom.loom` Decorators**: `@loom.run` context managers emit CISA **Runtime SBOM fragments** without corrupting static build metadata. `loom merge` allows command-line stitching.
2. **`SKILL.md` Agent Recipes**: Simplifies LLM agent routing trees (`loom generate <target>` or explicit target commands).
3. **Claude Code Plugin**: `loom model --offline` protects network-sandboxed Claude Code tool calls from unexpected external HTTP errors.
