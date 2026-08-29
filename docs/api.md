---
Created: 2026-08-11
Last-Modified: 2026-08-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# API reference

Auto-generated from docstrings -- full signatures, parameter types, and
defaults for the same [Python API](python-api.md) surface that page
introduces narratively. Start there for how to use it; come here for the
exact call signature.

## Generator functions

::: pitloom.assemble.generate

::: pitloom.assemble.generate_project_sbom

::: pitloom.assemble.generate_wheel_sbom

::: pitloom.assemble.generate_model_sbom

::: pitloom.assemble.generate_env_sbom

::: pitloom.assemble.enrich_model

## Wheel embedding

::: pitloom.embed.embed_wheel_sbom

::: pitloom.embed.embed_sbom_in_wheel

::: pitloom.embed.ConfigOverrides

## Fragment merging

::: pitloom.assemble.merge_fragments

::: pitloom.assemble.FragmentMergeError

## Tracking decorator

`loom.run` is the `Run` class below (`run = Run`) -- use it as a
decorator or a context manager, as shown on the [Python
API](python-api.md#tracking-decorator) page.

::: pitloom.loom.Run

::: pitloom.loom.set_model

::: pitloom.loom.use_model

::: pitloom.loom.set_model_hyperparameters

::: pitloom.loom.add_dataset

::: pitloom.loom.add_validation_dataset

::: pitloom.loom.add_input_dataset

::: pitloom.loom.add_output_dataset

## Creation metadata

::: pitloom.core.creation.CreationMetadata

::: pitloom.core.creation.Creator

::: pitloom.core.creation.Tool

::: pitloom.core.creation.VALID_CREATOR_TYPES

::: pitloom.core.creation.resolve_source_date_epoch

## Provenance configuration

::: pitloom.core.provenance.ProvenanceConfig

::: pitloom.core.provenance.normalize_max_source_metadata_bytes

## ID registry

::: pitloom.ids.IdRegistry

::: pitloom.ids.resolve_registry

::: pitloom.ids.EntityEntry

::: pitloom.ids.FileEntry

::: pitloom.ids.DEFAULT_REGISTRY_FILENAME
