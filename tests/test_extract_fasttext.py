# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the fastText metadata extractor (mocked and integration)."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict, cast
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import (
    detect_ai_model_format,
    read_fasttext,
)

# ---------------------------------------------------------------------------
# fastText extractor (mocked)
# ---------------------------------------------------------------------------

# The Python fasttext package exposes training configuration via the C++
# binding at model.f.getArgs().  Loss and model type are enum objects whose
# .name attribute gives the string value (e.g. "softmax", "supervised").


class _FasttextArgsConfig(TypedDict, total=False):
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


def test_fasttext_load_failure(tmp_path: Path) -> None:
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"corrupt")

    mock_fasttext = MagicMock()
    mock_fasttext.load_model.side_effect = OSError("bad file")

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        with pytest.raises(ValueError, match="Failed to load fastText"):
            read_fasttext(model_file)


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

    assert meta.format == AiModelFormat.FASTTEXT
    assert meta.type_of_model == "skipgram"
    assert meta.hyperparameters["dim"] == 300
    assert meta.hyperparameters["lr"] == 0.025
    assert meta.hyperparameters["epoch"] == 10
    assert meta.properties["lossName"] == "ns"
    assert "hyperparameters" in meta.provenance
    assert "type_of_model" in meta.provenance
    assert "properties" in meta.provenance


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


def test_fasttext_ftz_extension(tmp_path: Path) -> None:
    model_file = tmp_path / "model.ftz"
    model_file.write_bytes(b"fake")

    mock_model = _make_fasttext_model(model_name="cbow")
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        meta = read_fasttext(model_file)

    assert meta.format == AiModelFormat.FASTTEXT
    assert meta.type_of_model == "cbow"


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


# ---------------------------------------------------------------------------
# Integration tests — real fastText file (fasttext/sentimentdemo.bin)
# Thai text sentiment classifier; 4 labels: pos, neg, neu, q
# Require: fasttext installed AND tests/fixtures/fasttext/sentimentdemo.bin present
# ---------------------------------------------------------------------------

_FT = Path(__file__).parent / "fixtures" / "fasttext"
SENTIMENT_DEMO_FIXTURE = _FT / "sentimentdemo.bin"


@pytest.fixture(scope="module")
def sentiment_demo_metadata() -> AiModelMetadata:
    """Extract metadata from sentimentdemo.bin once per session."""
    pytest.importorskip("fasttext")
    if not SENTIMENT_DEMO_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SENTIMENT_DEMO_FIXTURE}")
    return read_fasttext(SENTIMENT_DEMO_FIXTURE)


def test_sentiment_demo_format(sentiment_demo_metadata: AiModelMetadata) -> None:
    assert sentiment_demo_metadata.format == AiModelFormat.FASTTEXT


def test_sentiment_demo_type_of_model(sentiment_demo_metadata: AiModelMetadata) -> None:
    assert sentiment_demo_metadata.type_of_model == "supervised"
    assert "args.model" in sentiment_demo_metadata.provenance["type_of_model"]


def test_sentiment_demo_hyperparameters(
    sentiment_demo_metadata: AiModelMetadata,
) -> None:
    hp = sentiment_demo_metadata.hyperparameters
    assert hp["dim"] == 21
    assert hp["lr"] == pytest.approx(0.05)
    assert hp["epoch"] == 100
    assert hp["wordNgrams"] == 4
    assert hp["minCount"] == 1
    assert hp["minCountLabel"] == 0
    assert hp["minn"] == 3
    assert hp["maxn"] == 6
    assert hp["neg"] == 5
    assert hp["bucket"] == 33502
    assert hp["ws"] == 5
    assert "hyperparameters" in sentiment_demo_metadata.provenance


def test_sentiment_demo_loss(sentiment_demo_metadata: AiModelMetadata) -> None:
    assert sentiment_demo_metadata.properties["lossName"] == "softmax"


def test_sentiment_demo_labels(sentiment_demo_metadata: AiModelMetadata) -> None:
    labels_str = sentiment_demo_metadata.properties["labels"]
    labels = labels_str.split(",")
    assert set(labels) == {"__label__pos", "__label__neu", "__label__neg", "__label__q"}


def test_sentiment_demo_no_name_description_version(
    sentiment_demo_metadata: AiModelMetadata,
) -> None:
    assert sentiment_demo_metadata.name is None
    assert sentiment_demo_metadata.description is None
    assert sentiment_demo_metadata.version is None


def test_sentiment_demo_magic_bytes_detect() -> None:
    """Magic byte sniffing must identify sentimentdemo.bin as FASTTEXT."""
    if not SENTIMENT_DEMO_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SENTIMENT_DEMO_FIXTURE}")
    assert detect_ai_model_format(SENTIMENT_DEMO_FIXTURE) == AiModelFormat.FASTTEXT


# ---------------------------------------------------------------------------
# Integration tests — real fastText file (fasttext/lid.176.ftz)
# Facebook language identification model; 176 language labels
# Require: fasttext installed AND tests/fixtures/fasttext/lid.176.ftz present
# ---------------------------------------------------------------------------

LID_176_FIXTURE = _FT / "lid.176.ftz"


@pytest.fixture(scope="module")
def lid_176_metadata() -> AiModelMetadata:
    """Extract metadata from lid.176.ftz once per session."""
    pytest.importorskip("fasttext")
    if not LID_176_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {LID_176_FIXTURE}")
    return read_fasttext(LID_176_FIXTURE)


def test_lid_176_format(lid_176_metadata: AiModelMetadata) -> None:
    assert lid_176_metadata.format == AiModelFormat.FASTTEXT


def test_lid_176_type_of_model(lid_176_metadata: AiModelMetadata) -> None:
    assert lid_176_metadata.type_of_model == "supervised"


def test_lid_176_hyperparameters(lid_176_metadata: AiModelMetadata) -> None:
    hp = lid_176_metadata.hyperparameters
    assert hp["dim"] == 16
    assert hp["lr"] == pytest.approx(0.05)
    assert hp["epoch"] == 5
    assert hp["wordNgrams"] == 1
    assert hp["minCount"] == 1000
    assert hp["minCountLabel"] == 0
    assert hp["minn"] == 2
    assert hp["maxn"] == 4
    assert hp["neg"] == 5
    assert hp["bucket"] == 2000000
    assert hp["ws"] == 5
    assert "hyperparameters" in lid_176_metadata.provenance


def test_lid_176_loss(lid_176_metadata: AiModelMetadata) -> None:
    assert lid_176_metadata.properties["lossName"] == "hs"


def test_lid_176_labels(lid_176_metadata: AiModelMetadata) -> None:
    labels_str = lid_176_metadata.properties["labels"]
    labels = labels_str.split(",")
    assert len(labels) == 176
    assert "__label__en" in labels
    assert "__label__de" in labels


def test_lid_176_no_name_description_version(
    lid_176_metadata: AiModelMetadata,
) -> None:
    assert lid_176_metadata.name is None
    assert lid_176_metadata.description is None
    assert lid_176_metadata.version is None


def test_lid_176_extension_detect() -> None:
    """Extension-based detection must identify lid.176.ftz as FASTTEXT."""
    if not LID_176_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {LID_176_FIXTURE}")
    assert detect_ai_model_format(LID_176_FIXTURE) == AiModelFormat.FASTTEXT
