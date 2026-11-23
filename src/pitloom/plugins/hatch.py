# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: embeds an SPDX 3 SBOM in the wheel (PEP 770).

See also: :mod:`pitloom.plugins._hatch_base` (the Hatchling base class),
:mod:`pitloom.plugins._hatch_config` (the table's validation) and
:mod:`pitloom.plugins._hatch_document` (the document the SBOM is made from).
"""

from __future__ import annotations

import logging
import os
import tempfile
import weakref
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any, cast

from hatchling.builders.wheel import WheelBuilderConfig
from hatchling.plugin import hookimpl
from packaging.version import Version
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._sbom_io import write_text_lf
from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import PitloomConfig, read_pitloom_config
from pitloom.core.file_names import sbom_file_name
from pitloom.core.inert_options import HOOK, configured_options, settle_inert
from pitloom.core.temp_dirs import check_frame, remove_temp_dir
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.id_registry import resolve_registry
from pitloom.logging_config import configure_logging, error_frame, one_line
from pitloom.messages import (
    HOOK_FRAME,
    HOOK_PREFIX,
    HOOK_STEP_FRAME,
    CodedValueError,
    code_extra_of,
    emit,
    say_summary,
)
from pitloom.messages.build import (
    HOOK_DISABLED_LINE,
    HOOK_EDITABLE_LINE,
    HOOK_NO_EFFECT,
    HOOK_SBOM_STAGED,
)
from pitloom.messages.models import (
    HATCHLING_TOO_OLD_LINE,
    HATCHLING_VERSION_UNKNOWN_LINE,
    LIBRARY_UNUSABLE_HATCHLING,
)
from pitloom.messages.url_credentials import ADVICE_CONFIG, credential_advice
from pitloom.messages.wheel_sboms import sbom_name_conflict
from pitloom.plugins._hatch_base import PitloomBuildHookBase
from pitloom.plugins._hatch_config import validate_config
from pitloom.plugins._hatch_document import (
    build_document_model,
    default_hook_sbom_basename,
)

log = logging.getLogger(__name__)

#: The name prefix of the directory the SBOM is staged in.
_STAGING_PREFIX = "pitloom-hatch-"


#: The first Hatchling that reads build_data["sbom_files"], which this hook
#: uses to place the SBOM at .dist-info/sboms/ (PEP 770). Older Hatchling
#: accepts the mutated build_data and never embeds the file, so the wheel
#: builds with no SBOM and no warning: the version is checked explicitly.
_MIN_HATCHLING_SBOM_VERSION = "1.29.0"


def _check_hatchling_sbom_support() -> None:
    """Raise if the running Hatchling can't embed the SBOM via build_data.

    Raises:
        pitloom.messages.CodedValueError: (a ``ValueError``)
            ``library-unusable/hatchling``: Hatchling's installed version
            can't be determined, or predates
            :data:`_MIN_HATCHLING_SBOM_VERSION`.
    """
    try:
        installed = Version(_pkg_version("hatchling"))
    except PackageNotFoundError as exc:
        raise CodedValueError(
            LIBRARY_UNUSABLE_HATCHLING,
            line=HATCHLING_VERSION_UNKNOWN_LINE,
            minimum_version=_MIN_HATCHLING_SBOM_VERSION,
        ) from exc

    minimum = Version(_MIN_HATCHLING_SBOM_VERSION)
    # Compare release segments only (ignoring pre/dev/post/local qualifiers)
    # so a pre-release or dev build of the minimum version -- which already
    # has the feature -- isn't rejected for sorting below the final release.
    if installed.release < minimum.release:
        raise CodedValueError(
            LIBRARY_UNUSABLE_HATCHLING,
            line=HATCHLING_TOO_OLD_LINE,
            version=str(installed),
            minimum_version=_MIN_HATCHLING_SBOM_VERSION,
        )


def _stage_sbom_file(sbom_json: str, sbom_filename: str) -> tuple[Path, Path]:
    """Write the canonical SBOM to a new temporary staging directory; return
    the directory and the file.

    Not a context manager: the directory must outlive initialize() and be
    removed in finalize(), after the wheel is packaged (or, when Hatchling
    never calls it, by a ``weakref.finalize`` of the hook), by
    :func:`~pitloom.core.temp_dirs.remove_temp_dir`, which never raises
    (``TemporaryDirectory.cleanup()`` raises when a file is still held open
    on Windows, failing a build whose wheel is already written).
    """
    check_frame(HOOK_STEP_FRAME)
    staging_dir = Path(tempfile.mkdtemp(prefix=_STAGING_PREFIX))
    staging_path = staging_dir / sbom_filename
    try:
        write_text_lf(staging_path, sbom_json)
    except BaseException:
        remove_temp_dir(staging_dir, frame=HOOK_STEP_FRAME)
        raise
    return staging_dir, staging_path


class PitloomBuildHook(PitloomBuildHookBase):
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
        self._staging_dir: Path | None = None
        #: The staging directory's removal, run once: by :meth:`finalize`,
        #: else when the hook is collected or the process exits.
        self._remove_staging: Callable[[], object] | None = None

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
            pitloom.messages.CodedValueError: (a ``ValueError``)
                ``library-unusable/hatchling``: the installed Hatchling's
                version can't be determined, or predates 1.29.0 and can't
                embed the SBOM (see :func:`_check_hatchling_sbom_support`).
        """
        # Without this, this process logs with whatever logging config
        # pip/hatchling set up, and lines lack the "WARNING: " prefix.
        configure_logging()
        try:
            # Each ERROR line said while the SBOM is made carries the hook's
            # frame (the configured handler writes it), and a refused URL
            # value names the pyproject.toml list that accepts it.
            with error_frame(HOOK_FRAME.render({})), credential_advice(ADVICE_CONFIG):
                self._generate(version, build_data)
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            # The one place a failure is reported, as the CLI's handler does;
            # the re-raise fails the build, with Hatchling's own traceback.
            # The frame is in the record's own text (what a handler reads), and
            # the hook runs where no command frame is open (its own process).
            log.error(
                "%s%s",
                HOOK_FRAME.render({}),
                one_line(exc),
                extra=code_extra_of(exc),
            )
            raise

    def _generate(self, version: str, build_data: dict[str, Any]) -> None:
        """:meth:`initialize` without its error report."""
        log.debug("%sbuild variant %r", HOOK_PREFIX, version)

        config = dict(self.config)
        validate_config(config)

        if not config.get("enabled", True):
            emit(
                log,
                HOOK_NO_EFFECT,
                logging.INFO,
                line=HOOK_DISABLED_LINE,
                frame=HOOK_STEP_FRAME,
            )
            return

        if self.target_name != "wheel":
            # PEP 770's .dist-info/sboms/ only applies to wheels; sdists
            # have no such convention, so there is nothing to stage.
            emit(
                log,
                HOOK_NO_EFFECT,
                logging.INFO,
                frame=HOOK_STEP_FRAME,
                target=self.target_name,
            )
            return

        if version == "editable":
            # An editable wheel holds a .pth file, not the project's files:
            # the SBOM would list files that are not in it.
            emit(
                log,
                HOOK_NO_EFFECT,
                logging.INFO,
                line=HOOK_EDITABLE_LINE,
                frame=HOOK_STEP_FRAME,
            )
            return

        _check_hatchling_sbom_support()

        project_dir = Path(self.root)
        pitloom_config: PitloomConfig = read_pitloom_config(
            project_dir / "pyproject.toml", source="pyproject.toml"
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
            else f"{default_hook_sbom_basename(self.metadata)}{SPDX3_JSONLD_EXTENSION}"
        )
        self._check_name_is_free(sbom_filename, build_data)

        registry = resolve_registry(
            None,
            pitloom_config.id_registry,
            project_dir,
            refuse_credentials=pitloom_config.credential_policy.refuse,
        )

        document, merkle_root, enrichment_results_by_model = build_document_model(
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
        # The pyproject.toml settings only: url-credentials, accept-url-credentials.
        sbom_json = exporter.to_json(
            pretty=False, credentials=pitloom_config.credential_policy
        )

        staging_dir, sbom_staging_path = _stage_sbom_file(sbom_json, sbom_filename)
        try:
            # Hatchling 1.29.0+ places each path in sbom_files at
            # .dist-info/sboms/<basename> inside the wheel (PEP 770).
            build_data.setdefault("sbom_files", []).append(str(sbom_staging_path))

            say_summary(log, HOOK_SBOM_STAGED, path=sbom_filename, number=merged)
        except Exception:
            # self._staging_dir is assigned only once every step below has
            # succeeded (see finalize()) -- if Hatchling failed to accept
            # build_data or a log handler raised, clean up here ourselves
            # rather than depend on finalize() being called after a failed
            # initialize(), which Hatchling's own hook contract doesn't
            # guarantee.
            remove_temp_dir(staging_dir, frame=HOOK_STEP_FRAME)
            raise

        self._staging_dir = staging_dir
        # Hatchling calls finalize() only after the artifact is built: never
        # with --hooks-only, nor when the build or a later hook fails. The
        # directory is removed when the hook is collected or the process
        # exits all the same.
        self._remove_staging = weakref.finalize(
            self, remove_temp_dir, staging_dir, frame=HOOK_STEP_FRAME
        )

    def _check_name_is_free(
        self, sbom_filename: str, build_data: dict[str, Any]
    ) -> None:
        """Raise unless no SBOM Hatchling will place under ``.dist-info/sboms/``
        is already named *sbom_filename*, ignoring case (the entries of
        ``sbom-files`` and of other hooks): two would be one archive name
        twice, and a case-insensitive extraction (Windows, macOS) writes one
        over the other.

        Raises:
            pitloom.messages.CodedValueError: (a ``ValueError``)
                ``sbom-name-conflict``: One is, typically a ``loom project``
                output of the same default name shipped through
                ``sbom-files``.
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
            raise sbom_name_conflict(sbom_filename, clash)

    def finalize(
        self,
        version: str,
        build_data: dict[str, Any],
        artifact_path: str,
    ) -> None:
        """Remove the temporary staging directory; one that cannot be fully
        removed is one ``WARNING:``, never a failed build. The removal runs
        once: when Hatchling never calls this (``--hooks-only``, a failed
        build), it runs when the hook is collected or the process exits."""
        remove, self._remove_staging = self._remove_staging, None
        self._staging_dir = None
        if remove is not None:
            remove()


@hookimpl
def hatch_register_build_hook() -> type[PitloomBuildHook]:
    """Register ``PitloomBuildHook`` with Hatchling's plugin system."""
    return PitloomBuildHook
