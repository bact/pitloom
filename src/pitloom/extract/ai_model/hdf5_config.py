# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Parsing of a Keras model config: the ``model_config`` root attribute of a
Keras v1/v2 HDF5 model, and ``config.json`` of a Keras v3 ``.keras``
archive, which hold the same object.

The config is untrusted JSON. A part that is not what Keras writes (not
valid JSON, nested too deeply, not an object, a name that is not a string)
is one problem per config: parsing stops there, what was read before it is
kept, and :class:`ConfigProblem` names what was lost. Absent parts are not
problems.

See also: :mod:`pitloom.extract.ai_model.hdf5` and
:mod:`pitloom.extract.ai_model.keras`, which read the configs,
:mod:`pitloom.extract.ai_model.keras_training_config` (the training config),
and :mod:`pitloom.extract.ai_model._hdf5_warnings`, which says the problems.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from pitloom.core.ai_metadata import record_scalar_property
from pitloom.core.provenance import provenance_segment
from pitloom.extract._extract_utils import record_dict_field_provenance
from pitloom.logging_config import one_line

#: Characters of an unparsed ``model_config`` kept in
#: ``properties["model_config_raw"]``.
RAW_CONFIG_CHARS = 500
#: The property an unparsed ``model_config`` is kept in.
RAW_CONFIG_KEY = "model_config_raw"

#: The fields a model config sets, named when it cannot be read.
MODEL_CONFIG_FIELDS = (
    "type_of_model",
    "name",
    "hyperparameters",
    "inputs",
    "properties.layer_count",
)
#: The fields a training config sets, named when it cannot be read.
TRAINING_CONFIG_FIELDS = (
    "properties.optimizer",
    "properties.loss",
    "properties.metrics",
)
#: The fields each root attribute sets, named when it cannot be read.
ATTRIBUTE_FIELDS = {
    "keras_version": ("framework_version", "format_version"),
    "backend": ("properties.backend",),
    "model_config": MODEL_CONFIG_FIELDS,
    "training_config": TRAINING_CONFIG_FIELDS,
}


class ConfigShapeError(ValueError):
    """A config *part* (``model_config.config``) that is not what Keras
    writes, and what is wrong with it, *reason*; its text is both."""

    def __init__(self, part: str, reason: str) -> None:
        super().__init__(f"{part} {reason}")
        #: The key path of the part.
        self.part: str = part
        #: What is wrong with it (``is not an object``).
        self.reason: str = reason

    def __reduce__(self) -> tuple[type[ConfigShapeError], tuple[str, str]]:
        return (type(self), (self.part, self.reason))


class ConfigProblem(NamedTuple):
    """Why an attribute could not be read whole.

    Attributes:
        part: The first part not as Keras writes it.
        error: What is wrong with it, then each later problem's own text,
            ``; ``-joined, on one line.
        lost: The fields that stay unset because of them.
    """

    part: str
    error: str
    lost: tuple[str, ...]

    @property
    def text(self) -> str:
        """The reason, as a warning says it."""
        return f"{self.part} {self.error}"

    @classmethod
    def of(
        cls, errors: Sequence[ConfigShapeError], lost: Iterable[str]
    ) -> ConfigProblem:
        """The problem of *errors*, at least one, in the order found."""
        first, *rest = errors
        error = "; ".join([one_line(first.reason), *(one_line(e) for e in rest)])
        return cls(first.part, error, tuple(lost))


def _object(value: Any, what: str) -> dict[str, Any]:
    """*value* as a mapping.

    Raises:
        ConfigShapeError: *value* is not an object (``null`` included).
    """
    if not isinstance(value, dict):
        raise ConfigShapeError(what, "is not an object")
    return value


def member_object(parent: dict[str, Any], key: str, what: str) -> dict[str, Any]:
    """``parent[key]`` as a mapping; ``{}`` when absent or ``null``.

    Raises:
        ConfigShapeError: The value is something else than an object.
    """
    value = parent.get(key)
    return {} if value is None else _object(value, what)


def member_text(parent: dict[str, Any], key: str, what: str) -> str | None:
    """``parent[key]`` as text; ``None`` when absent, ``null`` or empty.

    Raises:
        ConfigShapeError: The value is something else than a string.
    """
    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigShapeError(what, "is not a string")
    return value or None


def json_object(raw: str | bytes, what: str) -> dict[str, Any]:
    """The JSON object in *raw*; ``{}`` for JSON ``null`` (no data).

    *raw* as bytes is decoded as :func:`json.loads` does (UTF-8, -16 or -32,
    a UTF-8 byte order mark skipped).

    Raises:
        ConfigShapeError: *raw* is not valid JSON (nesting too deep for the
            parser, or bytes that are not text, included), or not an object;
            the message is the reason, as it reads after *what*.
    """
    try:
        parsed = json.loads(raw)
    except RecursionError as exc:
        raise ConfigShapeError(what, "is not valid JSON (nested too deeply)") from exc
    # JSONDecodeError, UnicodeDecodeError, or an over-long integer
    except ValueError as exc:
        raise ConfigShapeError(what, f"is not valid JSON ({exc})") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ConfigShapeError(what, "is not a JSON object")
    return parsed


def extract_input_from_layers(
    layers: list[Any], source: str, *, where: str = "model_config"
) -> tuple[list[dict[str, Any]], str]:
    """Extract the model input shape from a Keras ``config.layers`` list.

    Tries each layer in order:

    - **InputLayer**: uses ``config.batch_shape``.
    - **Other layers**: uses ``build_config.input_shape``.

    Args:
        layers: The ``config.layers`` list of the model config.
        source: Provenance source string (e.g. ``"Source: model.h5"``).
        where: The key path of the model config, as provenance names it
            (``model_config`` in HDF5, ``config`` in ``.keras``).

    Returns:
        Tuple of ``(inputs, provenance_value)`` where ``inputs`` is a
        one-element list or empty and ``provenance_value`` is the source
        description string (empty string when nothing was found).

    Raises:
        ConfigShapeError: A layer, or its ``config`` or ``build_config``,
            reached before a shape is found is not an object.
    """
    for i, entry in enumerate(layers):
        layer = _object(entry, f"layers[{i}]")
        if layer.get("class_name", "") == "InputLayer":
            layer_config = member_object(layer, "config", f"layers[{i}].config")
            batch_shape = layer_config.get("batch_shape")
            if batch_shape is not None:
                prov = provenance_segment(
                    source,
                    "Field",
                    f"{where}.config.layers[InputLayer].config.batch_shape",
                )
                return [{"shape": batch_shape}], prov
        else:
            build = member_object(layer, "build_config", f"layers[{i}].build_config")
            in_shape = build.get("input_shape")
            if in_shape is not None:
                prov = provenance_segment(
                    source,
                    "Field",
                    f"{where}.config.layers[{i}].build_config.input_shape",
                )
                return [{"shape": in_shape}], prov
    return [], ""


class ConfigLayout(NamedTuple):
    """Where a model config sits in its file, and how its reader treats it.

    Attributes:
        where: The key path of the model config, as provenance and a problem
            name it (``model_config`` in HDF5, ``config`` in ``.keras``).
        skipped_keys: The keys of its ``config`` that are no hyperparameters.
        skip_bad_names: Whether a class or model name that is not a string is
            skipped, reading going on; else reading stops there (HDF5 then
            keeps the raw text in its place).
    """

    where: str = "model_config"
    skipped_keys: tuple[str, ...] = ("name", "layers")
    skip_bad_names: bool = False


#: The layout of the ``model_config`` root attribute of an HDF5 model.
HDF5_LAYOUT = ConfigLayout()


@dataclass
class _Progress:
    """What :func:`_read_model_config` reads into, has read, and has yet to.

    Attributes:
        source: Provenance source string.
        hyperparameters: Filled in place.
        inputs: Filled in place.
        properties: Filled in place.
        provenance: Filled in place.
        layout: Where the config sits, and how it is read.
        natives: Filled in place with the native value of each property
            held as text, for :func:`pitloom.core.ai_metadata.source_metadata`.
        problems: Each name skipped by :attr:`ConfigLayout.skip_bad_names`,
            then the part that stopped reading, if any.
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
    layout: ConfigLayout = HDF5_LAYOUT
    natives: dict[str, Any] = field(default_factory=dict)
    problems: list[ConfigShapeError] = field(default_factory=list)
    type_of_model: str | None = None
    name: str | None = None
    lost: list[str] = field(default_factory=lambda: list(MODEL_CONFIG_FIELDS))

    def path(self, under: str) -> str:
        """The key path of *under*, a path under the model config."""
        return f"{self.layout.where}.{under}"

    def field_at(self, under: str) -> str:
        """The provenance of a value at *under* in the model config."""
        return provenance_segment(self.source, "Field", self.path(under))

    def text_at(
        self, parent: dict[str, Any], key: str, under: str
    ) -> tuple[str | None, bool]:
        """``parent[key]`` as text (:func:`member_text`), *under* naming it
        in the model config, and whether it was a value to keep.

        Raises:
            ConfigShapeError: The value is not a string, and the layout does
                not skip such a name.
        """
        try:
            return member_text(parent, key, self.path(under)), True
        except ConfigShapeError as exc:
            if not self.layout.skip_bad_names:
                raise
            self.problems.append(exc)
            return None, False


def _read_layers(config: dict[str, Any], done: _Progress) -> None:
    """The layer count and input shape of ``config.layers``, when present.

    Raises:
        ConfigShapeError: ``layers``, or a layer reached, is not what Keras
            writes.
    """
    layers = config.get("layers")
    if layers is not None and not isinstance(layers, list):
        raise ConfigShapeError(done.path("config.layers"), "is not a list")
    done.lost.remove("properties.layer_count")
    if layers is None:
        return
    record_scalar_property(done.properties, done.natives, "layer_count", len(layers))
    done.provenance["properties.layer_count"] = done.field_at("config.layers (count)")
    new_inputs, inputs_prov = extract_input_from_layers(
        layers, done.source, where=done.layout.where
    )
    done.inputs.extend(new_inputs)
    if inputs_prov:
        done.provenance["inputs"] = inputs_prov


def _read_hyperparameters(config: dict[str, Any], done: _Progress) -> None:
    """The scalar entries of ``config``, each with its provenance."""
    for key, val in config.items():
        if key in done.layout.skipped_keys:
            continue
        if isinstance(val, (int, float, bool, str)):
            done.hyperparameters[key] = val
    record_dict_field_provenance(
        done.provenance,
        "hyperparameters",
        done.hyperparameters,
        done.source,
        location_prefix=done.path("config."),
    )
    done.lost.remove("hyperparameters")


def _read_names(model_config: dict[str, Any], done: _Progress) -> dict[str, Any]:
    """The class and the name of the model; its ``config``, for the stages
    after them.

    Raises:
        ConfigShapeError: A name is not a string (when the layout does not
            skip it), or ``config`` is not an object.
    """
    type_of_model, kept = done.text_at(model_config, "class_name", "class_name")
    if kept:
        done.type_of_model = type_of_model
        if type_of_model:
            done.provenance["type_of_model"] = done.field_at("class_name")
        done.lost.remove("type_of_model")

    config = member_object(model_config, "config", done.path("config"))
    for key in ("name", "model_name"):
        name, kept = done.text_at(config, key, f"config.{key}")
        if not kept or name:
            break
    if kept:
        done.name = name
        if name:
            done.provenance["name"] = done.field_at(f"config.{key}")
        done.lost.remove("name")
    return config


def _read_model_config(model_config: dict[str, Any], done: _Progress) -> None:
    """The stages of :func:`parse_model_config_object`, in the order that
    keeps the most when one raises."""
    config = _read_names(model_config, done)
    # Layers are recorded before the hyperparameters, as SBOM output has always
    # ordered them; a bad layers part must not lose the hyperparameters.
    layers_error: ConfigShapeError | None = None
    try:
        _read_layers(config, done)
    except ConfigShapeError as exc:
        layers_error = exc
    _read_hyperparameters(config, done)
    if layers_error is not None:
        raise layers_error

    # Top-level build_config -- fallback if layers didn't give a shape.
    if not done.inputs:
        build = member_object(model_config, "build_config", done.path("build_config"))
        in_shape = build.get("input_shape")
        if in_shape is not None:
            done.inputs.append({"shape": in_shape})
            done.provenance["inputs"] = done.field_at("build_config.input_shape")
    done.lost.remove("inputs")


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def parse_model_config_object(
    model_config: dict[str, Any],
    source: str,
    hyperparameters: dict[str, Any],
    inputs: list[dict[str, Any]],
    properties: dict[str, str],
    provenance: dict[str, str],
    natives: dict[str, Any] | None = None,
    layout: ConfigLayout = HDF5_LAYOUT,
) -> tuple[str | None, str | None, ConfigProblem | None]:
    """Read a Keras model config, already parsed: the object of an HDF5
    ``model_config`` attribute or of a ``.keras`` archive's ``config.json``,
    where *layout* says it sits.

    Extracts:

    - ``class_name`` -> ``type_of_model`` (returned)
    - ``config.name`` (else ``config.model_name``) -> ``name`` (returned)
    - Scalar entries of ``config`` but the layout's skipped keys
      -> *hyperparameters*
    - The number of ``config.layers`` -> ``properties["layer_count"]``
    - The input shape: an ``InputLayer``'s ``config.batch_shape``, else a
      layer's ``build_config.input_shape``, else the top-level
      ``build_config.input_shape`` -> *inputs*
    - Per-field source paths -> *provenance*

    *hyperparameters*, *inputs*, *properties* and *provenance* are filled in
    place; *natives*, when given, with the native value of each property
    held as text (``layer_count``), for
    :func:`pitloom.core.ai_metadata.source_metadata`.

    Returns:
        ``(type_of_model, name, problem)``. *problem* is ``None``, or why the
        config could not be read whole (a part of it not an object or a
        string); what was read before it is kept.
    """
    done = _Progress(
        source, hyperparameters, inputs, properties, provenance, layout=layout
    )
    if natives is not None:
        done.natives = natives
    try:
        _read_model_config(model_config, done)
    except ConfigShapeError as exc:
        done.problems.append(exc)
    problem = ConfigProblem.of(done.problems, done.lost) if done.problems else None
    return done.type_of_model, done.name, problem


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def parse_model_config(
    raw: str,
    source: str,
    hyperparameters: dict[str, Any],
    inputs: list[dict[str, Any]],
    properties: dict[str, str],
    provenance: dict[str, str],
    natives: dict[str, Any] | None = None,
) -> tuple[str | None, str | None, ConfigProblem | None]:
    """Parse ``model_config`` JSON from a Keras v1/v2 HDF5 model, as
    :func:`parse_model_config_object` reads it.

    Returns:
        ``(type_of_model, name, problem)``. *problem* is ``None``, or why the
        config could not be read whole (not JSON, not an object, a part of
        it not an object or a string); what was read before it is kept.
    """
    try:
        model_config = json_object(raw, "model_config")
    except ConfigShapeError as exc:
        return None, None, ConfigProblem.of([exc], MODEL_CONFIG_FIELDS)
    return parse_model_config_object(
        model_config, source, hyperparameters, inputs, properties, provenance, natives
    )
