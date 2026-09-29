# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deployed SBOM generator for the active installed environment.

See also:
- :mod:`pitloom.assemble._generators_shared` for the helpers shared with the
  other generators.
- :mod:`pitloom.assemble._generators` for the project/sdist generator.
- :mod:`pitloom.assemble._generators_wheel` for the built-wheel generator,
  which resolves its settings the same way.
"""

from __future__ import annotations

from pathlib import Path

from pitloom._sbom_io import write_sbom_output
from pitloom.assemble._generators_shared import _sync_registry
from pitloom.assemble.spdx3.document import build_deployed
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, resolve_standalone_config
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.env import read_environment
from pitloom.id_registry import IdRegistry, resolve_registry
from pitloom.logging_config import configure_logging


# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def generate_env_sbom(
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
    """Generate a Deployed SPDX 3 SBOM for the current installed environment.

    Settings and the registry resolve exactly as
    :func:`~pitloom.assemble.generate_wheel_sbom` describes: arguments, then
    an explicit *pitloom_config*, then the built-in defaults, with nothing
    borrowed from the current directory.

    ``content_type_method`` applies here for one of its two jobs only: it
    steers whether each installed package's originator enrichment fetches a
    remote authors file. The per-file ``contentType`` half needs file
    scanning, which reading an installed environment never performs.
    """
    configure_logging()
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
    # Resolved before the expensive read_environment() call (pipdeptree)
    # below -- a declared-but-missing/malformed registry should fail fast,
    # never after paying for a full environment scan first.
    resolved_registry = resolve_registry(id_registry, cfg.id_registry, Path.cwd())
    project_metadata, env_tree = read_environment()

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or cfg.creation_metadata,
        ai_models=[],
    )
    exporter = build_deployed(
        doc,
        env_tree=env_tree,
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
