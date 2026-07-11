---
Created: 2026-07-11
Last-Modified: 2026-07-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI UX Analysis: Consolidating Generation Subcommands

This document analyzes the proposal to consolidate all lifecycle-centric SBOM generation subcommands under a single `from` (or similar) parent subcommand. 

## Current State

Currently, the CLI exposes generation modes directly at the top level, aligned loosely with CISA SBOM types:
* `loom source .` (Source SBOM)
* `loom analyze my_wheel.whl` (Analyzed SBOM)
* `loom deployed` (Deployed SBOM)
* `loom model model.bin` (AI Analyzed SBOM)
* `loom ids ...` (Registry management)

## Proposed State

The proposal suggests consolidating the generation commands:
* `loom from source`
* `loom from deployed`
* `loom from analyze`
* `loom from build`

## Analysis of the `loom from` Approach

### Pros
1. **Namespace Cleanliness**: It keeps the root namespace clean. If `loom` ever gains other top-level features (e.g., `loom verify`, `loom diff`, `loom merge`), pushing all generation into `from` prevents subcommand clutter.
2. **Mental Model Alignment**: It explicitly communicates to the user that they are generating an artifact *originating from* a specific state or lifecycle stage.

### Cons
1. **Verbosity**: It requires typing an extra word for every generation command (e.g., `loom source` is faster to type than `loom from source`).
2. **Grammar and Semantics**: 
    * "from" usually denotes an *input source* (e.g., "from a wheel", "from an environment"). 
    * "source", "deployed", and "build" can function as nouns describing the input origin, but "analyze" is an action (verb) or a state (analyzed). 
    * Saying `loom from analyze` reads slightly awkwardly compared to `loom from analyzed` or `loom from wheel`.

### Alternative: Action-Centric (`loom generate`)
Instead of `from`, using an action verb like `generate` might map more cleanly to CISA SBOM types:
* `loom generate source`
* `loom generate analyzed`
* `loom generate deployed`
* `loom generate build`

This aligns perfectly with the language: "Generate a Source SBOM", "Generate an Analyzed SBOM".

### Alternative: Input-Centric (`loom from`)
If we stick to `from`, the targets should describe the *inputs* rather than the output types:
* `loom from source` (Input: source tree)
* `loom from wheel` (Input: built artifact / Maps to Analyzed)
* `loom from env` (Input: Python environment / Maps to Deployed)
* `loom from model` (Input: AI model)

## Conclusion

Consolidating the commands is a solid architectural direction for future-proofing the CLI against bloat. 

However, if we adopt `loom from <target>`, we should ensure the `<target>` grammatically describes the input (e.g., `wheel`, `env`, `source`). If we want the target to describe the CISA lifecycle stage (Source, Analyzed, Deployed), a verb like `loom generate <stage>` (e.g., `loom generate analyzed`) provides a more natural sentence structure. 

*Recommendation*: Wait until a need for top-level non-generation commands (like `verify` or `merge`) arises before introducing the extra level of nesting, as flat CLI structures are often preferred by users for rapid usage. If consolidation is pursued, `loom generate <lifecycle_stage>` or `loom from <input_source>` are the two most linguistically consistent paths.
