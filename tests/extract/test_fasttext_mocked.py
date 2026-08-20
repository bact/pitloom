# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the fastText metadata extractor (mocked fasttext model).

See also: test_fasttext_integration.py for the real-fixture integration
tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypedDict, cast
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_fasttext

# The Python fasttext package exposes training configuration via the C++
# binding at model.f.getArgs().  Loss and model type are enum objects whose
# .name attribute gives the string value (e.g. "softmax", "supervised").


class _FasttextArgsConfig(TypedDict, total=True):
    model_name: str
    loss_name: str
    dim: int
    lr: float
    epoch: int
    word_ngrams: int
    min_count: int
    min_count_label: int
    minn: int
    maxn: int
    neg: int
    bucket: int
    ws: int


_FASTTEXT_ARGS_DEFAULTS: _FasttextArgsConfig = {
    "model_name": "skipgram",
    "loss_name": "ns",
    "dim": 100,
    "lr": 0.05,
    "epoch": 5,
    "word_ngrams": 1,
    "min_count": 5,
    "min_count_label": 0,
    "minn": 3,
    "maxn": 6,
    "neg": 5,
    "bucket": 2000000,
    "ws": 5,
}


def _make_fasttext_args(config: _FasttextArgsConfig) -> MagicMock:
    """Build a mock Args object as returned by model.f.getArgs().

    All keys must be present in *config*; merge with
    :data:`_FASTTEXT_ARGS_DEFAULTS` before calling when supplying partial
    overrides.
    """
    mock_loss = MagicMock()
    mock_loss.name = config["loss_name"]
    mock_model_enum = MagicMock()
    mock_model_enum.name = config["model_name"]

    args = MagicMock()
    args.dim = config["dim"]
    args.lr = config["lr"]
    args.epoch = config["epoch"]
    args.wordNgrams = config["word_ngrams"]
    args.minCount = config["min_count"]
    args.minCountLabel = config["min_count_label"]
    args.minn = config["minn"]
    args.maxn = config["maxn"]
    args.neg = config["neg"]
    args.bucket = config["bucket"]
    args.ws = config["ws"]
    args.loss = mock_loss
    args.model = mock_model_enum
    return args


def _make_fasttext_model(
    labels: list[str] | None = None,
    **kwargs: Any,
) -> MagicMock:
    """Build a mock fasttext model backed by a mock args object."""
    config = cast(_FasttextArgsConfig, {**_FASTTEXT_ARGS_DEFAULTS, **kwargs})
    mock_args = _make_fasttext_args(config)
    mock_f = MagicMock()
    mock_f.getArgs.return_value = mock_args

    mock_model = MagicMock()
    mock_model.f = mock_f
    mock_model.get_labels.return_value = labels or []
    return mock_model


def test_fasttext_missing_library(tmp_path: Path) -> None:
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")
    with patch.dict("sys.modules", {"fasttext": None}):
        with pytest.raises(ImportError, match="fasttext"):
            read_fasttext(model_file)


def test_fasttext_load_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"corrupt")

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.side_effect = OSError("bad file")

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._fasttext"):
            with pytest.raises(ValueError, match="Failed to load fastText"):
                read_fasttext(model_file)

    # Load failure is now logged at debug level before being re-raised.
    assert any("model.bin" in r.message for r in caplog.records)


def test_fasttext_get_args_failure_logs_and_returns_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """model.f.getArgs() failing (e.g. an unexpected binding version) is
    caught, logged, and hyperparameters/type_of_model fall back to empty/None
    rather than raising."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    mock_model = MagicMock()
    mock_model.f.getArgs.side_effect = RuntimeError("binding mismatch")
    mock_model.get_labels.return_value = []

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._fasttext"):
            meta = read_fasttext(model_file)

    assert meta.hyperparameters == {}
    assert meta.type_of_model is None
    assert any("getArgs" in r.message for r in caplog.records)


def test_fasttext_get_labels_failure_logs_and_returns_empty_outputs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """model.get_labels() failing is caught, logged, and outputs/labels fall
    back to empty rather than raising."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model()
    mock_model.get_labels.side_effect = RuntimeError("binding mismatch")

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        with caplog.at_level(logging.DEBUG, logger="pitloom.extract._fasttext"):
            meta = read_fasttext(model_file)

    assert meta.outputs == []
    assert "labels" not in meta.properties
    assert any("labels" in r.message for r in caplog.records)


def test_fasttext_basic_extraction(tmp_path: Path) -> None:
    model_file = tmp_path / "skipgram.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model(
        model_name="skipgram", dim=300, lr=0.025, epoch=10
    )
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.format_info.model_format == AiModelFormat.FASTTEXT
    assert meta.type_of_model == "skipgram"
    assert meta.hyperparameters["dim"] == 300
    assert meta.hyperparameters["lr"] == 0.025
    assert meta.hyperparameters["epoch"] == 10
    assert meta.properties["lossName"] == "ns"
    assert any(k.startswith("hyperparameters.") for k in meta.provenance)
    assert "type_of_model" in meta.provenance
    assert any(k.startswith("properties.") for k in meta.provenance)


def test_fasttext_all_hyperparameters(tmp_path: Path) -> None:
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model(
        word_ngrams=2,
        min_count=3,
        min_count_label=1,
        minn=2,
        maxn=5,
        neg=10,
        bucket=1000000,
        ws=3,
    )
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    hp = meta.hyperparameters
    assert hp["wordNgrams"] == 2
    assert hp["minCount"] == 3
    assert hp["minCountLabel"] == 1
    assert hp["minn"] == 2
    assert hp["maxn"] == 5
    assert hp["neg"] == 10
    assert hp["bucket"] == 1000000
    assert hp["ws"] == 3


def test_fasttext_supervised_with_labels(tmp_path: Path) -> None:
    model_file = tmp_path / "classifier.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model(
        model_name="supervised",
        loss_name="softmax",
        dim=100,
        labels=["__label__pos", "__label__neg"],
    )
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.type_of_model == "supervised"
    assert meta.properties["lossName"] == "softmax"
    assert "__label__pos" in meta.properties["labels"]
    assert "__label__neg" in meta.properties["labels"]


def test_fasttext_supervised_outputs_label_count(tmp_path: Path) -> None:
    model_file = tmp_path / "classifier.bin"
    model_file.write_bytes(b"fake")

    labels = ["__label__pos", "__label__neg", "__label__neu"]
    mock_model = _make_fasttext_model(
        model_name="supervised", loss_name="softmax", labels=labels
    )
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert len(meta.outputs) == 1
    assert meta.outputs[0]["name"] == "label_probabilities"
    assert meta.outputs[0]["shape"] == [3]
    assert "outputs" in meta.provenance


def test_fasttext_unsupervised_no_outputs(tmp_path: Path) -> None:
    model_file = tmp_path / "skipgram.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model(model_name="skipgram", labels=[])
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.outputs == []


def test_fasttext_ftz_extension(tmp_path: Path) -> None:
    model_file = tmp_path / "model.ftz"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model(model_name="cbow")
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.format_info.model_format == AiModelFormat.FASTTEXT
    assert meta.type_of_model == "cbow"


def test_fasttext_args_partial_attributes_skip_none_values(tmp_path: Path) -> None:
    """When getattr(args, attr, None) returns None for some hyperparameter
    attrs (e.g. an older binding missing a field), those keys are simply
    skipped rather than added with a None value."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    class _PartialArgs:
        # Only "dim" is present; all other hyperparameter attrs are absent,
        # so getattr(..., None) falls back to None and is skipped.
        dim = 100
        loss = None
        model = None

    mock_f = MagicMock()
    mock_f.getArgs.return_value = _PartialArgs()

    mock_model = MagicMock(spec=["f"])
    mock_model.f = mock_f

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.hyperparameters == {"dim": 100}
    assert "lr" not in meta.hyperparameters
    assert meta.type_of_model is None
    assert meta.properties == {}
    assert meta.outputs == []


def test_fasttext_no_loss_attribute_skips_loss_name(tmp_path: Path) -> None:
    """When args.loss is absent/falsy, "lossName" is not added to
    properties and no properties.lossName provenance entry is recorded."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model()
    mock_model.f.getArgs.return_value.loss = None

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert "lossName" not in meta.properties
    assert "properties.lossName" not in meta.provenance


def test_fasttext_no_get_labels_method_returns_empty_outputs(
    tmp_path: Path,
) -> None:
    """When the model object has no get_labels attribute at all (as opposed
    to it raising), properties/outputs stay empty without touching
    get_labels."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    mock_f = MagicMock()
    mock_f.getArgs.return_value = _make_fasttext_args(_FASTTEXT_ARGS_DEFAULTS)

    mock_model = MagicMock(spec=["f"])
    mock_model.f = mock_f

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.outputs == []
    assert "labels" not in meta.properties


def test_fasttext_no_name_or_description(tmp_path: Path) -> None:
    """fastText models do not store a name or description field."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model()
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.name is None
    assert meta.description is None
    assert meta.version is None
