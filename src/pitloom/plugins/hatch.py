# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: embeds an SPDX 3 SBOM in the wheel (PEP 770)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

from pitloom.assemble.spdx3.assembler import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.extract.pyproject import read_pyproject

log = logging.getLogger(__name__)

_SPDX3_JSON_EXT = ".spdx3.json"


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
        appended to ``build_data["sbom_files"]``, which Hatchling 1.16.0+
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

        sbom_basename: str = config.get("sbom-basename", "") or "sbom"
        sbom_filename: str = f"{sbom_basename}{_SPDX3_JSON_EXT}"
        creator_name: str = config.get("creator-name", "") or "Pitloom"
        creator_email: str = config.get("creator-email", "")
        hook_fragments: list[str] = config.get("fragments", [])

        project_dir = Path(self.root)
        metadata, loom_config = read_pyproject(project_dir / "pyproject.toml")

        creation_meta = CreationMetadata(
            creator_name=creator_name,
            creator_email=creator_email,
        )
        doc = DocumentModel(project=metadata, creation=creation_meta)
        exporter = assemble_spdx3(doc)

        # Merge fragments from [tool.pitloom] and [tool.hatch.build.hooks.pitloom]
        all_fragments = loom_config.fragments + hook_fragments
        merge_fragments(project_dir, all_fragments, exporter)

        sbom_json = exporter.to_json(pretty=loom_config.pretty)

        self._sbom_filename = sbom_filename
        # Not used as a context manager: the directory must outlive initialize()
        # and be cleaned up in finalize() after the wheel is packaged.
        # pylint: disable=consider-using-with
        self._staging_dir = tempfile.TemporaryDirectory()  # noqa: SIM115
        self._sbom_staging_path = Path(self._staging_dir.name) / sbom_filename
        self._sbom_staging_path.write_text(sbom_json, encoding="utf-8")

        # Hatchling 1.16.0+ places each path in sbom_files at
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
