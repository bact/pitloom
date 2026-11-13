# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read an SPDX 3 JSON-LD SBOM for ``id import``.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry.import_sbom``),
:mod:`pitloom.id_registry._harvest` (what is done with the elements).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.given_file import read_given_bytes
from pitloom.id_registry._harvest import _sorted_by_spdx_id
from pitloom.messages import CodedValueError
from pitloom.messages.files import (
    JSON_MALFORMED,
    NOT_JSON_LINE,
    NOT_OBJECT_LINE,
    SBOM_USE,
    file_unreadable_error,
)
from pitloom.messages.targets import (
    SBOM_GRAPH_ELEMENT_LINE,
    SBOM_GRAPH_NOT_LIST_LINE,
    SBOM_INVALID,
)

__all__ = ["document_id", "read_sbom_objects"]


def _require_graph_list(raw: bytes, sbom_path: Path) -> None:
    """Raise ``ValueError`` when the bytes *raw*, read from *sbom_path*,
    are not UTF-8 (``file-unreadable/not-utf8``) or not a JSON object
    (``json-malformed``), or have an ``@graph`` that
    is not a list, or holds a non-object (``sbom-invalid``; the
    deserialiser would leak a ``TypeError``). Each names *sbom_path*."""
    try:
        # Bytes, not text: a UTF-8 BOM is accepted, as the deserialiser does.
        data = json.loads(raw)
    except UnicodeDecodeError as exc:
        # Before ValueError (its base): the code embed-wheel gives the file.
        raise file_unreadable_error(exc, file=sbom_path, use=SBOM_USE) from exc
    except (ValueError, RecursionError) as exc:
        raise CodedValueError(
            JSON_MALFORMED,
            line=NOT_JSON_LINE,
            file=sbom_path,
            use=SBOM_USE,
            failure=exc,
        ) from exc
    if not isinstance(data, dict):
        raise CodedValueError(
            JSON_MALFORMED, line=NOT_OBJECT_LINE, file=sbom_path, use=SBOM_USE
        )
    graph = data.get("@graph", [])
    if not isinstance(graph, list):
        raise CodedValueError(
            SBOM_INVALID, line=SBOM_GRAPH_NOT_LIST_LINE, file=sbom_path
        )
    if not all(isinstance(element, dict) for element in graph):
        raise CodedValueError(
            SBOM_INVALID, line=SBOM_GRAPH_ELEMENT_LINE, file=sbom_path
        )


def read_sbom_objects(sbom_path: Path) -> list[Any]:
    """The objects of the SBOM at *sbom_path*, sorted by ``spdxId``
    (:func:`~pitloom.id_registry._harvest._sorted_by_spdx_id`).

    Raises:
        pitloom.messages.CodedFileNotFoundError: Nothing is at *sbom_path*
            (``input-not-found``).
        pitloom.messages.CodedValueError: It cannot be read
            (``file-unreadable``, ``file-unreadable/not-utf8``), is not a
            JSON object (``json-malformed``)
            or its ``@graph`` is malformed (``sbom-invalid``); each names
            *sbom_path*. The deserialiser's own errors are uncoded.
    """
    object_set = spdx3.SHACLObjectSet()
    raw = read_given_bytes(sbom_path, kind="SBOM file", use=SBOM_USE)
    _require_graph_list(raw, sbom_path)
    spdx3.JSONLDDeserializer().read(io.BytesIO(raw), object_set)
    return _sorted_by_spdx_id(object_set)


def document_id(sorted_objects: list[Any]) -> str | None:
    """The id of the first ``SpdxDocument`` of *sorted_objects*, or
    ``None`` (none, or one with no id)."""
    document = next(
        (o for o in sorted_objects if isinstance(o, spdx3.SpdxDocument)), None
    )
    return str(document.spdxId) if document is not None and document.spdxId else None
