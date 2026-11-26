# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The exported program of a PT2 Archive (``torch.export``): its signature's
inputs and outputs and the PyTorch version that exported it
(``models/model.json``), and its parameter count, the elements of its
stored weights (``data/weights/model_weights_config.json``).

See also: :mod:`pitloom.extract.ai_model.pytorch_pt2` (the reader).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import NamedTuple
from zipfile import ZipFile

from pitloom.core.internal_error import reraise_internal
from pitloom.extract.ai_model._stated_text import stated_text
from pitloom.extract.ai_model.archive_member import read_archive_member
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.extract.ai_model.parameter_count import derived_parameter_count
from pitloom.logging_config import one_line
from pitloom.messages import Line, emit
from pitloom.messages.model_fields import (
    MODEL_FIELD_UNREADABLE,
    PT2_GRAPH_LINE,
    PT2_VERSION_LINE,
)

log = logging.getLogger(__name__)

#: The exported program of the archive's one model, named ``model``.
MODEL_JSON = "models/model.json"
#: Each stored weight of that model (parameters and buffers) and its sizes.
WEIGHTS_CONFIG = "data/weights/model_weights_config.json"


def warn_pt2_unread(
    logger: logging.Logger,
    line: Line,
    exc: Exception,
    lost: tuple[str, ...],
    entry: str,
) -> None:
    """The ``model-field-unreadable`` warning of *line*, on *logger*, for
    the read of member *entry* that raised *exc*: the fields *lost*."""
    emit(
        logger,
        MODEL_FIELD_UNREADABLE,
        logging.WARNING,
        line=line,
        entry=entry,
        error=one_line(exc),
        fields=lost,
    )


class Pt2Graph(NamedTuple):
    """What ``models/model.json`` gives."""

    inputs: list[dict[str, object]]
    outputs: list[dict[str, object]]
    #: The ``torch_version`` that exported the program.
    torch_version: str | None = None


def _spec_tensor_names(specs: object, kind: str) -> list[dict[str, object]]:
    """The tensor names of the *kind* entries of a signature's *specs* list;
    an entry that is not a one-key union with a named tensor is skipped."""
    result: list[dict[str, object]] = []
    for spec in specs if isinstance(specs, list) else []:
        entry = spec.get(kind) if isinstance(spec, dict) else None
        arg = entry.get("arg") if isinstance(entry, dict) else None
        tensor = arg.get("as_tensor") if isinstance(arg, dict) else None
        if isinstance(tensor, dict) and tensor.get("name"):
            result.append({"name": tensor["name"]})
    return result


def _json_object(value: object, what: str) -> dict[str, object]:
    """*value* as a mapping; ``{}`` for an absent one (``None``).

    Raises:
        ValueError: *value* is present but not a JSON object.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{what} is not a JSON object")
    return value


def _program(raw: bytes) -> tuple[dict[str, object], str | None]:
    """The ``graph_module.signature`` object of a ``model.json`` text
    (``{}`` when the file has no graph module or no signature), and its
    ``torch_version`` when that is text.

    Raises:
        ValueError: The text is not JSON, or the file, its ``graph_module``
            or its ``signature`` is present but not a JSON object.
    """
    program = _json_object(json.loads(raw), "model.json")
    module = _json_object(program.get("graph_module"), "graph_module")
    signature = _json_object(module.get("signature"), "signature")
    return signature, stated_text(program.get("torch_version"))


def read_pt2_graph(
    zf: ZipFile,
    prefix: str,
    source: str,
    provenance: dict[str, str],
) -> Pt2Graph:
    """The model's inputs, outputs and ``torch_version`` from
    ``models/model.json``; their provenance set in *provenance*.

    The exported graph lists every placeholder as an input: parameters,
    buffers and constants as well as what a caller passes. Its
    ``signature`` says which is which, so only the ``user_input`` entries of
    ``input_specs`` are inputs and only the ``user_output`` entries of
    ``output_specs`` are outputs. A file without a signature gives none:
    the graph alone does not tell a weight from an input.

    Each entry of the signature is a one-key union of the kind and its
    ``arg``; the common ``arg`` is ``{"as_tensor": {"name": "<name>"}}``.
    Each input and output is ``{"name": str}``. Nothing when the member is
    absent; nothing, with a ``WARNING:``, when it does not parse.

    Args:
        zf: Open ZipFile handle.
        prefix: Common root prefix (e.g. ``"rich_model/"``), or ``""``.
        source: Provenance source string (e.g. ``"Source: model.pt2"``).
        provenance: Provenance dict updated in-place with field sources.
    """
    model_json_path = f"{prefix}{MODEL_JSON}"
    if model_json_path not in zf.namelist():
        return Pt2Graph([], [])

    try:
        signature, torch_version = _program(read_archive_member(zf, model_json_path))
    except ModelLimitExceeded:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        reraise_internal(exc)
        lost = ("inputs", "outputs", "framework_version")
        warn_pt2_unread(log, PT2_GRAPH_LINE, exc, lost, entry=model_json_path)
        return Pt2Graph([], [])

    inputs = _spec_tensor_names(signature.get("input_specs"), "user_input")
    outputs = _spec_tensor_names(signature.get("output_specs"), "user_output")
    if inputs:
        provenance["inputs"] = (
            f"{source} | Field: {MODEL_JSON} signature.input_specs user_input"
        )
    if outputs:
        provenance["outputs"] = (
            f"{source} | Field: {MODEL_JSON} signature.output_specs user_output"
        )
    if torch_version:
        provenance["framework_version"] = (
            f"{source} | Field: {MODEL_JSON} torch_version"
        )
    return Pt2Graph(inputs, outputs, torch_version)


def _size(size: object) -> object:
    """One ``tensor_meta.sizes`` entry: the ``as_int`` of a fixed size; any
    other (a symbolic ``as_expr``) as written, which no count accepts."""
    if isinstance(size, dict) and set(size) == {"as_int"}:
        return size["as_int"]
    return size


def _weight_shapes(raw: bytes) -> list[Sequence[object]]:
    """The sizes of each stored weight of a weights config: parameters and
    buffers alike (``is_param`` tells them apart), as every format's count
    includes the buffers a file stores.

    ``torch.export`` stores the storage that several names share (tied
    weights) as one blob and lists each name with that blob's
    ``path_name``; names whose ``path_name``, sizes, strides and storage
    offset all match are one stored weight, counted once. Different views
    of one blob are each counted.

    Raises:
        ValueError: The text is not JSON, or an entry is not as
            ``torch.export`` writes it.
    """
    config = _json_object(
        _json_object(json.loads(raw), "weights config").get("config"), "config"
    )
    shapes: list[Sequence[object]] = []
    seen: set[str] = set()
    for entry in config.values():
        weight = _json_object(entry, "weight")
        meta = _json_object(weight.get("tensor_meta"), "tensor_meta")
        sizes = meta.get("sizes")
        if not isinstance(sizes, list):
            raise ValueError("tensor_meta.sizes is not a list")
        if not isinstance(weight.get("path_name"), str):
            raise ValueError("path_name is not text")
        view = json.dumps(
            [
                weight.get("path_name"),
                sizes,
                meta.get("strides"),
                meta.get("storage_offset"),
            ],
            sort_keys=True,
        )
        if view not in seen:
            seen.add(view)
            shapes.append([_size(size) for size in sizes])
    return shapes


def read_pt2_parameter_count(
    zf: ZipFile, prefix: str, source: str, provenance: dict[str, str], where: str
) -> int | None:
    """The element sum of the model's stored weights (its weights config:
    parameters and buffers; lifted constants, in their own config, are not
    counted), from the sizes the config states; no tensor is read. ``None``
    when the member is absent or lists no weight; ``None``, with a
    ``WARNING:``, when it does not parse or a size is no count (*where*
    names the model).
    """
    path = f"{prefix}{WEIGHTS_CONFIG}"
    if path not in zf.namelist():
        return None
    try:
        shapes = _weight_shapes(read_archive_member(zf, path))
    except ModelLimitExceeded:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        reraise_internal(exc)
        warn_pt2_unread(log, PT2_VERSION_LINE, exc, ("parameter_count",), entry=path)
        return None
    return derived_parameter_count(
        shapes, f"{WEIGHTS_CONFIG} tensor_meta.sizes", source, provenance, where
    )
