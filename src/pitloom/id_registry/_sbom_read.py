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

from pitloom.id_registry._harvest import _sorted_by_spdx_id

__all__ = ["document_id", "read_sbom_objects"]


def _require_graph_list(raw: bytes) -> None:
    """Raise ``ValueError`` when the JSON *raw* has an ``@graph`` that is
    not a list, or holds a non-object (the deserializer would leak a
    ``TypeError``). Text that is not JSON is left to the deserializer's
    own error."""
    try:
        data = json.loads(raw)
    except ValueError:
        return
    graph = data.get("@graph", []) if isinstance(data, dict) else []
    if not isinstance(graph, list):
        raise ValueError("@graph is not a list")
    if not all(isinstance(element, dict) for element in graph):
        raise ValueError("@graph element is not an object")


def read_sbom_objects(sbom_path: Path) -> list[Any]:
    """The objects of the SBOM at *sbom_path*, sorted by ``spdxId``
    (:func:`~pitloom.id_registry._harvest._sorted_by_spdx_id`)."""
    object_set = spdx3.SHACLObjectSet()
    with open(sbom_path, "rb") as f:
        raw = f.read()
    _require_graph_list(raw)
    spdx3.JSONLDDeserializer().read(io.BytesIO(raw), object_set)
    return _sorted_by_spdx_id(object_set)


def document_id(sorted_objects: list[Any]) -> str | None:
    """The id of the first ``SpdxDocument`` of *sorted_objects*, or
    ``None`` (none, or one with no id)."""
    document = next(
        (o for o in sorted_objects if isinstance(o, spdx3.SpdxDocument)), None
    )
    return str(document.spdxId) if document is not None and document.spdxId else None
