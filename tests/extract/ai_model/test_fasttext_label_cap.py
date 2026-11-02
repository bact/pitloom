# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the fastText label-count cap (mocked fasttext model).

See also: test_fasttext_mocked.py for the other mocked reader tests.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import MAX_MODEL_ENTRIES
from pitloom.extract.ai_model.fasttext import read_fasttext
from pitloom.messages import over_cap_of

from .test_fasttext_mocked import _make_fasttext_model


def _read(
    tmp_path: Path, labels: list[str], caplog: pytest.LogCaptureFixture
) -> tuple[object, list[logging.LogRecord]]:
    model_file = tmp_path / "clf.bin"
    model_file.write_bytes(b"fake")
    mock_fasttext = MagicMock()
    mock_fasttext.load_model.return_value = _make_fasttext_model(
        labels=labels, model_name="supervised", loss_name="softmax"
    )
    with patch.dict("sys.modules", {"fasttext": mock_fasttext}):
        with caplog.at_level(logging.WARNING):
            meta = read_fasttext(model_file)
    return meta, [r for r in caplog.records if over_cap_of(r) is not None]


def test_labels_at_the_cap_are_recorded_quietly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    labels = [f"__label__{i}" for i in range(MAX_MODEL_ENTRIES)]
    meta, capped = _read(tmp_path, labels, caplog)
    assert json.loads(meta.properties["labels"]) == labels  # type: ignore[attr-defined]
    assert capped == []


@pytest.mark.parametrize("extra", [1, 500], ids=["one-over", "many-over"])
def test_labels_over_the_cap_record_none_with_one_over_cap_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, extra: int
) -> None:
    """A model over the cap keeps its label count (``outputs``) and records
    no label and no label property, with one ``[over-cap]`` warning."""
    count = MAX_MODEL_ENTRIES + extra
    meta, capped = _read(tmp_path, [f"l{i}" for i in range(count)], caplog)
    assert "labels" not in meta.properties  # type: ignore[attr-defined]
    assert "properties.labels" not in meta.provenance  # type: ignore[attr-defined]
    assert meta.outputs == [  # type: ignore[attr-defined]
        {"name": "label_probabilities", "shape": [count]}
    ]
    (record,) = capped
    cap, outcome = over_cap_of(record) or (None, "")
    assert (cap.limit, cap.unit, cap.purpose) == (  # type: ignore[union-attr]
        MAX_MODEL_ENTRIES,
        "label",
        "label-count",
    )
    assert outcome == "no label recorded"
    assert f"{MAX_MODEL_ENTRIES}-label label-count cap" in record.getMessage()
