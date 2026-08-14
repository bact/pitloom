# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM assemblers for different output specifications."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom.assemble.spdx3.document import (
    build,
    build_deployed,
    build_enrichment_fragment,
    build_model,
)
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import (
    VALID_CONTENT_TYPE_METHODS,
    PitloomConfig,
    read_pitloom_config,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.models import compute_doc_uuid, get_wheel_files
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import embed_sbom_in_wheel, embed_wheel_sbom
from pitloom.enrich import run_enrichers, run_enrichers_for_models
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract._huggingface import is_huggingface_source, read_huggingface
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.env import read_environment
from pitloom.extract.project import read_project
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.extract.wheel import read_wheel
from pitloom.ids import IdRegistry, resolve_registry


def _require_valid_content_type_method(value: str) -> None:
    """Raise ``ValueError`` unless *value* is a valid content-type method.

    The TOML path (``core/config.py``) and CLI (``choices=``) both already
    validate against this same set; a direct Python API caller passing
    ``content_type_method`` explicitly needs the same guard, or an invalid
    value silently falls through to ``guess_content_type``'s ``"auto"``
    behavior instead of failing loudly.
    """
    if value not in VALID_CONTENT_TYPE_METHODS:
        valid = ", ".join(sorted(VALID_CONTENT_TYPE_METHODS))
        raise ValueError(f"content_type_method must be one of {valid}, got {value!r}")


def _write_output_file(sbom_json: str, output_path: Path | None) -> None:
    """Write SBOM output to file or stdout if output_path is '-'."""
    if output_path is None:
        return
    if str(output_path) == "-":
        sys.stdout.write(sbom_json)
        if not sbom_json.endswith("\n"):
            sys.stdout.write("\n")
    else:
        output_path.write_text(sbom_json, encoding="utf-8")


def _resolve_local_offline_default(directory: Path) -> bool:
    """Read ``[tool.pitloom] offline`` from *directory*'s own
    ``pyproject.toml`` (no ancestor walk-up); falls back to ``False``
    (network attempted) when no such file exists. Mirrors
    :func:`_resolve_model_enrich_config`'s local, non-walking config
    lookup, applied to ``offline`` instead of ``enrich``.
    """
    try:
        return read_pitloom_config(directory / "pyproject.toml").offline
    except FileNotFoundError:
        return False


def _resolve_model_enrich_config(model_dir: Path) -> EnrichConfig:
    """Read ``[tool.pitloom] enrich`` from a ``pyproject.toml`` in
    *model_dir* (the model file's own directory only, no ancestor
    walk-up); falls back to :class:`EnrichConfig` defaults (enrichment
    off) when no such file exists. Shared by ``generate_model_sbom()``
    and ``enrich_model()`` so both resolve a local model's enrichment
    config identically.
    """
    try:
        return read_pitloom_config(model_dir / "pyproject.toml").enrich
    except FileNotFoundError:
        return EnrichConfig()


def _project_doc_identity(project_dir: Path) -> tuple[str, str]:
    """Compute ``(doc_name, doc_uuid)`` for a project directory, identical
    to what ``build()`` (``assemble/spdx3/document.py``) computes for the
    same project when :func:`generate_project_sbom` assembles it.

    Used by :func:`enrich_model`'s ``project_target`` parameter: a
    standalone enrichment fragment needs to predict the *project-level*
    identity a model's ``ai_AIPackage`` will get once embedded in a
    project SBOM -- which is derived from the project's own name/version/
    dependencies/Merkle root, not the model's -- so its references
    resolve correctly once merged. This duplicates ``build()``'s
    ``compute_doc_uuid(...)`` call by necessity (the project document
    doesn't exist yet to ask), not by oversight; keep the two formulas in
    sync if either changes.
    """
    project_metadata, _pitloom_config, _config_path = read_project(project_dir)
    merkle_root, project_files = get_wheel_files(project_dir)
    project_metadata.files = project_files
    doc_uuid = compute_doc_uuid(
        name=project_metadata.name,
        version=project_metadata.version or "unknown",
        dependencies=project_metadata.dependencies,
        merkle_root=merkle_root,
    )
    return project_metadata.name, doc_uuid


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate_project_sbom(
    project_target: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    project_metadata: ProjectMetadata | None = None,
    pitloom_config: PitloomConfig | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
    offline: bool | None = None,
) -> str:
    """Generate a Source SPDX 3 SBOM for a Python project or sdist archive.

    ``enrich``: ``None`` (default) defers to ``[tool.pitloom] enrich``
    (off by default); ``True``/``False`` overrides it for this run, applied
    to every AI model discovered in the project.

    ``extract_file_header``: ``None`` (default) defers to
    ``[tool.pitloom] extract-file-header`` (on by default); ``True``/
    ``False`` overrides it for this run. ``content_type``: ``None``
    (default) defers to ``[tool.pitloom.content-type] enabled`` (off by
    default -- real per-file cost); independently overridable of
    ``extract_file_header``. ``content_type_method``: ``None`` (default)
    defers to ``[tool.pitloom.content-type] method`` (``"auto"`` by
    default); one of ``"auto"``/``"magika"``/``"extension"`` -- an
    explicit invalid value raises ``ValueError`` immediately, matching
    the TOML/CLI paths' own validation. All apply only to a directory
    target (an sdist archive's ``project_files`` come from whatever
    extractor already ran).

    ``offline``: ``None`` (default) defers to ``[tool.pitloom] offline``
    (network attempted, best-effort, by default); ``True``/``False``
    overrides it for this run -- see ``pitloom.assemble.spdx3.document.build``.

    Raises:
        ValueError: If ``content_type_method`` is explicitly passed and
            isn't one of ``"auto"``/``"magika"``/``"extension"``.
    """
    target_path = Path(project_target)
    if project_metadata is None or pitloom_config is None:
        project_metadata, pitloom_config, _ = read_project(target_path)

    effective_pretty: bool = pitloom_config.pretty if pretty is None else pretty
    effective_describe: bool = bool(
        pitloom_config.describe_relationship
        if describe_relationship is None
        else describe_relationship
    )
    effective_provenance: ProvenanceConfig = provenance or pitloom_config.provenance
    effective_enrich_config: EnrichConfig = (
        dataclasses.replace(pitloom_config.enrich, local=enrich)
        if enrich is not None
        else pitloom_config.enrich
    )
    effective_extract_file_header: bool = (
        pitloom_config.extract_file_header
        if extract_file_header is None
        else extract_file_header
    )
    effective_content_type: bool = (
        pitloom_config.content_type.enabled if content_type is None else content_type
    )
    effective_content_type_method: str = (
        pitloom_config.content_type.method
        if content_type_method is None
        else content_type_method
    )
    _require_valid_content_type_method(effective_content_type_method)
    effective_offline: bool = pitloom_config.offline if offline is None else offline

    if target_path.is_file():
        merkle_root = None
        project_files = project_metadata.files
        search_root = target_path.parent
    else:
        merkle_root, project_files = get_wheel_files(
            target_path,
            scan_file_headers=effective_extract_file_header,
            detect_content_type=effective_content_type,
            content_type_method=effective_content_type_method,
            content_type_overrides=pitloom_config.content_type.overrides,
        )
        project_metadata.files = project_files
        search_root = target_path

    ai_models = (
        scan_project_for_ai_models(target_path, project_files)
        if target_path.is_dir()
        else []
    )

    # Run enrichers per discovered model before assembly, so N3/E1/E2 can
    # attach evidence to each model's own AI package.
    enrichment_results_by_model = run_enrichers_for_models(
        ai_models, effective_enrich_config, target_path
    )

    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(search_root / registry)
        if registry is not None
        else resolve_registry(search_root, pitloom_config.ids_file)
    )

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=ai_models,
    )
    exporter = build(
        doc,
        merkle_root=merkle_root,
        sbom_type=spdx3_bindings.software_SbomType.source,
        registry=resolved_registry,
        provenance=effective_provenance,
        enrichment_results_by_model=enrichment_results_by_model,
        offline=effective_offline,
    )

    if target_path.is_dir():
        merge_fragments(target_path, pitloom_config.fragments, exporter)

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate_wheel_sbom(
    wheel_path: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel.

    ``offline``: ``None`` (default) defers to ``[tool.pitloom] offline``
    in the current working directory's ``pyproject.toml`` if one exists
    (network attempted, best-effort, otherwise); ``True``/``False``
    overrides it for this run.
    """
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    wheel_path_obj = Path(wheel_path)
    project_metadata, project_files = read_wheel(wheel_path_obj)
    phantom_deps = find_phantom_dependencies(project_files)

    cwd = Path.cwd()
    effective_offline = (
        _resolve_local_offline_default(cwd) if offline is None else offline
    )
    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(cwd / registry)
        if registry is not None
        else resolve_registry(cwd, None)
    )

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
        phantom_dependencies=phantom_deps,
    )
    exporter = build(
        doc,
        merkle_root=None,
        sbom_type=spdx3_bindings.software_SbomType.analyzed,
        registry=resolved_registry,
        provenance=provenance,
        offline=effective_offline,
    )

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate_model_sbom(
    source: Path | str,
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 AIBOM for a local model file or HF repository.

    ``enrich``: ``None`` (default) defers to ``[tool.pitloom] enrich``
    (off by default); ``True``/``False`` overrides it for this run. Has no
    effect on a Hugging Face source -- local enrichers never run there
    (HF model cards are already parsed natively).

    ``offline``: for a Hugging Face *source*, a hard requirement -- ``None``
    (default) defers to ``[tool.pitloom] offline`` in the current working
    directory's ``pyproject.toml`` if one exists (network attempted,
    best-effort, otherwise); ``True`` (explicit or via config) raises
    ``ValueError`` rather than fetching it, since there's no local
    fallback for a remote-only source. For a local model file, a no-op --
    there's no network path in that case either way. This is a narrower
    contract than ``generate_project_sbom``/``generate_wheel_sbom``'s
    ``offline`` (a soft, always-silent skip of a best-effort PyPI lookup
    that local metadata can already partly cover); the two aren't
    interchangeable despite sharing a name.
    """
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    source_str = str(source)
    is_hf = is_huggingface_source(source_str)
    enrichment_results: list[EnrichmentResult] = []

    if is_hf:
        effective_offline = (
            _resolve_local_offline_default(Path.cwd()) if offline is None else offline
        )
        if effective_offline:
            raise ValueError(
                "Offline mode enabled: cannot fetch remote Hugging Face source "
                f"'{source_str}'"
            )
        model = read_huggingface(source_str)
        entity_spdx_id = None
    else:
        model_path = Path(source)
        model = read_ai_model(model_path)
        resolved_registry = (
            registry
            if isinstance(registry, IdRegistry)
            else IdRegistry.load(Path(registry))
            if registry is not None
            else IdRegistry.find()
        )
        entity_spdx_id = (
            resolved_registry.lookup_entity(model_path.stem, "ai_AIPackage")
            if resolved_registry is not None
            else None
        )

        model_dir = model_path.parent
        enrich_config = _resolve_model_enrich_config(model_dir)
        if enrich is not None:
            enrich_config = dataclasses.replace(enrich_config, local=enrich)
        enrichment_results = run_enrichers(model, enrich_config, model_dir)

    exporter = build_model(
        model,
        creation_metadata or CreationMetadata(),
        entity_spdx_id=entity_spdx_id,
        provenance=provenance,
        enrichment_results=enrichment_results,
    )

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def enrich_model(
    source: Path | str,
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    enrich: bool | None = None,
    project_target: Path | str | None = None,
    registry: str | Path | IdRegistry | None = None,
) -> str:
    """Run enrichment only for a local model file.

    Unlike ``generate_model_sbom``/``generate_project_sbom``, calling this
    is itself the explicit opt-in: ``enrich=True`` (default, same as
    ``None``) always runs enrichment regardless of
    ``[tool.pitloom] enrich`` (a per-source ``false`` would
    otherwise make this command silently write an empty fragment, which
    defeats the purpose of running it directly). Pass ``enrich=False`` to
    suppress it explicitly instead -- e.g. for scripting symmetry with the
    ``--enrich``/``--no-enrich`` flag other commands share -- which
    produces a valid but empty fragment rather than raising.

    ``project_target``: when the fragment is meant to merge into a
    **project**-level base document (``generate_project_sbom()``/the
    Hatchling build hook -- i.e. this model lives inside a larger Python
    project you will later run ``loom project``/``loom generate`` on),
    pass that project's root directory, the same path you'd pass to
    ``loom project``. This resolves the *project's* own doc identity
    (name/version/dependencies/Merkle root, exactly as
    ``generate_project_sbom()`` computes it -- see
    :func:`_project_doc_identity`) so the fragment's referenced
    ``ai_AIPackage`` id matches what the project build will actually
    assign. **Omitting this when the base document is project-level, not
    single-model, produces a fragment referencing an id that does not
    exist in the merged result** -- its ``Annotation``/`Relationship`
    silently become dangling references (see
    ``working-docs/design/sbom-enrichment.md``'s "Surfaces" section).
    Omit ``project_target`` when merging into a single-model
    ``loom model``-generated base document instead.

    ``registry``: resolved the same way ``generate_model_sbom()``/
    ``generate_project_sbom()`` resolve it (an explicit
    :class:`~pitloom.ids.IdRegistry`, a path to one, or the default
    discovered via :meth:`~pitloom.ids.IdRegistry.find`), so a
    registry-pinned ``ai_AIPackage`` id is referenced correctly too, not
    just the freshly computed one.

    Returns a standalone SPDX 3 fragment (a bare ``@graph``, no
    ``SpdxDocument``/``software_Sbom`` wrapper) containing just what the
    enrichment run found: N3 CreationInfo(s), any newly-created dataset
    elements, and the E1/E2 "enrichment" Annotation. Register the fragment
    under ``[tool.pitloom.fragment]`` and re-run ``loom project``/
    ``loom generate`` to merge it into a base SBOM (see
    ``working-docs/design/sbom-fragments.md``).

    Hugging Face sources are rejected: HF model cards already get YAML
    frontmatter parsed natively when the SBOM is generated
    (:func:`~pitloom.extract._huggingface.read_huggingface`), so there is
    nothing for a local enrichment run to add there.
    """
    effective_pretty = False if pretty is None else pretty
    source_str = str(source)
    if is_huggingface_source(source_str):
        raise ValueError(
            f"'{source_str}' is a Hugging Face source; local enrichment "
            "does not apply there -- Hugging Face model cards are already "
            "parsed natively when generating the SBOM."
        )

    model_path = Path(source)
    model = read_ai_model(model_path)
    model_dir = model_path.parent
    enrich_config = dataclasses.replace(
        _resolve_model_enrich_config(model_dir), local=enrich is not False
    )
    results = run_enrichers(model, enrich_config, model_dir)

    base_doc_identity = (
        _project_doc_identity(Path(project_target))
        if project_target is not None
        else None
    )
    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(Path(registry))
        if registry is not None
        else IdRegistry.find()
    )
    entity_spdx_id = (
        resolved_registry.lookup_entity(model_path.stem, "ai_AIPackage")
        if resolved_registry is not None
        else None
    )

    exporter = build_enrichment_fragment(
        model,
        results,
        creation_metadata or CreationMetadata(),
        entity_spdx_id=entity_spdx_id,
        base_doc_identity=base_doc_identity,
    )

    fragment_json = exporter.to_json(pretty=effective_pretty)

    _write_output_file(fragment_json, output_path)

    return fragment_json


def generate_env_sbom(
    *,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    offline: bool | None = None,
) -> str:
    """Generate a Deployed SPDX 3 SBOM for the current installed environment.

    ``offline``: ``None`` (default) defers to ``[tool.pitloom] offline``
    in the current working directory's ``pyproject.toml`` if one exists
    (network attempted, best-effort, otherwise); ``True``/``False``
    overrides it for this run.
    """
    effective_pretty = False if pretty is None else pretty
    effective_describe = (
        False if describe_relationship is None else describe_relationship
    )
    project_metadata, env_tree = read_environment()

    cwd = Path.cwd()
    effective_offline = (
        _resolve_local_offline_default(cwd) if offline is None else offline
    )
    resolved_registry = (
        registry
        if isinstance(registry, IdRegistry)
        else IdRegistry.load(cwd / registry)
        if registry is not None
        else resolve_registry(cwd, None)
    )

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=[],
    )
    exporter = build_deployed(
        doc,
        env_tree=env_tree,
        registry=resolved_registry,
        provenance=provenance,
        offline=effective_offline,
    )

    sbom_json = exporter.to_json(
        pretty=effective_pretty,
        describe_relationship=effective_describe,
    )

    _write_output_file(sbom_json, output_path)

    return sbom_json


def generate(
    target: Path | str = ".",
    *,
    offline: bool | None = None,
    output_path: Path | None = None,
    creation_metadata: CreationMetadata | None = None,
    pretty: bool | None = None,
    describe_relationship: bool | None = None,
    registry: str | Path | IdRegistry | None = None,
    provenance: ProvenanceConfig | None = None,
    enrich: bool | None = None,
    extract_file_header: bool | None = None,
    content_type: bool | None = None,
    content_type_method: str | None = None,
) -> str:
    """Smart unified entrypoint for generating SPDX 3 SBOMs across all target types.

    ``enrich`` is forwarded to ``generate_model_sbom``/``generate_project_sbom``
    only -- the environment and wheel targets have no enrichment to run.
    ``extract_file_header``/``content_type``/``content_type_method`` are
    forwarded to ``generate_project_sbom`` only (v1 scope -- see that
    function's docstring); a no-op elsewhere.

    ``offline``: forwarded as-is to whichever sub-generator the target
    resolves to; ``None`` (default) defers to that sub-generator's own
    ``[tool.pitloom] offline`` lookup -- see each one's docstring for the
    exact directory it reads from.
    """
    target_str = str(target).strip()

    if target_str.lower() in ("env", "environment", "--env"):
        return generate_env_sbom(
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
            provenance=provenance,
            offline=offline,
        )

    if target_str.lower().endswith(".whl"):
        return generate_wheel_sbom(
            target_str,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
            provenance=provenance,
            offline=offline,
        )

    if is_huggingface_source(target_str):
        return generate_model_sbom(
            target_str,
            offline=offline,
            output_path=output_path,
            creation_metadata=creation_metadata,
            pretty=pretty,
            describe_relationship=describe_relationship,
            registry=registry,
            provenance=provenance,
            enrich=enrich,
        )

    target_path = Path(target)
    if target_path.is_file():
        name_lower = target_path.name.lower()
        if any(
            name_lower.endswith(ext)
            for ext in (
                ".gguf",
                ".safetensors",
                ".onnx",
                ".pt",
                ".pth",
                ".h5",
                ".hdf5",
                ".keras",
                ".npy",
                ".npz",
                ".bin",
                ".ftz",
            )
        ):
            return generate_model_sbom(
                target_path,
                offline=offline,
                output_path=output_path,
                creation_metadata=creation_metadata,
                pretty=pretty,
                describe_relationship=describe_relationship,
                registry=registry,
                provenance=provenance,
                enrich=enrich,
            )

    return generate_project_sbom(
        target_path,
        output_path=output_path,
        creation_metadata=creation_metadata,
        pretty=pretty,
        describe_relationship=describe_relationship,
        registry=registry,
        provenance=provenance,
        enrich=enrich,
        extract_file_header=extract_file_header,
        content_type=content_type,
        content_type_method=content_type_method,
        offline=offline,
    )


__all__ = [
    "ProvenanceConfig",
    "embed_sbom_in_wheel",
    "embed_wheel_sbom",
    "enrich_model",
    "generate",
    "generate_env_sbom",
    "generate_model_sbom",
    "generate_project_sbom",
    "generate_wheel_sbom",
    "merge_fragments",
]
