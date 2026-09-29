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
"""

from __future__ import annotations

from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3_bindings

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble._generators_shared import _sync_registry
from pitloom.assemble.spdx3.document import build
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, resolve_standalone_config
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.wheel import read_wheel
from pitloom.id_registry import IdRegistry, resolve_registry
from pitloom.logging_config import configure_logging


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
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
    pitloom_config: PitloomConfig | None = None,
) -> str:
    """Generate an Analyzed SPDX 3 SBOM for a built Python wheel.

    A wheel has no ``[tool.pitloom]`` of its own, and none is borrowed: not
    from the current directory, not from beside the wheel -- either may
    belong to an unrelated project. Settings come from the arguments, then
    *pitloom_config* when the caller names one explicitly, then the built-in
    defaults. The same holds for the registry: *id_registry*, else the explicit
    config's ``id-registry``; no ``loom-id-registry.json`` is searched for.

    An explicit *pitloom_config* applies in full, identity included: its
    creators, creation datetime and comment fill in when *creation_metadata*
    is not given.

    ``extract_file_header``/``content_type``/``enrich`` have no parameter
    here: reading a built wheel scans no file contents and finds no AI
    models (see :data:`pitloom.core.inert_options.INERT`).
    ``content_type_method`` does apply, because it also steers whether
    dependency originator enrichment fetches a remote authors file.
    """
    configure_logging()
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
        ),
    )
    # Resolved before the expensive read_wheel()/find_phantom_dependencies()
    # calls below -- a declared-but-missing/malformed registry should fail
    # fast, never after paying for a full wheel read first.
    resolved_registry = resolve_registry(id_registry, cfg.id_registry, Path.cwd())
    project_metadata, project_files = read_wheel(wheel_path_obj)
    phantom_deps = find_phantom_dependencies(project_files)

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or cfg.creation_metadata,
        ai_models=[],
        phantom_dependencies=phantom_deps,
    )
    exporter = build(
        doc,
        merkle_root=None,
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

    return sbom_json
