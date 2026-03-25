# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hatchling build hook: embeds an SPDX 3 SBOM in the wheel (PEP 770)."""

from __future__ import annotations

import base64
import hashlib
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

from loom.assemble.spdx3.assembler import build as assemble_spdx3
from loom.assemble.spdx3.fragments import merge_fragments
from loom.core.creation import CreationMetadata
from loom.core.document import DocumentModel
from loom.extract.pyproject import read_pyproject

log = logging.getLogger(__name__)


class LoomBuildHook(BuildHookInterface[BuilderConfig]):
    """Hatchling build hook that embeds an SPDX 3 SBOM in the wheel.

    Activated by adding ``[tool.hatch.build.hooks.loom]`` to the project's
    ``pyproject.toml`` and listing ``loom`` as a build dependency.

    The SBOM is written to ``.dist-info/sboms/<filename>`` inside the wheel,
    conforming to PEP 770.

    Configuration (all fields optional):

    .. code-block:: toml

        [tool.hatch.build.hooks.loom]
        enabled = true             # set to false to skip SBOM generation
        filename = "sbom.spdx3.json"
        creator-name = ""          # defaults to "Loom"
        creator-email = ""
        fragments = []             # extra fragment paths relative to project root
    """

    PLUGIN_NAME = "loom"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._staging_dir: tempfile.TemporaryDirectory[str] | None = None
        self._sbom_staging_path: Path | None = None
        self._sbom_filename: str = "sbom.spdx3.json"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Generate the SBOM and stage it for later injection into the wheel.

        Called by Hatchling before packaging. The staged SBOM is injected
        into ``.dist-info/sboms/<filename>`` in :meth:`finalize`, after
        the wheel is assembled, to conform to PEP 770.

        Raises:
            ValueError: If a hook configuration value has an invalid type
                or is otherwise invalid.
            FileNotFoundError: If ``pyproject.toml`` is absent from the
                project root.
        """
        config = dict(self.config)
        _validate_config(config)

        if not config.get("enabled", True):
            log.info("Loom build hook: disabled; skipping SBOM generation.")
            return

        sbom_filename: str = config.get("filename", "sbom.spdx3.json")
        creator_name: str = config.get("creator-name", "") or "Loom"
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

        # Merge fragments from [tool.loom] and [tool.hatch.build.hooks.loom]
        all_fragments = loom_config.fragments + hook_fragments
        merge_fragments(project_dir, all_fragments, exporter)

        sbom_json = exporter.to_json(pretty=loom_config.pretty)

        self._sbom_filename = sbom_filename
        # Not used as a context manager: the directory must outlive initialize()
        # and be cleaned up in finalize() after the wheel is packaged.
        self._staging_dir = tempfile.TemporaryDirectory()  # noqa: SIM115  # pylint: disable=consider-using-with
        self._sbom_staging_path = Path(self._staging_dir.name) / sbom_filename
        self._sbom_staging_path.write_text(sbom_json, encoding="utf-8")

        log.info(
            "Loom: generated SBOM %s (%d fragment(s) merged); "
            "will inject into .dist-info/sboms/ in finalize().",
            sbom_filename,
            len(all_fragments),
        )

    def finalize(
        self,
        version: str,
        build_data: dict[str, Any],
        artifact_path: str,
    ) -> None:
        """Inject the staged SBOM into the wheel and clean up.

        Only acts on ``.whl`` artifacts; sdist archives are left untouched
        because PEP 770 applies to binary distribution format only.
        """
        try:
            if (
                self._sbom_staging_path is not None
                and artifact_path
                and artifact_path.endswith(".whl")
            ):
                _inject_sbom_into_wheel(
                    Path(artifact_path),
                    self._sbom_staging_path,
                    self._sbom_filename,
                )
                log.info(
                    "Loom: injected SBOM into .dist-info/sboms/%s in %s.",
                    self._sbom_filename,
                    Path(artifact_path).name,
                )
        finally:
            if self._staging_dir is not None:
                self._staging_dir.cleanup()
                self._staging_dir = None
                self._sbom_staging_path = None


def _validate_config(config: dict[str, Any]) -> None:
    """Validate ``[tool.hatch.build.hooks.loom]`` configuration values.

    Raises:
        ValueError: If any value has an unexpected type or is otherwise invalid.
    """
    section = "[tool.hatch.build.hooks.loom]"

    enabled = config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(
            f"{section} 'enabled' must be a boolean (true/false), "
            f"got {type(enabled).__name__!r}."
        )

    filename = config.get("filename", "sbom.spdx3.json")
    if not isinstance(filename, str):
        raise ValueError(
            f"{section} 'filename' must be a string, got {type(filename).__name__!r}."
        )
    if not filename:
        raise ValueError(f"{section} 'filename' must not be empty.")

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


def _inject_sbom_into_wheel(
    wheel_path: Path,
    sbom_path: Path,
    sbom_filename: str,
) -> None:
    """Add ``sbom_path`` to a wheel archive at the PEP 770 location.

    The SBOM is placed at ``<name>-<ver>.dist-info/sboms/<sbom_filename>``.
    The wheel's RECORD file is updated to include the new entry.

    Args:
        wheel_path: Path to the wheel (``.whl``) file to modify in-place.
        sbom_path: Path to the staged SBOM file.
        sbom_filename: Filename for the SBOM inside the wheel.
    """
    sbom_data = sbom_path.read_bytes()
    digest = hashlib.sha256(sbom_data).digest()
    sbom_hash = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    sbom_size = len(sbom_data)

    with zipfile.ZipFile(wheel_path, "r") as zf:
        all_names = zf.namelist()
        # Locate the .dist-info directory — RECORD is always present
        dist_info_dir = next(
            name.split("/")[0]
            for name in all_names
            if name.endswith(".dist-info/RECORD")
        )
        record_name = f"{dist_info_dir}/RECORD"
        old_record = zf.read(record_name).decode("utf-8")

    sbom_archive_name = f"{dist_info_dir}/sboms/{sbom_filename}"

    # Rebuild RECORD: drop stale RECORD self-entry, append SBOM, re-add RECORD
    rows = [
        line
        for line in old_record.splitlines()
        if line and not line.startswith(f"{record_name},")
    ]
    rows.append(f"{sbom_archive_name},sha256={sbom_hash},{sbom_size}")
    rows.append(f"{record_name},,")
    new_record = "\r\n".join(rows) + "\r\n"

    tmp_path = wheel_path.with_suffix(".tmp.whl")
    try:
        with (
            zipfile.ZipFile(wheel_path, "r") as zin,
            zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout,
        ):
            for info in zin.infolist():
                if info.filename == record_name:
                    continue  # replaced below
                zout.writestr(info, zin.read(info.filename))
            zout.writestr(sbom_archive_name, sbom_data)
            zout.writestr(record_name, new_record.encode("utf-8"))
        tmp_path.replace(wheel_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


@hookimpl
def hatch_register_build_hook() -> type[LoomBuildHook]:
    """Register ``LoomBuildHook`` with Hatchling's plugin system."""
    return LoomBuildHook
