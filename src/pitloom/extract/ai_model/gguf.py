# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF model metadata extractor."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    source_metadata,
    value_text,
)
from pitloom.core.dataset_metadata import DatasetReference
from pitloom.core.evidence import DECLARED, evidence_segment
from pitloom.core.internal_error import reraise_internal
from pitloom.core.model_originators import (
    ORIGINATORS_PROVENANCE_KEY,
    originator_names,
)
from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.core.quote_source import quote_source
from pitloom.core.scalar_text import scalar_text
from pitloom.extract._extract_utils import record_dict_field_provenance
from pitloom.extract.ai_model._gguf_bounds import load_gguf_header, stop_cap
from pitloom.extract.ai_model._gguf_datasets import (
    DATASETS_KEY,
    read_gguf_datasets,
)
from pitloom.extract.ai_model._gguf_fields import (
    FORMAT_VERSION_KEY,
    listed_strings,
    read_fields,
)
from pitloom.extract.ai_model._gguf_licence import read_gguf_license
from pitloom.extract.ai_model._stated_text import stated_text
from pitloom.extract.ai_model.formats.gguf_header import GgufStop
from pitloom.extract.ai_model.parameter_count import derived_parameter_count
from pitloom.extract.ai_model.reader_requirements import missing_library
from pitloom.logging_config import loggable
from pitloom.messages.files import warn_over_cap
from pitloom.messages.model_fields import (
    GGUF_ARRAY_CUT,
    GGUF_FIELDS_NOT_READ,
    GGUF_PAIR_ARRAY_CUT,
    GGUF_PAIR_NOT_READ,
    GGUF_TENSORS_NOT_READ,
)

log = logging.getLogger(__name__)

# Standard GGUF general keys used for SPDX AI fields
_GGUF_NAME_KEYS = ("general.name",)
_GGUF_DESCRIPTION_KEYS = ("general.description",)
_GGUF_ARCH_KEY = "general.architecture"
_GGUF_VERSION_KEY = "general.version"
_GGUF_FILE_TYPE_KEY = "general.file_type"
# Producer names, in the order they are read
_GGUF_ORIGINATOR_KEYS = ("general.author", "general.organization")
_GGUF_SPLIT_COUNT_KEY = "split.count"
# The reader's own pseudo-field for the header version, read in the file's
# byte order
# LlamaFileType.GUESSED: llama.cpp's "file type not stated", not a type
_GGUF_FILE_TYPE_GUESSED = 1024

# Hyperparameter key suffixes that are architecture-specific
_GGUF_HYPERPARAM_SUFFIXES = (
    ".context_length",
    ".embedding_length",
    ".feed_forward_length",
    ".block_count",
    ".attention.head_count",
    ".attention.head_count_kv",
    ".attention.layer_norm_epsilon",
    ".attention.layer_norm_rms_epsilon",
    ".expert_count",
    ".expert_used_count",
    ".rope.freq_base",
    ".rope.dimension_count",
    ".rope.scaling.type",
    ".rope.scaling.factor",
    ".rope.scaling.original_context_length",
)


def _resolve_quantization(file_type_value: Any) -> str | None:
    """Resolve a GGUF ``general.file_type`` integer to a quantization name.

    ``general.file_type`` is a ``gguf.LlamaFileType`` (the file's
    predominant tensor type), not a per-tensor ``GGMLQuantizationType``;
    the two number differently (7 is ``MOSTLY_Q8_0`` in one, ``Q5_1`` in
    the other). The name drops the ``MOSTLY_``/``ALL_`` prefix; a value the
    enum does not know is returned as the raw integer string.

    Args:
        file_type_value: The scalar value of the ``general.file_type``
            GGUF field.

    Returns:
        Quantization name string (e.g. ``"Q4_K_M"``), or ``None`` for a
        value that is no integer (a bool, a string, a float) or is
        ``GUESSED`` (not stated). The value stays in ``properties``.
    """
    if (
        isinstance(file_type_value, bool)
        or not isinstance(file_type_value, int)
        or file_type_value == _GGUF_FILE_TYPE_GUESSED
    ):
        return None
    int_val = file_type_value

    try:
        # pylint: disable=import-outside-toplevel

        from gguf import LlamaFileType

        name = str(LlamaFileType(int_val).name)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        reraise_internal(exc)
        log.debug(
            "Failed to resolve GGUF quantization name for file_type=%r: %s",
            file_type_value,
            loggable(str(exc)),
        )
        return str(int_val)
    for prefix in ("MOSTLY_", "ALL_"):
        name = name.removeprefix(prefix)
    return name


def _first_stated(
    fields: dict[str, Any],
    keys: tuple[str, ...],
    field: str,
    source: str,
    provenance: dict[str, str],
) -> str | None:
    """The first of *keys* stating text (a blank value reads as absent),
    with its provenance under *field*."""
    for key in keys:
        value = fields.get(key)
        # A string must state something; any other scalar is its own text,
        # as in ``properties``.
        if isinstance(value, str):
            text = stated_text(value)
        else:
            text = None if value is None else value_text(value)
        if text:
            provenance[field] = provenance_segment(source, "Field", key)
            return text
    return None


def _extract_gguf_core_fields(
    fields: dict[str, Any], source: str, provenance: dict[str, str]
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Extract core model identification fields from GGUF fields dictionary."""
    name = _first_stated(fields, _GGUF_NAME_KEYS, "name", source, provenance)
    description = _first_stated(
        fields, _GGUF_DESCRIPTION_KEYS, "description", source, provenance
    )
    architecture = _first_stated(
        fields, (_GGUF_ARCH_KEY,), "architecture", source, provenance
    )

    version = stated_text(fields.get(_GGUF_VERSION_KEY), scalar=True)
    if version:
        provenance["version"] = provenance_segment(source, "Field", _GGUF_VERSION_KEY)

    quantization: str | None = None
    if _GGUF_FILE_TYPE_KEY in fields:
        quantization = _resolve_quantization(fields[_GGUF_FILE_TYPE_KEY])
        if quantization:
            provenance["quantization"] = provenance_segment(
                source, "Field", _GGUF_FILE_TYPE_KEY
            )

    return name, description, architecture, version, quantization


def _originators(
    fields: dict[str, Any], source: str, provenance: dict[str, str]
) -> list[str]:
    """The producer names of ``general.author`` then ``general.organization``,
    each one name (not split); a value that is no string stays in
    ``properties`` only."""
    used = [k for k in _GGUF_ORIGINATOR_KEYS if stated_text(fields.get(k))]
    names = originator_names(*(fields.get(k) for k in used))
    if names:
        provenance[ORIGINATORS_PROVENANCE_KEY] = provenance_segment(
            source, "Field", ", ".join(used)
        )
    return names


def _parameter_count(
    shapes: list[list[int]] | None,
    fields: dict[str, Any],
    source: str,
    provenance: dict[str, str],
    where: str,
) -> int | None:
    """The sum of the tensor elements, ``None`` for a split file (it holds
    its own shard of the tensors, so its sum would understate the model)
    or with no tensor infos read (*shapes* ``None``)."""
    split_count = fields.get(_GGUF_SPLIT_COUNT_KEY)
    if shapes is None or (isinstance(split_count, int) and split_count > 1):
        return None
    return derived_parameter_count(shapes, "tensor_infos", source, provenance, where)


def _categorize_gguf_fields(
    loaded: _Loaded, source: str, provenance: dict[str, str]
) -> tuple[dict[str, Any], dict[str, str]]:
    """Separate hyperparameters from general properties and record provenance.

    A derived key (an array's length, see
    :func:`~pitloom.extract.ai_model._gguf_fields.read_fields`) is always a
    property, recorded as derived from the array's own key, and as
    ``Evidence: declared`` when the read did not reach the array's end.
    """
    fields, derived = loaded.fields, loaded.derived
    hyperparameters: dict[str, Any] = {}
    properties: dict[str, str] = {}
    for key, value in fields.items():
        if key not in derived and any(
            key.endswith(suffix) for suffix in _GGUF_HYPERPARAM_SUFFIXES
        ):
            hyperparameters[key] = value
        else:
            properties[key] = scalar_text(value)

    record_dict_field_provenance(provenance, "hyperparameters", hyperparameters, source)
    record_dict_field_provenance(provenance, "properties", properties, source)
    # Overwritten in place, so the entries keep their sorted order.
    for length_key, array_key in derived.items():
        entry = provenance_segment(
            provenance_segment(source, "Field", array_key), "Method", "array_length"
        )
        if length_key in loaded.declared:
            entry = f"{entry} | {evidence_segment(DECLARED)}"
        provenance[f"properties.{length_key}"] = entry
    return hyperparameters, properties


class _Loaded(NamedTuple):
    """What :func:`_load_fields` reads of a GGUF file (see
    :class:`~pitloom.extract.ai_model._gguf_fields.GgufFields`); *shapes*
    ``None`` when the tensor infos were not read, *unread* the pairs a
    partial read did not reach."""

    fields: dict[str, Any]
    raw_metadata: dict[str, Any]
    derived: dict[str, str]
    declared: frozenset[str]
    shapes: list[list[int]] | None
    unread: int
    datasets: list[DatasetReference]
    datasets_provenance: str | None


# How many ``general.datasets`` elements to parse: all, within the header
# read's own bounds (the datasets cap counts distinct datasets, not
# elements).
_DATASETS_KEEP = {DATASETS_KEY: 2**63}


def _warn_partial(stop: GgufStop, where: str) -> None:
    """The one ``over-cap`` warning of a header read in part."""
    if stop.pair is None:
        outcome = GGUF_TENSORS_NOT_READ
    elif not stop.key:  # over a bound itself, or empty: counted from 1
        template = GGUF_PAIR_ARRAY_CUT if stop.in_array else GGUF_PAIR_NOT_READ
        outcome = template % {"pair": stop.pair + 1}
    else:
        template = GGUF_ARRAY_CUT if stop.in_array else GGUF_FIELDS_NOT_READ
        outcome = template % {"key": loggable(stop.key)}
    warn_over_cap(log, stop_cap(stop), where, outcome)


def _load_fields(model_path: Path, source: str) -> _Loaded:
    """The fields of the GGUF file at *model_path* (its header read by
    :func:`~pitloom.extract.ai_model._gguf_bounds.load_gguf_header`), the
    shape of every tensor and the datasets it names
    (:func:`read_gguf_datasets`, *source* their provenance). A header read
    in part is said once (``over-cap``).

    Raises:
        ImportError: If ``gguf`` is not installed.
        ValueError: If the file cannot be read.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The header
            declares more than the file holds.
    """
    try:
        # pylint: disable-next=import-outside-toplevel,unused-import
        import gguf  # noqa: F401  # quantisation names, tensor type sizes
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # a broken install raises more than ImportError
        reraise_internal(exc)
        raise missing_library(AiModelFormat.GGUF, exc) from exc

    failed = f"Failed to read GGUF file {quote_source(model_path)}"
    try:
        header = load_gguf_header(model_path, _DATASETS_KEEP)
        read = read_fields(header)
    except (OSError, ValueError) as exc:
        reraise_internal(exc)
        log.debug("%s: %s", loggable(failed), loggable(str(exc)))
        raise ValueError(f"{failed}: {exc}") from exc
    if header.stop is not None:
        _warn_partial(header.stop, str(model_path))
    datasets, datasets_provenance = read_gguf_datasets(
        read.fields,
        listed_strings(header, DATASETS_KEY),
        source,
        str(model_path),
        model_path.name,
    )
    shapes = None
    if header.tensors is not None:
        shapes = [list(tensor.shape) for tensor in header.tensors]
    return _Loaded(
        read.fields,
        read.raw_metadata,
        read.derived,
        read.declared,
        shapes,
        header.kv_count - len(header.fields),
        datasets,
        datasets_provenance,
    )


def read_gguf(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a GGUF model file.

    Requires the ``gguf`` package (``pip install gguf``).

    Raises:
        ImportError: If ``gguf`` is not installed.
        ValueError: If the file cannot be read.
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The header
            declares more than the file holds
            (:func:`~pitloom.extract.ai_model._gguf_bounds.load_gguf_header`).
    """
    source = provenance_source(model_path.name)
    loaded = _load_fields(model_path, source)
    fields = loaded.fields
    provenance: dict[str, str] = {}
    if loaded.datasets_provenance:
        provenance["datasets"] = loaded.datasets_provenance
    # The header version is always read (2 or 3).
    format_version = stated_text(fields.get(FORMAT_VERSION_KEY), scalar=True)
    provenance["format_version"] = provenance_segment(
        source, "Field", FORMAT_VERSION_KEY
    )

    (
        name,
        description,
        architecture,
        version,
        quantization,
    ) = _extract_gguf_core_fields(fields, source, provenance)

    hyperparameters, properties = _categorize_gguf_fields(loaded, source, provenance)
    license_expr = read_gguf_license(fields, source, provenance)

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
        parameter_count=_parameter_count(
            loaded.shapes, fields, source, provenance, str(model_path)
        ),
        license=license_expr,
        originators=_originators(fields, source, provenance),
        hyperparameters=hyperparameters,
        properties=properties,
        **source_metadata(loaded.raw_metadata),
        raw_metadata_unread=loaded.unread,
        datasets=loaded.datasets,
        provenance=provenance,
    )
