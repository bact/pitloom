# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the fastText metadata extractor against real
fastText model fixtures (sentimentdemo.bin, lid.176.ftz).

See also: test_fasttext_mocked.py for the mocked fasttext model unit tests.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=use-implicit-booleaness-not-comparison

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.extract.ai_model import detect_ai_model_format, read_fasttext

# ---------------------------------------------------------------------------
# Integration tests -- real fastText file (fasttext/sentimentdemo.bin)
# Thai text sentiment classifier; 4 labels: pos, neg, neu, q
# Require: fasttext installed AND
#          tests/fixtures/aimodels/fasttext/sentimentdemo.bin present
# ---------------------------------------------------------------------------

_FT = Path(__file__).parent.parent / "fixtures" / "aimodels" / "fasttext"
SENTIMENT_DEMO_FIXTURE = _FT / "sentimentdemo.bin"


@pytest.fixture(scope="module")
def sentiment_demo_metadata() -> AiModelMetadata:
    """Extract metadata from sentimentdemo.bin once per session."""
    pytest.importorskip("fasttext")
    if not SENTIMENT_DEMO_FIXTURE.exists():
        pytest.skip(f"Fixture file not found: {SENTIMENT_DEMO_FIXTURE}")
    return read_fasttext(SENTIMENT_DEMO_FIXTURE)


def test_sentiment_demo_format(sentiment_demo_metadata: AiModelMetadata) -> None:
    assert sentiment_demo_metadata.format_info.model_format == AiModelFormat.FASTTEXT


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
    assert any(
        k.startswith("hyperparameters.") for k in sentiment_demo_metadata.provenance
    )


def test_sentiment_demo_loss(sentiment_demo_metadata: AiModelMetadata) -> None:
    assert sentiment_demo_metadata.properties["lossName"] == "softmax"


def test_sentiment_demo_labels(sentiment_demo_metadata: AiModelMetadata) -> None:
    labels_str = sentiment_demo_metadata.properties["labels"]
    labels = labels_str.split(",")
    assert set(labels) == {"__label__pos", "__label__neu", "__label__neg", "__label__q"}


def test_sentiment_demo_outputs(sentiment_demo_metadata: AiModelMetadata) -> None:
    # Supervised model with 4 labels -> outputs[0].shape == [4]
    assert len(sentiment_demo_metadata.outputs) == 1
    assert sentiment_demo_metadata.outputs[0]["shape"] == [4]
    assert "outputs" in sentiment_demo_metadata.provenance


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
# Integration tests -- real fastText file (fasttext/lid.176.ftz)
# Facebook language identification model; 176 language labels
# Require: fasttext installed AND
#          tests/fixtures/aimodels/fasttext/lid.176.ftz present
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
    assert lid_176_metadata.format_info.model_format == AiModelFormat.FASTTEXT


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
    assert any(k.startswith("hyperparameters.") for k in lid_176_metadata.provenance)


def test_lid_176_loss(lid_176_metadata: AiModelMetadata) -> None:
    assert lid_176_metadata.properties["lossName"] == "hs"


def test_lid_176_labels(lid_176_metadata: AiModelMetadata) -> None:
    labels_str = lid_176_metadata.properties["labels"]
    labels = labels_str.split(",")
    assert len(labels) == 176
    assert "__label__en" in labels
    assert "__label__de" in labels


def test_lid_176_outputs(lid_176_metadata: AiModelMetadata) -> None:
    # 176 language labels -> outputs[0].shape == [176]
    assert len(lid_176_metadata.outputs) == 1
    assert lid_176_metadata.outputs[0]["shape"] == [176]


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
