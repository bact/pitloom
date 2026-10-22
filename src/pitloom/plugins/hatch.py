# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: embeds an SPDX 3 SBOM in the wheel (PEP 770)."""

from __future__ import annotations

import dataclasses
import logging
import os
import tempfile
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.wheel import WheelBuilderConfig
from hatchling.plugin import hookimpl
from packaging.version import Version
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._sbom_io import write_text_lf
from pitloom.assemble.spdx3.creation_info import to_spdx3_datetime
from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import PitloomConfig, read_pitloom_config
from pitloom.core.creation import CreationMetadata, resolve_source_date_epoch
from pitloom.core.document import DocumentModel
from pitloom.core.file_names import sbom_file_name
from pitloom.core.inert_options import HOOK, configured_options, settle_inert
from pitloom.core.models import get_wheel_files
from pitloom.core.project import FilesOrigin
from pitloom.core.quote_source import quote_source
from pitloom.enrich import run_enrichers_for_models
from pitloom.enrich.base import EnrichmentResult
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.project.hatchling import metadata_from_hatchling
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import IdRegistry, registry_file_path, resolve_registry
from pitloom.logging_config import configure_logging, one_line
from pitloom.plugins._hatch_config import validate_config

log = logging.getLogger(__name__)


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
    environment variable, then the current UTC time (with one ``INFO:``
    saying so).  With either of the first two, repeated builds of unchanged
    sources produce byte-identical SBOMs (and therefore byte-identical
    wheels).

    Raises:
        ValueError: ``SOURCE_DATE_EPOCH`` is set and not a valid timestamp
            (see :func:`~pitloom.core.creation.resolve_source_date_epoch`).
    """
    # Read first, so a malformed value fails whether or not a date is pinned.
    epoch_dt = resolve_source_date_epoch()
    if pitloom_config.creation_datetime:
        return pitloom_config.creation_datetime
    if epoch_dt is not None:
        return to_spdx3_datetime(epoch_dt).isoformat()
    log.info(
        "Pitloom build hook: created and builtTime come from the clock; "
        "set SOURCE_DATE_EPOCH or creation-datetime to pin them."
    )
    return to_spdx3_datetime(datetime.now(timezone.utc)).isoformat()


def _build_creation_metadata(pitloom_config: PitloomConfig) -> CreationMetadata:
    """Build creation metadata from ``[[tool.pitloom.creator]]`` /
    ``[[tool.pitloom.creation-tool]]`` / ``[tool.pitloom.creation]``.

    Unset fields take :class:`CreationMetadata`'s defaults, as the CLI does:
    no named creators (the assembler emits the ``SoftwareAgent`` "Pitloom")
    and ``tools`` of ``[Pitloom]``. ``creation-comment`` defaults to a note
    naming the build hook, and ``builtTime`` is
    :func:`_resolve_build_datetime`.
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
    registry: IdRegistry | None,
) -> tuple[DocumentModel, str | None, list[list[EnrichmentResult]]]:
    """Load project metadata and assemble the format-neutral document.

    Project metadata (name, version, dependencies, license, urls, authors)
    comes from Hatchling's own resolved ``hatch_metadata`` -- not from
    re-parsing ``pyproject.toml`` -- so dynamic fields (e.g. a ``hatch-vcs``
    version, or dependencies added by ``hatch-requirements-txt``) are
    correctly reflected in the SBOM.

    Also runs enrichment for each discovered AI model, gated by the
    project's own ``[tool.pitloom] enrich`` (the hook has no key of its own,
    see :func:`~pitloom.plugins._hatch_config.validate_config`), through the same
    ``run_enrichers_for_models()`` call as
    :func:`~pitloom.assemble.generate_project_sbom`, so the hook and
    ``loom project`` enrich a project alike.
    """
    metadata = metadata_from_hatchling(hatch_metadata, project_dir)
    creation_metadata = _build_creation_metadata(pitloom_config)
    # No build_options: the backend is Hatchling, never a build-and-read
    # candidate, so the returned cleanup is a no-op.
    merkle_root, project_files, _cleanup = get_wheel_files(
        project_dir,
        scan_file_headers=pitloom_config.extract_file_header,
        detect_content_type=pitloom_config.content_type.enabled,
        content_type_method=pitloom_config.content_type.method,
        content_type_overrides=pitloom_config.content_type.overrides,
        # Skips get_wheel_files()'s pyproject.toml re-parse and backend
        # detection.
        assume_backend="hatchling",
        exclude_path=registry_file_path(registry),
    )
    _cleanup()
    metadata.files = project_files
    ai_models = scan_project_for_ai_models(
        project_dir,
        project_files,
        scan_usage=pitloom_config.scan_model_usage is True,
        usage_hint=lambda: pitloom_config.scan_model_usage is None,
    )
    phantom_deps = find_phantom_dependencies(project_files)
    enrichment_results_by_model = run_enrichers_for_models(
        ai_models, pitloom_config.enrich, project_dir
    )
    document = DocumentModel(
        project=metadata,
        creation_metadata=creation_metadata,
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
        files_origin=FilesOrigin(project_dir=project_dir),
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
    write_text_lf(staging_path, sbom_json)
    return staging_dir, staging_path


if TYPE_CHECKING:
    # Static shape for type checkers only: the one-parameter interface every
    # supported Hatchling except 1.32.3 declares. The ignore covers 1.32.3's
    # two-parameter shape; "unused-ignore" keeps it silent elsewhere. See
    # _resolve_build_hook_base() below for the base used at runtime.
    class _PitloomBuildHookBase(
        BuildHookInterface[BuilderConfig]  # type: ignore[type-arg, unused-ignore]
    ):
        """Static shape for type checkers -- see :func:`_resolve_build_hook_base`."""

else:
    from hatchling.plugin.manager import PluginManager

    def _resolve_build_hook_base() -> type:
        """Pick the Hatchling ``BuildHookInterface`` base matching the
        installed Hatchling's actual generic arity (see
        working-docs/implementation/hatchling-build-hook.md for why this
        varies by version). ``__parameters__`` is a side-effect-free
        tuple read, so detecting the arity this way can't itself trigger
        the subscription ``TypeError`` it works around.

        Raises:
            RuntimeError: If the arity is neither 1 nor 2.
        """
        param_count = len(BuildHookInterface.__parameters__)
        if param_count == 1:
            return BuildHookInterface[BuilderConfig]
        if param_count == 2:
            return BuildHookInterface[BuilderConfig, PluginManager]
        raise RuntimeError(
            f"{_HATCHLING_ERROR_PREFIX} BuildHookInterface has an "
            f"unexpected number of type parameters ({param_count}); "
            "Pitloom's Hatchling build hook may need updating for this "
            "Hatchling version."
        )

    _PitloomBuildHookBase = _resolve_build_hook_base()


class PitloomBuildHook(_PitloomBuildHookBase):
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
    ``[tool.pitloom] pretty``.  It also ignores ``[tool.pitloom]
    use-lockfile``: lock/pin files are source-stage-only and already excluded
    from the build hook's output (see
    ``hatchling.py::_poetry_fallback_metadata``'s
    ``include_locked_dependencies=False``).
    """

    PLUGIN_NAME = "pitloom"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._staging_dir: tempfile.TemporaryDirectory[str] | None = None

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Generate the SBOM and register it for injection into the wheel.

        Called by Hatchling before packaging.  The staged SBOM path is
        appended to ``build_data["sbom_files"]``, which Hatchling 1.29.0+
        places at ``.dist-info/sboms/<basename>`` inside the wheel
        (PEP 770).  The temporary staging directory is cleaned up in
        :meth:`finalize`.  Any failure is reported once as ``ERROR: SBOM
        generation failed: <reason>`` and then raised, failing the build.
        The ``editable`` variant is skipped with an ``INFO:``.

        Args:
            version: The build *variant* (e.g. ``"standard"``/``"editable"``),
                **not** the project version -- the project version is read
                from ``self.metadata.version``.
            build_data: Mutable build data dict; ``build_data["sbom_files"]``
                is appended to on success.

        Raises:
            ValueError: If a hook configuration value is invalid, the
                ID registry cannot be loaded, ``SOURCE_DATE_EPOCH`` is not a
                valid timestamp, or a project ``sbom-files`` entry has the
                staged SBOM's name.
            FragmentMergeError: If a ``required = true`` SBOM fragment
                (``[tool.pitloom.fragment]``) is missing or unreadable --
                a `ValueError` subclass, propagated uncaught like the
                other config-validation errors above (see
                :func:`pitloom.assemble.spdx3.fragments.merge_fragments`).
            FileNotFoundError: If ``pyproject.toml`` is absent from the
                project root.
            RuntimeError: If the installed Hatchling's version can't be
                determined, or predates 1.29.0 and can't embed the SBOM
                (see :func:`_check_hatchling_sbom_support`).
        """
        # Without this, this process logs with whatever logging config
        # pip/hatchling set up, and lines lack the "WARNING: " prefix.
        configure_logging()
        try:
            self._generate(version, build_data)
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            # The one place a failure is reported, as the CLI's handler does;
            # the re-raise fails the build, with Hatchling's own traceback.
            log.error("SBOM generation failed: %s", one_line(exc))
            raise

    def _generate(self, version: str, build_data: dict[str, Any]) -> None:
        """:meth:`initialize` without its error report."""
        log.debug("Pitloom build hook: build variant %r", version)

        config = dict(self.config)
        validate_config(config)

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

        if version == "editable":
            # An editable wheel holds a .pth file, not the project's files:
            # the SBOM would list files that are not in it.
            log.info(
                "Pitloom build hook: build variant 'editable' skipped; its "
                "wheel does not hold the project's files."
            )
            return

        _check_hatchling_sbom_support()

        project_dir = Path(self.root)
        pitloom_config: PitloomConfig = read_pitloom_config(
            project_dir / "pyproject.toml"
        )
        settle_inert(
            HOOK,
            project_dir,
            configured_options(pitloom_config),
            level=logging.INFO,
        )
        sbom_filename: str = (
            sbom_file_name(pitloom_config.sbom_basename)
            if pitloom_config.sbom_basename
            else f"{_default_sbom_basename(self.metadata)}{SPDX3_JSONLD_EXTENSION}"
        )
        self._check_name_is_free(sbom_filename, build_data)

        registry = resolve_registry(None, pitloom_config.id_registry, project_dir)

        document, merkle_root, enrichment_results_by_model = _build_document_model(
            project_dir, self.metadata, pitloom_config, registry
        )

        exporter = assemble_spdx3(
            document,
            merkle_root=merkle_root,
            sbom_type=spdx3.software_SbomType.build,
            registry=registry,
            enrichment_results_by_model=enrichment_results_by_model,
            **pitloom_config.assemble_options,
        )
        merged = merge_fragments(project_dir, pitloom_config.fragments, exporter)

        # Wheels (and sdists) must always contain a compact, RFC 8785 (JCS)
        # canonical SBOM regardless of the project's [tool.pitloom] pretty
        # setting or any --pretty CLI flag.  Canonicalization is required by
        # the SPDX JSON Serialization Scheme.
        sbom_json = exporter.to_json(pretty=False)

        staging_dir, sbom_staging_path = _stage_sbom_file(sbom_json, sbom_filename)
        try:
            # Hatchling 1.29.0+ places each path in sbom_files at
            # .dist-info/sboms/<basename> inside the wheel (PEP 770).
            build_data.setdefault("sbom_files", []).append(str(sbom_staging_path))

            log.info(
                "Pitloom: staged SBOM %s (%d fragment(s)); "
                "Hatchling will inject it into .dist-info/sboms/ in the wheel.",
                quote_source(sbom_filename),
                merged,
            )
        except Exception:
            # self._staging_dir is assigned only once every step below has
            # succeeded (see finalize()) -- if Hatchling failed to accept
            # build_data or a log handler raised, clean up here ourselves
            # rather than depend on finalize() being called after a failed
            # initialize(), which Hatchling's own hook contract doesn't
            # guarantee.
            staging_dir.cleanup()
            raise

        self._staging_dir = staging_dir

    def _check_name_is_free(
        self, sbom_filename: str, build_data: dict[str, Any]
    ) -> None:
        """Raise unless no SBOM Hatchling will place under ``.dist-info/sboms/``
        is already named *sbom_filename*, ignoring case (the entries of
        ``sbom-files`` and of other hooks): two would be one archive name
        twice, and a case-insensitive extraction (Windows, macOS) writes one
        over the other.

        Raises:
            ValueError: One is, typically a ``loom project`` output of the
                same default name shipped through ``sbom-files``.
        """
        placed = [
            *cast(WheelBuilderConfig, self.build_config).sbom_files,
            *build_data.get("sbom_files", []),
        ]
        wanted = sbom_filename.casefold()
        clash = next(
            (p for p in placed if os.path.basename(p).casefold() == wanted), None
        )
        if clash is not None:
            raise ValueError(
                f"SBOM file name {quote_source(sbom_filename)} is also, ignoring "
                f"case, the name of sbom-files entry {quote_source(clash)}; "
                "set [tool.pitloom] sbom-basename to another name or drop "
                "the entry."
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


@hookimpl
def hatch_register_build_hook() -> type[PitloomBuildHook]:
    """Register ``PitloomBuildHook`` with Hatchling's plugin system."""
    return PitloomBuildHook
