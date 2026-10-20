# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.dataset_names`: when two spellings are one
dataset, and the cap on a model card's ``datasets:`` list, on the local
model card as well as the Hub's.

See also: tests/extract/remote/test_huggingface_dataset_names.py (the Hub
model card).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.dataset_names import (
    CARD_DATASETS_CAP,
    MAX_CARD_DATASETS,
    dataset_key,
    distinct_dataset_names,
)
from pitloom.enrich.readme import ReadmeEnricher


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("O/D", "o/d"),
        ("Allenai/C4", "allenai/c4"),
        ("C4", "c4"),
        ("My  Web\tCorpus", "My Web Corpus"),  # not an id: the case is kept
        ("o /d", "o /d"),
        ("O/d.git", "O/d.git"),  # not an id either
        ("", ""),
    ],
)
def test_dataset_key(name: str, key: str) -> None:
    assert dataset_key(name) == key


def test_the_cap_cuts_in_order_and_counts_distinct_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    names = ["O/D", "o/d", *(f"o/e{i}" for i in range(MAX_CARD_DATASETS))]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        kept = distinct_dataset_names(names, CARD_DATASETS_CAP, "card.md")
    assert kept == ["O/D", *(f"o/e{i}" for i in range(MAX_CARD_DATASETS - 1))]
    assert caplog.messages == [
        f"FILE=card.md: larger than the {MAX_CARD_DATASETS}-dataset "
        f"model-card-datasets cap; the first {MAX_CARD_DATASETS} kept"
    ]


def _enrich(directory: Path, datasets: list[str], existing: list[str]) -> list[str]:
    lines = "".join(f"  - '{name}'\n" for name in datasets)
    (directory / "README.md").write_text(
        f"---\ndatasets:\n{lines}---\n", encoding="utf-8"
    )
    model = AiModelMetadata(
        datasets=[
            DatasetReference("trainedOn", DatasetMetadata(name=name))
            for name in existing
        ]
    )
    ReadmeEnricher().enrich(model, model_dir=directory)
    return [ref.metadata.name for ref in model.datasets]


@pytest.mark.parametrize(
    ("listed", "existing", "names"),
    [
        (["O/D", " o/d ", "o/e"], [], ["O/D", "o/e"]),
        (["O/D", "o/e"], ["o/d"], ["o/d", "o/e"]),  # one the model already has
        (["Some  corpus", "some corpus"], [], ["Some  corpus", "some corpus"]),
    ],
    ids=["listed-twice", "already-present", "plain-names"],
)
def test_the_local_model_card_lists_each_dataset_once(
    tmp_path: Path, listed: list[str], existing: list[str], names: list[str]
) -> None:
    assert _enrich(tmp_path, listed, existing) == names


def test_the_local_model_card_cap(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    listed = [f"o/d{i}" for i in range(MAX_CARD_DATASETS + 2)]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        names = _enrich(tmp_path, listed, [])
    assert names == listed[:MAX_CARD_DATASETS]
    (message,) = caplog.messages
    assert message.startswith(f"FILE={tmp_path / 'README.md'}: larger than the")
    assert f"the first {MAX_CARD_DATASETS} kept" in message
