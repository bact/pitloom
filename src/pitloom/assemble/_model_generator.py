# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model SBOM and enrichment fragment generators."""

from __future__ import annotations

import dataclasses
import functools
import logging
from collections.abc import Callable
from pathlib import Path

from pitloom._sbom_io import refuse_empty_output, write_sbom_output
from pitloom.assemble.spdx3.ai import lookup_model_id
from pitloom.assemble.spdx3.document import build_enrichment_fragment, build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.bool_arguments import checked_bools
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import (
    ConfigOverrides,
    require_download_override,
    resolve_fetch_policy,
    resolve_standalone_config,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.file_hash import HexDigests, file_digests, sha256_digest
from pitloom.core.given_path import TypedPath
from pitloom.core.inert_options import (
    ENRICH_STANDALONE,
    HF,
    MODEL_FILE,
    SDIST,
    settle_inert,
)
from pitloom.core.models import compute_doc_uuid, generate_spdx_id, get_wheel_files
from pitloom.core.path_probe import is_missing_errno
from pitloom.core.project import ProjectMetadata, is_sdist_archive
from pitloom.core.provenance import ProvenanceConfig
from pitloom.enrich import run_enrichers
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract.model_target import model_path_of, read_model_file
from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.extract.remote import is_huggingface_source, read_huggingface
from pitloom.extract.remote.pypi_url import is_pypi_url
from pitloom.id_registry import (
    Alias,
    IdRegistry,
    IdRegistrySession,
    artifact_key,
    registry_base_dir,
    registry_file_path,
    resolve_registry,
)
from pitloom.id_registry.import_keys import name_key_reason
from pitloom.logging_config import configure_logging
from pitloom.messages import CodedValueError, url_text
from pitloom.messages.config import (
    Parameter,
    invalid_value,
    require_path_argument,
)
from pitloom.messages.files import warn_file_unreadable
from pitloom.messages.id_registry_ids import info_name_key
from pitloom.messages.pypi import (
    MODEL_URL_LINES,
    PYPI_URL_UNUSABLE,
)
from pitloom.messages.targets import MODEL_FILE_KIND, refuse_empty_input

log = logging.getLogger(__name__)


def _read_local_model(model_path: Path, shown: str | None = None) -> AiModelMetadata:
    """Read a local model file by the rule a project or wheel scan applies
    (:func:`~pitloom.extract.scanner.read_model_candidate`): a confirmed model
    whose read fails or is over a limit keeps a format-only entry and one
    ``WARNING:``, the per-model entry cap applies, so every surface lists the
    same entry for the same file. A file named here is read by its content,
    whatever its suffix (``x.dat`` with GGUF magic is a GGUF model); see
    :func:`~pitloom.extract.model_target.read_model_file`.

    Messages name the file *shown* (default: *model_path*).

    Raises:
        pitloom.messages.CodedFileNotFoundError: *model_path* does not exist
            (``input-not-found``).
        ValueError: The file is not a model of a supported format: see
            :func:`~pitloom.extract.model_target.refuse_not_a_model`.
        OSError: The header cannot be read.
    """
    return read_model_file(model_path, shown=shown)


def _warn_hash_unread(model_path: Path, exc: OSError) -> None:
    """The ``file-unreadable`` ``WARNING:`` for the model file *model_path*
    that *exc* stopped hashing (no ``verifiedUsing``, the registry lookup not
    gated); none for one gone since it was read: absent."""
    if not is_missing_errno(exc):
        warn_file_unreadable(log, exc, file=model_path, use="for the model hash")


def _model_file_digests(model_path: Path) -> HexDigests | None:
    """The SHA-256 and SHA-512 of the model file at *model_path* (its
    ``verifiedUsing``), from one chunked read; ``None`` and one ``WARNING:``
    when it cannot be read. Called after :func:`_read_local_model` only, so
    the file is a confirmed model, never a Git LFS pointer (the gate refuses
    that unhashed): its raw and its stated digest are one."""
    try:
        return file_digests(model_path).hex()
    except OSError as exc:
        _warn_hash_unread(model_path, exc)
        return None


def _model_file_sha256(model_path: Path) -> str | None:
    """The SHA-256 alone of the model file at *model_path*, to gate a
    registry lookup; ``None`` as :func:`_model_file_digests`."""
    try:
        return sha256_digest(model_path).hex()
    except OSError as exc:
        _warn_hash_unread(model_path, exc)
        return None


def _model_registry_id(
    registry: IdRegistry | None,
    model: AiModelMetadata,
    model_path: Path,
    digest: Callable[[], str | None],
) -> str | None:
    """The registry id of the model file at *model_path* (as given: a
    relative one from the current directory). Its key is its path from the
    registry's root (:func:`~pitloom.id_registry.artifact_key`), looked up
    gated by *digest()*, its ``CANONICAL`` layout alias included (a wheel's
    key for a ``src/`` model, said in one ``INFO:``); outside the root, its
    stem, ungated, with one ``INFO:`` saying why. A message names the model
    by its own name (*model*), else its stem, as a project's does. ``None``
    without a *registry*."""
    if registry is None:
        return None
    stem = model_path.stem
    lookup = artifact_key(registry, path=model_path, name=stem, alias=Alias.CANONICAL)
    if not lookup.path:
        info_name_key(log, "model", stem, name_key_reason(model_path))
    session = IdRegistrySession(registry)
    spdx_id = lookup_model_id(
        session, model.own_name or stem, lookup, digest() if lookup.path else None
    )
    session.info_layout_alias_hits()
    return spdx_id


def _doc_identity_of(
    project_dir: Path,
    project_metadata: ProjectMetadata,
    registry: IdRegistry | None = None,
) -> tuple[str, str]:
    """``(doc_name, doc_uuid)`` for *project_metadata*, resolved from
    *project_dir* (see :func:`~pitloom.core.models.compute_doc_uuid` for
    the content-addressing this ``doc_uuid`` is built from).

    For a project directory, ``doc_uuid`` includes the Merkle root of
    :func:`~pitloom.core.models.get_wheel_files`'s resolved file set, so it
    changes whenever that set changes for this project -- including when a
    backend's file-discovery accuracy improves without any file on disk
    actually changing. An sdist target has no file walk, so no Merkle root.
    Callers merging an enrichment fragment against a
    previously-generated SBOM should regenerate that base SBOM first
    after a Pitloom upgrade that changes file discovery for this
    project's backend, or the fragment's element references may not
    match the base document's spdxIds.

    The file walk leaves out *registry*'s own file, as in the project's
    SBOM, so both compute the same Merkle root.
    """
    # No build_options (no --allow-build) for either caller, enrich_model()
    # and project_document_id(), so the returned cleanup is a no-op.
    merkle_root: str | None = None
    if not project_dir.is_file():  # an sdist has no file walk, as in its SBOM
        merkle_root, project_files, _cleanup = get_wheel_files(
            project_dir, exclude_path=registry_file_path(registry)
        )
        _cleanup()
        project_metadata.files = project_files
    doc_uuid = compute_doc_uuid(
        name=project_metadata.name,
        version=project_metadata.version or "unknown",
        dependencies=project_metadata.dependencies,
        merkle_root=merkle_root,
        locked_dependencies=project_metadata.locked_dependencies,
        locked_dependencies_seed=project_metadata.locked_dependencies_seed(),
    )
    return project_metadata.name, doc_uuid


def project_document_id(project_dir: Path) -> str:
    """The ``SpdxDocument`` id a ``loom project`` build of *project_dir*
    gives (without ``--allow-build``), resolved as :func:`_doc_identity_of`
    resolves it; ``loom fragment list`` compares fragments with it."""
    configure_logging()
    metadata, config, _path = resolve_project_with_lockfile(project_dir, None)
    registry = resolve_registry(
        None,
        config.id_registry,
        registry_base_dir(project_dir),
        refuse_credentials=config.credential_policy.refuse,
    )
    doc_name, doc_uuid = _doc_identity_of(project_dir, metadata, registry)
    return generate_spdx_id("SpdxDocument", doc_name=doc_name, doc_uuid=doc_uuid)


# pylint: disable=too-many-arguments,too-many-locals
def _refuse_pypi_url(source: Path | str) -> None:
    """Raise ``pypi-url-unusable`` when *source* is a PyPI URL, which would
    otherwise be read as a missing local path.

    Raises:
        CodedValueError: It is one (raised, not logged: the caller says
            it once, as the Git route does).
    """
    if not isinstance(source, str) or not is_pypi_url(source):
        return
    error = CodedValueError(
        PYPI_URL_UNUSABLE,
        line=MODEL_URL_LINES,
        url=url_text(source.strip()),
    )
    raise error


@checked_bools
def generate_model_sbom(
    source: Path | str,
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    max_source_metadata_bytes: int | None = None,
    pitloom_config: PitloomConfig | None = None,
    shown: str | None = None,
    max_download_bytes: int | None = None,
    check_url: Callable[[str], None] | None = None,
    credentials: CredentialPolicy | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 AIBOM for a local model file or HF repository.

    Settings resolve as :func:`~pitloom.assemble.generate_wheel_sbom`
    describes: arguments, then an explicit *pitloom_config*, then the
    built-in defaults. Nothing is read from the current directory or from
    the model file's own directory.

    Four parameters apply to one source kind only, and warn when given for
    the other (see :data:`pitloom.core.inert_options.INERT`):
    *offline* and *max_download_bytes* for a Hugging Face source (a local
    file never reaches the network), and *enrich*/*id_registry* for a local
    file; a local folder, its one model file
    (:func:`~pitloom.extract.model_target.model_path_of`).

    A Hugging Face source's metadata files are downloaded as
    :func:`~pitloom.extract.remote.read_huggingface` describes, under the
    policy every remote route resolves
    (:func:`~pitloom.core.config_cascade.resolve_fetch_policy`): with
    *offline* (else *pitloom_config*'s) true nothing is fetched
    (``huggingface.offline``, ``offline-unusable``); each file is capped at
    *max_download_bytes* (else *pitloom_config*'s ``max-download-bytes``,
    else 512 MiB); *check_url* is called with each file's URL and each
    redirect target before it is requested (a local file does not use it).

    *shown* is how messages name a local model file (default: as given): a
    caller that copied it to a temporary directory names it as its user
    knows it (its path in a Git repository). The SBOM names the file by its
    own name alone either way.

    *credentials* (:class:`~pitloom.core.credential_policy.CredentialPolicy`)
    adds to the credentials *pitloom_config* accepts.

    Raises:
        pitloom.messages.CodedTypeError: An argument is of the wrong type
            (a path that is no ``str`` or ``os.PathLike``, a ``bool``
            that is not one): ``option-invalid``, before anything is read.
        CodedValueError: ``pypi-url-unusable``: *source* is a PyPI URL (a
            release is not a model), refused as ``loom model`` refuses it,
            before anything is read or fetched.
        pitloom.messages.CodedFileNotFoundError: *source* is given as empty
            (``input-not-found``).
        pitloom.messages.CodedOSError: The system refused a write
            (``file-unwritable``): the ``-o`` copy at *output_path* (as
            given).
    """
    configure_logging()
    refuse_empty_output(output_path)
    require_path_argument(source, "source")
    _refuse_pypi_url(source)
    refuse_empty_input(source, MODEL_FILE_KIND)
    if max_download_bytes is not None:
        require_download_override(max_download_bytes)  # even if inert
    source_str = str(source)
    is_hf = is_huggingface_source(source_str)
    if is_hf:
        source_str = source_str.strip()
    settle_inert(
        HF if is_hf else MODEL_FILE,
        source_str,
        {
            "offline": offline,
            "enrich": enrich,
            "id_registry": id_registry,
            "max_download_bytes": max_download_bytes,
        },
    )
    cfg = resolve_standalone_config(
        pitloom_config,
        ConfigOverrides(
            provenance=provenance,
            enrich=enrich,
            offline=offline,
            pretty=pretty,
            describe_relationship=describe_relationship,
            max_source_metadata_bytes=max_source_metadata_bytes,
            credentials=credentials,
        ),
    )
    enrichment_results: list[EnrichmentResult] = []

    resolved_registry: IdRegistry | None = None
    if is_hf:
        policy = resolve_fetch_policy(
            pitloom_config,
            offline=offline,
            max_download_bytes=max_download_bytes,
            check_url=check_url,
        )
        model = read_huggingface(source_str, policy=policy)
        entity_spdx_id = digest = None
    else:
        model_path = model_path_of(Path(source), subject=source_str)
        # Resolved before _read_local_model()/run_enrichers() below -- a
        # declared-but-missing/malformed registry should fail fast, never
        # after paying for a model read and enrichment first.
        resolved_registry = resolve_registry(
            id_registry,
            cfg.id_registry,
            None,
            refuse_credentials=cfg.credential_policy.refuse,
        )
        model = _read_local_model(model_path, shown)
        digest = _model_file_digests(model_path)
        entity_spdx_id = _model_registry_id(
            resolved_registry,
            model,
            model_path,
            lambda: None if digest is None else digest.sha256,
        )
        enrichment_results = run_enrichers(model, cfg.enrich, model_path.parent)

    exporter = build_model(
        model,
        creation_metadata or cfg.creation_metadata,
        entity_spdx_id=entity_spdx_id,
        registry=resolved_registry,
        provenance=cfg.provenance,
        enrichment_results=enrichment_results,
        digest=digest,
    )

    sbom_json = exporter.to_json(
        pretty=cfg.pretty,
        describe_relationship=bool(cfg.describe_relationship),
        credentials=cfg.credential_policy,
    )

    write_sbom_output(sbom_json, output_path)

    return sbom_json


# pylint: disable=too-many-arguments,too-many-locals
@checked_bools
def enrich_model(
    source: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    enrich: bool | None = None,
    project_target: Path | str | None = None,
    id_registry: str | Path | IdRegistry | None = None,
    use_lockfile: bool | None = None,
    pitloom_config: PitloomConfig | None = None,
    credentials: CredentialPolicy | None = None,
) -> str:
    """Run enrichment only for a local model file.

    Settings come from the arguments, then an explicit *pitloom_config*,
    then the built-in defaults; nothing is read from the current directory
    or from the model file's directory. The registry is *id_registry*,
    else the explicit config's ``id-registry``; with *project_target*, the
    project's own ``id-registry`` key applies instead, since that project
    is the document the fragment will merge into, and the credentials its
    config accepts join those of *pitloom_config* and *credentials*
    (:class:`~pitloom.core.credential_policy.CredentialPolicy`).

    Raises:
        pitloom.messages.CodedTypeError: An argument is of the wrong type
            (a path that is no ``str`` or ``os.PathLike``, a ``bool``
            that is not one): ``option-invalid``, before anything is read.
        pitloom.messages.CodedFileNotFoundError: *source* is given as empty
            (``input-not-found``).
        pitloom.messages.CodedOSError: The system refused a write
            (``file-unwritable``): the fragment at *output_path* (as
            given).
    """
    configure_logging()
    refuse_empty_output(output_path)
    require_path_argument(source, "source")
    if project_target is not None:
        require_path_argument(project_target, "project_target")
    refuse_empty_input(source, MODEL_FILE_KIND)
    source_str = str(source)
    if is_huggingface_source(source_str):
        raise invalid_value(Parameter("source"), "local-model", got=source_str)
    # The CLI passes use_lockfile through, so this is the one layer that
    # settles it, before any work (an sdist project target as a project).
    if project_target is None:
        settle_inert(ENRICH_STANDALONE, source_str, {"use_lockfile": use_lockfile})
    elif is_sdist_archive(Path(project_target)):
        settle_inert(SDIST, project_target, {"use_lockfile": use_lockfile})
    cfg = resolve_standalone_config(
        pitloom_config, ConfigOverrides(pretty=pretty, credentials=credentials)
    )
    accepted = cfg.credential_policy

    model_path = Path(source)
    # Registry resolved before _read_local_model()/run_enrichers() below -- a
    # declared-but-missing/malformed registry should fail fast, never
    # after paying for a model read and enrichment first.
    if project_target is None:
        base_doc_identity = None
        resolved_registry = resolve_registry(
            id_registry,
            cfg.id_registry,
            None,
            refuse_credentials=accepted.refuse,
        )
    else:
        # The project the fragment merges into, resolved as its base SBOM
        # is: its identity and registry come from the config that SBOM
        # used (an explicit config, else the project's own). Registry
        # resolved right after resolve_project_with_lockfile(), before
        # _doc_identity_of()'s own file walk.
        project_dir = TypedPath(project_target)  # named as given
        base_metadata, base_config, _ = resolve_project_with_lockfile(
            project_dir, use_lockfile, pitloom_config
        )
        # Accepted, but given for the project's SBOM, not this fragment: a
        # fingerprint of them that matches nothing here is not stale.
        accepted = accepted.inheriting(base_config.credential_policy)
        # An sdist's directory is not its project, as in its base SBOM.
        resolved_registry = resolve_registry(
            id_registry,
            base_config.id_registry,
            registry_base_dir(project_dir),
            refuse_credentials=accepted.refuse,
        )
        base_doc_identity = _doc_identity_of(
            project_dir, base_metadata, resolved_registry
        )

    model = _read_local_model(model_path)
    # Calling enrich_model() is itself the opt-in, so the config's enrich
    # setting is no gate here; only an explicit enrich=False turns it off.
    enrich_config = dataclasses.replace(cfg.enrich, local=enrich is not False)
    results = run_enrichers(model, enrich_config, model_path.parent)

    # Hashed only to gate the lookup: the fragment has no ai_AIPackage. The
    # argument is from the current directory, the key from the registry's
    # root (with --project-dir, the project's registry).
    entity_spdx_id = _model_registry_id(
        resolved_registry,
        model,
        model_path,
        functools.partial(_model_file_sha256, model_path),
    )

    exporter = build_enrichment_fragment(
        model,
        results,
        creation_metadata or cfg.creation_metadata,
        entity_spdx_id=entity_spdx_id,
        base_doc_identity=base_doc_identity,
        registry=resolved_registry,
    )

    fragment_json = exporter.to_json(pretty=cfg.pretty, credentials=accepted)

    write_sbom_output(fragment_json, output_path)

    return fragment_json
