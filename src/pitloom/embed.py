# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Embed SPDX 3 SBOMs into built Python wheels (PEP 770).

See also: :mod:`pitloom._embed_wheel` for ZIP archive manipulation and
RECORD updating; :mod:`pitloom._embed_build_sbom` for the Build SBOM made
from a project directory's rescan and the wheel's own files;
:mod:`pitloom._embed_generate` for generating the SBOM JSON to embed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom._embed_build_sbom import (
    EmbedFileCache,
    _build_sbom_from_project_and_wheel,
)
from pitloom._embed_generate import (
    _generate_embed_sbom_json,
    _resolve_embed_registry,
)
from pitloom._embed_wheel import (
    _DEFAULT_FILE_ATTR,
    _ZIP_EPOCH_FLOOR,
    RECORD_SIGNATURES,
    _calculate_record_hash,
    _derive_wheel_sbom_filename,
    _plan_embed,
    _resolve_zip_timestamp,
    _rewrite_wheel_archive,
    _update_record_lines,
    _validate_sbom_filename,
    embed_sbom_in_wheel,
    refuse_unembeddable_wheel,
)
from pitloom._sbom_format import (
    RECOMMENDED_EXTENSIONS,
    VALIDATED_FORMATS,
    check_spdx3_name_version,
    detect_sbom_format,
    format_name_version_mismatch,
)
from pitloom._sbom_io import write_sbom_output
from pitloom._wheel_sbom_location import (
    EmbeddedSbomLocation,
    _find_dist_info_prefix,
    find_embedded_sbom,
)
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.creation import CreationMetadata
from pitloom.core.file_names import sbom_base_name, sbom_file_name
from pitloom.core.quote_source import quote_source
from pitloom.core.wheel_dist_info import require_wheel_path
from pitloom.extract.authors import AuthorSplit
from pitloom.extract.wheel import read_wheel, wheel_identity
from pitloom.id_registry import IdRegistry
from pitloom.logging_config import configure_logging

log = logging.getLogger(__name__)

__all__ = [
    "ConfigOverrides",
    "EmbedFileCache",
    "EmbeddedSbomLocation",
    "_DEFAULT_FILE_ATTR",
    "RECOMMENDED_EXTENSIONS",
    "RECORD_SIGNATURES",
    "VALIDATED_FORMATS",
    "_ZIP_EPOCH_FLOOR",
    "_build_sbom_from_project_and_wheel",
    "_calculate_record_hash",
    "_derive_wheel_sbom_filename",
    "detect_sbom_format",
    "_find_dist_info_prefix",
    "_plan_embed",
    "_resolve_zip_timestamp",
    "_rewrite_wheel_archive",
    "_update_record_lines",
    "_validate_sbom_filename",
    "embed_filename",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
    "find_embedded_sbom",
    "refuse_unembeddable_wheel",
]


def embed_filename(sbom_basename: str | None) -> str | None:
    """The file name an SBOM is embedded under for *sbom_basename*
    (``--sbom-basename``/``[tool.pitloom] sbom-basename``, checked by
    :func:`pitloom.core.file_names.sbom_file_name`), or ``None`` for the
    default name. Shared by ``embed-wheel`` and ``wheel --embed``."""
    if not sbom_basename:
        return None
    return sbom_file_name(sbom_basename)


def _enforce_sbom_name_version(
    wheel_filename: str,
    wheel_name: str | None,
    wheel_version: str | None,
    sbom_json: str,
    *,
    allow_mismatch: bool,
) -> None:
    """Cross-check an externally-supplied ``--sbom``'s declared subject
    name/version against the target wheel's own METADATA, *before*
    anything is written to the wheel.

    Raises ``ValueError`` on a genuine mismatch unless *allow_mismatch* --
    the embed is refused outright rather than writing a known-wrong SBOM
    and relying on a later `verify-wheel`/`--verify` to catch it, since
    nothing is on disk yet to roll back. *allow_mismatch* downgrades a
    mismatch to a `WARNING:` and lets the embed proceed (for CI/automation
    that wants best-effort embedding). Extraction failures (unsupported
    format, unexpected graph shape) are always a non-fatal `WARNING:`,
    regardless of *allow_mismatch* -- "couldn't check" is never escalated
    to "refused."

    Fatal-by-default here, unlike `verify-wheel`'s own WARNING-by-default
    (:func:`pitloom.cli.commands.verify_wheel._check_name_version`) --
    intentional, not an inconsistency: this runs *before* a wheel is
    written, so refusing is cheap (nothing to roll back), whereas
    verify-wheel inspects an already-built wheel after the fact.
    """
    sbom_data = sbom_json.encode("utf-8")
    sbom_format = detect_sbom_format(sbom_data)
    mismatches, warnings = check_spdx3_name_version(
        wheel_name, wheel_version, sbom_data, sbom_format
    )
    for warning in warnings:
        log.warning("%s: %s", quote_source(wheel_filename), warning)

    if not mismatches:
        return

    message = format_name_version_mismatch(wheel_filename, mismatches)
    if allow_mismatch:
        log.warning(message)
        return
    raise ValueError(message)


# pylint: disable=too-many-arguments
# pylint: disable-next=too-many-locals
def embed_wheel_sbom(
    wheel_path: Path | str,
    *,
    project_dir: Path | str | None = None,
    pitloom_config: PitloomConfig | None = None,
    sbom_path: Path | str | None = None,
    output_path: Path | str | None = None,
    sbom_basename: str | None = None,
    creation_metadata: CreationMetadata | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    overrides: ConfigOverrides | None = None,
    allow_mismatch: bool = False,
    allow_signed_wheel: bool = False,
    file_cache: EmbedFileCache | None = None,
) -> tuple[Path, str, str, tuple[str, ...], bool]:
    """Generate and embed a PEP 770 SBOM into a built Python wheel.

    When *sbom_path* supplies an externally-generated SBOM, its declared
    subject name/version is cross-checked against the wheel's own
    ``.dist-info/METADATA`` before anything is written -- see
    :func:`_enforce_sbom_name_version`. A genuine mismatch raises
    ``ValueError`` unless *allow_mismatch*. A signed wheel (``RECORD.jws``/
    ``RECORD.p7s``) raises ``ValueError`` unless *allow_signed_wheel*, which
    removes the signature the embed would invalidate. A Pitloom-generated SBOM
    (*sbom_path* unset) is never checked: it is built from the wheel's own
    metadata.

    With *project_dir* (the project the wheel was built from) the SBOM is a
    Build SBOM from that directory's rescan and the wheel's own files;
    without it, an Analyzed SBOM of the wheel alone. *pitloom_config*
    replaces the project's own ``[tool.pitloom]``; *overrides* are the
    per-run settings (:class:`~pitloom.core.config_cascade.ConfigOverrides`);
    *sbom_basename*, *creation_metadata* and *id_registry* are as for
    :func:`~pitloom.assemble.generate`. *output_path* also receives a copy of
    the SBOM JSON.

    *file_cache*: advanced/batch use only -- share one
    :class:`EmbedFileCache` across several calls that target the same
    *project_dir*/*pitloom_config*/``overrides.build_options`` (e.g. one
    wheel per call, in a loop) to resolve *project_dir*'s file list (and
    run any ``--allow-build`` real PEP 517 build) once for the whole
    batch instead of once per call. A batch logs each ineffective-option
    warning, the model-usage ``INFO:`` hint and each gated-format ``INFO:``
    once. Left ``None`` (the default), this
    call resolves and cleans up its own file list. When given, *this*
    call does NOT clean up -- make every call of the batch inside one
    ``with EmbedFileCache() as file_cache:`` block, whose exit does; a
    cache used outside its block raises :class:`RuntimeError`.

    Returns:
        ``(wheel path, SBOM arcname in the wheel, SBOM JSON, arcnames removed,
        floored)``, as :func:`~pitloom._embed_wheel.embed_sbom_in_wheel`
        returns them, with the SBOM JSON third.

    Raises:
        ValueError: The wheel is refused as a whole
            (:class:`~pitloom.core.wheel_dist_info.WheelRefused`: not a ZIP
            archive, a member cannot be read, two members have one name or
            one holds a NUL, a member of its own ``.dist-info`` has a
            non-conforming name),
            it has no single own ``.dist-info``, or the SBOM's name/version
            mismatches (see above). The wheel is left as it was.
        OSError: *wheel_path* cannot be opened (missing, permission denied).
    """
    configure_logging()
    if sbom_basename:
        sbom_basename = sbom_base_name(sbom_basename, "--sbom-basename")
    require_wheel_path(wheel_path)
    # Not resolved: a symlink's name is the one judged, and the one the
    # embed reports; ``embed_sbom_in_wheel`` resolves to write.
    wheel_obj = Path(wheel_path).absolute()
    eff_overrides = overrides if overrides is not None else ConfigOverrides()
    if sbom_path is None:
        # Fails on a declared-but-bad registry before the wheel is read. An
        # external SBOM never touches the registry, so only without
        # *sbom_path*. The resolved registry replaces *id_registry*, so
        # _generate_embed_sbom_json() does not load the file again.
        id_registry = _resolve_embed_registry(project_dir, pitloom_config, id_registry)
    # Before the SBOM is generated: that may run a build.
    refuse_unembeddable_wheel(wheel_obj, allow_signed_wheel)
    # The wheel's split Author-email is warned about only where its authors
    # are used.
    author_splits: list[AuthorSplit] = []
    wheel_metadata, _ = read_wheel(wheel_obj, author_splits=author_splits)

    sbom_json, eff_basename = _generate_embed_sbom_json(
        wheel_metadata,
        wheel_path=wheel_obj,
        project_dir=project_dir,
        pitloom_config=pitloom_config,
        sbom_path=sbom_path,
        sbom_basename=sbom_basename,
        creation_metadata=creation_metadata,
        id_registry=id_registry,
        overrides=eff_overrides,
        file_cache=file_cache,
        author_splits=author_splits,
    )
    wheel_name, wheel_version = wheel_identity(wheel_metadata)
    if sbom_path is not None:
        _enforce_sbom_name_version(
            wheel_obj.name,
            wheel_name,
            wheel_version,
            sbom_json,
            allow_mismatch=allow_mismatch,
        )
    # The identity just read goes down, so the embed does not read (and warn
    # about) the same METADATA again.
    res_path, arcname, removed_arcnames, timestamp_floored = embed_sbom_in_wheel(
        wheel_obj,
        sbom_json,
        sbom_filename=embed_filename(eff_basename),
        identity=(wheel_name, wheel_version),
        allow_signed_wheel=allow_signed_wheel,
    )

    write_sbom_output(sbom_json, output_path)

    return res_path, arcname, sbom_json, removed_arcnames, timestamp_floored
