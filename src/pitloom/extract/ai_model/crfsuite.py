# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""CRFsuite model metadata extractor.

Maps :func:`pitloom.extract.ai_model.formats.crfsuite.read_crfsuite` (the
pure-Python header-and-label reader) to
:class:`~pitloom.core.ai_metadata.AiModelMetadata`.

See also: :mod:`pitloom.extract.ai_model.formats.crfsuite`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.extract.ai_model.formats import FormatError, LimitExceeded, Limits
from pitloom.extract.ai_model.formats.crfsuite import (
    read_crfsuite as read_crfsuite_header,
)
from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES, ModelLimitExceeded

_LIMITS = Limits(max_crfsuite_labels=MAX_MODEL_ENTRIES)

#: Labels named in the generated description; the rest are counted.
_DESCRIPTION_LABELS = 20

#: Characters of one label shown in the description (a label can be 1 MiB).
_SHOWN_LABEL_CHARS = 64

# Where each property comes from in the file. Written by hand: the generic
# helper would cite ``Field: num_features``, the header field that is always 0.
_PROPERTY_FIELDS = {
    "labels": "labels CQDB",
    "model_type": "header.type",
    "num_attributes": "header.num_attrs",
    "num_features": "FEAT.num",
    "num_labels": "header.num_labels",
}


def _shown(label: str) -> str:
    """*label* cut to :data:`_SHOWN_LABEL_CHARS` characters."""
    if len(label) <= _SHOWN_LABEL_CHARS:
        return label
    return label[: _SHOWN_LABEL_CHARS - 3] + "..."


def _description(labels: tuple[str, ...]) -> str | None:
    """A one-line description naming the first labels, or ``None`` without."""
    if not labels:
        return None
    shown = ", ".join(_shown(label) for label in labels[:_DESCRIPTION_LABELS])
    more = len(labels) - _DESCRIPTION_LABELS
    suffix = f", ... ({more} more)" if more > 0 else ""
    noun = "label" if len(labels) == 1 else "labels"
    return f"CRFsuite model with {len(labels)} {noun}: {shown}{suffix}"


def read_crfsuite(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a CRFsuite model file.

    Reads the header and the label strings only: never the feature weights
    or the attribute strings (training-text features). The file carries no
    name, version or licence.

    Args:
        model_path: Path to a CRFsuite model (``.crfsuite``, or ``.model``).

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        pitloom.extract.ai_model.limits.ModelLimitExceeded: The model holds
            more labels, or a larger labels chunk, than the bounds allow.
        ValueError: The file cannot be read as a CRFsuite model.
    """
    try:
        with model_path.open("rb") as handle:
            model = read_crfsuite_header(handle, _LIMITS)
    except LimitExceeded as exc:
        raise ModelLimitExceeded(exc.reason) from None
    except FormatError as exc:
        raise ValueError(f"not a readable CRFsuite model: {exc.reason}") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read CRFsuite file {model_path}: {exc}") from exc

    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    labels = model.labels
    properties = {
        "labels": json.dumps(list(labels), ensure_ascii=False),
        "model_type": model.model_type,
        "num_attributes": str(model.num_attributes),
        "num_features": str(model.num_features),
        "num_labels": str(len(labels)),
    }
    raw_metadata: dict[str, Any] = {
        "labels": list(labels),
        "model_type": model.model_type,
        "num_attributes": model.num_attributes,
        "num_features": model.num_features,
        "num_labels": len(labels),
    }
    provenance = {
        "framework": f"{source} | Field: magic",
        "format_version": f"{source} | Field: version",
        "type_of_model": (
            f"{source} | Field: header.type | Method: crfsuite_model_type"
        ),
    }
    for key, location in _PROPERTY_FIELDS.items():
        provenance[f"properties.{key}"] = f"{source} | Field: {location}"

    outputs: list[dict[str, Any]] = []
    if labels:
        provenance["description"] = (
            f"{source} | Field: labels CQDB | Method: generated_from_labels"
        )
        provenance["outputs"] = f"{source} | Field: header.num_labels (label count)"
        outputs = [{"name": "label_sequence", "shape": [len(labels)]}]

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.CRFSUITE,
            format_version=str(model.version),
            framework="crfsuite",
        ),
        description=_description(labels),
        type_of_model="conditional random field",
        properties=properties,
        raw_metadata=raw_metadata,
        outputs=outputs,
        provenance=provenance,
    )
