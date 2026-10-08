# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""ONNX model metadata extractor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    record_scalar_property,
    source_metadata,
)
from pitloom.extract._extract_utils import (
    record_dict_field_provenance,
    sanitize_provenance_text,
)
from pitloom.extract.ai_model.reader_requirements import missing_library
from pitloom.logging_config import loggable, one_line

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

# metadata_props keys sit under this prefix in properties, so a free-form
# key never collides with a field-derived one (domain, opset.<domain>)
_METADATA_PROPS_PREFIX = "metadata_props."

# Characters of a metadata_props key shown in a warning
_SHOWN_KEY_CHARS = 40

# Standard metadata_props key defined by the ONNX IR spec ("Optional Metadata"):
# https://onnx.ai/onnx/repo-docs/IR.html#optional-metadata
_MODEL_LICENSE_KEY = _METADATA_PROPS_PREFIX + "model_license"

# model_version packs SemVer as MAJOR (16 bits), MINOR (16), PATCH (32); zero
# upper 32 bits mark a simple number instead. See "Serializing SemVer version
# numbers in protobuf" in https://onnx.ai/onnx/repo-docs/Versioning.html
_SEMVER_FLAG_SHIFT = 32
_MAJOR_SHIFT = 48
_MINOR_MASK = 0xFFFF
_PATCH_MASK = 0xFFFF_FFFF
_UINT64_MASK = 0xFFFF_FFFF_FFFF_FFFF


# TensorProto element type names that differ from NumPy's dtype name; every
# other name, lowercased, is NumPy's (int64, bool, float16, complex64) or,
# for a type NumPy lacks (bfloat16, string, float8e4m3fn), ONNX's own.
_NUMPY_DTYPE_NAMES = {"FLOAT": "float32", "DOUBLE": "float64"}

# Last IR version whose graph.input lists every initializer too
_LAST_IR_WITH_WEIGHT_INPUTS = 3

# Opset domain of the ONNX-ML operators (trees, linear models, SVMs, ...)
_ONNX_ML_DOMAIN = "ai.onnx.ml"


def _dtype_name(elem_type: int, type_names: Any) -> str | None:
    """The NumPy-style name of an ONNX ``TensorProto.DataType`` value, from
    the enum's own names (*type_names*: ``TensorProto.DataType``), so the
    same file reads the same under every ``onnx`` version. ``None`` for
    ``UNDEFINED`` or a value the enum does not know."""
    try:
        name = str(type_names.Name(elem_type))
    except ValueError:
        return None
    if name == "UNDEFINED":
        return None
    return _NUMPY_DTYPE_NAMES.get(name, name.lower())


def _onnx_tensor_specs(
    value_infos: Any, type_names: Any, skip: frozenset[str] = frozenset()
) -> list[dict[str, Any]]:
    """Convert ONNX ValueInfoProto list to plain dicts, leaving out the
    names in *skip*."""
    specs = []
    for vi in value_infos:
        if vi.name in skip:
            continue
        spec: dict[str, Any] = {"name": vi.name}
        tensor_type = vi.type.tensor_type
        dtype = _dtype_name(tensor_type.elem_type, type_names)
        if dtype is not None:
            spec["dtype"] = dtype
        # No shape field: an unknown rank, or no tensor (a sequence, a map)
        if tensor_type.HasField("shape"):
            dims = []
            for d in tensor_type.shape.dim:
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
) -> tuple[dict[str, str], dict[str, int]]:
    """Extract domain, opset versions, and metadata_props into properties dict.

    Returns ``(properties, natives)``: *natives* holds each opset version as
    the integer it is, for :func:`~pitloom.core.ai_metadata.source_metadata`.

    ``metadata_props`` keys get the ``metadata_props.`` prefix, so they never
    collide with ``domain`` or ``opset.<domain>``. A key the file repeats
    (the ONNX checker rejects that) keeps its last value; one warning per
    file names how many keys repeat and the first few.
    """
    properties: dict[str, str] = {}
    natives: dict[str, int] = {}
    if model.domain:
        properties["domain"] = model.domain
    for opset in model.opset_import:
        opset_domain = opset.domain if opset.domain else "ai.onnx"
        record_scalar_property(
            properties, natives, f"opset.{opset_domain}", opset.version
        )
    repeated: dict[str, None] = {}  # insertion-ordered set
    for prop in model.metadata_props:
        key = _METADATA_PROPS_PREFIX + prop.key
        if key in properties:
            repeated[prop.key] = None
        properties[key] = prop.value
    if repeated:
        _warn_repeated_keys(list(repeated))
    record_dict_field_provenance(provenance, "properties", properties, source)
    return properties, natives


def _warn_repeated_keys(keys: list[str]) -> None:
    """One warning for every repeated ``metadata_props`` key in a file,
    naming the first few, each cut short."""
    shown = ", ".join(one_line(key, limit=_SHOWN_KEY_CHARS) for key in keys[:3])
    more = ", ..." if len(keys) > 3 else ""
    log.warning(
        "ONNX metadata_props: %d key(s) appear more than once; kept the last "
        "value of each: %s%s",
        len(keys),
        shown,
        more,
    )


def _resolve_onnx_name(
    graph_name: str, source: str, provenance: dict[str, str]
) -> str | None:
    """Return ``graph.name``, stripped, unless blank or an exporter default.

    ``None`` leaves the shown name to
    :meth:`~pitloom.core.ai_metadata.AiModelMetadata.resolve_name`.
    """
    name = graph_name.strip()
    if not name or name in _EXPORTER_DEFAULT_GRAPH_NAMES:
        return None
    provenance["name"] = f"{source} | Field: graph.name"
    return name


def _initializer_names(model: Any) -> frozenset[str]:
    """Names of a graph's weights (dense and sparse initializers) up to IR
    version 3, which lists them in ``graph.input`` too; none from IR 4 on,
    where a name in both is an input the initializer gives a default."""
    if model.ir_version > _LAST_IR_WITH_WEIGHT_INPUTS:
        return frozenset()
    graph = model.graph
    names = {tensor.name for tensor in graph.initializer}
    names.update(sparse.values.name for sparse in graph.sparse_initializer)
    return frozenset(names)


def _onnx_type_of_model(model: Any) -> str | None:
    """``"neural network"``, unless an opset import is the ONNX-ML domain:
    such a model may be a tree ensemble, a linear model or an SVM, which
    the file does not say, so the type is left unset."""
    if any(opset.domain == _ONNX_ML_DOMAIN for opset in model.opset_import):
        return None
    return "neural network"


def _decode_model_version(value: int) -> tuple[str, bool]:
    """Return ``(version, is_semver)`` for an ONNX ``model_version``.

    The int64 is read as its 64 bits, as the packing rule defines it, so a
    negative value has its upper bits set and decodes as SemVer (``-1`` is
    ``65535.65535.4294967295``).
    See https://onnx.ai/onnx/repo-docs/Versioning.html
    """
    packed = value & _UINT64_MASK
    if packed >> _SEMVER_FLAG_SHIFT == 0:
        return str(value), False
    major = packed >> _MAJOR_SHIFT
    minor = (packed >> _SEMVER_FLAG_SHIFT) & _MINOR_MASK
    patch = packed & _PATCH_MASK
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

    ``name`` is ``graph.name`` stripped, or ``None`` when it is blank or an
    exporter default (``torch_jit``, ``tf2onnx``, ...).
    ``license`` is the standard ``model_license`` metadata property.
    ``version`` is ``model_version``, decoded to ``MAJOR.MINOR.PATCH`` when
    its upper 32 bits are non-zero (bit-packed SemVer). ``type_of_model`` is
    ``"neural network"``, unset when the model imports the ``ai.onnx.ml``
    opset; ``domain`` is kept in ``properties`` only. ``inputs`` and
    ``outputs`` give each tensor's NumPy-style ``dtype`` name; ``inputs``
    leaves out the initializers an IR version 3 graph lists as inputs
    (from IR 4 on, such an input is one with a default, and kept). A
    ``shape`` is given only where the file has one: not for an unknown
    rank or a non-tensor value (a sequence).
    ``properties`` holds ``domain``, ``opset.<domain>`` and every
    ``metadata_props`` entry as ``metadata_props.<key>``.

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

    properties, natives = _extract_onnx_properties(model, source, provenance)
    license_expr = _resolve_onnx_license(properties, source, provenance)

    type_names = onnx.TensorProto.DataType
    inputs = _onnx_tensor_specs(
        model.graph.input, type_names, _initializer_names(model)
    )
    if inputs:
        provenance["inputs"] = f"{source} | Field: graph.input"

    outputs = _onnx_tensor_specs(model.graph.output, type_names)
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
        type_of_model=_onnx_type_of_model(model),
        properties=properties,
        **source_metadata(properties, natives),
        inputs=inputs,
        outputs=outputs,
        provenance=provenance,
    )
