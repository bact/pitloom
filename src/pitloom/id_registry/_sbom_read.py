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
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._sbom_format import read_given_sbom
from pitloom.id_registry._harvest import _sorted_by_spdx_id

__all__ = ["document_id", "read_sbom_objects"]


def read_sbom_objects(sbom_path: Path) -> list[Any]:
    """The objects of the SBOM at *sbom_path*, sorted by ``spdxId``
    (:func:`~pitloom.id_registry._harvest._sorted_by_spdx_id`).

    Raises:
        pitloom.messages.CodedFileNotFoundError: Nothing is at *sbom_path*,
            or not a regular file (``input-not-found``).
        pitloom.messages.CodedValueError: It is refused as ``embed-wheel
            --sbom`` refuses it (:func:`~pitloom._sbom_format.read_given_sbom`:
            ``file-unreadable``, ``over-cap``, ``json-malformed``,
            ``sbom-wrong-format``, ``sbom-invalid`` for an ``@graph`` that
            is not a list of objects); each names *sbom_path*. The deserialiser's
            own errors are uncoded.
    """
    object_set = spdx3.SHACLObjectSet()
    given = read_given_sbom(sbom_path)
    raw = io.BytesIO(given.text.encode("utf-8"))
    spdx3.JSONLDDeserializer().read(raw, object_set)
    return _sorted_by_spdx_id(object_set)


def document_id(sorted_objects: list[Any]) -> str | None:
    """The id of the first ``SpdxDocument`` of *sorted_objects*, or
    ``None`` (none, or one with no id)."""
    document = next(
        (o for o in sorted_objects if isinstance(o, spdx3.SpdxDocument)), None
    )
    return str(document.spdxId) if document is not None and document.spdxId else None
