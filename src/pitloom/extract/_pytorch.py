# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PyTorch classic format metadata extractor (.pt, .pth).

References:
    - https://docs.pytorch.org/docs/stable/notes/serialization.html
    - https://www.loc.gov/preservation/digital/formats/fdd/fdd000644.shtml
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import IO, Any, BinaryIO, cast
from zipfile import ZipFile

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import sanitize_provenance_text

log = logging.getLogger(__name__)


def _dotted_name(node: Any) -> str | None:
    """Extract dotted identifier from an AST Name or Attribute node."""
    if isinstance(node, ast.Name):
        return str(node.id)
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else str(node.attr)
    return None


def _fickling_get_top_class(pkl_file: IO[bytes]) -> str | None:
    """Use fickling to safely extract the top-level class name from a pickle file.

    Returns the first dotted class name (title-case final component) found in
    the pickle AST, or ``None`` if fickling is not installed or the class
    cannot be determined.  Never executes the pickle.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from fickling.fickle import (
            Pickled,
        )
    except ImportError:
        return None

    try:
        pkl = Pickled.load(cast(BinaryIO, pkl_file))
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.debug("fickling failed to parse pickle bytes: %s", exc)
        return None

    try:
        for node in ast.walk(pkl.ast):
            if isinstance(node, ast.Call):
                name = _dotted_name(node.func)
                if name:
                    last = name.rsplit(".", 1)[-1]
                    if last[:1].isupper():
                        return name
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        log.warning(
            "fickling parsed pickle but AST walk failed, type_of_model unavailable: %s",
            exc,
        )
        return None

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
    provenance["properties.archive_contents"] = (
        f"{source} | Field: ZIP archive structure"
    )

    # Inspect archive/data.pkl safely via fickling.
    pkl_entry = next(
        (n for n in file_list if n.endswith("/data.pkl") or n == "data.pkl"),
        None,
    )
    if pkl_entry is not None:
        try:
            with zf.open(pkl_entry) as fh:
                type_of_model = _fickling_get_top_class(fh)
            if type_of_model:
                provenance["type_of_model"] = (
                    f"{source} | Field: {pkl_entry} (fickling)"
                )
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            log.debug("Failed to inspect %s in %s: %s", pkl_entry, source, exc)

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
    # pylint: disable=import-outside-toplevel
    import zipfile

    source = f"Source: {sanitize_provenance_text(model_path.name)}"
    framework = "pytorch"
    type_of_model: str | None = None
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    try:
        is_zip = zipfile.is_zipfile(str(model_path))
    except OSError:
        is_zip = False

    if not is_zip:
        # Old-style raw pickle -- use fickling for safe, non-executing inspection.
        properties["format_detail"] = "raw pickle"
        provenance["properties.format_detail"] = f"{source} | Field: raw pickle format"
        try:
            with model_path.open("rb") as fh:
                type_of_model = _fickling_get_top_class(fh)
            if type_of_model:
                provenance["type_of_model"] = f"{source} | Field: raw pickle (fickling)"
        except OSError:
            pass
        return AiModelMetadata(
            format_info=AiModelFormatInfo(
                file_name=model_path.name,
                model_format=AiModelFormat.PYTORCH,
                framework=framework,
            ),
            type_of_model=type_of_model,
            properties=properties,
            provenance=provenance,
        )

    with zipfile.ZipFile(str(model_path), "r") as zf:
        type_of_model, properties, provenance = _read_pytorch_zip(zf, source)

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.PYTORCH,
            framework=framework,
        ),
        type_of_model=type_of_model,
        properties=properties,
        provenance=provenance,
    )
