# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A PT2 Archive's framework, ``torch_version`` (``models/model.json``) and
parameter count (the stored weights of
``data/weights/model_weights_config.json``).

See also: :mod:`tests.extract.ai_model.test_pytorch_pt2_edge_cases` (the
signature's inputs and outputs).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path
from zipfile import ZipFile

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.model_parameters import PARAMETER_COUNT_PROVENANCE_KEY
from pitloom.extract.ai_model import _pt2_graph
from pitloom.extract.ai_model.archive_member import read_archive_member
from pitloom.extract.ai_model.limits import ModelOverCap
from pitloom.extract.ai_model.pytorch_pt2 import read_pytorch_pt2
from pitloom.messages.files import Cap
from tests.warning_helpers import logged_warnings

from .test_pytorch_pt2 import _make_pt2_zip

_FIXTURE = (
    Path(__file__).parents[2]
    / "fixtures"
    / "aimodels"
    / "pytorch_pt2"
    / "example-model.pt2"
)
_WEIGHTS = "data/weights/model_weights_config.json"
_COUNT = (
    "Source: m.pt2 | Field: data/weights/model_weights_config.json"
    " tensor_meta.sizes"
    " | Method: tensor_element_sum"
)


def _weight(sizes: object, is_param: object = True) -> dict[str, object]:
    return {"path_name": "w", "is_param": is_param, "tensor_meta": {"sizes": sizes}}


def _read(tmp_path: Path, files: dict[str, bytes]) -> AiModelMetadata:
    """Read an archive of *files* under one root directory, as
    ``torch.export.save`` writes them, beside its ``archive_format``."""
    path = tmp_path / "m.pt2"
    members = {"m/archive_format": b"pt2", **{f"m/{k}": v for k, v in files.items()}}
    path.write_bytes(_make_pt2_zip(members))
    return read_pytorch_pt2(path)


def _weights(config: object) -> dict[str, bytes]:
    return {_WEIGHTS: json.dumps({"config": config}).encode()}


def test_the_fixture_is_a_pytorch_export_with_its_count() -> None:
    meta = read_pytorch_pt2(_FIXTURE)
    info = meta.format_info
    assert (info.framework, info.framework_version) == ("pytorch", "2.11.0")
    assert meta.provenance["framework_version"] == (
        "Source: example-model.pt2 | Field: models/model.json torch_version"
    )
    # nn.Linear(10, 1): a 1x10 weight and a bias of 1
    assert meta.parameter_count == 11


def test_parameters_and_buffers_count_as_in_every_format(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _weights(
            {
                "w": _weight([{"as_int": 3}, {"as_int": 4}]),
                "b": _weight([{"as_int": 4}]),
                "running_mean": _weight([{"as_int": 100}], is_param=False),
            }
        ),
    )
    assert meta.parameter_count == 116
    assert meta.provenance[PARAMETER_COUNT_PROVENANCE_KEY] == _COUNT


@pytest.mark.parametrize(
    "files",
    [
        {},
        _weights({}),
        _weights({"empty": _weight([{"as_int": 0}])}),
    ],
    ids=["no-config", "no-weight", "zero-elements"],
)
def test_no_count_and_no_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, files: dict[str, bytes]
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(tmp_path, files)
    assert meta.parameter_count is None
    assert PARAMETER_COUNT_PROVENANCE_KEY not in meta.provenance
    assert not logged_warnings(caplog)


@pytest.mark.parametrize(
    ("files", "said"),
    [
        ({_WEIGHTS: b"{not json"}, "parameter_count"),
        (_weights([]), "parameter_count"),
        (_weights({"w": "x"}), "parameter_count"),
        (_weights({"w": {"is_param": True, "tensor_meta": {}}}), "parameter_count"),
        (_weights({"w": _weight([{"as_expr": {"expr_str": "s0"}}])}), "not a"),
    ],
    ids=["not-json", "config-list", "weight-text", "no-sizes", "symbolic-size"],
)
def test_an_unreadable_config_is_warned_and_gives_no_count(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, files: dict[str, bytes], said: str
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(tmp_path, files)
    assert meta.parameter_count is None
    warnings = logged_warnings(caplog)
    assert len(warnings) == 1
    assert said in warnings[0]


def test_a_torch_version_that_is_no_text_is_not_read(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        {"models/model.json": json.dumps({"torch_version": 2}).encode()},
    )
    assert meta.format_info.framework == "pytorch"
    assert meta.format_info.framework_version is None
    assert "framework_version" not in meta.provenance


def test_an_unparsable_model_json_loses_the_framework_version_too(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(tmp_path, {"models/model.json": b"[]"})
    assert meta.format_info.framework_version is None
    (warning,) = logged_warnings(caplog)
    assert "framework_version" in warning


def test_a_weights_config_over_a_cap_is_not_absorbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A member over the archive-member cap stops the read, as for every
    other member; it is never a mere unreadable config."""
    real = read_archive_member

    def capped(zf: ZipFile, name: str) -> bytes:
        if name.endswith(_WEIGHTS):
            raise ModelOverCap(Cap(1, "byte", "archive-member"))
        return real(zf, name)

    monkeypatch.setattr(_pt2_graph, "read_archive_member", capped)
    with pytest.raises(ModelOverCap):
        _read(tmp_path, _weights({"w": _weight([{"as_int": 1}])}))
