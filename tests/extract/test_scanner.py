# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the surface-agnostic AI model scanner policy.

Uses fake candidates and sources, so no project layout is involved.

See also: :mod:`tests.extract.test_scanner_project` for the project producer.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import contextlib
import io
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract.scanner import (
    ModelCandidate,
    UsageSource,
    attach_usage_references,
    discover_ai_models,
    scan_ai_models,
)
from tests.warning_helpers import file_values

_LOGGER_NAME = "pitloom.extract.scanner"
_READ = "pitloom.extract.scanner.read_ai_model"


def _cand(
    dist: str,
    phys: str | None = None,
    header: bytes = b"",
    materialize: Callable[[], AbstractContextManager[Path]] | None = None,
    sniff: Mock | None = None,
) -> ModelCandidate:
    return ModelCandidate(
        distribution_path=dist,
        physical_path=phys or dist,
        sniff=sniff or Mock(return_value=header),
        materialize=materialize or (lambda: contextlib.nullcontext(Path("unused"))),
    )


def _src(
    dist: str, phys: str | None = None, data: bytes | BaseException = b""
) -> UsageSource:
    def _open() -> AbstractContextManager[io.BytesIO]:
        if isinstance(data, BaseException):
            raise data
        return io.BytesIO(data)

    return UsageSource(
        distribution_path=dist,
        physical_path=phys or dist,
        open=_open,
    )


def _meta(fmt: AiModelFormat = AiModelFormat.ONNX) -> AiModelMetadata:
    return AiModelMetadata(format_info=AiModelFormatInfo(model_format=fmt))


def _file_values(caplog: pytest.LogCaptureFixture) -> list[str]:
    return file_values(r.getMessage() for r in caplog.records)


def _gguf_header() -> bytes:
    fmt = AiModelFormat.GGUF
    assert fmt.magic is not None
    return fmt.magic + b"\x00" * 20


def test_discover_filters_on_distribution_suffix() -> None:
    with patch(_READ, autospec=True, return_value=_meta(AiModelFormat.NUMPY)):
        found = discover_ai_models([_cand("pkg/model.npy", "assets/weights.dat")])
    assert len(found) == 1

    sniff = Mock(return_value=b"")
    with patch(_READ, autospec=True) as reader:
        found = discover_ai_models(
            [_cand("pkg/model.dat", "assets/model.npy", sniff=sniff)]
        )
    assert not found
    sniff.assert_not_called()
    reader.assert_not_called()


def test_discover_unreadable_sniff_warns_once_and_skips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sniff = Mock(side_effect=PermissionError(13, "denied"))
    with patch(_READ, autospec=True) as reader:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            found = discover_ai_models([_cand("pkg/m.bin", "src/m.bin", sniff=sniff)])
    assert not found
    reader.assert_not_called()
    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage().startswith("FORMAT=unknown ")
    assert _file_values(caplog) == ["src/m.bin"]


def test_discover_magic_beats_extension() -> None:
    with patch(_READ, autospec=True, return_value=_meta()) as reader:
        discover_ai_models([_cand("pkg/model.onnx", header=_gguf_header())])
    assert reader.call_args.kwargs["model_format"] == AiModelFormat.GGUF


def test_discover_passes_extension_format_when_no_magic() -> None:
    with patch(_READ, autospec=True, return_value=_meta()) as reader:
        discover_ai_models([_cand("pkg/model.onnx", header=b"")])
    assert reader.call_args.kwargs["model_format"] == AiModelFormat.ONNX


def test_discover_sets_paths_from_candidate() -> None:
    cand = _cand("pkg/model.npy", "assets/weights.dat")
    with patch(_READ, autospec=True, return_value=_meta(AiModelFormat.NUMPY)):
        found = discover_ai_models([cand])
        assert len(found) == 1
        meta = found[0]
    info = meta.format_info
    assert info.file_name == "model.npy"
    assert info.file_path_relative == "pkg/model.npy"
    assert info.physical_path == "assets/weights.dat"


def test_discover_import_error_keeps_stub_with_stable_paths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cand = _cand("pkg/model.npy", "assets/weights.dat")
    with patch(_READ, autospec=True, side_effect=ImportError("numpy")):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            found = discover_ai_models([cand])
            assert len(found) == 1
            stub = found[0]
    info = stub.format_info
    assert info.model_format == AiModelFormat.NUMPY
    assert info.file_name == "model.npy"
    assert info.file_path_relative == "pkg/model.npy"
    assert info.physical_path == "assets/weights.dat"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert _file_values(caplog) == ["assets/weights.dat"]


def test_discover_read_error_warns_with_stable_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cand = _cand("pkg/model.onnx", "src/pkg/model.onnx")
    with patch(_READ, autospec=True, side_effect=ValueError("bad")):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            found = discover_ai_models([cand])
    assert not found
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    assert _file_values(caplog) == ["src/pkg/model.onnx"]


def test_discover_materialize_error_is_a_read_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _boom() -> AbstractContextManager[Path]:
        raise OSError("cannot copy")

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        found = discover_ai_models([_cand("pkg/model.onnx", materialize=_boom)])
    assert not found
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "failed to extract metadata" in messages[0]


def test_discover_unknown_format_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    materialize = Mock()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        found = discover_ai_models(
            [_cand("pkg/notes.bin", header=b"plain text", materialize=materialize)]
        )
    assert not found
    assert not caplog.records
    materialize.assert_not_called()


def test_attach_records_match_and_skips_non_match() -> None:
    meta = _meta()
    meta.format_info.file_name = "model.onnx"
    attach_usage_references(
        [meta],
        [
            _src("pkg/use.py", data=b'load("model.onnx")'),
            _src("pkg/other.py", data=b"print(1)"),
        ],
    )
    assert meta.usage_files == ["pkg/use.py"]


def test_attach_py_filter_uses_distribution_path() -> None:
    meta = _meta()
    meta.format_info.file_name = "model.onnx"
    not_py = Mock()
    attach_usage_references(
        [meta],
        [
            _src("pkg/use.py", "tools/use.txt", data=b"model.onnx"),
            UsageSource("pkg/use.txt", "x.py", not_py),
        ],
    )
    assert meta.usage_files == ["pkg/use.py"]
    not_py.assert_not_called()


def test_attach_read_error_warns_once_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    meta = _meta()
    meta.format_info.file_name = "model.onnx"
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        attach_usage_references(
            [meta],
            [
                _src("pkg/a.py", "src/pkg/a.py", data=OSError("gone")),
                _src("pkg/b.py", "src/pkg/b.py", data=b"model.onnx"),
            ],
        )
    assert _file_values(caplog) == ["src/pkg/a.py"]
    assert len(caplog.records) == 1
    assert meta.usage_files == ["pkg/b.py"]


def test_attach_non_utf8_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        attach_usage_references([_meta()], [_src("pkg/a.py", data=b"\xff\xfe")])
    assert len(caplog.records) == 1
    assert "could not read for usage scanning" in caplog.records[0].getMessage()


def test_attach_runs_with_no_models(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        attach_usage_references([], [_src("pkg/a.py", data=OSError("gone"))])
    assert _file_values(caplog) == ["pkg/a.py"]


def test_scan_ai_models_attaches_usage_to_discovered_models() -> None:
    with patch(_READ, autospec=True, return_value=_meta()):
        found = scan_ai_models(
            [_cand("pkg/model.onnx")],
            [_src("pkg/use.py", data=b'open("model.onnx")')],
        )
        assert len(found) == 1
        meta = found[0]
    assert meta.usage_files == ["pkg/use.py"]
