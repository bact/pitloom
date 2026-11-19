# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Orbax (JAX) checkpoint reader and folder detection."""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model.directory import (
    detect_directory_format,
    directory_models_in,
)
from pitloom.extract.ai_model.jax import MAX_ORBAX_JSON_BYTES, read_jax
from pitloom.extract.ai_model.limits import ModelOverCap
from pitloom.extract.ai_model.reader import detect_ai_model_format, read_ai_model

pytestmark = pytest.mark.platform

_MARKER = "_CHECKPOINT_METADATA"


def _step(
    root: Path, marker: object | None = None, items: tuple[str, ...] = ()
) -> Path:
    """A step folder: the marker, and each of *items* with a ``_METADATA``."""
    step = root / "0"
    step.mkdir()
    body = (
        marker
        if marker is not None
        else {
            "item_handlers": dict.fromkeys(items, "h"),
            "metrics": {},
            "init_timestamp_nsecs": 1,
        }
    )
    (step / _MARKER).write_text(json.dumps(body))
    for name in items:
        (step / name).mkdir()
        (step / name / "_METADATA").write_text(
            json.dumps({"tree_metadata": {"('w',)": {"value_type": "jax.Array"}}})
        )
    return step


def _library(shapes: Mapping[str, Sequence[tuple[int, ...]]]) -> MagicMock:
    """A stand-in ``orbax.checkpoint`` giving *shapes* per item folder."""
    ocp = MagicMock()

    def metadata(folder: Path) -> SimpleNamespace:
        return SimpleNamespace(
            tree={
                f"a{i}": SimpleNamespace(shape=s)
                for i, s in enumerate(shapes[Path(folder).name])
            }
        )

    ocp.PyTreeCheckpointer.return_value.metadata.side_effect = metadata
    return ocp


def _with(ocp: MagicMock) -> dict[str, MagicMock]:
    """``sys.modules`` entries making ``import orbax.checkpoint`` give *ocp*."""
    return {"orbax": MagicMock(checkpoint=ocp), "orbax.checkpoint": ocp}


def _no_library() -> dict[str, None]:
    return {"orbax": None, "orbax.checkpoint": None}


def test_detect_and_read_without_library(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    step = _step(tmp_path, items=("params",))
    assert detect_directory_format(step) == AiModelFormat.JAX
    assert detect_ai_model_format(step) == AiModelFormat.JAX
    with caplog.at_level(logging.INFO), patch.dict("sys.modules", _no_library()):
        meta = read_ai_model(step)
    assert meta.format_info.model_format == AiModelFormat.JAX
    assert meta.format_info.framework == "orbax"
    assert meta.parameter_count is None
    assert meta.properties["items.params.arrays"] == "1"
    assert meta.properties["item_handlers.params"] == "h"
    assert sum("pitloom[jax]" in r.getMessage() for r in caplog.records) == 1
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_parameter_count_sums_every_item(tmp_path: Path) -> None:
    step = _step(tmp_path, items=("params", "opt"))
    shapes = {"params": [(4, 8), (8,)], "opt": [(), (2, 2)]}
    with patch.dict("sys.modules", _with(_library(shapes))):
        meta = read_jax(step)
    assert meta.parameter_count == 32 + 8 + 1 + 4


def test_library_failure_keeps_other_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    step = _step(tmp_path, items=("params",))
    ocp = MagicMock()
    ocp.PyTreeCheckpointer.return_value.metadata.side_effect = ValueError("damaged")
    with (
        caplog.at_level(logging.INFO),
        patch.dict("sys.modules", _with(ocp)),
    ):
        meta = read_jax(step)
    assert meta.parameter_count is None
    assert meta.properties["items.params.arrays"] == "1"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "parameter_count" in warnings[0].getMessage()


def test_untrusted_clone_skips_library(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    step = _step(tmp_path, items=("params",))
    lib = _library({"params": [(2,)]})
    with (
        caplog.at_level(logging.INFO),
        patch("pitloom.extract.ai_model.jax.in_remote_clone", return_value=True),
        patch("pitloom.extract.ai_model.jax.remote_clone_trusted", return_value=False),
        patch.dict("sys.modules", _with(lib)),
    ):
        meta = read_jax(step)
    assert meta.parameter_count is None
    lib.PyTreeCheckpointer.assert_not_called()
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_custom_and_metrics_kept_verbatim(tmp_path: Path) -> None:
    step = _step(
        tmp_path,
        {
            "item_handlers": {},
            "metrics": {"loss": 0.5},
            "custom_metadata": {"model_name": "x"},
        },
    )
    with patch.dict("sys.modules", _no_library()):
        meta = read_jax(step)
    assert meta.properties["custom.model_name"] == "x"
    assert meta.properties["metrics.loss"] == "0.5"
    assert meta.name is None  # not guessed from custom metadata


@pytest.mark.parametrize(
    "marker",
    ["not json", "[1]", '{"no": "handlers"}', '{"item_handlers": []}'],
    ids=["garbage", "list", "no-handlers", "handlers-list"],
)
def test_malformed_marker_refused(tmp_path: Path, marker: str) -> None:
    step = tmp_path / "0"
    step.mkdir()
    (step / _MARKER).write_text(marker)
    with pytest.raises(ValueError):
        read_jax(step)


def test_oversize_marker_refused(tmp_path: Path) -> None:
    step = _step(tmp_path)
    (step / _MARKER).write_bytes(b" " * (MAX_ORBAX_JSON_BYTES + 1))
    with pytest.raises(ModelOverCap):
        read_jax(step)


def test_detection_ignores_non_regular_marker(tmp_path: Path) -> None:
    step = tmp_path / "0"
    (step / _MARKER).mkdir(parents=True)
    assert detect_directory_format(step) == AiModelFormat.UNKNOWN
    assert detect_directory_format(tmp_path / "missing") == AiModelFormat.UNKNOWN


def test_directory_models_in_limit(tmp_path: Path) -> None:
    _step(tmp_path, items=())
    (tmp_path / "other").mkdir()
    assert directory_models_in(tmp_path) == [("0", AiModelFormat.JAX)]
    assert directory_models_in(tmp_path, limit=1) is None
