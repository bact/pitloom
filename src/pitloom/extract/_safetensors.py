# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Safetensors model metadata extractor."""

from __future__ import annotations

from pathlib import Path

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata


def read_safetensors(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a Safetensors model file.

    Requires the ``safetensors`` package (``pip install safetensors``).

    The Safetensors format stores an optional ``__metadata__`` dict in its
    header alongside tensor descriptors (name, dtype, shape). This extractor
    reads only the header — it does not load tensor data into memory.

    Commonly stored ``__metadata__`` keys (by convention):
    - ``modelspec.architecture`` -> type_of_model
    - ``modelspec.title`` or ``name`` -> name
    - ``modelspec.description`` or ``description`` -> description

    Args:
        model_path: Path to a ``.safetensors`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ImportError: If ``safetensors`` is not installed.
        ValueError: If the file cannot be read as a valid Safetensors file.
    """
    try:
        from safetensors import safe_open  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "The 'safetensors' package is required "
            "to extract Safetensors model metadata. "
            "Install it with: pip install safetensors"
        ) from exc

    try:
        # Use numpy framework to avoid requiring torch/tf; metadata-only read
        with safe_open(
            str(model_path),
            framework="numpy",
        ) as f:  # type: ignore[no-untyped-call]
            raw_metadata: dict[str, str] = f.metadata() or {}
            tensor_keys: list[str] = list(f.keys())
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(
            f"Failed to read Safetensors file {model_path}: {exc}"
        ) from exc

    source = f"Source: {model_path.name}"
    provenance: dict[str, str] = {}

    # Pull well-known keys from __metadata__
    name = (
        raw_metadata.get("modelspec.title")
        or raw_metadata.get("name")
        or raw_metadata.get("ss_base_model_version")
    )
    if name:
        provenance["name"] = f"{source} | Field: __metadata__"

    description = raw_metadata.get("modelspec.description") or raw_metadata.get(
        "description"
    )
    if description:
        provenance["description"] = f"{source} | Field: __metadata__"

    version = raw_metadata.get("modelspec.version") or raw_metadata.get("version")
    if version:
        provenance["version"] = f"{source} | Field: __metadata__"

    type_of_model = raw_metadata.get("modelspec.architecture") or raw_metadata.get(
        "architecture"
    )
    if type_of_model:
        provenance["type_of_model"] = f"{source} | Field: __metadata__"

    # Remaining metadata as properties
    properties = dict(raw_metadata.items())
    if properties:
        provenance["properties"] = f"{source} | Field: __metadata__"

    # Tensor key listing as a lightweight inventory (names only, no data loaded)
    inputs = [{"name": k} for k in tensor_keys]
    if inputs:
        provenance["inputs"] = f"{source} | Field: tensor keys (header only)"

    return AiModelMetadata(
        format=AiModelFormat.SAFETENSORS,
        name=name,
        description=description,
        version=version,
        type_of_model=type_of_model,
        properties=properties,
        inputs=inputs,
        provenance=provenance,
    )
