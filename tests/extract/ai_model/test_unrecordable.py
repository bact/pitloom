# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The G7 honesty notice: its line, once per model file that holds a value
SPDX 3.0.1 has no property for, silence otherwise, on the library and CLI
surfaces, and no change to the SBOM.

See also: tests/extract/remote/test_huggingface_unrecordable.py (the Hub),
tests/conformance/test_g7ai_unrecordable.py (the names against the mapping).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract.ai_model.unrecordable import (
    NOTICE_LEVEL,
    NOTICE_TEXT,
    Unrecordable,
    log_unrecordable,
    notice_unrecordable,
)
from pitloom.extract.scanner import read_model_candidate
from pitloom.extract.scanner_project import local_model_candidate
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string

_LOGGER = "pitloom.extract.ai_model.unrecordable"
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "aimodels"
_GGUF = _FIXTURES / "gguf" / "stories260K.gguf"
_ARCH = "model-architecture (written in ai_typeOfModel)"


def _notices(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if NOTICE_TEXT in r.getMessage()]


def _entry(element: str, written_in: str | None) -> Unrecordable:
    return Unrecordable(element, written_in, lambda _meta: True)


@pytest.mark.parametrize(
    ("entries", "where", "expected"),
    [
        ([], "m.gguf", None),
        (
            [_entry("b-el", "ai_x"), _entry("a-el", None)],
            "m.gguf",
            "FORMAT=gguf FILE=m.gguf: no SPDX 3.0.1 property: "
            "a-el (not recorded), b-el (written in ai_x)",
        ),
        (
            [_entry("a-el", None)],
            "m\x1b.gguf",
            "FORMAT=gguf FILE='m\\x1b.gguf': no SPDX 3.0.1 property: "
            "a-el (not recorded)",
        ),
    ],
    ids=["none", "sorted-one-line", "escaped-file"],
)
def test_the_notice_line(
    entries: list[Unrecordable],
    where: str,
    expected: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    log_unrecordable("gguf", where, entries)
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == (
        [(NOTICE_LEVEL, expected)] if expected else []
    )


@pytest.mark.parametrize(("architecture", "count"), [("llama", 1), ("", 0), (None, 0)])
def test_only_a_value_read_is_named(
    architecture: str | None, count: int, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        architecture=architecture,
    )
    notice_unrecordable(meta, "gguf", "m.gguf")
    assert len(_notices(caplog)) == count


def _gguf_without_architecture(path: Path) -> Path:
    path.write_bytes(gguf_file(0, 1, kv(b"general.name", STRING, string("m"))))
    return path


def _safetensors(path: Path, metadata: dict[str, str]) -> Path:
    np = pytest.importorskip("numpy")
    save_file = pytest.importorskip("safetensors.numpy").save_file
    save_file({"w": np.zeros((2, 2), dtype=np.float32)}, str(path), metadata=metadata)
    return path


_ST_ARCH = {"modelspec.architecture": "llama"}
_ST_NAME = {"modelspec.title": "m"}


@pytest.mark.parametrize(
    ("make", "fmt", "named"),
    [
        (lambda _tmp: _GGUF, "gguf", True),
        (lambda tmp: _gguf_without_architecture(tmp / "m.gguf"), "gguf", False),
        (lambda tmp: _safetensors(tmp / "m.safetensors", _ST_ARCH), "st", True),
        (lambda tmp: _safetensors(tmp / "m.safetensors", _ST_NAME), "st", False),
        (lambda _tmp: _FIXTURES / "onnx" / "squeezenet1.1-7.onnx", "onnx", False),
        (lambda _tmp: _FIXTURES / "numpy" / "example-model-v1.npy", "npy", False),
        (lambda _tmp: _FIXTURES / "numpy" / "example-model-bundle.npz", "npz", False),
        (lambda _tmp: _FIXTURES / "fasttext" / "sentimentdemo.bin", "ft", False),
    ],
    ids=[
        "gguf",
        "gguf-no-arch",
        "safetensors",
        "safetensors-no-arch",
        "onnx",
        "npy",
        "npz",
        "fasttext",
    ],
)
def test_each_reader_logs_the_notice_once_or_not_at_all(
    make: Callable[[Path], Path],
    fmt: str,
    named: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = make(tmp_path)
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    meta = read_model_candidate(local_model_candidate(path))
    assert meta.format_info.model_format != AiModelFormat.UNKNOWN, fmt
    assert meta.provenance, "the reader ran"
    notices = _notices(caplog)
    if named:
        (record,) = notices
        assert record.levelno == NOTICE_LEVEL
        assert record.getMessage().endswith(f": {NOTICE_TEXT}: {_ARCH}")
        assert f"FORMAT={meta.format_info.model_format} " in record.getMessage()
    else:
        assert not notices


def test_the_sbom_is_the_same_with_and_without_the_notice(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    with_notice = generate_model_sbom(_GGUF)
    assert len(_notices(caplog)) == 1
    caplog.clear()
    with patch(
        "pitloom.extract.ai_model.limits.notice_unrecordable", autospec=True
    ) as silenced:
        without_notice = generate_model_sbom(_GGUF)
    assert silenced.called
    assert not _notices(caplog)
    assert with_notice == without_notice


def test_the_cli_prints_the_notice_once_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["loom", "model", str(_GGUF), "-o", str(out)])
    assert __main__.main() == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if NOTICE_TEXT in line]
    assert len(lines) == 1
    assert lines[0].startswith("INFO: FORMAT=gguf FILE=")
    assert lines[0].endswith(f"stories260K.gguf: {NOTICE_TEXT}: {_ARCH}")
    assert NOTICE_TEXT not in captured.out
