---
Created: 2026-07-11
Last-Modified: 2026-08-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI UX Analysis: Consolidating Generation Subcommands & Input-Centric Redesign

This document details the architectural evolution of Pitloom's CLI subcommands, from stage-centric names (`source`, `analyze`, `deployed`) to an **Input-Centric Surface** with CISA SBOM Types compliance.

---

## 1. Background & Evolution

### Initial State (v0.12.0+)
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

## 4. Input-Centric CLI Architecture

```
                       +----------------------------------+
                       |    loom generate [TARGET]        |  <-- Smart Auto-Detect Entrypoint
                       +----------------------------------+
                                        |
       +-------------------+------------+------------+-------------------+
       |                   |                         |                   |
[ loom project ]     [ loom wheel ]            [ loom model ]      [ loom env ]
 (Source / Sdist)     (Built .whl)              (GGUF/Safetensors   (Installed venv)
                                                 HF URLs --offline)
```

### Subcommand Specification

#### 1. Smart Entrypoint: `loom generate [TARGET]`
Auto-detects the target type and dispatches to the corresponding target command:
```bash
loom generate .                          # Project directory -> Source SBOM
loom generate mypkg-1.0.0.tar.gz         # Sdist archive     -> Source SBOM
loom generate dist/pkg-1.0-py3-none.whl  # Wheel file        -> Analyzed SBOM
loom generate models/model.gguf          # Model file        -> AI Model SBOM
loom generate mistralai/Mistral-7B      # HF Model ID       -> Remote AI Model SBOM
loom generate env                      # Active venv       -> Deployed SBOM
```

#### 2. Project Source & Sdist: `loom project [PATH]`
Scans unbuilt source directories OR archived source distributions (`.tar.gz` / `.zip` sdists):
```bash
loom project .                           # Unpacked project root
loom project /path/to/project
loom project dist/mypkg-1.0.0.tar.gz     # Native sdist support (no manual extraction required)
```
- **CISA SBOM Type**: `Source` (`software_sbomType = [source]`)

#### 3. Built Wheel: `loom wheel <WHEEL_FILE>`
Inspects built Python `.whl` archives:
```bash
loom wheel dist/mypkg-1.0.0-py3-none-any.whl -o sbom.spdx3.json
```
- **CISA SBOM Type**: `Analyzed` (`software_sbomType = [analyzed]`)

#### 4. AI Model Asset: `loom model <FILE_OR_URL> [--offline]`
Inspects local model weight files (`.gguf`, `.safetensors`, `.onnx`, `.pt`, etc.) or Hugging Face Hub repositories:
```bash
loom model models/sentiment.gguf
loom model mistralai/Mistral-7B-v0.1
loom model models/sentiment.gguf --offline    # Guarantees zero network calls in sandboxed runners
```
- **CISA SBOM Type**: `Analyzed` (`software_sbomType = [analyzed]`, `ai_AIPackage`)

#### 5. Deployed Environment: `loom env`
Inspects active Python environment (`site-packages` via `pipdeptree`):
```bash
loom env -o env.spdx3.json
```
- **CISA SBOM Type**: `Deployed` (`software_sbomType = [deployed]`)

#### 6. Fragment Merging: `loom merge <FRAGMENTS_DIR>`
Stitches dynamic `@loom.run` runtime execution fragments into a static parent SBOM:
```bash
loom merge .spdx3-fragments/ -o combined.spdx3.json
```
- **CISA SBOM Type**: `Runtime` (`software_sbomType = [runtime]`)

---

## 5. Input Target to CISA SBOM Type Mapping

| Subcommand | Input Target | Network | CISA SBOM Type | SPDX 3 `software_sbomType` |
| :--- | :--- | :--- | :--- | :--- |
| `loom project` | Directory or `.tar.gz`/`.zip` sdist | Offline | **Source** | `[source]` |
| `loom wheel` | Built `.whl` archive | Offline | **Analyzed** | `[analyzed]` |
| `loom model` | Local `.gguf`/`.safetensors`/`.onnx` file | Offline | **Analyzed** | `[analyzed]` |
| `loom model` | Hugging Face URL / Model ID | Online (unless `--offline`) | **Analyzed** | `[analyzed]` |
| `loom env` | Python `venv` / `site-packages` | Offline | **Deployed** | `[deployed]` |
| `loom merge` | Dynamic execution `.spdx3.json` fragments | Offline | **Runtime** | `[runtime]` |
| *Hatchling Hook* | `hatch build` wheel output | Offline | **Build** | `[build]` |
