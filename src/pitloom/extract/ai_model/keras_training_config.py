# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing of a Keras training config: the ``training_config`` root attribute
of a Keras v1/v2 HDF5 model, and the ``compile_config`` of a Keras v3
``.keras`` archive's ``config.json``, which state the optimizer, the loss and
the metrics the model was compiled with.

A part that is not what Keras writes is a problem: the optimizer's is one
for the optimizer alone, the loss and the metrics are still read.

See also: :mod:`pitloom.extract.ai_model.hdf5_config` (the model config and
the shared shape checks) and :mod:`pitloom.extract.ai_model._hdf5_warnings`,
which says the problems.
"""

from __future__ import annotations

import copy
from typing import Any, NamedTuple

from pitloom.core.ai_metadata import record_scalar_property
from pitloom.core.canonical_json import canonical_json
from pitloom.core.provenance import provenance_segment
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.extract.ai_model.hdf5_config import (
    TRAINING_CONFIG_FIELDS,
    ConfigProblem,
    ConfigShapeError,
    json_object,
    member_object,
    member_text,
)


class TrainingLayout(NamedTuple):
    """Where a training config sits in its file, and what it may hold.

    Attributes:
        where: The key path of the training config, as provenance and a
            problem name it (``training_config`` in HDF5,
            ``config.compile_config`` in ``.keras``).
        text_optimizer: Whether the optimizer may be a string, its
            identifier (``"adam"``), as Keras 3 keeps the one ``compile()``
            was given; else it is an object with a class name.
    """

    where: str = "training_config"
    text_optimizer: bool = False


#: The layout of the ``training_config`` root attribute of an HDF5 model.
HDF5_TRAINING_LAYOUT = TrainingLayout()
#: The layout of the ``compile_config`` of a ``.keras`` archive.
KERAS_COMPILE_LAYOUT = TrainingLayout("config.compile_config", text_optimizer=True)


def _read_optimizer(
    training_config: dict[str, Any],
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
    layout: TrainingLayout,
) -> None:
    """``optimizer_config.class_name`` (or ``optimizer.class_name``, or an
    ``optimizer`` string when the layout allows one).

    Raises:
        ConfigShapeError: The optimizer is not an object (nor a string, when
            allowed), or its class name is not a string.
    """
    opt_key = (
        "optimizer_config"
        if training_config.get("optimizer_config") is not None
        else "optimizer"
    )
    part = f"{layout.where}.{opt_key}"
    value = training_config.get(opt_key)
    if layout.text_optimizer and isinstance(value, str):
        opt_class, field = value or None, part
    elif layout.text_optimizer and value is not None and not isinstance(value, dict):
        raise ConfigShapeError(part, "is not an object or a string")
    else:
        optimizer = member_object(training_config, opt_key, part)
        field = f"{part}.class_name"
        opt_class = member_text(optimizer, "class_name", field)
    if opt_class:
        properties["optimizer"] = opt_class
        provenance["properties.optimizer"] = provenance_segment(source, "Field", field)


def _collection_text(value: list[Any] | dict[str, Any]) -> str:
    """*value* as its :func:`~pitloom.core.canonical_json.canonical_json`.

    RFC 8785 cannot write a lone surrogate (``"\\ud800"``, which
    ``json.loads`` accepts) in a string or a key, and raises
    :class:`ValueError`: a collection holding one is written from a copy with
    each escaped
    (:func:`~pitloom.core.untrusted_text.escape_lone_surrogates_in`), as a
    PT2 tag is.

    Raises:
        RecursionError: *value* is nested too deeply to serialise or copy.
    """
    try:
        return canonical_json(value)
    except ValueError:
        return canonical_json(escape_lone_surrogates_in(copy.deepcopy(value))[0])


def _record_json_value(
    properties: dict[str, str],
    natives: dict[str, Any],
    key: str,
    value: Any,
    where: str,
) -> None:
    """Record JSON *value* of the training config at *where* under *key*: a
    string as is; a number or a boolean as by
    :func:`~pitloom.core.ai_metadata.record_scalar_property`; a list or an
    object as its JSON text (:func:`_collection_text`) in *properties* and
    as read in *natives*.

    Raises:
        ConfigShapeError: *value* is nested too deeply to serialise (the
            parser's stack held it, the serialiser's did not).
    """
    if isinstance(value, str):
        properties[key] = value
    elif isinstance(value, (list, dict)):
        try:
            properties[key] = _collection_text(value)
        except RecursionError as exc:
            raise ConfigShapeError(f"{where}.{key}", "is nested too deeply") from exc
        natives[key] = value
    else:
        record_scalar_property(properties, natives, key, value)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def parse_training_config_object(
    training_config: dict[str, Any],
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
    natives: dict[str, Any] | None = None,
    layout: TrainingLayout = HDF5_TRAINING_LAYOUT,
) -> ConfigProblem | None:
    """Read a Keras training config, already parsed, where *layout* says it
    sits.

    Extracts:

    - ``loss`` and ``metrics`` -> ``properties`` (updated in-place): a
      string as is, a number or a boolean its scalar text, a list or an
      object its JSON text; the value as read, when not a string, also
      -> ``natives``. A ``null`` or ``""`` loss is absent, as an ``""``
      optimizer is; a ``null`` or empty metrics too.
    - ``optimizer_config.class_name`` (or ``optimizer.class_name``, or an
      ``optimizer`` string when the layout allows one)
      -> ``properties["optimizer"]`` (updated in-place)
    - Per-field source paths -> ``provenance`` (updated in-place)

    Args:
        training_config: The parsed training config.
        source: Provenance source string (e.g. ``"Source: model.h5"``).
        properties: Updated in-place with optimizer, loss, and metrics entries.
        provenance: Updated in-place with per-field source descriptions.
        natives: Updated in-place with ``loss`` and ``metrics`` as read,
            when not a string, for
            :func:`pitloom.core.ai_metadata.source_metadata`.
        layout: Where the config sits, and what its optimizer may be.

    Returns:
        ``None``, or why the config could not be read whole: an optimizer
        that is not as the layout allows (loss and metrics are read), or a
        loss or metrics nested too deeply to serialise (that field is not
        read).
    """
    lost = list(TRAINING_CONFIG_FIELDS)
    # Optimizer first, as SBOM output has always ordered the properties; a bad
    # optimizer must not lose the loss and metrics.
    errors: list[ConfigShapeError] = []
    try:
        _read_optimizer(training_config, source, properties, provenance, layout)
        lost.remove("properties.optimizer")
    except ConfigShapeError as exc:
        errors.append(exc)

    sink: dict[str, Any] = {} if natives is None else natives
    for key in ("loss", "metrics"):
        value = training_config.get(key)
        # A null or empty-string loss is absent; a null or empty metrics too.
        if value is not None and value != "" and (key == "loss" or value):
            try:
                _record_json_value(properties, sink, key, value, layout.where)
            except ConfigShapeError as exc:
                errors.append(exc)
                continue
            provenance[f"properties.{key}"] = provenance_segment(
                source, "Field", f"{layout.where}.{key}"
            )
        lost.remove(f"properties.{key}")

    if errors:
        return ConfigProblem.of(errors, lost)
    return None


def parse_training_config(
    raw: str,
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
    natives: dict[str, Any] | None = None,
) -> ConfigProblem | None:
    """Parse ``training_config`` JSON from a Keras v1/v2 HDF5 model, as
    :func:`parse_training_config_object` reads it.

    Returns:
        ``None``, or why the attribute could not be read whole: not a JSON
        object (nothing is read), or a problem
        :func:`parse_training_config_object` names.
    """
    try:
        training_config = json_object(raw, "training_config")
    except ConfigShapeError as exc:
        return ConfigProblem.of([exc], TRAINING_CONFIG_FIELDS)
    return parse_training_config_object(
        training_config, source, properties, provenance, natives
    )
