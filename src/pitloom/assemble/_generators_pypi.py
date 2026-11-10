# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM generator for the wheel or the sdist of a release named by a PyPI
URL.

The file is downloaded and verified
(:func:`~pitloom.extract.remote.pypi.fetch_pypi_file`), then read by the local
generator of its kind, so its SBOM is the local file's plus one provenance
record of how it was obtained (:class:`~pitloom.core.acquisition.Acquisition`).

See also:
- :mod:`pitloom.assemble._generators_wheel` and
  :mod:`pitloom.assemble._generators`, the local generators it delegates to.
- :mod:`pitloom.assemble._generators_git`, the Git URL route it mirrors.
- :mod:`pitloom.assemble.spdx3.provenance_acquisition`, the record's writer.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitloom.core.acquisition import Acquisition
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    require_model_extract_override,
    resolve_fetch_policy,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.inert_options import INERT, PYPI_SDIST, PYPI_WHEEL, settle_inert
from pitloom.core.internal_error import InternalError
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.extract.remote.pypi import SDIST, WHEEL, PypiDownload, fetch_pypi_file
from pitloom.extract.remote.pypi_url import PYPI_JSON_API
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging
from pitloom.messages import CONFIG_UNSAFE, CONFIG_UNSAFE_PYPI_LINE, emit

log = logging.getLogger(__name__)

__all__ = [
    "PYPI_BUILD_REASON",
    "PYPI_INDEX",
    "PYPI_JSON_API",
    "PypiSbom",
    "generate_pypi_sbom",
    "generate_pypi_sbom_with_download",
]

#: Why a build flag has no effect for a PyPI URL target.
PYPI_BUILD_REASON = (
    "for a PyPI URL target (the download is untrusted: no build backend is run)"
)
#: The index a download is recorded as coming from.
PYPI_INDEX = "PyPI"

#: The inert-option kind of each file kind.
_KINDS = {WHEEL: PYPI_WHEEL, SDIST: PYPI_SDIST}


@dataclass(frozen=True)
class PypiSbom:
    """What :func:`generate_pypi_sbom_with_download` generated.

    Attributes:
        sbom: The SBOM (SPDX 3 JSON-LD).
        download: The file it was read from (its temporary ``path`` is
            already removed; ``filename`` and the rest are what the download
            was).
        metadata: The project metadata read from the file, as the local
            generator of its kind read it (what a local wheel's or sdist's
            default output name is made of).
    """

    sbom: str
    download: PypiDownload
    metadata: ProjectMetadata


def _acquisition_of(download: PypiDownload) -> Acquisition:
    """The record of *download* the SBOM carries: the digest measured from
    the bytes, and the one PyPI declared, which it equals (a mismatch is
    refused before this point)."""
    wheel = download.kind == WHEEL
    return Acquisition(
        index=PYPI_INDEX,
        project_url=download.project_url,
        file_url=download.file_url,
        filename=download.filename,
        version=download.version,
        sha256=download.sha256,
        declared_sha256=download.sha256,
        declared_by=PYPI_JSON_API,
        status=download.status,
        yanked_reason=download.yanked_reason,
        tags=download.tags,
        compatible_skipped=download.compatible_skipped if wheel else None,
        chosen_by=download.chosen_by,
        requested_version=download.requested_version,
    )


def _read_download(
    download: PypiDownload, options: dict[str, Any], explicit_config: bool
) -> tuple[str, ProjectMetadata]:
    """The SBOM of *download* and the project metadata it was made from, by
    the local generator of its kind, with *options* (each one that generator
    accepts)."""
    # The local generators delegate a PyPI URL here: imported late, the
    # cycle never forms at import time.
    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.assemble._generators import generate_project_sbom

    # pylint: disable-next=import-outside-toplevel,cyclic-import
    from pitloom.assemble._generators_wheel import generate_wheel_sbom_with_metadata

    acquisition = _acquisition_of(download)
    if download.kind == WHEEL:
        return generate_wheel_sbom_with_metadata(
            download.path, **options, acquisition=acquisition
        )
    if not explicit_config:
        emit(
            log,
            CONFIG_UNSAFE,
            logging.INFO,
            line=CONFIG_UNSAFE_PYPI_LINE,
            file=download.filename,
        )
    # The sdist's own [tool.pitloom] is never read: the defaults stand in.
    config = (
        PitloomConfig()
        if options["pitloom_config"] is None
        else options["pitloom_config"]
    )
    # Read here, as generate_project_sbom() would, so the caller gets it.
    metadata, config, _ = resolve_project_with_lockfile(
        download.path, options.get("use_lockfile"), config
    )
    sdist_options: dict[str, Any] = {**options, "pitloom_config": config}
    sbom = generate_project_sbom(
        download.path,
        **sdist_options,
        project_metadata=metadata,
        acquisition=acquisition,
    )
    return sbom, metadata


# pylint: disable-next=too-many-arguments,too-many-locals
def generate_pypi_sbom_with_download(
    url: str,
    *,
    kind: str = WHEEL,
    check_url: Callable[[str], None] | None = None,
    max_download_bytes: int | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    scan_model_usage: bool | None = None,
    trust_model_files: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    update_id_registry: bool | None = None,
    use_lockfile: bool | None = None,
    max_source_metadata_bytes: int | None = None,
    max_model_extract_bytes: int | None = None,
    build_options: BuildOptions = BuildOptions(),
    project_dir: Path | str | None = None,
) -> PypiSbom:
    """Generate an SPDX 3 SBOM for the wheel (*kind* ``"wheel"``, an
    Analyzed SBOM) or the sdist (``"sdist"``, a Source SBOM) of the release
    the PyPI URL *url* names (``https://pypi.org/project/<name>/`` for the
    latest release, ``.../<name>/<version>/`` for one).

    The file is downloaded into a temporary directory removed on return, its
    SHA-256 checked against the one PyPI declares
    (:func:`~pitloom.extract.remote.pypi.fetch_pypi_file`, which picks the
    wheel that best matches the running environment), and read as the local
    file is (:func:`~pitloom.assemble.generate_wheel_sbom`,
    :func:`~pitloom.assemble.generate_project_sbom`): every option means
    what it means there. The SBOM adds one provenance record on the main
    package: the project page, the file's URL and name, the SHA-256
    measured from the bytes and the one PyPI declared, the release (and
    whether the URL named it), its status when a pre-release or yanked, and
    for a wheel its tags and how many other compatible wheels were skipped.
    No message or SBOM names the temporary path.

    *check_url* is called with every URL of the release lookup and the
    download before it is requested (the JSON API's, the file's and each
    redirect target), the caller's address policy; the PyPI lookup of a
    dependency's licence and originator (made, as *offline* is never true
    once a file is downloaded) does not pass through it. *max_download_bytes* caps
    the file: else *pitloom_config*'s ``max-download-bytes``, else 512 MiB.
    With *offline* (else *pitloom_config*'s ``offline``) true nothing is
    fetched (``pypi.offline``, ``network-unusable``; an invalid *url* is
    ``pypi-url-invalid`` first). The three resolve as every remote route
    resolves them
    (:func:`~pitloom.core.config_cascade.resolve_fetch_policy`).

    The download is untrusted: an sdist's own ``[tool.pitloom]`` is never
    read (only *pitloom_config* applies, with one ``INFO:`` when it is not
    given), no build backend is run (a build flag in *build_options* warns
    once) and *project_dir* has no effect; each option the kind cannot use
    warns once against *url*. A relative *id_registry* means the caller's
    directory, as for any local wheel or sdist.

    Returns a :class:`PypiSbom`: the SBOM, the
    :class:`~pitloom.extract.remote.pypi.PypiDownload` it was read from and
    the project metadata read from the file. :func:`generate_pypi_sbom`
    returns the SBOM alone.

    Raises:
        pitloom.core.internal_error.InternalError: *kind* is neither.
        ValueError: *max_download_bytes* (or the config's) or
            *max_model_extract_bytes* is not an integer of at least 1.
        pitloom.messages.CodedValueError: *url* is not a PyPI project or
            release URL (``pypi-url-invalid``).
        pitloom.extract.remote.errors.RemoteSourceError: the release or the
            file could not be fetched or verified (``pypi.*``).
    """
    configure_logging()
    if kind not in _KINDS:
        raise InternalError(f"kind must be {WHEEL!r} or {SDIST!r}, got {kind!r}")
    if max_model_extract_bytes is not None:
        require_model_extract_override(max_model_extract_bytes)  # even if inert
    policy = resolve_fetch_policy(
        pitloom_config,
        offline=offline,
        max_download_bytes=max_download_bytes,
        check_url=check_url,
    )
    subject = url.strip()
    build_options.settle_not_applicable(subject, PYPI_BUILD_REASON)
    options: dict[str, Any] = {
        "output_path": output_path,
        "creation_metadata": creation_metadata,
        "pretty": pretty,
        "describe_relationship": describe_relationship,
        "pitloom_config": pitloom_config,
        "id_registry": id_registry,
        "provenance": provenance,
        "offline": offline,
        "enrich": enrich,
        "extract_file_header": extract_file_header,
        "scan_model_usage": scan_model_usage,
        "trust_model_files": trust_model_files,
        "content_type": content_type,
        "content_type_method": content_type_method,
        "update_id_registry": update_id_registry,
        "use_lockfile": use_lockfile,
        "max_source_metadata_bytes": max_source_metadata_bytes,
        "max_model_extract_bytes": max_model_extract_bytes,
        "project_dir": project_dir,
    }
    # Settled here, against the URL: the local generator never names the
    # temporary file in a warning.
    inert_kind = _KINDS[kind]
    settle_inert(inert_kind, subject, options)
    forwarded = {k: v for k, v in options.items() if k not in INERT[inert_kind]}
    with fetch_pypi_file(url, kind=kind, policy=policy) as download:
        sbom, metadata = _read_download(download, forwarded, pitloom_config is not None)
        return PypiSbom(sbom=sbom, download=download, metadata=metadata)


@functools.wraps(generate_pypi_sbom_with_download)
def generate_pypi_sbom(url: str, **kwargs: Any) -> str:
    """:func:`generate_pypi_sbom_with_download`, returning the SBOM alone;
    it takes the same parameters (its signature is that function's)."""
    return generate_pypi_sbom_with_download(url, **kwargs).sbom
