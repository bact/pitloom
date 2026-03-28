# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PyTorch PT2 Archive metadata extractor (.pt2 / ExecuTorch)."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata


def _read_pt2_meta_entry(
    zf: ZipFile,
    meta_entry: str,
    source: str,
) -> tuple[str | None, str | None]:
    """Read name from a single PT2 metadata JSON entry in *zf*.

    Args:
        zf: Open ZipFile handle.
        meta_entry: ZIP member path to the metadata JSON file.
        source: Provenance source string (e.g. "Source: model.pt2").

    Returns:
        Tuple of (name, provenance_value), both ``None`` on failure.
    """
    import json  # pylint: disable=import-outside-toplevel

    try:
        meta = json.loads(zf.read(meta_entry))
        if isinstance(meta, dict):
            name = meta.get("name") or meta.get("model_name") or None
            if name:
                return name, f"{source} | Field: {meta_entry}.name"
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None, None


def _read_pt2_zip(
    zf: ZipFile,
    source: str,
) -> tuple[str | None, str | None, dict[str, str], dict[str, str]]:
    """Read metadata from a PT2 Archive ZIP.

    Args:
        zf: Open ZipFile handle.
        source: Provenance source string (e.g. "Source: model.pt2").

    Returns:
        Tuple of (name, version, properties, provenance).
    """
    file_list = zf.namelist()
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}
    name: str | None = None
    version: str | None = None

    shown = file_list[:20]
    properties["archive_contents"] = ", ".join(shown)
    if len(file_list) > 20:
        properties["archive_contents"] += f", ... ({len(file_list)} total)"
    provenance["properties"] = f"{source} | Field: ZIP archive structure"

    # PT2 Archive: dedicated root-level version file.
    if "version" in file_list:
        ver_bytes = zf.read("version")
        ver = ver_bytes.decode("utf-8", errors="replace").strip()
        if ver:
            version = ver
            provenance["version"] = f"{source} | Field: version file"

    # PT2 Archive: optional metadata JSON.
    for meta_entry in ("METADATA.json", "metadata.json", "extra/metadata.json"):
        if meta_entry in file_list:
            name, prov_name = _read_pt2_meta_entry(zf, meta_entry, source)
            if prov_name:
                provenance["name"] = prov_name
            break

    return name, version, properties, provenance


def read_pytorch_pt2(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a PyTorch PT2 Archive file (``.pt2``).

    PT2 Archive is the ExecuTorch on-device deployment format.  It is a ZIP
    archive containing a root-level ``version`` file and optionally a
    ``METADATA.json``.  No pickle inspection is performed.

    Args:
        model_path: Path to a ``.pt2`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ValueError: If the file is not a valid ZIP archive.
    """
    import zipfile  # pylint: disable=import-outside-toplevel

    source = f"Source: {model_path.name}"

    try:
        is_zip = zipfile.is_zipfile(str(model_path))
    except OSError as exc:
        raise ValueError(f"Failed to open PT2 Archive: {model_path}") from exc

    if not is_zip:
        raise ValueError(f"PT2 Archive must be a ZIP file, got: {model_path}")

    with zipfile.ZipFile(str(model_path), "r") as zf:
        name, version, properties, provenance = _read_pt2_zip(zf, source)

    return AiModelMetadata(
        format=AiModelFormat.PYTORCH_PT2,
        name=name,
        version=version,
        properties=properties,
        provenance=provenance,
    )
