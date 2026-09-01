# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PyTorch PT2 Archive metadata extractor (.pt2 / ExecuTorch).

References:
    - https://docs.pytorch.org/docs/stable/user_guide/torch_compiler/export.html
"""

from __future__ import annotations

import logging
from pathlib import Path
from zipfile import ZipFile

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import sanitize_provenance_text

log = logging.getLogger(__name__)


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
    # pylint: disable=import-outside-toplevel
    import json

    try:
        meta = json.loads(zf.read(meta_entry))
        if isinstance(meta, dict):
            name = None
            field_name = None
            if meta.get("name"):
                name = meta.get("name")
                field_name = "name"
            elif meta.get("model_name"):
                name = meta.get("model_name")
                field_name = "model_name"
            if name and field_name:
                return name, f"{source} | Field: {meta_entry}.{field_name}"
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning(
            "Failed to parse PT2 metadata entry %s: %s | Field(s) skipped: name",
            meta_entry,
            exc,
        )
    return None, None


def _detect_root_prefix(file_list: list[str]) -> str:
    """Detect a common root directory prefix from the ZIP file list.

    ExecuTorch archives often nest all content under a single root directory
    (the model name).  Returns that prefix with a trailing slash, or an
    empty string if the archive has no common root.

    Args:
        file_list: List of ZIP member paths.

    Returns:
        The common root prefix (e.g. ``"rich_model/"``), or ``""``.
    """
    if not file_list:
        return ""
    first = file_list[0]
    slash = first.find("/")
    if slash < 0:
        return ""
    candidate = first[: slash + 1]
    if all(f.startswith(candidate) for f in file_list):
        return candidate
    return ""


def _read_pt2_extra_files(
    zf: ZipFile,
    prefix: str,
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Read metadata from the ``extra/`` directory of a PT2 Archive.

    ExecuTorch archives may include individual UTF-8 files under
    ``{prefix}extra/`` carrying human-readable metadata:

    - ``name``          -> :attr:`~AiModelMetadata.name`
    - ``description``   -> :attr:`~AiModelMetadata.description`
    - ``model_version`` or ``version`` -> :attr:`~AiModelMetadata.version`
    - ``license``       -> :attr:`~AiModelMetadata.license`
    - ``author``        -> ``properties["author"]``
    - ``tags``          -> ``properties["tags"]`` (JSON array serialized as
      comma-separated string, or raw value if not JSON)

    Args:
        zf: Open ZipFile handle.
        prefix: Common root prefix (e.g. ``"rich_model/"``), or ``""``.
        source: Provenance source string (e.g. ``"Source: model.pt2"``).
        properties: Properties dict updated in-place with ``author`` / ``tags``.
        provenance: Provenance dict updated in-place with field sources.

    Returns:
        Tuple of ``(name, description, version, license_expr)``.
    """
    # pylint: disable=import-outside-toplevel
    import json

    file_list = set(zf.namelist())
    name: str | None = None
    description: str | None = None
    version: str | None = None
    license_expr: str | None = None

    _EXTRA_FILE_FIELD: dict[str, str] = {
        "extra/name": "name",
        "extra/description": "description",
        "extra/model_version": "version",
        "extra/version": "version",
        "extra/license": "license",
        "extra/author": "properties.author",
        "extra/tags": "properties.tags",
    }

    def _read_text(rel_path: str) -> str | None:
        full = f"{prefix}{rel_path}"
        if full in file_list:
            try:
                return zf.read(full).decode("utf-8", errors="replace").strip() or None
            # pylint: disable=broad-exception-caught
            except Exception as exc:
                log.warning(
                    "Failed to read PT2 extra file %s: %s | Field(s) skipped: %s",
                    full,
                    exc,
                    _EXTRA_FILE_FIELD.get(rel_path, rel_path),
                )
        return None

    name = _read_text("extra/name")
    if name:
        provenance["name"] = f"{source} | Field: extra/name"

    description = _read_text("extra/description")
    if description:
        provenance["description"] = f"{source} | Field: extra/description"

    # model_version takes precedence over version
    version = _read_text("extra/model_version") or _read_text("extra/version")
    if version:
        key = "model_version" if _read_text("extra/model_version") else "version"
        provenance["version"] = f"{source} | Field: extra/{key}"

    license_expr = _read_text("extra/license")
    if license_expr:
        provenance["license"] = f"{source} | Field: extra/license"

    author = _read_text("extra/author")
    if author:
        properties["author"] = author
        provenance["properties.author"] = f"{source} | Field: extra/author"

    tags_raw = _read_text("extra/tags")
    if tags_raw:
        try:
            tags_list = json.loads(tags_raw)
            if isinstance(tags_list, list):
                properties["tags"] = ", ".join(str(t) for t in tags_list)
            else:
                properties["tags"] = tags_raw
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            log.warning(
                "Failed to parse PT2 extra/tags as JSON: %s | Field(s) "
                "degraded: properties.tags (kept as raw string)",
                exc,
            )
            properties["tags"] = tags_raw
        provenance["properties.tags"] = f"{source} | Field: extra/tags"

    return name, description, version, license_expr


def _read_pt2_graph_io(
    zf: ZipFile,
    prefix: str,
    source: str,
    provenance: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Extract graph inputs and outputs from ``models/model.json``.

    The ExecuTorch ``models/model.json`` file describes the exported
    ``graph_module.graph`` with ``inputs`` and ``outputs`` lists.  Each
    entry is a typed union; the most common variant is
    ``{"as_tensor": {"name": "<tensor_name>"}}``.

    Args:
        zf: Open ZipFile handle.
        prefix: Common root prefix (e.g. ``"rich_model/"``), or ``""``.
        source: Provenance source string (e.g. ``"Source: model.pt2"``).
        provenance: Provenance dict updated in-place with field sources.

    Returns:
        Tuple of ``(inputs, outputs)``.
        Each element of ``inputs`` / ``outputs`` is a dict with at least
        ``{"name": str}``.  Returns empty lists if the file is absent or
        unparseable.
    """
    # pylint: disable=import-outside-toplevel
    import json

    model_json_path = f"{prefix}models/model.json"
    if model_json_path not in zf.namelist():
        return [], []

    try:
        data = json.loads(zf.read(model_json_path))
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning(
            "Failed to parse PT2 model graph %s: %s | Field(s) skipped: "
            "inputs, outputs",
            model_json_path,
            exc,
        )
        return [], []

    graph = (data.get("graph_module") or {}).get("graph") or {}

    def _parse_io(entries: list[object]) -> list[dict[str, object]]:
        result = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            tensor = entry.get("as_tensor") or {}
            if isinstance(tensor, dict) and tensor.get("name"):
                result.append({"name": tensor["name"]})
        return result

    inputs = _parse_io(graph.get("inputs", []))
    outputs = _parse_io(graph.get("outputs", []))
    if inputs:
        provenance["inputs"] = f"{source} | Field: models/model.json graph.inputs"
    if outputs:
        provenance["outputs"] = f"{source} | Field: models/model.json graph.outputs"
    return inputs, outputs


def _read_pt2_format_version(
    zf: ZipFile, prefix: str, file_list: list[str], source: str
) -> tuple[str | None, str | None]:
    """Read ExecuTorch archive format version if present."""
    if f"{prefix}archive_version" in file_list:
        try:
            arch_ver = (
                zf.read(f"{prefix}archive_version")
                .decode("utf-8", errors="replace")
                .strip()
            )
            if arch_ver:
                return arch_ver, f"{source} | Field: {prefix}archive_version"
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            log.warning(
                "Failed to read PT2 %sarchive_version: %s | Field(s) "
                "skipped: version (archive_version fallback)",
                prefix,
                exc,
            )
    return None, None


def _find_pt2_metadata_entry(
    zf: ZipFile, file_list: list[str], source: str
) -> tuple[str | None, str | None]:
    """Search for simple PT2 metadata JSON entry."""
    for meta_entry in ("METADATA.json", "metadata.json", "extra/metadata.json"):
        if meta_entry in file_list:
            name, prov_name = _read_pt2_meta_entry(zf, meta_entry, source)
            if name:
                return name, prov_name
    return None, None


# pylint: disable=too-many-locals
def _read_pt2_zip(
    zf: ZipFile,
    source: str,
) -> tuple[
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    dict[str, str],
    dict[str, str],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Read metadata from a PT2 Archive ZIP."""
    file_list = zf.namelist()
    description: str | None = None
    version: str | None = None
    license_expr: str | None = None
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    properties["archive_contents"] = ", ".join(file_list[:20])
    if len(file_list) > 20:
        properties["archive_contents"] += f", ... ({len(file_list)} total)"
    provenance["properties.archive_contents"] = (
        f"{source} | Field: ZIP archive structure"
    )

    prefix = _detect_root_prefix(file_list)

    if "version" in file_list:
        version = zf.read("version").decode("utf-8", errors="replace").strip() or None
        if version:
            provenance["version"] = f"{source} | Field: version file"

    format_version, prov_fv = _read_pt2_format_version(zf, prefix, file_list, source)
    if prov_fv:
        provenance["format_version"] = prov_fv

    name, prov_name = _find_pt2_metadata_entry(zf, file_list, source)
    if prov_name:
        provenance["name"] = prov_name

    # ExecuTorch rich format: extra/ metadata directory (updates properties/provenance
    # in-place; returns scalar fields that may override the above).
    extra_name, extra_desc, extra_ver, extra_license = _read_pt2_extra_files(
        zf, prefix, source, properties, provenance
    )

    # extra/ values override METADATA.json when both are present.
    if extra_name:
        name = extra_name
    if extra_desc:
        description = extra_desc
    # extra/model_version is the semantic model version; always preferred.
    if extra_ver:
        version = extra_ver
    if extra_license:
        license_expr = extra_license

    # Graph inputs / outputs from models/model.json (updates provenance in-place).
    inputs, outputs = _read_pt2_graph_io(zf, prefix, source, provenance)

    return (
        name,
        description,
        version,
        license_expr,
        format_version,
        properties,
        provenance,
        inputs,
        outputs,
    )


def read_pytorch_pt2(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a PyTorch PT2 Archive file (``.pt2``).

    PT2 Archive is the ExecuTorch on-device deployment format.  It is a ZIP
    archive.  Two layout variants are supported:

    **Simple format** -- a root-level ``version`` file and optionally a
    ``METADATA.json`` with ``name`` / ``model_name``.  No pickle inspection
    is performed.

    **Rich ExecuTorch format** -- a single root directory
    (e.g. ``model_name/``) containing:

    - ``archive_version``      -> :attr:`~AiModelMetadata.version`
    - ``extra/name``           -> :attr:`~AiModelMetadata.name`
    - ``extra/description``    -> :attr:`~AiModelMetadata.description`
    - ``extra/model_version``  -> :attr:`~AiModelMetadata.version` (preferred)
    - ``extra/license``        -> :attr:`~AiModelMetadata.license`
    - ``extra/author``         -> ``properties["author"]``
    - ``extra/tags``           -> ``properties["tags"]``
    - ``models/model.json``    -> :attr:`~AiModelMetadata.inputs` /
      :attr:`~AiModelMetadata.outputs` (graph tensor names)

    Args:
        model_path: Path to a ``.pt2`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ValueError: If the file is not a valid ZIP archive.
    """
    # pylint: disable=import-outside-toplevel
    import zipfile

    source = f"Source: {sanitize_provenance_text(model_path.name)}"

    try:
        is_zip = zipfile.is_zipfile(str(model_path))
    except OSError as exc:
        raise ValueError(f"Failed to open PT2 Archive: {model_path}") from exc

    if not is_zip:
        raise ValueError(f"PT2 Archive must be a ZIP file, got: {model_path}")

    with zipfile.ZipFile(str(model_path), "r") as zf:
        (
            name,
            description,
            version,
            license_expr,
            format_version,
            properties,
            provenance,
            inputs,
            outputs,
        ) = _read_pt2_zip(zf, source)

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.PYTORCH_PT2,
            format_version=format_version,
            framework="executorch",
        ),
        name=name,
        description=description,
        version=version,
        license=license_expr,
        properties=properties,
        provenance=provenance,
        inputs=inputs,
        outputs=outputs,
    )
