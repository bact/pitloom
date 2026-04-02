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

from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import get_wheel_files
from pitloom.extract.pyproject import read_pyproject
from pitloom.extract.scanner import scan_project_for_ai_models

log = logging.getLogger(__name__)

_SPDX3_JSON_EXT = ".spdx3.json"


def _get_hook_settings(config: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    """Read validated hook settings with defaults applied."""
    return (
        config.get("sbom-basename", "") or "sbom",
        config.get("creator-name", "") or "Pitloom",
        config.get("creator-email", ""),
        config.get("fragments", []),
    )


def _build_document_model(
    project_dir: Path,
    creator_name: str,
    creator_email: str,
) -> tuple[DocumentModel, str | None, list[str]]:
    """Load project metadata and assemble the format-neutral document."""
    metadata, pitloom_config = read_pyproject(project_dir / "pyproject.toml")
    creation_meta = CreationMetadata(
        creator_name=creator_name,
        creator_email=creator_email,
        build_datetime=datetime.now(timezone.utc).isoformat(),
    )
    merkle_root, project_files = get_wheel_files(project_dir)
    metadata.files = project_files
    ai_models = scan_project_for_ai_models(project_dir, project_files)
    document = DocumentModel(
        project=metadata,
        creation=creation_meta,
        ai_models=ai_models,
    )
    return document, merkle_root, pitloom_config.fragments


def _stage_sbom_file(sbom_json: str, sbom_filename: str) -> tuple[
    tempfile.TemporaryDirectory[str], Path
]:
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

    Configuration (all fields optional):

    .. code-block:: toml

        [tool.hatch.build.hooks.pitloom]
        enabled = true             # set to false to skip SBOM generation
        sbom-basename = ""         # name part only, no extension; default "sbom"
        creator-name = ""          # defaults to "Pitloom"
        creator-email = ""
        fragments = []             # extra fragment paths relative to project root
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

        Raises:
            ValueError: If a hook configuration value has an invalid type
                or is otherwise invalid.
            FileNotFoundError: If ``pyproject.toml`` is absent from the
                project root.
        """
        config = dict(self.config)
        _validate_config(config)

        if not config.get("enabled", True):
            log.info("Pitloom build hook: disabled; skipping SBOM generation.")
            return

        sbom_basename, creator_name, creator_email, hook_fragments = _get_hook_settings(
            config
        )
        sbom_filename: str = f"{sbom_basename}{_SPDX3_JSON_EXT}"

        project_dir = Path(self.root)
        document, merkle_root, pitloom_fragments = _build_document_model(
            project_dir,
            creator_name,
            creator_email,
        )

        exporter = assemble_spdx3(document, merkle_root=merkle_root)

        # Merge fragments from [tool.pitloom] and [tool.hatch.build.hooks.pitloom]
        all_fragments = pitloom_fragments + hook_fragments
        merge_fragments(project_dir, all_fragments, exporter)

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
            len(all_fragments),
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


def _validate_config(config: dict[str, Any]) -> None:
    """Validate ``[tool.hatch.build.hooks.pitloom]`` configuration values.

    Raises:
        ValueError: If any value has an unexpected type or is otherwise invalid.
    """
    section = "[tool.hatch.build.hooks.pitloom]"

    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(
            f"{section} 'enabled' must be a boolean (true/false), "
            f"got {type(enabled).__name__!r}."
        )

    sbom_basename = config.get("sbom-basename", "")
    if not isinstance(sbom_basename, str):
        raise ValueError(
            f"{section} 'sbom-basename' must be a string, "
            f"got {type(sbom_basename).__name__!r}."
        )

    for key in ("creator-name", "creator-email"):
        value = config.get(key, "")
        if not isinstance(value, str):
            raise ValueError(
                f"{section} {key!r} must be a string, got {type(value).__name__!r}."
            )

    fragments = config.get("fragments", [])
    if not isinstance(fragments, list) or not all(
        isinstance(f, str) for f in fragments
    ):
        raise ValueError(f"{section} 'fragments' must be a list of strings.")


@hookimpl
def hatch_register_build_hook() -> type[PitloomBuildHook]:
    """Register ``PitloomBuildHook`` with Hatchling's plugin system."""
    return PitloomBuildHook
