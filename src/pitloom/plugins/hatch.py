# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: embeds an SPDX 3 SBOM in the wheel (PEP 770)."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

from pitloom.assemble.spdx3.creation_info import to_spdx3_datetime
from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import PitloomConfig, read_pitloom_config
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.extract.hatchling import metadata_from_hatchling
from pitloom.extract.scanner import scan_project_for_ai_models

log = logging.getLogger(__name__)

_SPDX3_JSON_EXT = ".spdx3.json"


def _build_creation_metadata(pitloom_config: PitloomConfig) -> CreationMetadata:
    """Build creation metadata from ``[tool.pitloom.creation]``.

    Unset fields fall through to :class:`CreationMetadata`'s own defaults --
    no named creator (the assembler emits the ``SoftwareAgent`` "Pitloom")
    and ``creation_tool`` -> ``"Pitloom"`` -- matching the CLI.
    """
    comment = pitloom_config.creation_comment
    kwargs: dict[str, Any] = {
        "creation_comment": (
            comment
            if comment is not None
            else "Generated via Pitloom Hatchling build hook (PEP 770)"
        ),
        "build_datetime": to_spdx3_datetime(datetime.now(timezone.utc)).isoformat(),
    }
    if pitloom_config.creation_creator_name:
        kwargs["creator_name"] = pitloom_config.creation_creator_name
    if pitloom_config.creation_creator_email:
        kwargs["creator_email"] = pitloom_config.creation_creator_email
    if pitloom_config.creation_creator_type:
        kwargs["creator_type"] = pitloom_config.creation_creator_type
    if pitloom_config.creation_creation_tool:
        kwargs["creation_tool"] = pitloom_config.creation_creation_tool
    if pitloom_config.creation_creation_datetime:
        kwargs["creation_datetime"] = pitloom_config.creation_creation_datetime
    return CreationMetadata(**kwargs)


def _build_document_model(
    project_dir: Path,
    hatch_metadata: Any,
    pitloom_config: PitloomConfig,
) -> tuple[DocumentModel, str | None]:
    """Load project metadata and assemble the format-neutral document.

    Project metadata (name, version, dependencies, license, urls, authors)
    comes from Hatchling's own resolved ``hatch_metadata`` -- not from
    re-parsing ``pyproject.toml`` -- so dynamic fields (e.g. a ``hatch-vcs``
    version, or dependencies added by ``hatch-requirements-txt``) are
    correctly reflected in the SBOM.
    """
    metadata = metadata_from_hatchling(hatch_metadata, project_dir)
    creation_metadata = _build_creation_metadata(pitloom_config)
    merkle_root, project_files = get_wheel_files(project_dir)
    metadata.files = project_files
    ai_models = scan_project_for_ai_models(project_dir, project_files)
    document = DocumentModel(
        project=metadata,
        creation_metadata=creation_metadata,
        ai_models=ai_models,
    )
    return document, merkle_root


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
    conforming to PEP 770.  Hatchling 1.28.0+ handles the injection natively
    via ``build_data["sbom_files"]``.

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
        appended to ``build_data["sbom_files"]``, which Hatchling 1.28.0+
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

        project_dir = Path(self.root)
        pitloom_config: PitloomConfig = read_pitloom_config(
            project_dir / "pyproject.toml"
        )
        sbom_basename = pitloom_config.sbom_basename or "sbom"
        sbom_filename: str = f"{sbom_basename}{_SPDX3_JSON_EXT}"

        document, merkle_root = _build_document_model(
            project_dir, self.metadata, pitloom_config
        )

        exporter = assemble_spdx3(document, merkle_root=merkle_root)
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

        # Hatchling 1.28.0+ places each path in sbom_files at
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
    "fragments": "[tool.pitloom.fragments] files",
    "creator-name": "[tool.pitloom.creation] creator-name",
    "creator-email": "[tool.pitloom.creation] creator-email",
    "creator-type": "[tool.pitloom.creation] creator-type",
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
