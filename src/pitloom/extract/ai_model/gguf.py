# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF model metadata extractor."""

from __future__ import annotations

import logging
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import (
    record_dict_field_provenance,
    sanitize_provenance_text,
)
from pitloom.extract.ai_model._gguf_bounds import check_gguf_header
from pitloom.extract.ai_model.reader_requirements import missing_library
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

# Standard GGUF general keys used for SPDX AI fields
_GGUF_NAME_KEYS = ("general.name",)
_GGUF_DESCRIPTION_KEYS = ("general.description",)
_GGUF_ARCH_KEY = "general.architecture"
_GGUF_VERSION_KEY = "general.version"
_GGUF_FILE_TYPE_KEY = "general.file_type"

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

# An array is recorded as its length, under its key plus this suffix, in
# ``properties``; its element values are never used.
_ARRAY_LENGTH_SUFFIX = ".length"


def _resolve_quantization(file_type_value: Any) -> str | None:
    """Resolve a GGUF ``general.file_type`` integer to a quantization name.

    Uses the ``gguf`` library's ``GGMLQuantizationType`` enum when available,
    otherwise returns the raw integer as a string.

    Args:
        file_type_value: The raw value extracted from the ``general.file_type``
            GGUF field (an integer or a list containing one integer).

    Returns:
        Quantization name string (e.g. ``"Q4_K_M"``) or ``None``.
    """
    if file_type_value is None:
        return None

    try:
        int_val = int(file_type_value)
    except (TypeError, ValueError):
        return None

    try:
        # pylint: disable=import-outside-toplevel

        from gguf import GGMLQuantizationType

        return str(GGMLQuantizationType(int_val).name)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to resolve GGUF quantization name for file_type=%r: %s",
            file_type_value,
            loggable(str(exc)),
        )
        return str(int_val)


def _read_gguf_format_version(model_path: Path, source: str) -> tuple[str | None, str]:
    """Read GGUF format version from the binary header (uint32 at offset 4)."""
    try:
        with model_path.open("rb") as fh:
            fh.seek(4)
            ver_bytes = fh.read(4)
        if len(ver_bytes) == 4:
            format_version = str(struct.unpack("<I", ver_bytes)[0])
            return format_version, f"{source} | Field: GGUF header version (bytes 4-7)"
    except OSError:
        pass
    return None, ""


def _type_name(gguf_type: Any) -> str:
    """The name of a ``gguf.GGUFValueType`` (``"STRING"``, ``"ARRAY"``)."""
    return str(getattr(gguf_type, "name", ""))


def _is_array(gguf_field: Any) -> bool:
    """Whether a ``gguf.ReaderField`` holds an array."""
    return bool(gguf_field.types) and _type_name(gguf_field.types[0]) == "ARRAY"


def _array_length(gguf_field: Any) -> int:
    """The declared top-level element count of an array field.

    ``ReaderField.parts`` holds the key length, the key, the value type, the
    element type, then the count; ``len(field.data)`` would count the leaves
    of a nested array instead.

    Raises:
        ValueError: *gguf_field* does not have that layout.
    """
    parts = gguf_field.parts
    if len(parts) < 5:
        raise ValueError("GGUF array field without an element count")
    return int(parts[4][0])


def _array_summary(gguf_field: Any) -> dict[str, Any]:
    """An array field as its length and declared element type name.

    The type is read from the header (``parts[3]``), not ``types``, which
    the reader fills from the first element and so lacks for an empty
    array. A code that is no ``gguf.GGUFValueType`` (the reader checks it
    only when there are elements) leaves the type absent.
    """
    summary: dict[str, Any] = {"length": _array_length(gguf_field)}
    value_type = type(gguf_field.types[0])
    try:
        summary["type"] = _type_name(value_type(int(gguf_field.parts[3][0])))
    except ValueError:
        pass
    return summary


def _field_value(gguf_field: Any) -> Any:
    """Resolve a scalar GGUF field to a plain Python value (arrays: see
    :func:`_read_fields`)."""
    parts = gguf_field.parts
    if not parts:
        return None
    last = parts[-1]
    # String fields are stored as raw byte arrays; decode explicitly
    if gguf_field.types and _type_name(gguf_field.types[0]) == "STRING":
        return last.tobytes().decode("utf-8")
    if hasattr(last, "tolist"):
        val = last.tolist()
        return val[0] if isinstance(val, list) and len(val) == 1 else val
    return last


def _read_fields(
    reader_fields: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Every field of a GGUF file, in file order.

    Returns ``(fields, raw_metadata, derived)``. In *fields* a scalar keeps
    its key and an array ``k`` becomes ``k.length``, its declared element
    count, at ``k``'s position; *derived* maps each such length key back to
    ``k``. *raw_metadata* keeps the file's keys: a scalar's value, an
    array's :func:`_array_summary`. A real key ``k.length`` wins over an
    array ``k``'s length, whatever their order in the file.

    Raises:
        ValueError: An array field without an element count.
    """
    scalar_keys = {key for key, f in reader_fields.items() if not _is_array(f)}
    fields: dict[str, Any] = {}
    raw_metadata: dict[str, Any] = {}
    derived: dict[str, str] = {}
    for key, gguf_field in reader_fields.items():
        if not _is_array(gguf_field):
            fields[key] = raw_metadata[key] = _field_value(gguf_field)
            continue
        raw_metadata[key] = _array_summary(gguf_field)
        length_key = key + _ARRAY_LENGTH_SUFFIX
        if length_key in scalar_keys:
            log.warning(
                "GGUF key %s is in the file; the length of array %s is not a property",
                loggable(length_key),
                loggable(key),
            )
            continue
        fields[length_key] = raw_metadata[key]["length"]
        derived[length_key] = key
    return fields, raw_metadata, derived


def _extract_gguf_core_fields(
    fields: dict[str, Any], source: str, provenance: dict[str, str]
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Extract core model identification fields from GGUF fields dictionary."""
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
        provenance["architecture"] = f"{source} | Field: {_GGUF_ARCH_KEY}"

    version: str | None = None
    if _GGUF_VERSION_KEY in fields and fields[_GGUF_VERSION_KEY] is not None:
        version = str(fields[_GGUF_VERSION_KEY])
        provenance["version"] = f"{source} | Field: {_GGUF_VERSION_KEY}"

    quantization: str | None = None
    if _GGUF_FILE_TYPE_KEY in fields:
        quantization = _resolve_quantization(fields[_GGUF_FILE_TYPE_KEY])
        if quantization:
            provenance["quantization"] = f"{source} | Field: {_GGUF_FILE_TYPE_KEY}"

    return name, description, architecture, version, quantization


def _categorize_gguf_fields(
    fields: dict[str, Any],
    source: str,
    provenance: dict[str, str],
    derived: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Separate hyperparameters from general properties and record provenance.

    A *derived* key (an array's length, see :func:`_read_fields`) is always
    a property, recorded as derived from the array's own key.
    """
    hyperparameters: dict[str, Any] = {}
    properties: dict[str, str] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key not in derived and any(
            key.endswith(suffix) for suffix in _GGUF_HYPERPARAM_SUFFIXES
        ):
            hyperparameters[key] = value
        else:
            properties[key] = str(value)

    record_dict_field_provenance(provenance, "hyperparameters", hyperparameters, source)
    record_dict_field_provenance(provenance, "properties", properties, source)
    # Overwritten in place, so the entries keep their sorted order.
    safe_source = sanitize_provenance_text(source)
    for length_key, array_key in derived.items():
        provenance[f"properties.{length_key}"] = (
            f"{safe_source} | Field: {sanitize_provenance_text(array_key)}"
            " | Method: array_length"
        )
    return hyperparameters, properties


def _load_fields(
    model_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """:func:`_read_fields` of the file at *model_path*, its header bounded
    first.

    Raises:
        ImportError: If ``gguf`` is not installed.
        ValueError: If the file cannot be read.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The header is over
            a bound.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from gguf import GGUFReader
    except ImportError as exc:
        raise missing_library(AiModelFormat.GGUF) from exc

    try:
        check_gguf_header(model_path)
    except OSError as exc:
        raise ValueError(f"Failed to read GGUF file {model_path}: {exc}") from exc

    try:
        reader = GGUFReader(str(model_path), mode="r")
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to open GGUF file %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(f"Failed to read GGUF file {model_path}: {exc}") from exc

    try:
        return _read_fields(reader.fields)
    except ValueError as exc:
        raise ValueError(f"Failed to read GGUF file {model_path}: {exc}") from exc
    finally:
        # GGUFReader (the gguf package) memory-maps the whole file and
        # exposes no close()/context-manager protocol of its own -- drop the
        # only reference to it as soon as every field we need is copied out,
        # so the mapping is released deterministically here rather than
        # implicitly whenever the interpreter next collects this frame.
        del reader


def read_gguf(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a GGUF model file.

    Requires the ``gguf`` package (``pip install gguf``).

    Raises:
        ImportError: If ``gguf`` is not installed.
        ValueError: If the file cannot be read.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The header is over
            a bound (:func:`~pitloom.extract.ai_model._gguf_bounds.check_gguf_header`).
    """
    fields, raw_metadata, derived = _load_fields(model_path)
    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    format_version, prov_ver = _read_gguf_format_version(model_path, source)
    provenance: dict[str, str] = {}
    if format_version:
        provenance["format_version"] = prov_ver

    (
        name,
        description,
        architecture,
        version,
        quantization,
    ) = _extract_gguf_core_fields(fields, source, provenance)

    hyperparameters, properties = _categorize_gguf_fields(
        fields, source, provenance, derived
    )

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.GGUF,
            format_version=format_version,
            framework="llama.cpp",
        ),
        name=name,
        description=description,
        version=version,
        architecture=architecture,
        quantization=quantization,
        hyperparameters=hyperparameters,
        properties=properties,
        raw_metadata=raw_metadata,
        provenance=provenance,
    )
