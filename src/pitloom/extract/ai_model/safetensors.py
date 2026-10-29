# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Safetensors model metadata extractor."""

from __future__ import annotations

import heapq
import logging
import struct
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import (
    MAX_MODEL_ENTRIES,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    source_metadata,
)
from pitloom.core.model_originators import ORIGINATORS_PROVENANCE_KEY, originator_names
from pitloom.core.quote_source import quote_source
from pitloom.extract._extract_utils import (
    record_dict_field_provenance,
    sanitize_provenance_text,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded, ModelOverCap
from pitloom.extract.ai_model.parameter_count import derived_parameter_count
from pitloom.extract.ai_model.reader_requirements import missing_library
from pitloom.logging_config import Cap, loggable

log = logging.getLogger(__name__)

#: The ModelSpec key stable-diffusion-xl-base-1.0 and stable-cascade write the
#: licence in; no other licence key appears in the files measured.
_LICENSE_KEY = "modelspec.license"

#: Longest JSON header the format allows: ``safetensors``' own
#: ``MAX_HEADER_SIZE``, inclusive. It decides whether a file is Safetensors
#: at all (``reader.detect_ai_model_format_from_header``).
SAFETENSORS_FORMAT_MAX_HEADER_BYTES = 100_000_000

#: Longest JSON header read. ``safetensors`` builds every entry in Python and
#: again in a dict, at tens of times the header's size; a real model's is
#: well under a MiB. Kept below the format's limit, so a header between the
#: two is detected and refused with its size, not called an unsupported
#: format.
MAX_SAFETENSORS_HEADER_BYTES = 16 * 1024 * 1024


def _check_header_length(model_path: Path) -> None:
    """Refuse a file whose 8-byte little-endian header length is over
    :data:`MAX_SAFETENSORS_HEADER_BYTES`, before ``safetensors`` reads it.

    Raises:
        ModelLimitExceeded: The declared header is over the cap.
        OSError: The file cannot be read.
    """
    with model_path.open("rb") as fh:
        prefix = fh.read(8)
    if len(prefix) == 8:
        (length,) = struct.unpack("<Q", prefix)
        if length > MAX_SAFETENSORS_HEADER_BYTES:
            cap = Cap(MAX_SAFETENSORS_HEADER_BYTES, "byte", "Safetensors-header")
            raise ModelOverCap(cap)


def _stable_metadata(raw: dict[str, str]) -> dict[str, str]:
    """*raw* with a stable order where the entry cap can cut it.

    ``safetensors`` returns ``__metadata__`` in an order that differs from one
    process to the next, and the cap keeps the first entries: over the cap, the
    smallest keys stay, in key order, one past the cap so that the scanner
    still sees the map is too long. Under it, every entry stays and the
    output is sorted downstream.
    """
    if len(raw) <= MAX_MODEL_ENTRIES:
        return raw
    return dict(heapq.nsmallest(MAX_MODEL_ENTRIES + 1, raw.items()))


def _read_header(
    model_path: Path, safe_open: Any, source: str, provenance: dict[str, str]
) -> tuple[dict[str, str], int | None]:
    """The ``__metadata__`` map and the parameter count (its provenance set in
    *provenance*) of *model_path*, read with *safe_open*.

    Raises:
        ModelLimitExceeded: The declared header is over the cap.
        ValueError: The file cannot be read as a Safetensors file.
    """
    try:
        _check_header_length(model_path)
        # Use numpy framework to avoid requiring torch/tf; metadata-only read
        with safe_open(
            str(model_path),
            framework="numpy",
        ) as f:
            metadata: dict[str, str] = f.metadata() or {}
            # Every tensor; the header alone gives each shape, no tensor data
            # is read.
            parameter_count = derived_parameter_count(
                (f.get_slice(k).get_shape() for k in f.keys()),
                "tensor shapes (header only)",
                source,
                provenance,
                str(model_path),
            )
    except ModelLimitExceeded:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to read Safetensors file %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(
            f"Failed to read Safetensors file {quote_source(model_path)}: {exc}"
        ) from exc
    return metadata, parameter_count


def _originators(
    metadata: dict[str, str], source: str, provenance: dict[str, str]
) -> list[str]:
    """The one originator of ``modelspec.author``: a name may hold a comma,
    so it is not split."""
    names = originator_names(metadata.get("modelspec.author"))
    if names:
        provenance[ORIGINATORS_PROVENANCE_KEY] = (
            f"{source} | Field: __metadata__.modelspec.author"
        )
    return names


def _license(
    metadata: dict[str, str], source: str, provenance: dict[str, str]
) -> str | None:
    """The model licence of ``modelspec.license`` (a licence name or an SPDX
    expression, as written), if it is non-blank. Free text, so this reader
    calls no SPDX-only warning; the assembler's own classification still
    reports a value that looks like a broken expression. The format has no
    licence key of its own."""
    value = (metadata.get(_LICENSE_KEY) or "").strip()
    if not value:
        return None
    provenance["license"] = f"{source} | Field: __metadata__.{_LICENSE_KEY}"
    return value


def read_safetensors(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a Safetensors model file.

    Requires the ``safetensors`` package (``pip install safetensors``).

    The Safetensors format stores an optional ``__metadata__`` dict in its
    header alongside tensor descriptors (name, dtype, shape). This extractor
    reads only the header -- it does not load tensor data into memory.

    The well-known keys are looked up in the whole ``__metadata__``. Over
    :data:`~pitloom.extract.ai_model.limits.MAX_MODEL_ENTRIES` entries, only
    what is kept as ``properties`` and ``raw_metadata`` is cut to its
    smallest keys (see :func:`_stable_metadata`).

    Commonly stored ``__metadata__`` keys (by convention):
    - ``modelspec.architecture`` -> architecture
    - ``modelspec.title`` or ``name`` -> name
    - ``modelspec.description`` or ``description`` -> description
    - ``modelspec.precision`` -> quantization (e.g. "fp16", "bf16")
    - ``modelspec.author`` -> one originator (not split on commas)
    - ``modelspec.license`` -> the licence, as written

    ``parameter_count`` is the sum of the elements of every tensor, from the
    header's shapes. A model sharded over several files gets each file's own
    count. The format itself has no author key; only ModelSpec's is read.

    Args:
        model_path: Path to a ``.safetensors`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ImportError: If ``safetensors`` is not installed.
        ModelLimitExceeded: If the declared header is over
            :data:`MAX_SAFETENSORS_HEADER_BYTES`.
        ValueError: If the file cannot be read as a valid Safetensors file.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from safetensors import safe_open
    except ImportError as exc:
        raise missing_library(AiModelFormat.SAFETENSORS) from exc

    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    provenance: dict[str, str] = {}
    metadata, parameter_count = _read_header(model_path, safe_open, source, provenance)

    # Some Safetensors files record the originating framework under "format"
    # (e.g. "pt" for PyTorch) or "modelspec.implementation".
    framework = (
        metadata.get("format") or metadata.get("modelspec.implementation") or None
    )
    if framework:
        provenance["framework"] = f"{source} | Field: __metadata__"

    # Pull well-known keys from __metadata__
    name = (
        metadata.get("modelspec.title")
        or metadata.get("name")
        or metadata.get("ss_base_model_version")
    )
    if name:
        provenance["name"] = f"{source} | Field: __metadata__"

    description = metadata.get("modelspec.description") or metadata.get("description")
    if description:
        provenance["description"] = f"{source} | Field: __metadata__"

    version = metadata.get("modelspec.version") or metadata.get("version")
    if version:
        provenance["version"] = f"{source} | Field: __metadata__"

    # modelspec.architecture -> architecture (specific arch name)
    architecture = metadata.get("modelspec.architecture") or metadata.get(
        "architecture"
    )
    if architecture:
        provenance["architecture"] = f"{source} | Field: __metadata__"

    # modelspec.precision -> quantization (e.g. "fp16", "bf16", "int8")
    quantization = metadata.get("modelspec.precision") or metadata.get("precision")
    if quantization:
        provenance["quantization"] = f"{source} | Field: __metadata__"

    # The well-known keys above came from the whole map; only what is kept
    # below is cut. Exact per-key provenance: each entry is traceable to its
    # own ``__metadata__`` key.
    raw = source_metadata(_stable_metadata(metadata))
    properties = dict(raw["raw_metadata"])  # every value is text
    record_dict_field_provenance(
        provenance, "properties", properties, source, location_prefix="__metadata__."
    )

    # No inputs or outputs: a Safetensors file holds weights, not a model
    # signature, and its tensor keys are not inputs.

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.SAFETENSORS,
            framework=framework,
        ),
        name=name,
        description=description,
        version=version,
        architecture=architecture,
        quantization=quantization,
        parameter_count=parameter_count,
        originators=_originators(metadata, source, provenance),
        license=_license(metadata, source, provenance),
        properties=properties,
        **raw,
        # The keys _stable_metadata cut (every value is a string, so
        # source_metadata keeps every key); cap_entries adds the one past
        # the cap.
        raw_metadata_dropped=len(metadata) - len(raw["raw_metadata"]),
        provenance=provenance,
    )
