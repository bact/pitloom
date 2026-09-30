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
import contextlib
import io
import logging
from pathlib import Path
from typing import IO, Any
from zipfile import ZipFile

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.extract.ai_model import archive_member
from pitloom.extract.ai_model._pickle_bounds import first_pickle
from pitloom.extract.ai_model.archive_member import (
    ArchiveMemberTooLarge,
    open_archive_member,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.logging_config import field_loss_suffix, loggable, one_line

log = logging.getLogger(__name__)


def _dotted_name(node: Any) -> str | None:
    """Extract dotted identifier from an AST Name or Attribute node."""
    if isinstance(node, ast.Name):
        return str(node.id)
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else str(node.attr)
    return None


# What of fickling's own stderr output a warning quotes.
_FICKLING_STDERR_CHARS = 200


class _BoundedStderr(io.TextIOBase):
    """A write-only text sink that keeps the first :data:`_KEEP` characters."""

    _KEEP = 4096

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._size = 0

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if self._size < self._KEEP:
            self._parts.append(s[: self._KEEP - self._size])
            self._size += len(self._parts[-1])
        return len(s)

    def text(self) -> str:
        """What was kept."""
        return "".join(self._parts)


def _top_class(pickled: Any) -> str | None:
    """The first dotted class name (title-case last part) called in the
    pickle's AST."""
    for node in ast.walk(pickled.ast):
        if isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name and name.rsplit(".", 1)[-1][:1].isupper():
                return name
    return None


def _bounded_pickle(pkl_file: IO[bytes]) -> bytes | None:
    """The first pickle of *pkl_file*, verified bounded; ``None`` (with a
    warning) when it is not a well-formed pickle.

    Raises:
        ModelLimitExceeded: Too many opcodes.
        pitloom.extract.ai_model.archive_member.ArchiveMemberTooLarge:
            No complete pickle within :data:`archive_member.MAX_ARCHIVE_MEMBER_BYTES`.
    """
    limit = archive_member.MAX_ARCHIVE_MEMBER_BYTES
    data = pkl_file.read(limit + 1)
    try:
        return first_pickle(data[:limit])
    except ValueError as exc:
        if len(data) > limit:
            raise ArchiveMemberTooLarge("pickle", limit) from None
        msg = "fickling failed to parse pickle bytes: %s" + field_loss_suffix(
            "skipped", "type_of_model"
        )
        log.warning(msg, one_line(exc))
        return None


def _fickling_get_top_class(pkl_file: IO[bytes]) -> str | None:
    """Use fickling to safely extract the top-level class name from a pickle.

    Returns the first dotted class name (title-case final component) found in
    the pickle AST, or ``None`` if fickling is not installed or the class
    cannot be determined.  Never executes the pickle.

    Only the first pickle of *pkl_file*, at most
    :data:`~pitloom.extract.ai_model.archive_member.MAX_ARCHIVE_MEMBER_BYTES`
    and :data:`~pitloom.extract.ai_model._pickle_bounds.MAX_PICKLE_OPCODES`
    opcodes, reaches fickling (see :func:`_bounded_pickle`). What fickling
    writes to stderr is held back and summarised in one warning.

    Raises:
        ModelLimitExceeded: The pickle is over a bound.
    """
    try:
        # pylint: disable=import-outside-toplevel
        from fickling.fickle import Pickled
    except ImportError:
        return None

    pickle_bytes = _bounded_pickle(pkl_file)
    if pickle_bytes is None:
        return None

    sink = _BoundedStderr()
    failure: str | None = None
    type_of_model: str | None = None
    with contextlib.redirect_stderr(sink):
        try:
            pkl = Pickled.load(io.BytesIO(pickle_bytes))
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            failure = f"fickling failed to parse pickle bytes: {one_line(exc)}"
        else:
            try:
                type_of_model = _top_class(pkl)
            # pylint: disable-next=broad-exception-caught
            except Exception as exc:
                failure = f"fickling parsed pickle but AST walk failed: {one_line(exc)}"
    if failure is not None:
        log.warning("%s%s", failure, field_loss_suffix("skipped", "type_of_model"))
    stderr = one_line(sink.text())[:_FICKLING_STDERR_CHARS]
    if stderr:
        log.warning("fickling reported on stderr: %s", stderr)
    return type_of_model


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
            type_of_model = _fickling_get_top_class(open_archive_member(zf, pkl_entry))
            if type_of_model:
                provenance["type_of_model"] = (
                    f"{source} | Field: {pkl_entry} (fickling)"
                )
        except ModelLimitExceeded:
            raise
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:
            msg = "Failed to inspect %s in %s: %s" + field_loss_suffix(
                "skipped", "type_of_model"
            )
            log.warning(msg, loggable(pkl_entry), loggable(source), loggable(str(exc)))

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
        except OSError as exc:
            # The file itself couldn't be opened (not just a single field
            # failing to extract) -- same "Raises: ValueError" contract
            # every sibling extractor (hdf5.py, numpy.py, ...) honors.
            raise ValueError(
                f"Failed to read PyTorch file {model_path}: {exc}"
            ) from exc
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

    try:
        with zipfile.ZipFile(str(model_path), "r") as zf:
            type_of_model, properties, provenance = _read_pytorch_zip(zf, source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Failed to read PyTorch file {model_path}: {exc}") from exc

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
