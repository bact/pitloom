# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How the archive an SBOM describes was obtained, when it was downloaded
rather than given as a local file.

:class:`Acquisition` is format-neutral: a generator that downloads the file
(:func:`pitloom.assemble.generate_pypi_sbom`) sets it on the
:class:`~pitloom.core.document.DocumentModel`, and the SPDX 3 assembler
writes it as one provenance record on the main package
(:func:`pitloom.assemble.spdx3.provenance_acquisition.acquisition_provenance`).
A local target has none.

No leading underscore: imported by :mod:`pitloom.assemble`.

See also: :class:`pitloom.extract.remote.pypi.PypiDownload` (what the PyPI
download returns, which the generator copies here).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Acquisition"]


# Every fact the SBOM records about the download is one field of it.
@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes
class Acquisition:
    """A file downloaded from a package index and verified.

    Attributes:
        index: The index it came from, as provenance names it (``PyPI``).
        project_url: The release page.
        file_url: The URL the file was downloaded from.
        filename: The file's name on the index.
        version: The release, as the index lists it.
        sha256: The SHA-256 (lower-case hex) measured from the bytes read.
        declared_sha256: The SHA-256 the index declares, which *sha256*
            was checked against (equal, or the download is refused).
        declared_by: What declared *declared_sha256* (provenance ``Source``).
        status: ``"prerelease"`` and ``"yanked"`` as they apply, in that
            order.
        yanked_reason: The index's reason for a yank, when it gives one.
        tags: A wheel's tags, sorted; empty for an sdist.
        compatible_skipped: How many other wheels matched the environment
            and were not picked; ``None`` for an sdist (no choice was made).
        chosen_by: How the file was picked (``running-environment``), or
            ``None`` when nothing was chosen between.
        requested_version: The version the URL named, as spelled there
            (*version* is the index's spelling of the same release), or
            ``None``: the URL named none and the latest release was read.
    """

    index: str
    project_url: str
    file_url: str
    filename: str
    version: str
    sha256: str
    declared_sha256: str
    declared_by: str
    status: tuple[str, ...] = ()
    yanked_reason: str | None = None
    tags: tuple[str, ...] = ()
    compatible_skipped: int | None = None
    chosen_by: str | None = None
    requested_version: str | None = None
