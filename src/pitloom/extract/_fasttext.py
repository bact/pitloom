# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""fastText model metadata extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata

# Maps Args attribute names (from model.f.getArgs()) to hyperparameter keys.
# The Python fasttext package exposes training configuration via the C++
# binding at model.f.getArgs(), not via individual get_*() methods on the
# model object.  model.get_dimension() is the only training param available
# directly on the model; it mirrors args.dim.
_FASTTEXT_ARGS_HYPERPARAMS: tuple[tuple[str, str], ...] = (
    ("dim", "dim"),
    ("lr", "lr"),
    ("epoch", "epoch"),
    ("wordNgrams", "wordNgrams"),
    ("minCount", "minCount"),
    ("minCountLabel", "minCountLabel"),
    ("minn", "minn"),
    ("maxn", "maxn"),
    ("neg", "neg"),
    ("bucket", "bucket"),
    ("ws", "ws"),
)


def _load_fasttext_model(model_path: Path) -> Any:
    """Load a fastText model with consistent dependency and format errors."""
    try:
        # pylint: disable=import-outside-toplevel
        import fasttext
    except ImportError as exc:
        raise ImportError(
            "The 'fasttext' package is required to extract fastText model metadata. "
            "Install it with: pip install fasttext"
        ) from exc

    try:
        return fasttext.load_model(str(model_path))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(
            f"Failed to load fastText model from {model_path}: {exc}"
        ) from exc


def _extract_fasttext_args(
    model: Any, source: str
) -> tuple[dict[str, Any], dict[str, str], str | None]:
    """Read optional training arguments exposed by the fastText binding."""
    hyperparameters: dict[str, Any] = {}
    properties: dict[str, str] = {}
    type_of_model: str | None = None

    try:
        args = model.f.getArgs()
    except Exception:  # pylint: disable=broad-exception-caught
        return hyperparameters, properties, type_of_model

    for attr, param_key in _FASTTEXT_ARGS_HYPERPARAMS:
        value = getattr(args, attr, None)
        if value is not None:
            hyperparameters[param_key] = value

    model_enum = getattr(args, "model", None)
    type_of_model = getattr(model_enum, "name", None) or None

    loss_enum = getattr(args, "loss", None)
    loss_name: str | None = getattr(loss_enum, "name", None) or None
    if loss_name:
        properties["lossName"] = loss_name

    if hyperparameters:
        properties["__hyperparameters_provenance__"] = f"{source} | Fields: args.*"
    if type_of_model:
        properties["__type_of_model_provenance__"] = f"{source} | Field: args.model"
    return hyperparameters, properties, type_of_model


def _extract_fasttext_outputs(
    model: Any,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Read supervised labels when available."""
    properties: dict[str, str] = {}
    outputs: list[dict[str, Any]] = []
    get_labels = getattr(model, "get_labels", None)
    if get_labels is None:
        return properties, outputs

    try:
        labels = get_labels()
    except Exception:  # pylint: disable=broad-exception-caught
        return properties, outputs

    if labels:
        properties["labels"] = ",".join(labels)
        outputs = [{"name": "label_probabilities", "shape": [len(labels)]}]
    return properties, outputs


def read_fasttext(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a fastText binary model file.

    Requires the ``fasttext`` package (``pip install fasttext``).

    fastText binary models (``.bin``) and quantised models (``.ftz``) store
    their training configuration in an Args struct accessible via the C++
    binding at ``model.f.getArgs()``.  This extractor reads all available
    training hyperparameters and maps them to the SPDX 3 AI profile
    ``hyperparameter`` field.  The model type (``skipgram``, ``cbow``, or
    ``supervised``) is mapped to ``type_of_model``.

    Extracted hyperparameters: dim, lr, epoch, wordNgrams, minCount,
    minCountLabel, minn, maxn, neg, bucket, ws (window size).

    Args:
        model_path: Path to a ``.bin`` or ``.ftz`` fastText model file.

    Returns:
        AiModelMetadata with available fields populated.

    Raises:
        ImportError: If ``fasttext`` is not installed.
        ValueError: If the file cannot be loaded as a valid fastText model.
    """
    model = _load_fasttext_model(model_path)

    source = f"Source: {model_path.name}"
    # Since fastText is a text classification and word embedding library,
    # we will assume the domains.
    domain: list[str] = ["text classification", "natural language processing"]
    provenance: dict[str, str] = {}
    hyperparameters, args_properties, type_of_model = _extract_fasttext_args(
        model, source
    )
    properties, outputs = _extract_fasttext_outputs(model)
    properties.update(args_properties)

    hyperparameters_provenance = properties.pop("__hyperparameters_provenance__", None)
    type_of_model_provenance = properties.pop("__type_of_model_provenance__", None)
    if hyperparameters_provenance is not None:
        provenance["hyperparameters"] = hyperparameters_provenance
    if type_of_model_provenance is not None:
        provenance["type_of_model"] = type_of_model_provenance

    if properties:
        provenance["properties"] = f"{source} | Fields: args.loss, labels"

    if outputs:
        provenance["outputs"] = f"{source} | Field: labels (supervised class count)"

    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=model_path.name,
            model_format=AiModelFormat.FASTTEXT,
            framework="fasttext",
        ),
        domain=domain,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        outputs=outputs,
        provenance=provenance,
    )
