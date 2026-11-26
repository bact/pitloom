# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``dataset-conflict`` line names its model: by its file (``FILE=``, a
wheel member by its path in the wheel, never a temporary copy), else by
its name (``MODEL=``), so two models of one wheel can be told apart.

See also: :mod:`tests.messages.test_datasets` (the entry) and
:mod:`tests.extract.ai_model.test_gguf_dataset_conflicts` (said once).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import re
import struct
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.dataset import dataset_model
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import (
    MAX_MODEL_NAME_CHARS,
    AiModelFormat,
    AiModelFormatInfo,
    AiModelMetadata,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import trusted_message
from pitloom.messages.datasets import DATASET_CONFLICT, DatasetModel
from tests._wheel_fixtures import run_cli
from tests._wheel_models import write_model_wheel
from tests.extract.ai_model.gguf_builders import STRING, UINT32, gguf_file, kv, string

pytestmark = pytest.mark.platform

_CREATED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_TAIL = "references differ; kept the first"
#: The ``FILE=`` value of a conflict line or a model's over-cap line.
_FILE_FIELD = r"FILE=(.*?)(?: DATASET=|: larger)"


def _text(key: str, value: str) -> bytes:
    return kv(key.encode(), STRING, string(value))


def _gguf(*urls: str) -> bytes:
    """A GGUF naming dataset ``d`` at version 1 once per URL of *urls*."""
    pairs = [kv(b"general.dataset.count", UINT32, struct.pack("<I", len(urls)))]
    for index, url in enumerate(urls):
        pairs += [
            _text(f"general.dataset.{index}.name", "d"),
            _text(f"general.dataset.{index}.version", "1"),
            _text(f"general.dataset.{index}.repo_url", f"https://x.org/{url}"),
        ]
    return gguf_file(0, len(pairs), b"".join(pairs))


def test_two_models_of_one_wheel_are_told_apart_by_their_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One conflict in each model, both of one file name: each line names
    its member, said once each, trusted as the entry."""
    pytest.importorskip("gguf")
    wheel = write_model_wheel(
        tmp_path, {"demo/a/m.gguf": _gguf("a", "b"), "demo/b/m.gguf": _gguf("c", "d")}
    )
    run = run_cli(
        monkeypatch,
        capsys,
        "wheel",
        wheel,
        "--trust-model-files",
        "-o",
        tmp_path / "o.json",
        "--creation-datetime",
        "2026-01-01T00:00:00Z",
    )
    assert run.status == 0, run.err
    lines = [line for line in run.err if _TAIL in line]
    assert lines == [
        f"WARNING: FILE={member} DATASET='d' FIELD=download_url: {_TAIL} "
        "[dataset-conflict]"
        for member in ("demo/a/m.gguf", "demo/b/m.gguf")
    ]
    assert all(trusted_message(line) is DATASET_CONFLICT for line in lines)


def _two_releases(**model: Any) -> AiModelMetadata:
    return AiModelMetadata(
        datasets=[
            DatasetReference("trainedOn", DatasetMetadata(name="d", version=v))
            for v in ("1", "2")
        ],
        **model,
    )


@pytest.mark.parametrize(
    ("model", "subject"),
    [
        ({"name": "org/tiny"}, "MODEL='org/tiny'"),
        # a Hub model: no file, named by its name, not its URL
        ({"name": "org/tiny", "url": "https://huggingface.co/org/tiny"},
         "MODEL='org/tiny'"),
        (
            {"format_info": AiModelFormatInfo(file_name="t.onnx")},
            "FILE=t.onnx",
        ),
    ],
    ids=["named", "hub", "file"],
)  # fmt: skip
def test_the_assembler_names_the_model_by_its_file_else_its_name(
    caplog: pytest.LogCaptureFixture, model: dict[str, Any], subject: str
) -> None:
    with caplog.at_level(logging.WARNING):
        build_model(_two_releases(**model), _CREATED)
    said = [
        f"WARNING: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
        if getattr(r, CODE_ATTR, None) == "dataset-conflict"
    ]
    assert said == [
        f"WARNING: {subject} DATASET='d' FIELD=version: {_TAIL} [dataset-conflict]"
    ]
    assert trusted_message(said[0]) is DATASET_CONFLICT


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (
            {"physical_path": "p/m.gguf", "file_path_relative": "r", "file_name": "n"},
            DatasetModel(file="p/m.gguf"),
        ),
        ({"physical_path": "", "file_path_relative": "r/m", "file_name": "n"},
         DatasetModel(file="r/m")),
        ({"physical_path": None, "file_path_relative": "", "file_name": "n"},
         DatasetModel(file="n")),
        ({"file_name": ""}, DatasetModel(name="gguf")),  # the format, shown
    ],
    ids=["physical", "relative", "file-name", "no-file"],
)  # fmt: skip
def test_the_model_is_named_by_its_first_stated_path(
    paths: dict[str, Any], expected: DatasetModel
) -> None:
    """An empty path is no path: the next one names the model."""
    info = AiModelFormatInfo(model_format=AiModelFormat.GGUF, **paths)
    assert dataset_model(AiModelMetadata(format_info=info)) == expected


@pytest.mark.parametrize(
    "paths",
    [
        {"physical_path": "p/m.gguf", "file_name": "m.gguf"},
        {"file_path_relative": "r/m.gguf", "file_name": "m.gguf"},
        {"file_name": "m.gguf"},
        {"physical_path": "p q/m\n.gguf"},
    ],
    ids=["physical", "relative", "file-name", "hostile"],
)
def test_a_conflict_names_the_model_as_its_own_warnings_do(
    caplog: pytest.LogCaptureFixture, paths: dict[str, Any]
) -> None:
    """Drift guard: the ``dataset-conflict`` line and the model's own
    ``over-cap`` line (``_model_where``) give one ``FILE=`` value. A model
    with no file is left out: its conflict says ``MODEL=<name>`` where its
    other lines fall back to the URL, by design."""
    info = AiModelFormatInfo(model_format=AiModelFormat.GGUF, **paths)
    model = _two_releases(format_info=info)
    long_name = "d" * (MAX_MODEL_NAME_CHARS + 1)
    model.datasets = [
        DatasetReference("trainedOn", DatasetMetadata(name=long_name, version=v))
        for v in ("1", "2")
    ]
    with caplog.at_level(logging.WARNING):
        build_model(model, _CREATED)
    files = {
        getattr(r, CODE_ATTR): re.search(_FILE_FIELD, r.getMessage())
        for r in caplog.records
        if getattr(r, CODE_ATTR, None) in ("dataset-conflict", "over-cap")
    }
    conflict, cap = files["dataset-conflict"], files["over-cap"]
    assert conflict and cap and conflict[1] == cap[1]
