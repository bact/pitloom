# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``SpdxDocument`` envelope of a ``loom merge`` output: made before the
fragments merge into it, so the merge adds ``profileConformance``, imports,
unification Annotations and the model ``Sbom`` as it does for a project.

The document id is content-addressed (each fragment's name with its
SHA-256, sorted by name), so it does not depend on the directory path or
the order the files were written in; ``created`` is
``SOURCE_DATE_EPOCH``, else the latest ``created`` of the fragments, never
the current time.

See also: :mod:`pitloom.assemble.spdx3.fragments` (the merge) and
:func:`pitloom.assemble.generate_merged_sbom` (the caller).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import uuid5

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.core.creation import CreationMetadata, resolve_source_date_epoch
from pitloom.core.models import PITLOOM_NS, _clear_doc_counters, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import sha256_file

log = logging.getLogger(__name__)

#: ``doc_name`` of every merged document's ids.
MERGED_DOC_NAME = "merged"

#: ``created`` when neither ``SOURCE_DATE_EPOCH`` nor any fragment gives one.
_NO_CREATED = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _merged_doc_uuid(fragments_dir: Path, names: list[str]) -> str:
    """UUIDv5 of each fragment's name (relative, POSIX) with its SHA-256,
    sorted by name: the names decide which equal element survives. An
    unreadable fragment counts by nothing (the merge reports it)."""
    entries: list[str] = []
    for name in sorted(names):
        try:
            entries.append(f"{name}\x00{sha256_file(fragments_dir / name)}")
        except OSError:
            continue
    return str(uuid5(PITLOOM_NS, "\x01".join(entries)))


def new_merge_document(fragments_dir: Path, names: list[str]) -> Spdx3JsonExporter:
    """An exporter holding only the merged document's envelope: the
    ``SpdxDocument`` with the ``core`` and ``software`` profiles, and its
    creation info, the ``Pitloom`` agent and tool. *names* are the fragment
    files, relative to *fragments_dir*."""
    doc_uuid = _merged_doc_uuid(fragments_dir, names)
    _clear_doc_counters(doc_uuid)
    spdx_ci, agents, tools = build_creation_info(
        CreationMetadata(creation_datetime=_NO_CREATED.isoformat()),
        MERGED_DOC_NAME,
        doc_uuid,
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(spdx_ci)
    for agent in agents:
        exporter.add_agent(agent)
    for tool in tools:
        exporter.object_set.add(tool)
    document = spdx3.SpdxDocument(
        spdxId=generate_spdx_id(
            "SpdxDocument", doc_name=MERGED_DOC_NAME, doc_uuid=doc_uuid
        ),
        creationInfo=spdx_ci,
    )
    document.profileConformance = [
        spdx3.ProfileIdentifierType.core,
        spdx3.ProfileIdentifierType.software,
    ]
    exporter.add_document(document)
    return exporter


def _latest_fragment_created(
    exporter: Spdx3JsonExporter, own: spdx3.CreationInfo
) -> datetime | None:
    """The latest ``created`` of any creation info in the merged graph other
    than the document's own *own*."""
    found: list[datetime] = []
    for obj in exporter.object_set.objects:
        for info in (obj, getattr(obj, "creationInfo", None)):
            is_info = isinstance(info, spdx3.CreationInfo)
            created = getattr(info, "created", None) if is_info else None
            if info is not own and isinstance(created, datetime):
                found.append(created)
    return max(found, default=None)


def finish_merge_document(exporter: Spdx3JsonExporter) -> None:
    """Set the merged document's ``created``; the merge already rooted it."""
    document = next(
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    )
    own = cast(spdx3.CreationInfo, document.creationInfo)
    created = resolve_source_date_epoch() or _latest_fragment_created(exporter, own)
    if created is None:
        log.warning(
            "merge: no fragment states a creation time; created set to %s",
            _NO_CREATED.isoformat().replace("+00:00", "Z"),
        )
        created = _NO_CREATED
    own.created = created.astimezone(timezone.utc).replace(microsecond=0)
