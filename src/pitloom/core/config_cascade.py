# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one configuration cascade every SBOM-producing surface resolves through.

Pitloom is invoked from several surfaces (CLI subcommands, the library API,
the Hatchling build hook, the GitHub Action). A surface resolving
``[tool.pitloom]`` and its per-run overrides itself is what lets a setting
reach the assembler only where a call site remembers to pass it. The shared
pieces live here so that no surface has to:

- :func:`load_config_file` -- read an explicitly named config file.
- :func:`apply_overrides` -- layer one run's explicit choices on top.

The precedence is: per-run override > an explicitly named config
(``--config``/``pitloom_config=``) > the target project's own
``[tool.pitloom]`` > hardcoded default. Only a *project* target (a project
directory, an sdist, ``embed-wheel --project-dir``, the Hatchling hook) has a
config of its own; a wheel, an installed environment or a model file never
borrows one from the current directory or from its own location, since
either may belong to an unrelated project. Adding a setting means one
:class:`~pitloom.core.config.PitloomConfig` field, one
:class:`ConfigOverrides` field and one line in :func:`apply_overrides`.

:mod:`pitloom.plugins.hatch` still reads and splats its project's config by
its own route (``PitloomConfig.assemble_options``); it has no per-run
overrides to layer.

No leading underscore: imported from outside ``pitloom.core`` (see AGENTS.md
"Naming"). This module must never import from ``pitloom.assemble`` or
``pitloom.embed`` -- the dependency runs one way, and a cycle here would be
imported by every surface at once.

See also: :attr:`~pitloom.core.config.PitloomConfig.assemble_options`, the
matching hand-off from a resolved config into the assemblers.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path
from typing import Any

from pitloom._toml_io import load_toml_file
from pitloom.core._config_types import _require_valid_content_type_method
from pitloom.core.build_options import BuildOptions
from pitloom.core.config import PitloomConfig, parse_pitloom_config
from pitloom.core.no_effect import INERT_LOG_PREFIX
from pitloom.core.provenance import ProvenanceConfig, require_max_source_metadata_bytes

log = logging.getLogger(__name__)

__all__ = [
    "ConfigOverrides",
    "apply_overrides",
    "load_config_file",
    "resolve_standalone_config",
]


@dataclasses.dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes
class ConfigOverrides:
    """Per-run overrides layered onto a project's ``[tool.pitloom]`` config.

    Every field defaults to ``None``, meaning "not given, defer to the
    config"; any other value wins, including one equal to the built-in
    default. Each maps to the ``PitloomConfig`` field of the same name,
    except ``enrich`` -> ``enrich_local`` and ``content_type`` ->
    ``content_type_enabled``.

    Attributes:
        provenance: Replaces the config's whole provenance settings, not
            field by field: a field left at its default resets the
            config's value.
        max_source_metadata_bytes: Overrides that one provenance field and
            leaves the others as the config (or ``provenance``) set them.
            Applied after ``provenance``, so it wins over that object's own
            value. Checked by
            :func:`~pitloom.core.provenance.require_max_source_metadata_bytes`:
            ``0`` or at least 8, else ``ValueError``.
        pretty: The embed path (``embed_wheel_sbom(overrides=...)``)
            always writes JCS-canonical JSON and warns that a given value
            has no effect, as it does for ``describe_relationship`` and
            ``update_id_registry`` (see
            :data:`pitloom.core.inert_options.INERT`).
        trust_wheel_model: ``--trust-wheel-model``: read a wheel's AI model
            files with every format reader, including those gated in a wheel. Like
            ``build_options``, no ``[tool.pitloom]`` cascade (a config must
            not opt in) and :func:`apply_overrides` never touches it; only a
            standalone wheel embed reads it, and any other embed warns.
        build_options: ``--allow-build`` and its companion flags (see
            :class:`~pitloom.core.build_options.BuildOptions`). Unlike
            every other field here, deliberately has no
            ``[tool.pitloom]`` cascade to defer to, and is read by
            ``embed-wheel`` alone -- :func:`apply_overrides` never touches
            it, and ``generate_project_sbom()`` takes its own separate
            ``build_options`` parameter rather than reading this one.
            Threaded into
            ``_build_sbom_from_project_and_wheel()``'s own project-dir
            rescan, whose only use for the resulting file list is
            layering content-type/file-header extras onto the wheel's
            already-known files (see that function's own comment on
            discarding the rescan's ``merkle_root``/digests) -- so on a
            project whose backend has no static discovery module (or
            whose static discovery fails), enabling this runs a full,
            real, potentially slow PEP 517 build *purely* to compute
            those extras more accurately, not to learn the file list
            itself (the wheel's own ``read_wheel()`` result already has
            that). Deliberate: this is the only way ``embed-wheel``
            avoids silently staying stuck on the Hatchling-heuristic
            rescan for such a project's content-type/header extras.
    """

    provenance: ProvenanceConfig | None = None
    enrich: bool | None = None
    extract_file_header: bool | None = None
    scan_model_usage: bool | None = None
    content_type: bool | None = None
    content_type_method: str | None = None
    offline: bool | None = None
    pretty: bool | None = None
    describe_relationship: bool | None = None
    update_id_registry: bool | None = None
    max_source_metadata_bytes: int | None = None
    trust_wheel_model: bool | None = None
    build_options: BuildOptions = BuildOptions()


def load_config_file(path: Path) -> PitloomConfig:
    """Read ``[tool.pitloom]`` from an explicitly named config file.

    Unlike a target project's own config, a file the user named is a source
    that claimed to carry settings, so every failure raises instead of
    degrading to defaults. A relative ``id-registry`` or fragment path
    resolves against the file's own directory, so the config means the same
    thing whatever directory Pitloom runs from (as a project's own
    ``pyproject.toml`` already does).

    A file with no ``[tool.pitloom]`` table gives the defaults and one
    ``WARNING:``, since a wrong path would otherwise pass unnoticed. A
    relative ``id-registry`` resolves against the directory *path* names, not
    that of a symbolic link's target.

    Raises:
        FileNotFoundError: *path* is not a regular file (missing, or a
            directory). ``os.path.isfile`` never raises, on any Python
            version (see AGENTS.md on ``Path.exists()``).
        ValueError: the file is not UTF-8, not valid TOML, or its settings
            are invalid (a wrong value or a wrong table shape); the message
            names *path*.
        OSError: the file cannot be read.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"config file not found or not a file: {path}")
    try:
        data = load_toml_file(Path(path))
        cfg = parse_pitloom_config(data, source=str(path))
    except ValueError as exc:  # also TOMLDecodeError, UnicodeDecodeError
        raise ValueError(f"config file {path}: {exc}") from exc
    tool = data.get("tool")
    if not isinstance(tool, dict) or not isinstance(tool.get("pitloom"), dict):
        log.warning(
            "%s%s: --config file has no [tool.pitloom] table; using the defaults",
            INERT_LOG_PREFIX,
            path,
        )
    # Every relative path in the file means the same thing wherever
    # Pitloom runs: it resolves against the file's own directory.
    config_dir = Path(path).absolute().parent
    if cfg.id_registry is not None and not Path(cfg.id_registry).is_absolute():
        cfg = dataclasses.replace(cfg, id_registry=str(config_dir / cfg.id_registry))
    return dataclasses.replace(
        cfg,
        fragments=[
            dataclasses.replace(fragment, base_dir=str(config_dir))
            for fragment in cfg.fragments
        ],
    )


def apply_overrides(cfg: PitloomConfig, overrides: ConfigOverrides) -> PitloomConfig:
    """Layer one run's explicit overrides onto *cfg*.

    A field left ``None`` defers to *cfg*; anything else wins, including a
    value that happens to equal the built-in default (``0``/``False`` are
    explicit choices, not absences -- see AGENTS.md's ``None`` vs empty
    tri-state rule).

    Raises:
        ValueError: if the *resulting* content-type method is not one of
            :data:`~pitloom.core.config.VALID_CONTENT_TYPE_METHODS`. The
            effective value is what gets checked, not just the override, so
            a hand-built :class:`~pitloom.core.config.PitloomConfig` cannot
            smuggle an invalid method past a caller that overrode nothing.
    """
    changes: dict[str, Any] = {}
    if overrides.provenance is not None:
        # Every ProvenanceConfig field maps to PitloomConfig.provenance_<name>;
        # a field without one fails in dataclasses.replace() below, never
        # silently. Fields are read from the class, so a subclass's extras
        # are ignored.
        for prov_field in dataclasses.fields(ProvenanceConfig):
            changes[f"provenance_{prov_field.name}"] = getattr(
                overrides.provenance, prov_field.name
            )
    if overrides.enrich is not None:
        changes["enrich_local"] = overrides.enrich
    if overrides.extract_file_header is not None:
        changes["extract_file_header"] = overrides.extract_file_header
    if overrides.scan_model_usage is not None:
        changes["scan_model_usage"] = overrides.scan_model_usage
    if overrides.content_type is not None:
        changes["content_type_enabled"] = overrides.content_type
    if overrides.content_type_method is not None:
        changes["content_type_method"] = overrides.content_type_method
    if overrides.offline is not None:
        changes["offline"] = overrides.offline
    if overrides.pretty is not None:
        changes["pretty"] = overrides.pretty
    if overrides.describe_relationship is not None:
        changes["describe_relationship"] = overrides.describe_relationship
    if overrides.update_id_registry is not None:
        changes["update_id_registry"] = overrides.update_id_registry
    if overrides.max_source_metadata_bytes is not None:
        changes["provenance_max_source_metadata_bytes"] = (
            require_max_source_metadata_bytes(overrides.max_source_metadata_bytes)
        )
    merged = dataclasses.replace(cfg, **changes)
    _require_valid_content_type_method(merged.content_type_method)
    return merged


def resolve_standalone_config(
    pitloom_config: PitloomConfig | None, overrides: ConfigOverrides
) -> PitloomConfig:
    """The config for a target with no project of its own (a wheel, an
    installed environment, a model file, a wheel embedded without a project
    directory).

    Only explicit sources apply: *overrides*, then *pitloom_config* (an
    explicitly named config), then the built-in defaults. Nothing is read
    from the current directory or from beside the target -- either may
    belong to an unrelated project.
    """
    return apply_overrides(pitloom_config or PitloomConfig(), overrides)
