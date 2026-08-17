# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: embeds an SPDX 3 SBOM in the wheel (PEP 770)."""

from __future__ import annotations

import dataclasses
import logging
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl
from packaging.version import Version
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.creation_info import to_spdx3_datetime
from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import PitloomConfig, read_pitloom_config
from pitloom.core.creation import CreationMetadata, resolve_source_date_epoch
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.enrich import run_enrichers_for_models
from pitloom.enrich.base import EnrichmentResult
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.hatchling import metadata_from_hatchling
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.ids import resolve_registry

log = logging.getLogger(__name__)

_SPDX3_JSON_EXT = ".spdx3.json"

#: Hatchling only started reading build_data["sbom_files"] -- the mechanism
#: this hook relies on to place a build-time-generated SBOM at
#: .dist-info/sboms/ -- in this release (PEP 770). Older Hatchling accepts
#: the mutated build_data silently and never embeds the file, so the wheel
#: builds "successfully" with no SBOM and no warning; this must therefore be
#: checked explicitly rather than left to fail silently.
_MIN_HATCHLING_SBOM_VERSION = "1.29.0"

#: Shared prefix for every _check_hatchling_sbom_support() error, so both
#: failure modes are easy to grep/filter for as one family of error.
_HATCHLING_ERROR_PREFIX = "Pitloom build hook: Hatchling"


def _check_hatchling_sbom_support() -> None:
    """Raise if the running Hatchling can't embed the SBOM via build_data.

    Raises:
        RuntimeError: If Hatchling's installed version can't be determined,
            or predates :data:`_MIN_HATCHLING_SBOM_VERSION`.
    """
    try:
        installed = Version(_pkg_version("hatchling"))
    except PackageNotFoundError as exc:
        raise RuntimeError(
            f"{_HATCHLING_ERROR_PREFIX} version unknown (no package metadata "
            f"found); requires >= {_MIN_HATCHLING_SBOM_VERSION} for PEP 770 "
            "SBOM embedding."
        ) from exc

    minimum = Version(_MIN_HATCHLING_SBOM_VERSION)
    # Compare release segments only (ignoring pre/dev/post/local qualifiers)
    # so a pre-release or dev build of the minimum version -- which already
    # has the feature -- isn't rejected for sorting below the final release.
    if installed.release < minimum.release:
        raise RuntimeError(
            f"{_HATCHLING_ERROR_PREFIX} {installed} too old for PEP 770 SBOM "
            f"embedding (requires >= {_MIN_HATCHLING_SBOM_VERSION}); "
            "upgrade Hatchling."
        )


def _resolve_build_datetime(pitloom_config: PitloomConfig) -> str:
    """Resolve the ``builtTime`` stamped on the main package.

    Priority: a pinned ``[tool.pitloom.creation]`` ``creation-datetime``
    (a deliberate, explicit pin -- more specific than an ambient env var,
    so it wins), then the standard reproducible-builds ``SOURCE_DATE_EPOCH``
    environment variable, then the current UTC time.  With either of the
    first two, repeated builds of unchanged sources produce byte-identical
    SBOMs (and therefore byte-identical wheels).
    """
    if pitloom_config.creation_datetime:
        return pitloom_config.creation_datetime
    epoch_dt = resolve_source_date_epoch()
    if epoch_dt is not None:
        return to_spdx3_datetime(epoch_dt).isoformat()
    return to_spdx3_datetime(datetime.now(timezone.utc)).isoformat()


def _build_creation_metadata(pitloom_config: PitloomConfig) -> CreationMetadata:
    """Build creation metadata from ``[[tool.pitloom.creator]]`` /
    ``[[tool.pitloom.creation-tool]]`` / ``[tool.pitloom.creation]``.

    Unset fields fall through to :class:`CreationMetadata`'s own defaults --
    no named creators (the assembler emits the ``SoftwareAgent`` "Pitloom")
    and ``tools`` -> ``[Pitloom]`` -- matching the CLI.
    """
    comment = pitloom_config.creation_comment
    return dataclasses.replace(
        pitloom_config.creation_metadata,
        creation_comment=(
            comment
            if comment is not None
            else "Generated via Pitloom Hatchling build hook (PEP 770)"
        ),
        build_datetime=_resolve_build_datetime(pitloom_config),
    )


def _build_document_model(
    project_dir: Path,
    hatch_metadata: Any,
    pitloom_config: PitloomConfig,
) -> tuple[DocumentModel, str | None, list[list[EnrichmentResult]]]:
    """Load project metadata and assemble the format-neutral document.

    Project metadata (name, version, dependencies, license, urls, authors)
    comes from Hatchling's own resolved ``hatch_metadata`` -- not from
    re-parsing ``pyproject.toml`` -- so dynamic fields (e.g. a ``hatch-vcs``
    version, or dependencies added by ``hatch-requirements-txt``) are
    correctly reflected in the SBOM.

    Also runs enrichment for each discovered AI model, gated by the
    project's own ``[tool.pitloom] enrich`` (no separate hook-level key,
    same "one config surface" rule ``_validate_config`` already enforces
    for creator/tool/fragment settings) -- uses the same
    ``run_enrichers_for_models()`` helper ``generate_project_sbom()``
    (``src/pitloom/assemble/__init__.py``) does, so the build hook
    produces the same N3/E1/E2 artifacts ``loom project`` would for the
    same project.
    """
    metadata = metadata_from_hatchling(hatch_metadata, project_dir)
    creation_metadata = _build_creation_metadata(pitloom_config)
    merkle_root, project_files = get_wheel_files(
        project_dir,
        scan_file_headers=pitloom_config.extract_file_header,
        detect_content_type=pitloom_config.content_type.enabled,
        content_type_method=pitloom_config.content_type.method,
        content_type_overrides=pitloom_config.content_type.overrides,
    )
    metadata.files = project_files
    ai_models = scan_project_for_ai_models(project_dir, project_files)
    phantom_deps = find_phantom_dependencies(project_files)
    enrichment_results_by_model = run_enrichers_for_models(
        ai_models, pitloom_config.enrich, project_dir
    )
    document = DocumentModel(
        project=metadata,
        creation_metadata=creation_metadata,
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
    )
    return document, merkle_root, enrichment_results_by_model


def _default_sbom_basename(hatch_metadata: Any) -> str:
    """Derive the default embedded-SBOM basename from package name/version.

    The final wheel filename's platform/ABI/Python tags aren't resolved
    yet at hook ``initialize()`` time, so this can't reproduce the exact
    wheel filename -- only ``<name>-<version>``, matching what ``loom
    project``'s own default (``_resolve_output_path``) uses.
    """
    name = hatch_metadata.core.raw_name
    version = str(hatch_metadata.version) if hatch_metadata.version else None
    return f"{name}-{version}" if version else name


def _stage_sbom_file(
    sbom_json: str, sbom_filename: str
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Write the canonical SBOM to a temporary staging location."""
    # Not used as a context manager: the directory must outlive initialize()
    # and be cleaned up in finalize() after the wheel is packaged.
    # pylint: disable=consider-using-with

    staging_dir = tempfile.TemporaryDirectory()  # noqa: SIM115
    staging_path = Path(staging_dir.name) / sbom_filename
    staging_path.write_text(sbom_json, encoding="utf-8")
    return staging_dir, staging_path


class PitloomBuildHook(BuildHookInterface[BuilderConfig]):
    """Hatchling build hook that embeds an SPDX 3 SBOM in the wheel.

    Activated by adding ``[tool.hatch.build.hooks.pitloom]`` to the project's
    ``pyproject.toml`` and listing ``pitloom`` as a build dependency.

    The SBOM is written to ``.dist-info/sboms/<filename>`` inside the wheel,
    conforming to PEP 770.  Hatchling 1.29.0+ handles the injection natively
    via ``build_data["sbom_files"]``; older Hatchling is rejected outright
    (see :func:`_check_hatchling_sbom_support`) rather than silently
    producing a wheel with no SBOM.

    ``[tool.hatch.build.hooks.pitloom]`` controls only whether the hook runs:

    .. code-block:: toml

        [tool.hatch.build.hooks.pitloom]
        enabled = true   # set to false to skip SBOM generation

    Basename, fragments, and creator/tool metadata are read from
    ``[tool.pitloom]`` / ``[tool.pitloom.creation]`` -- the same settings the
    CLI uses -- so there is one place to configure them for both.  The hook
    always emits compact, RFC 8785 (JCS) canonical JSON, ignoring
    ``[tool.pitloom] pretty``.
    """

    PLUGIN_NAME = "pitloom"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._staging_dir: tempfile.TemporaryDirectory[str] | None = None
        self._sbom_staging_path: Path | None = None
        self._sbom_filename: str = f"sbom{_SPDX3_JSON_EXT}"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Generate the SBOM and register it for injection into the wheel.

        Called by Hatchling before packaging.  The staged SBOM path is
        appended to ``build_data["sbom_files"]``, which Hatchling 1.29.0+
        places at ``.dist-info/sboms/<basename>`` inside the wheel
        (PEP 770).  The temporary staging directory is cleaned up in
        :meth:`finalize`.

        Args:
            version: The build *variant* (e.g. ``"standard"``/``"editable"``),
                **not** the project version -- the project version is read
                from ``self.metadata.version``.
            build_data: Mutable build data dict; ``build_data["sbom_files"]``
                is appended to on success.

        Raises:
            ValueError: If a hook configuration value has an invalid type
                or is otherwise invalid.
            FileNotFoundError: If ``pyproject.toml`` is absent from the
                project root.
            RuntimeError: If the installed Hatchling's version can't be
                determined, or predates 1.29.0 and can't embed the SBOM
                (see :func:`_check_hatchling_sbom_support`).
        """
        log.debug("Pitloom build hook: build variant %r", version)

        config = dict(self.config)
        _validate_config(config)

        if not config.get("enabled", True):
            log.info("Pitloom build hook: disabled; skipping SBOM generation.")
            return

        if self.target_name != "wheel":
            # PEP 770's .dist-info/sboms/ only applies to wheels; sdists
            # have no such convention, so there is nothing to stage.
            log.info(
                "Pitloom build hook: target %r is not 'wheel'; "
                "skipping SBOM generation.",
                self.target_name,
            )
            return

        _check_hatchling_sbom_support()

        project_dir = Path(self.root)
        pitloom_config: PitloomConfig = read_pitloom_config(
            project_dir / "pyproject.toml"
        )
        sbom_basename = pitloom_config.sbom_basename or _default_sbom_basename(
            self.metadata
        )
        sbom_filename: str = f"{sbom_basename}{_SPDX3_JSON_EXT}"

        document, merkle_root, enrichment_results_by_model = _build_document_model(
            project_dir, self.metadata, pitloom_config
        )
        registry = resolve_registry(project_dir, pitloom_config.ids_file)

        exporter = assemble_spdx3(
            document,
            merkle_root=merkle_root,
            sbom_type=spdx3.software_SbomType.build,
            registry=registry,
            provenance=pitloom_config.provenance,
            enrichment_results_by_model=enrichment_results_by_model,
            offline=pitloom_config.offline,
        )
        merge_fragments(project_dir, pitloom_config.fragments, exporter)

        # Wheels (and sdists) must always contain a compact, RFC 8785 (JCS)
        # canonical SBOM regardless of the project's [tool.pitloom] pretty
        # setting or any --pretty CLI flag.  Canonicalization is required by
        # the SPDX JSON Serialization Scheme.
        sbom_json = exporter.to_json(pretty=False)

        self._sbom_filename = sbom_filename
        self._staging_dir, self._sbom_staging_path = _stage_sbom_file(
            sbom_json, sbom_filename
        )

        # Hatchling 1.29.0+ places each path in sbom_files at
        # .dist-info/sboms/<basename> inside the wheel (PEP 770).
        build_data.setdefault("sbom_files", []).append(str(self._sbom_staging_path))

        log.info(
            "Pitloom: staged SBOM %s (%d fragment(s)); "
            "Hatchling will inject it into .dist-info/sboms/ in the wheel.",
            sbom_filename,
            len(pitloom_config.fragments),
        )

    def finalize(
        self,
        version: str,
        build_data: dict[str, Any],
        artifact_path: str,
    ) -> None:
        """Clean up the temporary staging directory."""
        if self._staging_dir is not None:
            self._staging_dir.cleanup()
            self._staging_dir = None
            self._sbom_staging_path = None


#: Keys that moved to [tool.pitloom] / [tool.pitloom.creation] -- one source
#: of truth shared with the CLI -- mapped to their new location.
_MOVED_KEYS = {
    "sbom-basename": "[tool.pitloom] sbom-basename",
    "fragments": "[tool.pitloom.fragment] files",
    "creator-name": "[[tool.pitloom.creator]] (key: name)",
    "creator-email": "[[tool.pitloom.creator]] (key: email)",
    "creator-type": "[[tool.pitloom.creator]] (key: type)",
    "creation-tool": "[[tool.pitloom.creation-tool]] (key: name)",
}


def _validate_config(config: dict[str, Any]) -> None:
    """Validate ``[tool.hatch.build.hooks.pitloom]`` configuration values.

    This section controls only whether the hook runs (``enabled``); all
    other settings live in ``[tool.pitloom]`` / ``[tool.pitloom.creation]``.

    Raises:
        ValueError: If ``enabled`` has an unexpected type, a moved key is
            still present here, or an unknown key is present.
    """
    section = "[tool.hatch.build.hooks.pitloom]"

    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(
            f"{section} 'enabled' must be a boolean (true/false), "
            f"got {type(enabled).__name__!r}."
        )

    for key, new_location in _MOVED_KEYS.items():
        if key in config:
            raise ValueError(
                f"{section} {key!r} is no longer supported here; "
                f"set it under {new_location} instead."
            )

    unknown = set(config) - {"enabled", *_MOVED_KEYS}
    if unknown:
        raise ValueError(
            f"{section} unknown key(s): {sorted(unknown)!r}. "
            "Only 'enabled' is supported; all other SBOM settings live in "
            "[tool.pitloom] / [tool.pitloom.creation]."
        )


@hookimpl
def hatch_register_build_hook() -> type[PitloomBuildHook]:
    """Register ``PitloomBuildHook`` with Hatchling's plugin system."""
    return PitloomBuildHook
