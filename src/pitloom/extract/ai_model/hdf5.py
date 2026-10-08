# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic HDF5 model metadata extractor with Keras v1/v2 legacy support.

HDF5 is a general-purpose hierarchical data format used by many frameworks.
Keras v1 and v2 stored models in HDF5 (``.h5`` / ``.hdf5``) with a set of
JSON-encoded root attributes.  This extractor reads the following root
attributes opportunistically -- any HDF5 model that happens to carry them
will have the corresponding metadata extracted and recorded:

- ``keras_version``
  -> ``format_info.framework_version`` (and ``format_info.format_version``,
  ``v1`` or ``v2``, from its major number)
- ``backend``
  -> ``properties["backend"]``
- ``model_config.class_name``
  -> :attr:`~AiModelMetadata.type_of_model`
- ``model_config.config.name``
  -> :attr:`~AiModelMetadata.name`
- Scalar entries of ``model_config.config``
  -> :attr:`~AiModelMetadata.hyperparameters`
- ``model_config.config.layers`` count
  -> ``properties["layer_count"]``
- ``model_config.build_config.input_shape`` (or layer batch_shape)
  -> :attr:`~AiModelMetadata.inputs`
- ``training_config.optimizer_config.class_name``
  -> ``properties["optimizer"]``
- ``training_config.loss``
  -> ``properties["loss"]``
- ``training_config.metrics``
  -> ``properties["metrics"]``

A **per-field provenance entry** is recorded for every populated field so
that downstream consumers can trace each value back to its exact HDF5
attribute and JSON path.

For plain HDF5 files without any of these attributes the extractor returns a
minimal :class:`~pitloom.core.ai_metadata.AiModelMetadata` with only
``format_info`` set.

The JSON attributes are parsed by :mod:`pitloom.extract.ai_model.hdf5_config`.

Native Keras v3 models use the ``.keras`` format (ZIP archive) and are
handled by the separate :mod:`pitloom.extract.ai_model.keras` extractor.

References:
    - https://docs.hdfgroup.org/hdf5/
    - https://keras.io/api/saving/model_saving_and_loading/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

from pitloom.core.ai_metadata import (
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
    source_metadata,
    value_text,
)
from pitloom.core.scalar_text import scalar_type
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.extract.ai_model.hdf5_config import (
    RAW_CONFIG_CHARS,
    log_attribute_problem,
    log_model_config_problem,
    log_training_config_problem,
    parse_model_config,
    parse_training_config,
)
from pitloom.extract.ai_model.reader_requirements import missing_library
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

# Elements of a string array decoded at a time.
_DECODE_BLOCK = 1 << 16

# What reading one attribute raises: h5py's TypeError for a type with no NumPy
# equivalent, OSError for a damaged one, or _UnsupportedAttribute.
_READ_ERRORS = (TypeError, ValueError, OSError)


class _UnsupportedAttribute(ValueError):
    """An attribute value whose bytes are not stable text."""


def _decode_text_array(value: Any) -> str:
    """The elements of a fixed-length ``S``/``U`` array, one per line, in
    blocks: a Python object per element costs ~160 bytes, so decoding them all
    at once multiplies the array's size."""
    flat = value.reshape(-1)
    is_bytes = value.dtype.kind == "S"
    parts: list[str] = []
    for start in range(0, flat.size, _DECODE_BLOCK):
        block = flat[start : start + _DECODE_BLOCK].tolist()
        parts.append(
            b"\n".join(block).decode("utf-8", errors="replace")
            if is_bytes
            else "\n".join(block)
        )
    return "\n".join(parts)


def _decode_h5_attr(value: Any) -> str | None:
    """Decode an h5py attribute value to a Python string.

    h5py may return string attributes as ``str``, ``bytes``, or
    ``numpy.bytes_`` depending on version and how the file was written. An
    array of strings is one element per line: a fixed-length one (``bytes_``
    or ``str_`` dtype) in bulk, one holding Python objects (``object`` dtype,
    what ``h5py.string_dtype()`` arrays read as) element by element. The raw
    buffer of an array holding objects is never used: it is pointers, which
    differ per run.

    A numeric or boolean attribute is its
    :func:`~pitloom.core.ai_metadata.value_text`. An attribute with an
    empty dataspace (``h5py.Empty``) has a dtype but no data, and decodes to
    ``None``.

    Raises:
        _UnsupportedAttribute: A compound dtype with an object field.
    """
    if value is None or getattr(value, "shape", ()) is None:
        return None  # absent, or an empty dataspace (h5py.Empty): no data
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    dtype = getattr(value, "dtype", None)
    if dtype is not None and dtype.hasobject:
        if dtype.kind != "O":
            raise _UnsupportedAttribute(
                f"a compound type with a string field ({dtype})"
            )
        leaves = value.reshape(-1).tolist()
        return "\n".join(str(_decode_h5_attr(leaf)) for leaf in leaves)
    if getattr(dtype, "kind", None) in ("S", "U"):
        return _decode_text_array(value)
    if hasattr(value, "tobytes") and scalar_type(value) is None:  # not a number
        return str(value.tobytes().decode("utf-8", errors="replace"))
    return value_text(value)


class _Attribute(NamedTuple):
    """A root attribute as read: its text, and its value when that is a
    number or a boolean (else ``None``), for ``valueTypes``."""

    text: str | None
    scalar: Any = None


def _read_attr(attrs: Any, name: str) -> _Attribute:
    """Root attribute *name*; no text when it is absent. One that cannot be
    read (a type h5py has no NumPy equivalent for, a compound with a string
    field) is one ``WARNING:`` naming the fields it would set."""
    try:
        value = attrs.get(name)
        text = _decode_h5_attr(value)
    except _READ_ERRORS as exc:
        log_attribute_problem(name, exc)
        return _Attribute(None)
    return _Attribute(text, value if scalar_type(value) is not None else None)


def _keras_format_version(
    keras_version: str, source: str, provenance: dict[str, str]
) -> str:
    """The Keras HDF5 format generation, ``v1`` for Keras 1.x and ``v2``
    for any later (or unparsable) version, recording the provenance of
    ``keras_version`` (the Keras library version, e.g. ``2.15.0``, not the
    model's) as the framework version too."""
    provenance["framework_version"] = f"{source} | Field: keras_version attribute"
    try:
        keras_major = int(keras_version.split(".")[0])
    except (ValueError, IndexError):
        keras_major = 2
    provenance["format_version"] = (
        f"{source} | Field: keras_version attribute (major version)"
    )
    return "v1" if keras_major == 1 else "v2"


# pylint: disable-next=too-many-locals
def read_hdf5(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a generic HDF5 file (``.h5`` or ``.hdf5``).

    Requires the ``h5py`` package (``pip install h5py``).

    Reads ``keras_version``, ``backend``, ``model_config``, and
    ``training_config`` root attributes opportunistically -- any HDF5 model
    that carries those attributes will have its metadata extracted.
    See the module docstring for the full list of extracted fields and their
    HDF5/JSON source paths.

    For native Keras v3 (``.keras``) files use
    :func:`pitloom.extract.ai_model.keras.read_keras` instead.

    Args:
        model_path: Path to a ``.h5`` or ``.hdf5`` file.

    Returns:
        :class:`~pitloom.core.ai_metadata.AiModelMetadata` with all
        available fields populated.  Plain HDF5 files without recognised
        root attributes return a minimal object with only ``format_info``
        set.

    Raises:
        ImportError: If ``h5py`` is not installed.
        ValueError: If the file cannot be read as a valid HDF5 file.
    """
    try:
        # pylint: disable=import-outside-toplevel
        import h5py
    except ImportError as exc:
        raise missing_library(AiModelFormat.HDF5) from exc

    try:
        hf = h5py.File(str(model_path), "r")
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.debug(
            "Failed to open HDF5 file %s: %s",
            loggable(str(model_path)),
            loggable(str(exc)),
        )
        raise ValueError(f"Failed to read HDF5 file {model_path}: {exc}") from exc

    with hf:
        source = f"Source: {sanitize_provenance_text(model_path.name)}"
        format_version: str | None = None
        framework: str | None = None
        framework_version: str | None = None
        name: str | None = None
        type_of_model: str | None = None
        hyperparameters: dict[str, Any] = {}
        properties: dict[str, str] = {}
        natives: dict[str, Any] = {}
        inputs: list[dict[str, Any]] = []
        provenance: dict[str, str] = {}

        keras_version_raw = _read_attr(hf.attrs, "keras_version").text
        model_config = _read_attr(hf.attrs, "model_config")
        model_config_raw = model_config.text
        training_config_raw = _read_attr(hf.attrs, "training_config").text
        backend = _read_attr(hf.attrs, "backend")

        if keras_version_raw:
            framework = "keras"
            framework_version = keras_version_raw
            format_version = _keras_format_version(
                keras_version_raw, source, provenance
            )

        if backend.text:
            properties["backend"] = backend.text
            provenance["properties.backend"] = f"{source} | Field: backend attribute"

        if model_config_raw:
            type_of_model, name, problem = parse_model_config(
                model_config_raw,
                source,
                hyperparameters,
                inputs,
                properties,
                provenance,
                natives,
            )
            kept_raw = not type_of_model and not name
            if kept_raw:
                properties["model_config_raw"] = model_config_raw[:RAW_CONFIG_CHARS]
                provenance["properties.model_config_raw"] = (
                    f"{source} | Field: model_config attribute (unparsed)"
                )
            log_model_config_problem(problem, model_config_raw, kept_raw)

        if training_config_raw:
            log_training_config_problem(
                parse_training_config(
                    training_config_raw, source, properties, provenance, natives
                )
            )

    # A number or boolean attribute is typed; its text is never cut (64 bits).
    for key, attr in (("backend", backend), ("model_config_raw", model_config)):
        if key in properties and attr.scalar is not None:
            natives[key] = attr.scalar
    fmt = AiModelFormat.KERAS if keras_version_raw else AiModelFormat.HDF5
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=fmt,
            format_version=format_version,
            framework=framework,
            framework_version=framework_version,
        ),
        name=name,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        **source_metadata(properties, natives),
        inputs=inputs,
        provenance=provenance,
    )
