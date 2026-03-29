# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""ONNX model metadata extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata


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


def read_onnx(model_path: Path) -> AiModelMetadata:  # pylint: disable=too-many-locals
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
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    # ONNX IR format version (integer, e.g. 9 for IR version 9)
    format_version: str | None = None
    if model.ir_version:
        format_version = str(model.ir_version)
        provenance["format_version"] = f"{source} | Field: ir_version"

    # Producer name/version (the framework that exported the model)
    framework = model.producer_name if model.producer_name else None
    if framework:
        provenance["framework"] = f"{source} | Field: producer_name"

    framework_version = model.producer_version if model.producer_version else None
    if framework_version:
        provenance["framework_version"] = f"{source} | Field: producer_version"

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
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.ONNX,
            format_version=format_version,
            framework=framework,
            framework_version=framework_version,
        ),
        name=name,
        description=description,
        version=version,
        type_of_model=domain or "neural network",
        properties=properties,
        inputs=inputs,
        outputs=outputs,
        provenance=provenance,
    )
