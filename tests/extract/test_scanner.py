# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.scanner.scan_project_for_ai_models().

The "happy path" (a real model file successfully identified and read) is
already exercised indirectly by the higher-level project/document assembly
tests. This module targets the branches those integration tests never hit:
non-model extensions, magic-byte sniffing that comes back UNKNOWN, the
ImportError/generic-exception handlers around read_ai_model(), the
usage-detection debug log, and the file-read failure handler in the
usage-scanning pass.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner import scan_project_for_ai_models

_LOGGER_NAME = "pitloom.extract.scanner"


def _pf(physical_path: str, distribution_path: str | None = None) -> ProjectFile:
    return ProjectFile(
        physical_path=physical_path,
        distribution_path=distribution_path or physical_path,
        digest_sha256="0" * 64,
    )


def _fake_meta(fmt: AiModelFormat = AiModelFormat.GGUF) -> AiModelMetadata:
    return AiModelMetadata(format_info=AiModelFormatInfo(model_format=fmt))


def test_scan_ignores_files_with_non_model_extensions(tmp_path: Path) -> None:
    files = [_pf("README.md"), _pf("setup.py")]
    result = scan_project_for_ai_models(tmp_path, files)
    assert result == []


def test_scan_skips_extension_match_when_format_unknown(tmp_path: Path) -> None:
    # The extension is a candidate (.bin), but magic-byte sniffing comes
    # back UNKNOWN (e.g. a generic data file, not actually an AI model).
    (tmp_path / "weights.bin").write_bytes(b"not really a model")
    files = [_pf("weights.bin")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format",
        return_value=AiModelFormat.UNKNOWN,
    ):
        result = scan_project_for_ai_models(tmp_path, files)

    assert result == []


def test_scan_detects_and_reads_model_successfully(tmp_path: Path) -> None:
    (tmp_path / "model.gguf").write_bytes(b"fake gguf")
    files = [_pf("model.gguf", "dist/model.gguf")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format",
        return_value=AiModelFormat.GGUF,
    ):
        with patch("pitloom.extract.scanner.read_ai_model", return_value=_fake_meta()):
            result = scan_project_for_ai_models(tmp_path, files)

    assert len(result) == 1
    assert result[0].format_info.file_name == "model.gguf"
    assert result[0].format_info.file_path_relative == "dist/model.gguf"
    assert result[0].format_info.physical_path == "model.gguf"


def test_scan_logs_warning_and_continues_on_import_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A recognised format whose optional dependency isn't installed must
    # log a warning (not crash the whole scan) and simply skip that file.
    (tmp_path / "model.h5").write_bytes(b"fake h5")
    files = [_pf("model.h5")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format",
        return_value=AiModelFormat.HDF5,
    ):
        with patch(
            "pitloom.extract.scanner.read_ai_model",
            side_effect=ImportError("h5py is required"),
        ):
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                result = scan_project_for_ai_models(tmp_path, files)

    assert result == []
    assert any("required library not installed" in r.message for r in caplog.records)


def test_scan_logs_warning_and_continues_on_generic_exception(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A corrupt/unreadable model file must not abort the whole scan.
    (tmp_path / "model.onnx").write_bytes(b"corrupt")
    files = [_pf("model.onnx")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format",
        return_value=AiModelFormat.ONNX,
    ):
        with patch(
            "pitloom.extract.scanner.read_ai_model",
            side_effect=ValueError("bad protobuf"),
        ):
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                result = scan_project_for_ai_models(tmp_path, files)

    assert result == []
    assert any("failed to extract metadata" in r.message for r in caplog.records)


def test_scan_finds_usage_of_model_in_python_source(tmp_path: Path) -> None:
    (tmp_path / "model.gguf").write_bytes(b"fake gguf")
    script = tmp_path / "load.py"
    script.write_text('load("model.gguf")\n', encoding="utf-8")
    files = [_pf("model.gguf"), _pf("load.py")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format",
        return_value=AiModelFormat.GGUF,
    ):
        with patch("pitloom.extract.scanner.read_ai_model", return_value=_fake_meta()):
            result = scan_project_for_ai_models(tmp_path, files)

    assert len(result) == 1
    assert "load.py" in result[0].usage_files


def test_scan_no_usage_when_filename_absent_from_source(tmp_path: Path) -> None:
    (tmp_path / "model.gguf").write_bytes(b"fake gguf")
    script = tmp_path / "unrelated.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    files = [_pf("model.gguf"), _pf("unrelated.py")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format",
        return_value=AiModelFormat.GGUF,
    ):
        with patch("pitloom.extract.scanner.read_ai_model", return_value=_fake_meta()):
            result = scan_project_for_ai_models(tmp_path, files)

    assert result[0].usage_files == []


def test_scan_logs_warning_when_python_source_unreadable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A .py file listed but missing/unreadable on disk must not abort the
    # usage-scanning pass -- it's caught, logged, and scanning continues.
    files = [_pf("missing.py")]

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = scan_project_for_ai_models(tmp_path, files)

    assert result == []
    assert any("Could not read text from" in r.message for r in caplog.records)
