# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Analyzed SBOM generator for a built Python wheel.

See also:
- :mod:`pitloom.assemble._generators_shared` for the helpers shared with the
  other generators.
- :mod:`pitloom.assemble._generators` for the project/sdist generator.
- :mod:`pitloom.assemble._generators_env` for the installed-environment
  generator, which resolves its settings the same way.
- :mod:`pitloom.assemble._generators_pypi` for a wheel named by a PyPI URL,
  which it delegates to and which reads the download here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble._generators_pypi import generate_pypi_sbom
from pitloom.assemble._generators_shared import _sync_registry, archive_project_dir
from pitloom.assemble.spdx3.document import build
from pitloom.core.acquisition import Acquisition
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    ConfigOverrides,
    require_download_override,
    resolve_standalone_config,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.inert_options import WHEEL, settle_inert
from pitloom.core.models import merkle_root_of_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.core.walk_rules import without_registry_copies
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.remote.pypi import WHEEL as WHEEL_FILE
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from pitloom.extract.wheel import read_wheel, wheel_document_identity
from pitloom.id_registry import IdRegistry, registry_copy, resolve_registry
from pitloom.logging_config import configure_logging


# pylint: disable=too-many-arguments,too-many-locals
def generate_wheel_sbom(
    wheel_path: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
    content_type_method: str | None = None,
    update_id_registry: bool | None = None,
    max_source_metadata_bytes: int | None = None,
    max_model_extract_bytes: int | None = None,
    scan_model_usage: bool | None = None,
    trust_model_files: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
    project_dir: Path | str | None = None,
    check_url: Callable[[str], None] | None = None,
    max_download_bytes: int | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel.

    *wheel_path* may be a PyPI project or release URL (a ``str``; a
    :class:`~pathlib.Path` is always a local file): the release's wheel that
    best matches the running environment is downloaded and read
    (:func:`~pitloom.assemble.generate_pypi_sbom`): *check_url* is called
    with every URL of the release lookup and the download before it is
    requested (a dependency's licence lookup does not pass through it), and
    *max_download_bytes* caps the file. For a local wheel *check_url* is not used
    and *max_download_bytes* has no effect (one ``WARNING:``; an invalid
    value raises all the same).

    A wheel has no ``[tool.pitloom]`` of its own, and none is borrowed: not
    from the current directory, not from beside the wheel -- either may
    belong to an unrelated project. Settings come from the arguments, then
    *pitloom_config* when the caller names one explicitly, then the built-in
    defaults. The same holds for the registry: *id_registry*, else the explicit
    config's ``id-registry``; no ``loom-id-registry.json`` is searched for.
    The copy of that registry a build put in the wheel is left out, with one
    ``WARNING:``, when its path below the project directory is the member's
    (see :func:`~pitloom.id_registry.registry_copy` for the directory).

    *project_dir* names the project directory the wheel was built from: its
    members are then keyed below that directory's path from the registry's
    root (a registry above the project, a monorepo), as ``embed-wheel
    --project-dir`` keys them. Nothing is read from it; without a registry
    it has no effect, with one ``WARNING:``.

    An explicit *pitloom_config* applies in full, identity included: its
    creators, creation datetime and comment fill in when *creation_metadata*
    is not given.

    AI models inside the wheel are found; *scan_model_usage* also records
    which Python files in it reference them. One model file is copied out
    of the wheel at a time, each up to *max_model_extract_bytes*
    (``--max-model-extract-bytes``; else the config's
    ``max-model-extract-bytes``, 512 MiB by default) and four times that in
    all, counting bytes copied and bytes read from archive
    members; a model beyond either limit is listed without metadata. Models
    in a format whose reader a hostile file can crash or hang (fastText,
    GGUF, HDF5, ONNX, PyTorch ``.pt``/``.pth``) are listed without metadata
    too, with one ``INFO:``, unless *trust_model_files* (for a wheel you
    trust only; it has no config key, so a config cannot opt in).

    ``extract_file_header``/``content_type``/``enrich`` have no parameter
    here: reading a built wheel scans no file headers or content types, and
    its AI models are not enriched (see :data:`pitloom.core.inert_options.INERT`).
    ``content_type_method`` does apply, because it also steers whether
    dependency originator enrichment fetches a remote authors file.

    Raises:
        ValueError: The wheel is refused as a whole
            (:class:`~pitloom.core.wheel_dist_info.WheelRefused`): not a ZIP
            archive, a member cannot be read, two members have one name or
            one holds a NUL; or *max_model_extract_bytes* is not an
            integer of at least 1.
        FileNotFoundError: *project_dir* is given and is not a directory.
        OSError: *wheel_path* cannot be opened (missing, permission denied).
        pitloom.extract.remote.errors.RemoteSourceError: a PyPI URL's
            wheel could not be fetched or verified (``pypi.*``).
    """
    if isinstance(wheel_path, str) and is_pypi_url(wheel_path):
        return generate_pypi_sbom(
            wheel_path,
            kind=WHEEL_FILE,
            check_url=check_url,
            max_download_bytes=max_download_bytes,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            id_registry=id_registry,
            provenance=provenance,
            offline=offline,
            content_type_method=content_type_method,
            update_id_registry=update_id_registry,
            max_source_metadata_bytes=max_source_metadata_bytes,
            max_model_extract_bytes=max_model_extract_bytes,
            scan_model_usage=scan_model_usage,
            trust_model_files=trust_model_files,
            pitloom_config=pitloom_config,
            project_dir=project_dir,
        )
    return generate_wheel_sbom_with_metadata(
        wheel_path,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        id_registry=id_registry,
        provenance=provenance,
        offline=offline,
        content_type_method=content_type_method,
        update_id_registry=update_id_registry,
        max_source_metadata_bytes=max_source_metadata_bytes,
        max_model_extract_bytes=max_model_extract_bytes,
        scan_model_usage=scan_model_usage,
        trust_model_files=trust_model_files,
        pitloom_config=pitloom_config,
        project_dir=project_dir,
        check_url=check_url,
        max_download_bytes=max_download_bytes,
    )[0]


def generate_wheel_sbom_with_metadata(
    wheel_path: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
    content_type_method: str | None = None,
    update_id_registry: bool | None = None,
    max_source_metadata_bytes: int | None = None,
    max_model_extract_bytes: int | None = None,
    scan_model_usage: bool | None = None,
    trust_model_files: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
    project_dir: Path | str | None = None,
    check_url: Callable[[str], None] | None = None,
    max_download_bytes: int | None = None,
    acquisition: Acquisition | None = None,
) -> tuple[str, ProjectMetadata]:
    """:func:`generate_wheel_sbom`, and the :class:`ProjectMetadata` read from
    the wheel, for a caller that goes on to use the wheel's declared identity
    (it need not read ``METADATA`` again, and warn about it twice).

    *wheel_path* is a local wheel only (a PyPI URL is read by
    :func:`generate_wheel_sbom`): *check_url* is not used and
    *max_download_bytes* has no effect (one ``WARNING:``; an invalid value
    raises all the same). Both are accepted so that a caller forwarding
    :func:`generate_wheel_sbom`'s options can call this instead.

    *acquisition* records how the wheel was downloaded (set by
    :func:`~pitloom.assemble.generate_pypi_sbom`); it adds one provenance
    record on the main package and changes nothing else.

    Raises:
        ValueError: The wheel is refused as a whole
            (:class:`~pitloom.core.wheel_dist_info.WheelRefused`): not a ZIP
            archive, a member cannot be read, two members have one name or
            one holds a NUL; or *max_model_extract_bytes* is not an
            integer of at least 1.
        FileNotFoundError: *project_dir* is given and is not a directory.
        OSError: *wheel_path* cannot be opened (missing, permission denied).
    """
    configure_logging()
    del check_url  # nothing is fetched for a local wheel
    if max_download_bytes is not None:
        require_download_override(max_download_bytes)  # even if inert
        settle_inert(WHEEL, wheel_path, {"max_download_bytes": max_download_bytes})
    wheel_path_obj = Path(wheel_path)
    cfg = resolve_standalone_config(
        pitloom_config,
        ConfigOverrides(
            provenance=provenance,
            offline=offline,
            content_type_method=content_type_method,
            pretty=pretty,
            describe_relationship=describe_relationship,
            update_id_registry=update_id_registry,
            max_source_metadata_bytes=max_source_metadata_bytes,
            max_model_extract_bytes=max_model_extract_bytes,
            scan_model_usage=scan_model_usage,
        ),
    )
    # Resolved before the expensive read_wheel()/find_phantom_dependencies()
    # calls below -- a declared-but-missing/malformed registry should fail
    # fast, never after paying for a full wheel read first.
    resolved_registry = resolve_registry(id_registry, cfg.id_registry, Path.cwd())
    origin_dir = archive_project_dir(project_dir, resolved_registry, wheel_path)
    project_metadata, project_files = read_wheel(wheel_path_obj)
    # A copy of an in-tree registry the build put in the wheel: neither a
    # file of the SBOM nor of its Merkle root.
    project_files = without_registry_copies(
        project_files, registry_copy(resolved_registry, origin_dir)
    )
    project_metadata.files = project_files
    ai_models = scan_wheel_for_ai_models(
        wheel_path_obj,
        scan_usage=cfg.scan_model_usage is True,
        usage_hint=lambda: cfg.scan_model_usage is None,
        max_bytes=cfg.max_model_extract_bytes,
        trust=trust_model_files is True,
    )
    phantom_deps = find_phantom_dependencies(project_files)

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or cfg.creation_metadata,
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
        acquisition=acquisition,
        **wheel_document_identity(project_metadata, wheel_path_obj, origin_dir),
    )
    exporter = build(
        doc,
        merkle_root=merkle_root_of_files(project_files),
        sbom_type=spdx3_bindings.software_SbomType.analyzed,
        registry=resolved_registry,
        **cfg.assemble_options,
    )

    _sync_registry(exporter, resolved_registry, cfg.update_id_registry)

    sbom_json = exporter.to_json(
        pretty=cfg.pretty,
        describe_relationship=bool(cfg.describe_relationship),
    )

    write_sbom_output(sbom_json, output_path)

    return sbom_json, project_metadata
