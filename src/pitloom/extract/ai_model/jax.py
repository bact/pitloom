# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""JAX model metadata extractor: an Orbax checkpoint step folder.

A step folder (what ``CheckpointManager`` writes under its root, one per
step) holds ``_CHECKPOINT_METADATA`` (JSON), an optional ``metrics/metrics``
(JSON) and one folder per saved item, each with a ``_METADATA`` (JSON) and
the array data.

See also: :mod:`pitloom.extract.ai_model.directory` (what recognises the
folder) and ``working-docs/design/jax-orbax-support.md``.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    record_scalar_property,
    source_metadata,
)
from pitloom.core.clone_mark import in_remote_clone, remote_clone_trusted
from pitloom.core.optional_libraries import Requirement
from pitloom.core.provenance import provenance_segment, provenance_source
from pitloom.core.quote_source import quote_source
from pitloom.extract.ai_model.directory import DIRECTORY_MARKERS
from pitloom.extract.ai_model.limits import ModelOverCap
from pitloom.extract.ai_model.parameter_count import derived_parameter_count
from pitloom.logging_config import loggable, one_line
from pitloom.messages import emit
from pitloom.messages.files import Cap
from pitloom.messages.model_fields import (
    JAX_LIBRARY_LINE,
    JAX_PART_LINE,
    MODEL_FIELD_UNREADABLE,
)

__all__ = ["MAX_ORBAX_JSON_BYTES", "read_jax"]

log = logging.getLogger(__name__)

_MARKER = DIRECTORY_MARKERS[AiModelFormat.JAX]

#: Most bytes read of one JSON file of the folder. A real checkpoint's
#: ``_METADATA`` holds one entry per array, a few hundred bytes each.
MAX_ORBAX_JSON_BYTES = 16 * 1024 * 1024

_JSON_CAP = Cap(MAX_ORBAX_JSON_BYTES, "byte", "Orbax-metadata")

#: The keys ``_CHECKPOINT_METADATA`` may hold the writer's own extra metadata
#: under: ``custom`` as ``CheckpointManager.save(custom_metadata=...)`` writes
#: it (orbax-checkpoint 0.11), ``custom_metadata`` as the v1 format's guide
#: names it.
_CUSTOM_KEYS = ("custom", "custom_metadata")

_TIMESTAMP_KEYS = ("init_timestamp_nsecs", "commit_timestamp_nsecs")

#: The library that gives the shape of each array. Optional: without it the
#: folder's own files are still read.
_LIBRARY = Requirement("orbax.checkpoint", "jax")
_LIBRARY_MODULES = frozenset({"orbax", "orbax.checkpoint"})
_LIBRARY_EXTRA = f"pitloom[{_LIBRARY.extra}]"


def _read_json_file(path: Path) -> Any:
    """The JSON of the regular file *path* (a link is not followed), read
    within :data:`MAX_ORBAX_JSON_BYTES`.

    Raises:
        ModelOverCap: The file is over the cap.
        ValueError: The file is no regular file or holds no JSON.
        OSError: The file cannot be read.
    """
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise ValueError("not a regular file")
    with path.open("rb") as fh:
        raw = fh.read(MAX_ORBAX_JSON_BYTES + 1)
    if len(raw) > MAX_ORBAX_JSON_BYTES:
        raise ModelOverCap(_JSON_CAP)
    try:
        # Bytes: json strips a UTF-8 byte order mark itself.
        return json.loads(raw)
    except (RecursionError, ValueError) as exc:  # UnicodeDecodeError is one
        raise ValueError(f"not JSON: {one_line(exc)}") from exc


def _warn_part(entry: str, exc: BaseException, *fields: str) -> None:
    """The ``model-field-unreadable`` ``WARNING:`` for the part *entry* of the
    folder, which *exc* stopped: the *fields* it leaves unset."""
    emit(
        log,
        MODEL_FIELD_UNREADABLE,
        logging.WARNING,
        line=JAX_PART_LINE,
        entry=entry,
        error=one_line(exc),
        fields=fields,
    )


def _read_marker(model_path: Path) -> dict[str, Any]:
    """The ``_CHECKPOINT_METADATA`` of the folder *model_path*, which must
    hold an ``item_handlers`` object, as every checkpoint's does.

    Raises:
        ModelOverCap: The file is over the cap.
        ValueError: The file is unreadable, not JSON, or not a checkpoint's.
    """
    path = model_path / _MARKER
    try:
        data = _read_json_file(path)
    except (OSError, ValueError) as exc:
        log.debug(
            "Failed to read Orbax %s: %s", loggable(str(path)), loggable(str(exc))
        )
        raise ValueError(
            f"Failed to read Orbax checkpoint {quote_source(model_path)}: "
            f"{_MARKER}: {one_line(exc)}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("item_handlers"), dict):
        raise ValueError(
            f"Failed to read Orbax checkpoint {quote_source(model_path)}: "
            f"{_MARKER} has no item_handlers"
        )
    return data


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _record_value(
    properties: dict[str, str],
    natives: dict[str, Any],
    provenance: dict[str, str],
    key: str,
    value: Any,
    source: str,
    location: str,
) -> None:
    """Record *value* under *key* in *properties* (text) and *natives* (the
    value itself when it is a scalar or a collection), with the provenance
    of *location*."""
    if value is None:
        return
    if isinstance(value, (dict, list)):
        properties[key] = json.dumps(value, sort_keys=True, ensure_ascii=False)
        natives[key] = value
    else:
        record_scalar_property(properties, natives, key, value)
    provenance[f"properties.{key}"] = provenance_segment(source, "Field", location)


def _record_marker(
    marker: dict[str, Any],
    properties: dict[str, str],
    natives: dict[str, Any],
    provenance: dict[str, str],
    source: str,
) -> None:
    """The item handlers, the timestamps and the writer's own metadata of
    ``_CHECKPOINT_METADATA`` as properties."""
    for item, handler in marker["item_handlers"].items():
        _record_value(
            properties,
            natives,
            provenance,
            f"item_handlers.{item}",
            handler,
            source,
            f"{_MARKER}.item_handlers.{item}",
        )
    for key in _TIMESTAMP_KEYS:
        _record_value(
            properties,
            natives,
            provenance,
            key,
            marker.get(key),
            source,
            f"{_MARKER}.{key}",
        )
    for custom_key in _CUSTOM_KEYS:
        custom = marker.get(custom_key)
        if isinstance(custom, dict):
            for key, value in custom.items():
                _record_value(
                    properties,
                    natives,
                    provenance,
                    f"custom.{key}",
                    value,
                    source,
                    f"{_MARKER}.{custom_key}.{key}",
                )
            break


def _record_metrics(
    model_path: Path,
    marker: dict[str, Any],
    properties: dict[str, str],
    natives: dict[str, Any],
    provenance: dict[str, str],
    source: str,
) -> None:
    """The metrics the writer tracked, as ``metrics.<name>`` properties:
    those of ``metrics/metrics`` (what ``CheckpointManager`` writes when it
    tracks the best checkpoint), then any ``_CHECKPOINT_METADATA`` holds for
    a name the file lacks. Neither is a default: a checkpoint saved without
    metrics holds none, and an empty object is no metric."""
    found: dict[str, Any] = {}
    locations: dict[str, str] = {}
    path = model_path / "metrics" / "metrics"
    if os.path.lexists(path):
        try:
            data = _read_json_file(path)
        except (OSError, ValueError) as exc:
            _warn_part("metrics/metrics", exc, "properties.metrics")
        else:
            if isinstance(data, dict):
                found.update(data)
                locations.update({k: f"metrics/metrics.{k}" for k in data})
    held = marker.get("metrics")
    if isinstance(held, dict):
        for key, value in held.items():
            if key not in found:
                found[key] = value
                locations[key] = f"{_MARKER}.metrics.{key}"
    for key, value in found.items():
        _record_value(
            properties,
            natives,
            provenance,
            f"metrics.{key}",
            value,
            source,
            locations[key],
        )


def _item_dirs(model_path: Path, marker: dict[str, Any]) -> list[tuple[str, Path]]:
    """The saved items named by ``_CHECKPOINT_METADATA``, each with its
    folder: only a name that is a single folder name is looked up (the names
    are the file's own, so ``..`` or a path is never joined)."""
    items: list[tuple[str, Path]] = []
    for name in sorted(marker["item_handlers"]):
        if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
            _warn_part("item name", ValueError("not a folder name"), "properties.items")
            continue
        items.append((name, model_path / name))
    return items


def _record_leaf_counts(
    items: list[tuple[str, Path]],
    properties: dict[str, str],
    natives: dict[str, Any],
    provenance: dict[str, str],
    source: str,
) -> list[Path]:
    """The number of arrays each item holds (the entries of its
    ``_METADATA``'s ``tree_metadata``) as ``items.<name>.arrays``, for an
    item whose ``_METADATA`` is there and readable. Returns the folders of
    the items that hold arrays: the others (the ``metrics`` JSON item) hold
    none."""
    holding: list[Path] = []
    for name, folder in items:
        path = folder / "_METADATA"
        if not os.path.lexists(path):
            continue
        try:
            data = _read_json_file(path)
        except (OSError, ValueError) as exc:
            _warn_part(f"{name}/_METADATA", exc, f"properties.items.{name}.arrays")
            continue
        tree = data.get("tree_metadata") if isinstance(data, dict) else None
        if isinstance(tree, dict):
            holding.append(folder)
            _record_value(
                properties,
                natives,
                provenance,
                f"items.{name}.arrays",
                len(tree),
                source,
                f"{name}/_METADATA.tree_metadata",
            )
    return holding


def _array_shapes(tree: Any) -> list[tuple[int, ...]]:
    """The shape of every array in *tree*, the metadata the library returns
    for an item: nested dicts, lists and tuples whose leaves with a ``shape``
    are arrays (a leaf with none is not one). Walked without recursion."""
    shapes: list[tuple[int, ...]] = []
    pending = [tree]
    while pending:
        node = pending.pop()
        shape = getattr(node, "shape", None)
        if shape is not None:
            shapes.append(tuple(int(dim) for dim in shape))
        elif isinstance(node, dict):
            pending.extend(node.values())
        elif isinstance(node, (list, tuple)):
            pending.extend(node)
    return shapes


def _item_shapes(ocp: Any, folder: Path) -> list[tuple[int, ...]]:
    """The array shapes of one item folder, read by the library without
    opening array data. *ocp* is the ``orbax.checkpoint`` module, typed as
    ``Any`` because its metadata types differ between versions."""
    return _array_shapes(ocp.PyTreeCheckpointer().metadata(folder).tree)


def _skip_library(model_path: Path, reason: str) -> None:
    """Say the parameter count is not read, for *reason*."""
    _warn_part("parameter count", ValueError(reason), "parameter_count")
    log.debug("Orbax parameter count skipped for %s", loggable(str(model_path)))


def _import_library(model_path: Path) -> Any:
    """The ``orbax.checkpoint`` module, or ``None`` with one message: ``INFO:``
    when it is not installed, ``WARNING:`` when its import fails."""
    try:
        # pylint: disable-next=import-outside-toplevel
        import orbax.checkpoint as ocp
    except ModuleNotFoundError as exc:
        if exc.name not in _LIBRARY_MODULES:
            _warn_part("library import", exc, "parameter_count")
            return None
        emit(
            log,
            MODEL_FIELD_UNREADABLE,
            logging.INFO,
            line=JAX_LIBRARY_LINE,
            format=AiModelFormat.JAX,
            file=model_path,
            requirement=_LIBRARY_EXTRA,
        )
        return None
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # a broken install raises more than ImportError
        _warn_part("library import", exc, "parameter_count")
        return None
    return ocp


def _parameter_count(
    model_path: Path, holding: list[Path], source: str, provenance: dict[str, str]
) -> int | None:
    """The number of elements in every array of the *holding* items, from the
    shapes the library reads (``PyTreeCheckpointer().metadata``: no array
    data is opened, nothing is written). All items or none: a sum over part of
    them would be wrong. ``None``, with one message, when the library is not
    installed (``INFO:``), fails to import or to read (``WARNING:``), or is
    not run on a file from a Git URL's clone the user has not vouched for (the
    library runs native code on the file's own bytes)."""
    if not holding:
        return None
    if in_remote_clone() and not remote_clone_trusted():
        _skip_library(
            model_path, "not run on a Git URL's files without --trust-model-files"
        )
        return None
    ocp = _import_library(model_path)
    if ocp is None:
        return None
    shapes: list[tuple[int, ...]] = []
    for folder in holding:
        try:
            shapes.extend(_item_shapes(ocp, folder))
        # pylint: disable-next=broad-exception-caught
        except Exception as exc:  # the library's errors are not one class
            _warn_part(f"arrays of {folder.name}", exc, "parameter_count")
            return None
    return derived_parameter_count(
        shapes, "array shapes (orbax-checkpoint)", source, provenance, str(model_path)
    )


def read_jax(model_path: Path) -> AiModelMetadata:
    """Extract metadata from an Orbax checkpoint step folder.

    Reads, with the standard library only, ``_CHECKPOINT_METADATA`` (item
    handlers, commit and init times, the writer's own ``custom`` metadata),
    ``metrics/metrics`` (the metrics ``CheckpointManager`` tracked, when it
    was set to track the best checkpoint) and each item's ``_METADATA`` (the
    number of arrays). No array data is opened. With ``orbax-checkpoint``
    installed (``pip install pitloom[jax]``) it also reads each array's
    shape, for ``parameter_count``, the sum of the elements of every array of
    every item; without it that field stays unset, said in one ``INFO:``.

    What the checkpoint does not state stays unset: it has no name,
    description, version or licence of its own, and the writer's ``custom``
    metadata is recorded as written, never read for those fields.
    ``performance_metrics`` is the time the save took, not the model's
    performance, and is not recorded.

    Args:
        model_path: A checkpoint step folder.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ModelOverCap: A JSON file of the checkpoint is over
            :data:`MAX_ORBAX_JSON_BYTES`.
        ValueError: ``_CHECKPOINT_METADATA`` cannot be read as a checkpoint's.
    """
    source = provenance_source(model_path.name)
    marker = _read_marker(model_path)
    properties: dict[str, str] = {}
    natives: dict[str, Any] = {}
    provenance: dict[str, str] = {}

    _record_marker(marker, properties, natives, provenance, source)
    _record_metrics(model_path, marker, properties, natives, provenance, source)
    items = _item_dirs(model_path, marker)
    holding = _record_leaf_counts(items, properties, natives, provenance, source)
    parameter_count = _parameter_count(model_path, holding, source, provenance)

    provenance["framework"] = f"{source} | Field: {_MARKER}"
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.JAX,
            framework="orbax",
        ),
        parameter_count=parameter_count,
        properties=properties,
        **source_metadata(properties, natives),
        provenance=provenance,
    )
