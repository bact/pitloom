# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF model metadata extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata

# Standard GGUF general keys used for SPDX AI fields
_GGUF_NAME_KEYS = ("general.name",)
_GGUF_DESCRIPTION_KEYS = ("general.description",)
_GGUF_ARCH_KEY = "general.architecture"
_GGUF_VERSION_KEY = "general.version"

# Hyperparameter key suffixes that are architecture-specific
_GGUF_HYPERPARAM_SUFFIXES = (
    ".context_length",
    ".embedding_length",
    ".feed_forward_length",
    ".block_count",
    ".attention.head_count",
    ".attention.head_count_kv",
    ".attention.layer_norm_rms_epsilon",
    ".rope.freq_base",
    ".rope.dimension_count",
)


def read_gguf(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a GGUF model file.

    Requires the ``gguf`` package (``pip install gguf``).

    GGUF stores typed key-value pairs in its header. This extractor reads:
    - ``general.*`` keys for name, description, architecture, and version
    - Architecture-specific hyperparameter keys (e.g. ``llama.context_length``)
    - All remaining key-value pairs as generic properties

    Args:
        model_path: Path to a ``.gguf`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ImportError: If ``gguf`` is not installed.
        ValueError: If the file cannot be read as a valid GGUF file.
    """
    try:
        from gguf import (  # pylint: disable=import-outside-toplevel
            GGUFReader,
            GGUFValueType,
        )
    except ImportError as exc:
        raise ImportError(
            "The 'gguf' package is required to extract GGUF model metadata. "
            "Install it with: pip install gguf"
        ) from exc

    try:
        reader = GGUFReader(str(model_path), mode="r")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to read GGUF file {model_path}: {exc}") from exc

    source = f"Source: {model_path.name}"
    hyperparameters: dict[str, Any] = {}
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    # Resolve field values to plain Python scalars
    def _field_value(gguf_field: Any) -> Any:
        parts = gguf_field.parts
        if not parts:
            return None
        last = parts[-1]
        # String fields are stored as a raw byte array; decode them explicitly
        if gguf_field.types and gguf_field.types[0] == GGUFValueType.STRING:
            return last.tobytes().decode("utf-8")
        if hasattr(last, "tolist"):
            val = last.tolist()
            return val[0] if isinstance(val, list) and len(val) == 1 else val
        return last

    fields: dict[str, Any] = {k: _field_value(v) for k, v in reader.fields.items()}

    name: str | None = None
    for key in _GGUF_NAME_KEYS:
        if key in fields and fields[key] is not None:
            name = str(fields[key])
            provenance["name"] = f"{source} | Field: {key}"
            break

    description: str | None = None
    for key in _GGUF_DESCRIPTION_KEYS:
        if key in fields and fields[key] is not None:
            description = str(fields[key])
            provenance["description"] = f"{source} | Field: {key}"
            break

    architecture: str | None = fields.get(_GGUF_ARCH_KEY)
    if architecture is not None:
        architecture = str(architecture)
        provenance["type_of_model"] = f"{source} | Field: {_GGUF_ARCH_KEY}"

    version: str | None = None
    if _GGUF_VERSION_KEY in fields and fields[_GGUF_VERSION_KEY] is not None:
        version = str(fields[_GGUF_VERSION_KEY])
        provenance["version"] = f"{source} | Field: {_GGUF_VERSION_KEY}"

    # Separate hyperparameters from general properties
    for key, value in fields.items():
        if value is None:
            continue
        if any(key.endswith(suffix) for suffix in _GGUF_HYPERPARAM_SUFFIXES):
            hyperparameters[key] = value
        else:
            properties[key] = str(value)

    if hyperparameters:
        provenance["hyperparameters"] = f"{source} | Fields: architecture-specific keys"

    if properties:
        provenance["properties"] = f"{source} | Fields: general.* and other GGUF keys"

    return AiModelMetadata(
        format=AiModelFormat.GGUF,
        name=name,
        description=description,
        version=version,
        type_of_model=architecture,
        hyperparameters=hyperparameters,
        properties=properties,
        provenance=provenance,
    )
