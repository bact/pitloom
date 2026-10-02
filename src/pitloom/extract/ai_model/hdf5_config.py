# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing of the JSON root attributes of a Keras v1/v2 HDF5 model.

``model_config`` and ``training_config`` are untrusted JSON. A part that is
not what Keras writes (not valid JSON, nested too deeply, not an object, a
name that is not a string) is one problem per attribute: parsing stops there,
what was read before it is kept, and :class:`ConfigProblem` names what was
lost. Absent parts are not problems.

See also: :mod:`pitloom.extract.ai_model.hdf5`, which reads the attributes and
logs the problems.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from pitloom.extract._extract_utils import record_dict_field_provenance
from pitloom.logging_config import field_loss_suffix, one_line

log = logging.getLogger(__name__)

#: Characters of an unparsed ``model_config`` kept in
#: ``properties["model_config_raw"]``.
RAW_CONFIG_CHARS = 500

_MODEL_CONFIG_FIELDS = (
    "type_of_model",
    "name",
    "hyperparameters",
    "inputs",
    "properties.layer_count",
)
_TRAINING_CONFIG_FIELDS = (
    "properties.optimizer",
    "properties.loss",
    "properties.metrics",
)
# The fields each root attribute sets, named when it cannot be read.
_ATTRIBUTE_FIELDS = {
    "keras_version": ("framework_version", "format_version"),
    "backend": ("properties.backend",),
    "model_config": _MODEL_CONFIG_FIELDS,
    "training_config": _TRAINING_CONFIG_FIELDS,
}


class ConfigProblem(NamedTuple):
    """Why an attribute could not be read whole.

    Attributes:
        text: The reason, on one line.
        lost: The fields that stay unset because of it.
    """

    text: str
    lost: tuple[str, ...]


class _ConfigShapeError(ValueError):
    """A config part that is not what Keras writes."""


def _object(value: Any, what: str) -> dict[str, Any]:
    """*value* as a mapping.

    Raises:
        _ConfigShapeError: *value* is not an object (``null`` included).
    """
    if not isinstance(value, dict):
        raise _ConfigShapeError(f"{what} is not an object")
    return value


def _member_object(parent: dict[str, Any], key: str, what: str) -> dict[str, Any]:
    """``parent[key]`` as a mapping; ``{}`` when absent or ``null``."""
    value = parent.get(key)
    return {} if value is None else _object(value, what)


def _member_text(parent: dict[str, Any], key: str, what: str) -> str | None:
    """``parent[key]`` as text; ``None`` when absent, ``null`` or empty.

    Raises:
        _ConfigShapeError: The value is something else than a string.
    """
    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _ConfigShapeError(f"{what} is not a string")
    return value or None


def _json_object(raw: str, what: str) -> dict[str, Any]:
    """The JSON object in *raw*.

    Raises:
        _ConfigShapeError: *raw* is not valid JSON (nesting too deep for the
            parser included), or not an object; the message is the reason, as
            it reads after *what*.
    """
    try:
        parsed = json.loads(raw)
    except RecursionError as exc:
        raise _ConfigShapeError(
            f"{what} is not valid JSON (nested too deeply)"
        ) from exc
    except ValueError as exc:  # JSONDecodeError, or an over-long integer
        raise _ConfigShapeError(f"{what} is not valid JSON ({exc})") from exc
    if not isinstance(parsed, dict):
        raise _ConfigShapeError(f"{what} is not a JSON object")
    return parsed


def extract_input_from_layers(
    layers: list[Any], source: str
) -> tuple[list[dict[str, Any]], str]:
    """Extract the model input shape from a Keras ``config.layers`` list.

    Tries each layer in order:

    - **InputLayer**: uses ``config.batch_shape``.
    - **Other layers**: uses ``build_config.input_shape``.

    Args:
        layers: The ``config.layers`` list from ``model_config``.
        source: Provenance source string (e.g. ``"Source: model.h5"``).

    Returns:
        Tuple of ``(inputs, provenance_value)`` where ``inputs`` is a
        one-element list or empty and ``provenance_value`` is the source
        description string (empty string when nothing was found).

    Raises:
        _ConfigShapeError: A layer, or its ``config`` or ``build_config``,
            reached before a shape is found is not an object.
    """
    for i, entry in enumerate(layers):
        layer = _object(entry, f"layers[{i}]")
        if layer.get("class_name", "") == "InputLayer":
            layer_config = _member_object(layer, "config", f"layers[{i}].config")
            batch_shape = layer_config.get("batch_shape")
            if batch_shape is not None:
                prov = (
                    f"{source} | Field: model_config.config.layers"
                    "[InputLayer].config.batch_shape"
                )
                return [{"shape": batch_shape}], prov
        else:
            build = _member_object(layer, "build_config", f"layers[{i}].build_config")
            in_shape = build.get("input_shape")
            if in_shape is not None:
                prov = (
                    f"{source} | Field: model_config.config.layers[{i}]"
                    ".build_config.input_shape"
                )
                return [{"shape": in_shape}], prov
    return [], ""


def _extract_layers_info(
    layers: list[Any],
    source: str,
    properties: dict[str, str],
    inputs: list[dict[str, Any]],
    provenance: dict[str, str],
) -> None:
    """Extract layer count and input shapes from layers list."""
    properties["layer_count"] = str(len(layers))
    provenance["properties.layer_count"] = (
        f"{source} | Field: model_config.config.layers (count)"
    )
    new_inputs, inputs_prov = extract_input_from_layers(layers, source)
    if new_inputs:
        inputs.extend(new_inputs)
    if inputs_prov:
        provenance["inputs"] = inputs_prov


def _extract_config_hyperparameters(
    config: dict[str, Any],
    source: str,
    hyperparameters: dict[str, Any],
    provenance: dict[str, str],
) -> None:
    """Extract scalar hyperparameter entries and record their provenance."""
    for key, val in config.items():
        if key in ("name", "layers"):
            continue
        if isinstance(val, (int, float, bool, str)):
            hyperparameters[key] = val

    record_dict_field_provenance(
        provenance,
        "hyperparameters",
        hyperparameters,
        source,
        location_prefix="model_config.config.",
    )


@dataclass
class _Progress:
    """What :func:`_read_model_config` reads into, has read, and has yet to.

    Attributes:
        source: Provenance source string.
        hyperparameters: Filled in place.
        inputs: Filled in place.
        properties: Filled in place.
        provenance: Filled in place.
        type_of_model: The model class, once read.
        name: The model name, once read.
        lost: The fields the stages not yet passed would set, so that a raise
            names them.
    """

    source: str
    hyperparameters: dict[str, Any]
    inputs: list[dict[str, Any]]
    properties: dict[str, str]
    provenance: dict[str, str]
    type_of_model: str | None = None
    name: str | None = None
    lost: list[str] = field(default_factory=lambda: list(_MODEL_CONFIG_FIELDS))


def _read_layers(config: dict[str, Any], done: _Progress) -> None:
    """The layer count and input shape of ``config.layers``, when present.

    Raises:
        _ConfigShapeError: ``layers``, or a layer reached, is not what Keras
            writes.
    """
    layers = config.get("layers")
    if layers is not None and not isinstance(layers, list):
        raise _ConfigShapeError("model_config.config.layers is not a list")
    done.lost.remove("properties.layer_count")
    if layers is not None:
        _extract_layers_info(
            layers, done.source, done.properties, done.inputs, done.provenance
        )


def _read_model_config(model_config: dict[str, Any], done: _Progress) -> None:
    """The stages of :func:`parse_model_config`, in the order that keeps the
    most when one raises."""
    source, provenance = done.source, done.provenance
    done.type_of_model = _member_text(
        model_config, "class_name", "model_config.class_name"
    )
    if done.type_of_model:
        provenance["type_of_model"] = f"{source} | Field: model_config.class_name"
    done.lost.remove("type_of_model")

    config = _member_object(model_config, "config", "model_config.config")
    done.name = _member_text(config, "name", "model_config.config.name") or (
        _member_text(config, "model_name", "model_config.config.model_name")
    )
    if done.name:
        provenance["name"] = f"{source} | Field: model_config.config.name"
    done.lost.remove("name")

    # Layers are recorded before the hyperparameters, as SBOM output has always
    # ordered them; a bad layers part must not lose the hyperparameters.
    layers_error: _ConfigShapeError | None = None
    try:
        _read_layers(config, done)
    except _ConfigShapeError as exc:
        layers_error = exc
    _extract_config_hyperparameters(config, source, done.hyperparameters, provenance)
    done.lost.remove("hyperparameters")
    if layers_error is not None:
        raise layers_error

    # Top-level build_config -- fallback if layers didn't give a shape.
    if not done.inputs:
        build = _member_object(
            model_config, "build_config", "model_config.build_config"
        )
        in_shape = build.get("input_shape")
        if in_shape is not None:
            done.inputs.append({"shape": in_shape})
            provenance["inputs"] = (
                f"{source} | Field: model_config.build_config.input_shape"
            )


def parse_model_config(
    raw: str,
    source: str,
    hyperparameters: dict[str, Any],
    inputs: list[dict[str, Any]],
    properties: dict[str, str],
    provenance: dict[str, str],
) -> tuple[str | None, str | None, ConfigProblem | None]:
    """Parse ``model_config`` JSON from a Keras v1/v2 HDF5 model.

    Returns:
        ``(type_of_model, name, problem)``. *problem* is ``None``, or why the
        config could not be read whole (not JSON, not an object, a part of
        it not an object or a string); what was read before it is kept.
    """
    done = _Progress(source, hyperparameters, inputs, properties, provenance)
    problem: str | None = None
    try:
        _read_model_config(_json_object(raw, "model_config"), done)
    except _ConfigShapeError as exc:
        problem = one_line(exc)
    if problem is None:
        return done.type_of_model, done.name, None
    return done.type_of_model, done.name, ConfigProblem(problem, tuple(done.lost))


def _read_optimizer(
    training_config: dict[str, Any],
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
) -> None:
    """``optimizer_config.class_name`` (or ``optimizer.class_name``).

    Raises:
        _ConfigShapeError: The optimizer is not an object, or its class name
            is not a string.
    """
    opt_key = (
        "optimizer_config" if "optimizer_config" in training_config else "optimizer"
    )
    optimizer = _member_object(training_config, opt_key, f"training_config.{opt_key}")
    opt_class = _member_text(
        optimizer, "class_name", f"training_config.{opt_key}.class_name"
    )
    if opt_class:
        properties["optimizer"] = opt_class
        provenance["properties.optimizer"] = (
            f"{source} | Field: training_config.{opt_key}.class_name"
        )


def parse_training_config(
    raw: str,
    source: str,
    properties: dict[str, str],
    provenance: dict[str, str],
) -> ConfigProblem | None:
    """Parse ``training_config`` JSON from a Keras v1/v2 HDF5 model.

    Extracts:

    - ``loss`` -> ``properties["loss"]`` (updated in-place)
    - ``metrics`` -> ``properties["metrics"]`` (updated in-place)
    - ``optimizer_config.class_name`` (or ``optimizer.class_name``)
      -> ``properties["optimizer"]`` (updated in-place)
    - Per-field source paths -> ``provenance`` (updated in-place)

    Args:
        raw: Raw JSON string from the ``training_config`` HDF5 attribute.
        source: Provenance source string (e.g. ``"Source: model.h5"``).
        properties: Updated in-place with optimizer, loss, and metrics entries.
        provenance: Updated in-place with per-field source descriptions.

    Returns:
        ``None``, or why the attribute could not be read whole: not a JSON
        object (nothing is read), or an optimizer that is not an object with
        a string class name (loss and metrics are read).
    """
    lost = list(_TRAINING_CONFIG_FIELDS)
    try:
        training_config = _json_object(raw, "training_config")
    except _ConfigShapeError as exc:
        return ConfigProblem(one_line(exc), tuple(lost))
    # Optimizer first, as SBOM output has always ordered the properties; a bad
    # optimizer must not lose the loss and metrics.
    optimizer_error: _ConfigShapeError | None = None
    try:
        _read_optimizer(training_config, source, properties, provenance)
        lost.remove("properties.optimizer")
    except _ConfigShapeError as exc:
        optimizer_error = exc

    loss = training_config.get("loss")
    if loss is not None:
        properties["loss"] = str(loss)
        provenance["properties.loss"] = f"{source} | Field: training_config.loss"
    lost.remove("properties.loss")

    metrics = training_config.get("metrics")
    if metrics:
        properties["metrics"] = json.dumps(metrics)
        provenance["properties.metrics"] = f"{source} | Field: training_config.metrics"
    lost.remove("properties.metrics")

    if optimizer_error is not None:
        return ConfigProblem(one_line(optimizer_error), tuple(lost))
    return None


def log_model_config_problem(
    problem: ConfigProblem | None, raw: str, kept_raw: bool
) -> None:
    """Say, in one ``WARNING:``, what became of a ``model_config`` that could
    not be read whole: *problem* (``None`` for a valid object without a class
    or name), whether the raw text is *kept_raw* in
    ``properties.model_config_raw`` (cut to :data:`RAW_CONFIG_CHARS`), or the
    fields read before it are kept and the rest skipped."""
    cut = kept_raw and len(raw) > RAW_CONFIG_CHARS
    if problem is None and not cut:
        return
    cut_note = f", the first {RAW_CONFIG_CHARS} of {len(raw)} characters" if cut else ""
    if problem is None:
        log.warning(
            "Unparsed model_config of %d characters; the first %d are kept%s",
            len(raw),
            RAW_CONFIG_CHARS,
            field_loss_suffix("degraded", "properties.model_config_raw"),
        )
    elif kept_raw:
        log.warning(
            "%s; kept as properties.model_config_raw%s%s",
            problem.text,
            cut_note,
            field_loss_suffix("skipped", *problem.lost),
        )
    else:
        log.warning(
            "%s; the fields read before it are kept%s",
            problem.text,
            field_loss_suffix("skipped", *problem.lost),
        )


def log_attribute_problem(name: str, exc: BaseException) -> None:
    """Say, in one ``WARNING:``, that root attribute *name* cannot be read."""
    log.warning(
        "%s attribute cannot be read; %s%s",
        name,
        one_line(exc),
        field_loss_suffix("skipped", *_ATTRIBUTE_FIELDS[name]),
    )


def log_training_config_problem(problem: ConfigProblem | None) -> None:
    """Say, in one ``WARNING:``, that a ``training_config`` was not read whole."""
    if problem is not None:
        log.warning(
            "%s; reading stopped there%s",
            problem.text,
            field_loss_suffix("skipped", *problem.lost),
        )
