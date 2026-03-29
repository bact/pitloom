# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""fastText model metadata extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata

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
    try:
        # pylint: disable=import-outside-toplevel
        import fasttext  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "The 'fasttext' package is required to extract fastText model metadata. "
            "Install it with: pip install fasttext"
        ) from exc

    try:
        model = fasttext.load_model(str(model_path))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(
            f"Failed to load fastText model from {model_path}: {exc}"
        ) from exc

    source = f"Source: {model_path.name}"
    framework = "fasttext"
    hyperparameters: dict[str, Any] = {}
    properties: dict[str, str] = {}
    provenance: dict[str, str] = {}

    # Training args are on the C++ binding at model.f.getArgs().
    args = None
    try:
        args = model.f.getArgs()
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    if args is not None:
        for attr, param_key in _FASTTEXT_ARGS_HYPERPARAMS:
            value = getattr(args, attr, None)
            if value is not None:
                hyperparameters[param_key] = value

        # model attribute is a model_name enum; .name gives the string value.
        model_enum = getattr(args, "model", None)
        type_of_model: str | None = getattr(model_enum, "name", None) or None
        if type_of_model:
            provenance["type_of_model"] = f"{source} | Field: args.model"

        # loss attribute is a loss_name enum; .name gives the string value.
        loss_enum = getattr(args, "loss", None)
        loss_name: str | None = getattr(loss_enum, "name", None) or None
        if loss_name:
            properties["lossName"] = loss_name
    else:
        type_of_model = None

    if hyperparameters:
        provenance["hyperparameters"] = f"{source} | Fields: args.*"

    # Labels for supervised models (empty for unsupervised word vectors).
    outputs: list[dict[str, Any]] = []
    get_labels = getattr(model, "get_labels", None)
    if get_labels is not None:
        try:
            labels = get_labels()
            if labels:
                properties["labels"] = ",".join(labels)
                outputs = [{"name": "label_probabilities", "shape": [len(labels)]}]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    if properties:
        provenance["properties"] = f"{source} | Fields: args.loss, labels"

    if outputs:
        provenance["outputs"] = f"{source} | Field: labels (supervised class count)"

    return AiModelMetadata(
        format=AiModelFormat.FASTTEXT,
        framework=framework,
        type_of_model=type_of_model,
        hyperparameters=hyperparameters,
        properties=properties,
        outputs=outputs,
        provenance=provenance,
    )
