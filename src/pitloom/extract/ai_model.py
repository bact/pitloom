# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for model metadata from AI model files.

Supports GGUF, ONNX, and Safetensors formats via optional dependencies.

    pip install pitloom[gguf]        # for GGUF support
    pip install pitloom[onnx]        # for ONNX support
    pip install pitloom[safetensors] # for Safetensors support
    pip install pitloom[aimodel]     # for all model formats
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata

__all__ = [
    "AiModelFormat",
    "AiModelMetadata",
    "detect_ai_model_format",
    "read_ai_model",
    "read_gguf",
    "read_onnx",
    "read_safetensors",
]

# File extension to format mapping
_EXTENSION_TO_FORMAT: dict[str, AiModelFormat] = {
    ".gguf": AiModelFormat.GGUF,
    ".onnx": AiModelFormat.ONNX,
    ".safetensors": AiModelFormat.SAFETENSORS,
}


def detect_ai_model_format(model_path: Path) -> AiModelFormat:
    """Detect model file format from its extension.

    The detection is based on the file extension (case-insensitive).
    If the extension is not recognized, ModelFormat.UNKNOWN is returned.

    Args:
        model_path: Path to the model file.

    Returns:
        ModelFormat matching the file extension, or ModelFormat.UNKNOWN.
    """
    return _EXTENSION_TO_FORMAT.get(model_path.suffix.lower(), AiModelFormat.UNKNOWN)


def read_ai_model(model_path: Path) -> AiModelMetadata:
    """Extract metadata from an AI model file, dispatching by format.

    Args:
        model_path: Path to the model file.

    Returns:
        AiModelMetadata populated with available fields.

    Raises:
        FileNotFoundError: If the model file does not exist.
        ValueError: If the format is unsupported or the file cannot be parsed.
    """
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    fmt = detect_ai_model_format(model_path)

    if fmt == AiModelFormat.GGUF:
        return read_gguf(model_path)
    if fmt == AiModelFormat.ONNX:
        return read_onnx(model_path)
    if fmt == AiModelFormat.SAFETENSORS:
        return read_safetensors(model_path)

    raise ValueError(
        f"Unsupported model format for file: {model_path}. "
        f"Supported extensions: {', '.join(_EXTENSION_TO_FORMAT)}"
    )


# ---------------------------------------------------------------------------
# GGUF extractor
# ---------------------------------------------------------------------------

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
    provenance: dict[str, str] = {}
    properties: dict[str, str] = {}
    hyperparameters: dict[str, Any] = {}

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


# ---------------------------------------------------------------------------
# ONNX extractor
# ---------------------------------------------------------------------------


def read_onnx(model_path: Path) -> AiModelMetadata:
    """Extract metadata from an ONNX model file.

    Requires the ``onnx`` package (``pip install onnx``).

    Extracted fields:
    - name: from the graph name or model doc_string
    - description: model doc_string
    - version: model_version integer cast to string
    - type_of_model: domain (e.g. "ai.onnx")
    - properties: metadata_props key/value pairs and opset versions
    - inputs/outputs: tensor names and shapes

    Args:
        model_path: Path to a ``.onnx`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ImportError: If ``onnx`` is not installed.
        ValueError: If the file cannot be loaded as a valid ONNX model.
    """
    try:
        import onnx  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "The 'onnx' package is required to extract ONNX model metadata. "
            "Install it with: pip install onnx"
        ) from exc

    try:
        # load_external_data=False avoids loading large external tensor files
        model = onnx.load(str(model_path), load_external_data=False)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to load ONNX model from {model_path}: {exc}") from exc

    source = f"Source: {model_path.name}"
    provenance: dict[str, str] = {}
    properties: dict[str, str] = {}

    # Graph name as the model name fallback
    graph_name = model.graph.name if model.graph.name else None
    doc_string = model.doc_string if model.doc_string else None

    name = graph_name
    if name:
        provenance["name"] = f"{source} | Field: graph.name"

    description = doc_string
    if description:
        provenance["description"] = f"{source} | Field: doc_string"

    version: str | None = None
    if model.model_version:
        version = str(model.model_version)
        provenance["version"] = f"{source} | Field: model_version"

    domain = model.domain if model.domain else None
    if domain:
        properties["domain"] = domain

    # Opset versions
    for opset in model.opset_import:
        opset_domain = opset.domain if opset.domain else "ai.onnx"
        properties[f"opset.{opset_domain}"] = str(opset.version)

    # metadata_props: list of StringStringEntryProto
    for prop in model.metadata_props:
        properties[prop.key] = prop.value

    if properties:
        provenance["properties"] = (
            f"{source} | Fields: metadata_props, opset_import, domain"
        )

    # Input tensor specifications
    inputs = _onnx_tensor_specs(model.graph.input)
    if inputs:
        provenance["inputs"] = f"{source} | Field: graph.input"

    # Output tensor specifications
    outputs = _onnx_tensor_specs(model.graph.output)
    if outputs:
        provenance["outputs"] = f"{source} | Field: graph.output"

    return AiModelMetadata(
        format=AiModelFormat.ONNX,
        name=name,
        description=description,
        version=version,
        type_of_model=domain or "neural network",
        properties=properties,
        inputs=inputs,
        outputs=outputs,
        provenance=provenance,
    )


def _onnx_tensor_specs(value_infos: Any) -> list[dict[str, Any]]:
    """Convert ONNX ValueInfoProto list to plain dicts."""
    specs = []
    for vi in value_infos:
        spec: dict[str, Any] = {"name": vi.name}
        tensor_type = vi.type.tensor_type
        if tensor_type.HasField("elem_type"):
            spec["dtype"] = tensor_type.elem_type
        shape = tensor_type.shape
        if shape:
            dims = []
            for d in shape.dim:
                if d.HasField("dim_value"):
                    dims.append(d.dim_value)
                elif d.HasField("dim_param"):
                    dims.append(d.dim_param)
                else:
                    dims.append(None)
            spec["shape"] = dims
        specs.append(spec)
    return specs


# ---------------------------------------------------------------------------
# Safetensors extractor
# ---------------------------------------------------------------------------


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
