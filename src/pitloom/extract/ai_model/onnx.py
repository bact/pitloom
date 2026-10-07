# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""ONNX model metadata extractor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import (
    record_dict_field_provenance,
    sanitize_provenance_text,
)
from pitloom.extract.ai_model.reader_requirements import missing_library
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

# graph.name values written by exporters when the user names nothing: they
# identify the tool, not the model, so they are not read as its name.
_EXPORTER_DEFAULT_GRAPH_NAMES = frozenset(
    {
        "main_graph",  # torch.onnx, seen from PyTorch 2.6.0
        "tf2onnx",  # tf2onnx
        "torch-jit-export",  # torch.onnx, seen from PyTorch 1.8
        "torch_jit",  # torch.onnx, seen from PyTorch 1.12.0 and 1.13.1
    }
)

# Standard metadata_props key defined by the ONNX IR spec ("Optional Metadata"):
# https://onnx.ai/onnx/repo-docs/IR.html#optional-metadata
_MODEL_LICENSE_KEY = "model_license"

# model_version packs SemVer as MAJOR (16 bits), MINOR (16), PATCH (32); zero
# upper 32 bits mark a simple number instead. See "Serializing SemVer version
# numbers in protobuf" in https://onnx.ai/onnx/repo-docs/Versioning.html
_SEMVER_FLAG_SHIFT = 32
_UINT64_MASK = 0xFFFF_FFFF_FFFF_FFFF


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


def _extract_onnx_properties(
    model: Any, source: str, provenance: dict[str, str]
) -> dict[str, str]:
    """Extract domain, opset versions, and metadata_props into properties dict."""
    properties: dict[str, str] = {}
    domain = model.domain if model.domain else None
    if domain:
        properties["domain"] = domain

    for opset in model.opset_import:
        opset_domain = opset.domain if opset.domain else "ai.onnx"
        properties[f"opset.{opset_domain}"] = str(opset.version)

    for prop in model.metadata_props:
        properties[prop.key] = prop.value

    record_dict_field_provenance(provenance, "properties", properties, source)
    return properties


def _resolve_onnx_name(
    graph_name: str, source: str, provenance: dict[str, str]
) -> str | None:
    """Return ``graph.name``, or ``None`` when it is empty or an exporter
    default, leaving the name to the assembler's file-name fallback."""
    if not graph_name or graph_name in _EXPORTER_DEFAULT_GRAPH_NAMES:
        return None
    provenance["name"] = f"{source} | Field: graph.name"
    return graph_name


def _decode_model_version(value: int) -> tuple[str, bool]:
    """Return ``(version, is_semver)`` for an ONNX ``model_version``.

    See https://onnx.ai/onnx/repo-docs/Versioning.html
    """
    packed = value & _UINT64_MASK
    if packed >> _SEMVER_FLAG_SHIFT == 0:
        return str(value), False
    major = packed >> 48
    minor = (packed >> _SEMVER_FLAG_SHIFT) & 0xFFFF
    patch = packed & 0xFFFF_FFFF
    return f"{major}.{minor}.{patch}", True


def _resolve_onnx_license(
    properties: dict[str, str], source: str, provenance: dict[str, str]
) -> str | None:
    """Return the ``model_license`` metadata property, if it has a value."""
    license_expr = properties.get(_MODEL_LICENSE_KEY, "").strip()
    if not license_expr:
        return None
    provenance["license"] = f"{source} | Field: {_MODEL_LICENSE_KEY}"
    return license_expr


# pylint: disable=too-many-locals
def read_onnx(model_path: Path) -> AiModelMetadata:
    """Extract metadata from an ONNX model file.

    ``name`` is ``graph.name``, or ``None`` when ``graph.name`` is empty or
    an exporter default (``torch_jit``, ``tf2onnx``, ...).
    ``license`` is the standard ``model_license`` metadata property.
    ``version`` is ``model_version``, decoded to ``MAJOR.MINOR.PATCH`` when
    its upper 32 bits are non-zero (bit-packed SemVer). ``type_of_model`` is
    always ``"neural network"``; ``domain`` is kept in ``properties`` only.

    Requires the ``onnx`` package (``pip install onnx``).
    """
    try:
        # pylint: disable=import-outside-toplevel
        import onnx
    except ImportError as exc:
        raise missing_library(AiModelFormat.ONNX) from exc

    try:
        # load_external_data=False avoids loading large external tensor files
        model = onnx.load(str(model_path), load_external_data=False)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to load ONNX model from %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(f"Failed to load ONNX model from {model_path}: {exc}") from exc

    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    provenance: dict[str, str] = {}

    format_version: str | None = None
    if model.ir_version:
        format_version = str(model.ir_version)
        provenance["format_version"] = f"{source} | Field: ir_version"

    framework = model.producer_name if model.producer_name else None
    if framework:
        provenance["framework"] = f"{source} | Field: producer_name"

    framework_version = model.producer_version if model.producer_version else None
    if framework_version:
        provenance["framework_version"] = f"{source} | Field: producer_version"

    name = _resolve_onnx_name(model.graph.name, source, provenance)
    doc_string = model.doc_string if model.doc_string else None

    description = doc_string
    if description:
        provenance["description"] = f"{source} | Field: doc_string"

    version: str | None = None
    if model.model_version:
        version, is_semver = _decode_model_version(model.model_version)
        provenance["version"] = f"{source} | Field: model_version" + (
            " | Method: semver_bit_packed" if is_semver else ""
        )

    properties = _extract_onnx_properties(model, source, provenance)
    license_expr = _resolve_onnx_license(properties, source, provenance)

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
        license=license_expr,
        # ONNX has no model-type field. ``domain`` is the owner's reverse-DNS
        # namespace (``org.onnx``), not a type; it stays in ``properties``.
        type_of_model="neural network",
        properties=properties,
        inputs=inputs,
        outputs=outputs,
        provenance=provenance,
    )
