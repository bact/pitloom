# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PyTorch PT2 Archive metadata extractor (.pt2 / ExecuTorch).

References:
    - https://docs.pytorch.org/docs/stable/user_guide/torch_compiler/export.html
"""

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
    except Exception:  # pylint: disable=broad-exception-caught
        pass
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

    - ``name``          → :attr:`~AiModelMetadata.name`
    - ``description``   → :attr:`~AiModelMetadata.description`
    - ``model_version`` or ``version`` → :attr:`~AiModelMetadata.version`
    - ``license``       → :attr:`~AiModelMetadata.license`
    - ``author``        → ``properties["author"]``
    - ``tags``          → ``properties["tags"]`` (JSON array serialized as
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
    import json  # pylint: disable=import-outside-toplevel

    file_list = set(zf.namelist())
    name: str | None = None
    description: str | None = None
    version: str | None = None
    license_expr: str | None = None

    def _read_text(rel_path: str) -> str | None:
        full = f"{prefix}{rel_path}"
        if full in file_list:
            try:
                return zf.read(full).decode("utf-8", errors="replace").strip() or None
            except Exception:  # pylint: disable=broad-exception-caught
                pass
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

    tags_raw = _read_text("extra/tags")
    if tags_raw:
        try:
            tags_list = json.loads(tags_raw)
            if isinstance(tags_list, list):
                properties["tags"] = ", ".join(str(t) for t in tags_list)
            else:
                properties["tags"] = tags_raw
        except Exception:  # pylint: disable=broad-exception-caught
            properties["tags"] = tags_raw

    if "author" in properties or "tags" in properties:
        provenance["properties.extra"] = f"{source} | Field: extra/*"

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
    import json  # pylint: disable=import-outside-toplevel

    model_json_path = f"{prefix}models/model.json"
    if model_json_path not in zf.namelist():
        return [], []

    try:
        data = json.loads(zf.read(model_json_path))
    except Exception:  # pylint: disable=broad-exception-caught
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


def _read_pt2_zip(
    zf: ZipFile,
    source: str,
) -> tuple[
    str | None,
    str | None,
    str | None,
    str | None,
    dict[str, str],
    dict[str, str],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Read metadata from a PT2 Archive ZIP.

    Args:
        zf: Open ZipFile handle.
        source: Provenance source string (e.g. "Source: model.pt2").

    Returns:
        Tuple of (name, description, version, license_expr, properties,
        provenance, inputs, outputs).
    """
    file_list = zf.namelist()
    name: str | None = None
    description: str | None = None
    version: str | None = None
    license_expr: str | None = None
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    properties["archive_contents"] = ", ".join(file_list[:20])
    if len(file_list) > 20:
        properties["archive_contents"] += f", ... ({len(file_list)} total)"
    provenance["properties"] = f"{source} | Field: ZIP archive structure"

    prefix = _detect_root_prefix(file_list)

    # PT2 Archive: dedicated root-level version file (simple format).
    if "version" in file_list:
        version = zf.read("version").decode("utf-8", errors="replace").strip() or None
        if version:
            provenance["version"] = f"{source} | Field: version file"

    # ExecuTorch rich format: archive_version is the archive format version,
    # stored in properties rather than used as the model version.
    if f"{prefix}archive_version" in file_list:
        try:
            arch_ver = (
                zf.read(f"{prefix}archive_version")
                .decode("utf-8", errors="replace")
                .strip()
            )
            if arch_ver:
                properties["archive_version"] = arch_ver
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # PT2 Archive: optional metadata JSON (simple format).
    for meta_entry in ("METADATA.json", "metadata.json", "extra/metadata.json"):
        if meta_entry in file_list:
            name, prov_name = _read_pt2_meta_entry(zf, meta_entry, source)
            if name:
                if prov_name:
                    provenance["name"] = prov_name
                break

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
        properties,
        provenance,
        inputs,
        outputs,
    )


def read_pytorch_pt2(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a PyTorch PT2 Archive file (``.pt2``).

    PT2 Archive is the ExecuTorch on-device deployment format.  It is a ZIP
    archive.  Two layout variants are supported:

    **Simple format** — a root-level ``version`` file and optionally a
    ``METADATA.json`` with ``name`` / ``model_name``.  No pickle inspection
    is performed.

    **Rich ExecuTorch format** — a single root directory
    (e.g. ``model_name/``) containing:

    - ``archive_version``      → :attr:`~AiModelMetadata.version`
    - ``extra/name``           → :attr:`~AiModelMetadata.name`
    - ``extra/description``    → :attr:`~AiModelMetadata.description`
    - ``extra/model_version``  → :attr:`~AiModelMetadata.version` (preferred)
    - ``extra/license``        → :attr:`~AiModelMetadata.license`
    - ``extra/author``         → ``properties["author"]``
    - ``extra/tags``           → ``properties["tags"]``
    - ``models/model.json``    → :attr:`~AiModelMetadata.inputs` /
      :attr:`~AiModelMetadata.outputs` (graph tensor names)

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
        (
            name,
            description,
            version,
            license_expr,
            properties,
            provenance,
            inputs,
            outputs,
        ) = _read_pt2_zip(zf, source)

    return AiModelMetadata(
        format=AiModelFormat.PYTORCH_PT2,
        name=name,
        description=description,
        version=version,
        license=license_expr,
        properties=properties,
        provenance=provenance,
        inputs=inputs,
        outputs=outputs,
    )
