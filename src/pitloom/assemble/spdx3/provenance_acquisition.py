# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The provenance record of a downloaded archive: where it came from, the
digest measured from its bytes and the one the index declared, how it was
chosen and the release's status.

SPDX 3 has no property for "this package's archive was obtained from URL X,
digest Y verified against a declared source, chosen because Z" (gap FG-15),
so these facts are one ``field -> provenance string`` map, which
:func:`~pitloom.assemble.spdx3.provenance.emit_provenance` writes on the main
package as every other provenance record is (an Annotation, a comment or
both, as the provenance settings say). Each string is built only by
:func:`~pitloom.core.provenance.provenance_source`,
:func:`~pitloom.core.provenance.provenance_segment` and
:func:`~pitloom.core.evidence.evidence_segment`, so text from the index (a
file name, a yank reason, a URL) cannot add a segment.

See also: :class:`pitloom.core.acquisition.Acquisition` (the record) and
:func:`pitloom.assemble.generate_pypi_sbom` (which sets it).
"""

from __future__ import annotations

from pitloom.core.acquisition import Acquisition
from pitloom.core.evidence import DECLARED, MEASURED_READ, evidence_segment
from pitloom.core.provenance import provenance_segment, provenance_source

__all__ = [
    "DOWNLOADED_FILE_SOURCE",
    "LATEST_RELEASE_METHOD",
    "WHEEL_FILENAME_SOURCE",
    "acquisition_provenance",
]

#: The ``Source`` of the digest measured from the bytes downloaded.
DOWNLOADED_FILE_SOURCE = "downloaded file"
#: The ``Source`` of a wheel's tags: its file name.
WHEEL_FILENAME_SOURCE = "wheel filename"
#: The ``Method`` of a version picked because the URL named none.
LATEST_RELEASE_METHOD = "latest-release"


def _release_version(acquisition: Acquisition) -> str:
    """The release as the index lists it: the one the URL named (no
    ``Method``; ``Normalized-From`` the URL's spelling when it differs), or
    the index's latest (``Method`` :data:`LATEST_RELEASE_METHOD`)."""
    base = provenance_source(acquisition.declared_by)
    requested = acquisition.requested_version
    if requested is None:
        base = provenance_segment(base, "Method", LATEST_RELEASE_METHOD)
    found = provenance_segment(base, "Value", acquisition.version)
    if requested is not None and requested != acquisition.version:
        found = provenance_segment(found, "Normalized-From", requested)
    return found


def _release_status(acquisition: Acquisition) -> str:
    """The release's status, and the yank reason when the index gives one."""
    status = provenance_segment(
        provenance_source(acquisition.declared_by),
        "Value",
        ", ".join(acquisition.status),
    )
    if "yanked" in acquisition.status and acquisition.yanked_reason:
        status = provenance_segment(status, "Note", acquisition.yanked_reason)
    return status


def _digest(source: str, filename: str, value: str, level: str) -> str:
    """A digest of *filename* from *source* at evidence *level*."""
    found = provenance_segment(provenance_source(source, file=filename), "Value", value)
    return f"{found} | {evidence_segment(level)}"


def _wheel_choice(acquisition: Acquisition, skipped: int) -> str:
    """How the wheel was picked and how many other matching ones were not."""
    base = provenance_source(acquisition.declared_by)
    if acquisition.chosen_by is not None:
        base = provenance_segment(base, "Method", acquisition.chosen_by)
    return provenance_segment(base, "Value", str(skipped))


def acquisition_provenance(acquisition: Acquisition) -> dict[str, str]:
    """The provenance record of *acquisition*, one entry per fact, in a fixed
    order: the project page, the file and its URL, the SHA-256 measured from
    the bytes (``Evidence: measured_read``) and the one the index declared
    (``Evidence: declared``), the release as the index lists it (the one
    the URL named, or the latest),
    its status when it is a pre-release or yanked, a wheel's tags, and how
    many other compatible wheels were skipped (with how the pick was made)."""
    record = {
        "project_url": provenance_segment(
            provenance_source(acquisition.index), "Value", acquisition.project_url
        ),
        "download_location": provenance_segment(
            provenance_source(acquisition.index, file=acquisition.filename),
            "Value",
            acquisition.file_url,
        ),
        "sha256": _digest(
            DOWNLOADED_FILE_SOURCE,
            acquisition.filename,
            acquisition.sha256,
            MEASURED_READ,
        ),
        "sha256_declared": _digest(
            acquisition.declared_by,
            acquisition.filename,
            acquisition.declared_sha256,
            DECLARED,
        ),
        "release_version": _release_version(acquisition),
    }
    if acquisition.status:
        record["release_status"] = _release_status(acquisition)
    if acquisition.tags:
        record["wheel_tags"] = provenance_segment(
            provenance_source(WHEEL_FILENAME_SOURCE, file=acquisition.filename),
            "Value",
            ", ".join(acquisition.tags),
        )
    if acquisition.compatible_skipped is not None:
        record["compatible_wheels_skipped"] = _wheel_choice(
            acquisition, acquisition.compatible_skipped
        )
    return record
