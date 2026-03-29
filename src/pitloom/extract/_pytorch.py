# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PyTorch classic format metadata extractor (.pt, .pth).

References:
    - https://docs.pytorch.org/docs/stable/notes/serialization.html
    - https://www.loc.gov/preservation/digital/formats/fdd/fdd000644.shtml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import ZipFile

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata


def _fickling_get_top_class(pkl_bytes: bytes) -> str | None:
    """Use fickling to safely extract the top-level class name from pickle bytes.

    Returns the first dotted class name (title-case final component) found in
    the pickle AST, or ``None`` if fickling is not installed or the class
    cannot be determined.  Never executes the pickle.
    """
    try:
        import ast as pyast  # pylint: disable=import-outside-toplevel
        import io  # pylint: disable=import-outside-toplevel

        from fickling.pickle import (  # pylint: disable=import-outside-toplevel
            Pickle,
        )
    except ImportError:
        return None

    try:
        pkl = Pickle.load(io.BytesIO(pkl_bytes))
    except Exception:  # pylint: disable=broad-exception-caught
        return None

    def _dotted_name(node: Any) -> str | None:
        if isinstance(node, pyast.Name):
            return node.id
        if isinstance(node, pyast.Attribute):
            parent = _dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return None

    for node in pyast.walk(pkl.ast):
        if isinstance(node, pyast.Call):
            name = _dotted_name(node.func)
            if name:
                last = name.rsplit(".", 1)[-1]
                if last[:1].isupper():
                    return name
    return None


def _read_pytorch_zip(
    zf: ZipFile,
    source: str,
) -> tuple[str | None, dict[str, str], dict[str, str]]:
    """Read metadata from a classic ZIP-based PyTorch archive.

    Args:
        zf: Open ZipFile handle.
        source: Provenance source string (e.g. "Source: model.pt").

    Returns:
        Tuple of (type_of_model, properties, provenance).
    """
    file_list = zf.namelist()
    type_of_model: str | None = None
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    shown = file_list[:20]
    properties["archive_contents"] = ", ".join(shown)
    if len(file_list) > 20:
        properties["archive_contents"] += f", ... ({len(file_list)} total)"
    provenance["properties"] = f"{source} | Field: ZIP archive structure"

    # Inspect archive/data.pkl safely via fickling.
    pkl_entry = next(
        (n for n in file_list if n.endswith("/data.pkl") or n == "data.pkl"),
        None,
    )
    if pkl_entry is not None:
        try:
            pkl_data = zf.read(pkl_entry)
            type_of_model = _fickling_get_top_class(pkl_data)
            if type_of_model:
                provenance["type_of_model"] = (
                    f"{source} | Field: {pkl_entry} (fickling)"
                )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    return type_of_model, properties, provenance


def read_pytorch(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a classic PyTorch model file (``.pt``, ``.pth``).

    Most modern PyTorch files are ZIP archives.  This extractor inspects the
    archive structure without executing any code, then optionally uses
    ``fickling`` for safe pickle inspection to determine the top-level class
    name (``type_of_model``).

    Supported variants:

    - **ZIP archive** (``.pt`` / ``.pth``): Contains ``archive/data.pkl``;
      class name extracted via fickling if available.
    - **Raw pickle** (old format): inspected via fickling without execution.

    .. warning::
        Raw pickle files can execute arbitrary code when loaded with
        ``pickle.load``.  This extractor never calls ``pickle.load``; it uses
        fickling's AST-based parser which is safe by design.

    Args:
        model_path: Path to a ``.pt`` or ``.pth`` file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ValueError: If the file cannot be opened.
    """
    import zipfile  # pylint: disable=import-outside-toplevel

    source = f"Source: {model_path.name}"
    type_of_model: str | None = None
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    try:
        is_zip = zipfile.is_zipfile(str(model_path))
    except OSError:
        is_zip = False

    if not is_zip:
        # Old-style raw pickle — use fickling for safe, non-executing inspection.
        properties["format_detail"] = "raw pickle"
        provenance["properties"] = f"{source} | raw pickle format"
        try:
            with model_path.open("rb") as fh:
                pkl_data = fh.read()
            type_of_model = _fickling_get_top_class(pkl_data)
            if type_of_model:
                provenance["type_of_model"] = f"{source} | Field: raw pickle (fickling)"
        except OSError:
            pass
        return AiModelMetadata(
            format=AiModelFormat.PYTORCH,
            type_of_model=type_of_model,
            properties=properties,
            provenance=provenance,
        )

    with zipfile.ZipFile(str(model_path), "r") as zf:
        type_of_model, properties, provenance = _read_pytorch_zip(zf, source)

    return AiModelMetadata(
        format=AiModelFormat.PYTORCH,
        type_of_model=type_of_model,
        properties=properties,
        provenance=provenance,
    )
