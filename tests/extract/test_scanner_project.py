# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.scanner_project.scan_project_for_ai_models().

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
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import SNIFF_BYTES, read_ai_model_header
from pitloom.extract.scanner_project import (
    project_candidates,
    project_sources,
    scan_project_for_ai_models,
)
from tests.warning_helpers import file_values

_LOGGER_NAME = "pitloom.extract.scanner"

# Evaluated at import on every platform: short-circuit before POSIX-only names.
_CAN_DENY_ACCESS = sys.platform != "win32" and os.geteuid() != 0


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
    assert not result


def test_scan_skips_extension_match_when_format_unknown(tmp_path: Path) -> None:
    # The extension is a candidate (.bin), but magic-byte sniffing comes
    # back UNKNOWN (e.g. a generic data file, not actually an AI model).
    (tmp_path / "weights.bin").write_bytes(b"not really a model")
    files = [_pf("weights.bin")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format_from_header",
        return_value=AiModelFormat.UNKNOWN,
    ):
        result = scan_project_for_ai_models(tmp_path, files)

    assert not result


def test_scan_detects_and_reads_model_successfully(tmp_path: Path) -> None:
    (tmp_path / "model.gguf").write_bytes(b"fake gguf")
    files = [_pf("model.gguf", "dist/model.gguf")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format_from_header",
        return_value=AiModelFormat.GGUF,
    ):
        with patch("pitloom.extract.scanner.read_ai_model", return_value=_fake_meta()):
            result = scan_project_for_ai_models(tmp_path, files)

    assert len(result) == 1
    assert result[0].format_info.file_name == "model.gguf"
    assert result[0].format_info.file_path_relative == "dist/model.gguf"
    assert result[0].format_info.physical_path == "model.gguf"


def test_scan_logs_warning_and_keeps_degraded_record_on_import_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A recognised format whose optional dependency isn't installed must
    # log a warning (not crash the whole scan) and still record the model
    # with degraded (format + filename only) metadata, not drop it.
    (tmp_path / "model.h5").write_bytes(b"fake h5")
    files = [_pf("model.h5")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format_from_header",
        return_value=AiModelFormat.HDF5,
    ):
        with patch(
            "pitloom.extract.scanner.read_ai_model",
            side_effect=ImportError("h5py is required"),
        ):
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                result = scan_project_for_ai_models(tmp_path, files)

    assert len(result) == 1
    assert result[0].name is None
    assert result[0].format_info.model_format == AiModelFormat.HDF5
    assert result[0].format_info.file_name == "model.h5"
    assert any("required library not installed" in r.message for r in caplog.records)


def test_scan_logs_warning_and_continues_on_generic_exception(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A corrupt/unreadable model file must not abort the whole scan.
    (tmp_path / "model.onnx").write_bytes(b"corrupt")
    files = [_pf("model.onnx")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format_from_header",
        return_value=AiModelFormat.ONNX,
    ):
        with patch(
            "pitloom.extract.scanner.read_ai_model",
            side_effect=ValueError("bad protobuf"),
        ):
            with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
                result = scan_project_for_ai_models(tmp_path, files)

    assert not result
    assert any("failed to extract metadata" in r.message for r in caplog.records)


def test_scan_finds_usage_of_model_in_python_source(tmp_path: Path) -> None:
    (tmp_path / "model.gguf").write_bytes(b"fake gguf")
    script = tmp_path / "load.py"
    script.write_text('load("model.gguf")\n', encoding="utf-8")
    files = [_pf("model.gguf"), _pf("load.py")]

    with patch(
        "pitloom.extract.scanner.detect_ai_model_format_from_header",
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
        "pitloom.extract.scanner.detect_ai_model_format_from_header",
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

    assert not result
    assert any("could not read for usage scanning" in r.message for r in caplog.records)


def _file_values(caplog: pytest.LogCaptureFixture) -> list[str]:
    return file_values(r.getMessage() for r in caplog.records)


def test_scan_allow_build_physical_path_is_not_stored(tmp_path: Path) -> None:
    """Regression: an absolute ``--allow-build`` extraction path must not
    end up in ``format_info.physical_path``."""
    extract = tmp_path / "extract"
    pf = _pf(str(extract / "pkg" / "model.gguf"), "pkg/model.gguf")
    assert Path(pf.physical_path).is_absolute()

    with patch("pitloom.extract.scanner.read_ai_model", return_value=_fake_meta()):
        found = scan_project_for_ai_models(tmp_path / "proj", [pf])
        assert len(found) == 1
        meta = found[0]

    assert meta.format_info.physical_path == "pkg/model.gguf"
    assert meta.format_info.file_name == "model.gguf"


@pytest.mark.parametrize(
    "error", [ImportError("x"), ValueError("x")], ids=["import", "value"]
)
def test_scan_allow_build_warnings_print_stable_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    """Regression: scanner warnings print ``FILE=`` without the temporary
    extraction directory."""
    extract = tmp_path / "extract"
    files = [
        _pf(str(extract / "pkg" / "model.gguf"), "pkg/model.gguf"),
        _pf(str(extract / "pkg" / "gone.py"), "pkg/gone.py"),
    ]
    assert all(Path(f.physical_path).is_absolute() for f in files)

    with patch("pitloom.extract.scanner.read_ai_model", side_effect=error):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            scan_project_for_ai_models(tmp_path / "proj", files)

    values = _file_values(caplog)
    assert values
    assert set(values) <= {"pkg/model.gguf", "pkg/gone.py"}
    assert not any(str(extract) in v for v in values)


def test_scan_src_layout_warning_prints_project_relative_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: ``FILE=`` was the absolute joined path; now it is the
    project-relative one (not the distribution path)."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "model.onnx").write_bytes(b"corrupt")
    files = [_pf("src/pkg/model.onnx", "pkg/model.onnx")]

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = scan_project_for_ai_models(tmp_path, files)

    assert not result
    assert _file_values(caplog) == ["src/pkg/model.onnx"]


def test_scan_force_include_rename_uses_installed_name(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\n"
        'name = "demo"\n'
        'version = "1.0"\n'
        "[tool.hatch.build.targets.wheel]\n"
        'packages = ["pkg"]\n'
        "[tool.hatch.build.targets.wheel.force-include]\n"
        '"assets/weights.dat" = "pkg/model.npy"\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "use.py").write_text('load("model.npy")\n', encoding="utf-8")
    (tmp_path / "assets").mkdir()
    shutil.copyfile(
        Path(__file__).parent.parent
        / "fixtures"
        / "aimodels"
        / "numpy"
        / "example-model-v1.npy",
        tmp_path / "assets" / "weights.dat",
    )

    _, files, _ = get_wheel_files(tmp_path)
    assert any(
        f.physical_path == "assets/weights.dat"
        and f.distribution_path == "pkg/model.npy"
        for f in files
    )

    found = scan_project_for_ai_models(tmp_path, files)
    assert len(found) == 1
    meta = found[0]
    assert meta.format_info.file_name == "model.npy"
    assert meta.format_info.physical_path == "assets/weights.dat"
    assert meta.usage_files == ["pkg/use.py"]


def test_scan_renamed_to_non_model_suffix_is_not_discovered(tmp_path: Path) -> None:
    """The installed name decides discovery in both directions: a model
    renamed to a non-model suffix (``assets/blob.npy`` -> ``demo/blob.dat``)
    is not read, as under ``--allow-build``."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "blob.npy").write_bytes(b"\x93NUMPY")
    files = [_pf("assets/blob.npy", "demo/blob.dat")]

    with patch("pitloom.extract.scanner.read_ai_model") as reader:
        result = scan_project_for_ai_models(tmp_path, files)

    assert not result
    reader.assert_not_called()


_SUFFIX_FORMATS = [(".npy", "numpy"), (".bin", "unknown"), (".zip", "unknown")]


def _one_warning_naming(caplog: pytest.LogCaptureFixture, path: str, fmt: str) -> None:
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert message.startswith(f"FORMAT={fmt} ")
    assert file_values([message]) == [path]


@pytest.mark.skipif(not _CAN_DENY_ACCESS, reason="needs POSIX and non-root")
@pytest.mark.parametrize(("suffix", "fmt"), _SUFFIX_FORMATS)
@pytest.mark.parametrize("deny", ["file", "directory"])
def test_scan_unreadable_candidate_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    suffix: str,
    fmt: str,
    deny: str,
) -> None:
    """A candidate that exists but cannot be read is a genuine access
    failure: one ``FORMAT= FILE=`` warning and a skip, on every suffix."""
    sub = tmp_path / "sub"
    sub.mkdir()
    target = sub / f"m{suffix}"
    target.write_bytes(b"\x93NUMPY\x01\x00")
    denied = target if deny == "file" else sub
    denied.chmod(0)
    try:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            result = scan_project_for_ai_models(tmp_path, [_pf(f"sub/m{suffix}")])
    finally:
        denied.chmod(0o700)

    assert not result
    _one_warning_naming(caplog, f"sub/m{suffix}", fmt)


@pytest.mark.parametrize(("suffix", "fmt"), _SUFFIX_FORMATS)
def test_scan_candidate_with_denied_open_warns_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    fmt: str,
) -> None:
    """Same as the chmod case, on every platform and Python version."""
    target = tmp_path / f"m{suffix}"
    target.write_bytes(b"\x93NUMPY\x01\x00")
    real_open = Path.open

    def _denied(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == target:
            raise PermissionError(13, "denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _denied)
    with pytest.raises(PermissionError):
        read_ai_model_header(target)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = scan_project_for_ai_models(tmp_path, [_pf(f"m{suffix}")])

    assert not result
    _one_warning_naming(caplog, f"m{suffix}", fmt)


def test_project_candidates_and_sources_shape(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    data = b"0123456789abcdef"
    (tmp_path / "src" / "m.bin").write_bytes(data)
    abs_pf = _pf(str(tmp_path / "elsewhere" / "n.bin"), "pkg/n.bin")
    rel_pf = _pf("src/m.bin", "pkg/m.bin")

    rel_c, abs_c = project_candidates(tmp_path, [rel_pf, abs_pf])
    assert rel_c.sniff() == data[:SNIFF_BYTES]
    with rel_c.materialize() as path:
        assert path == tmp_path / "src" / "m.bin"
    assert rel_c.physical_path == "src/m.bin"
    assert abs_c.physical_path == "pkg/n.bin"
    assert abs_c.sniff() == b""

    rel_s, abs_s = project_sources(tmp_path, [rel_pf, abs_pf])
    with rel_s.open() as fh:
        assert fh.read() == data
    assert rel_s.distribution_path == "pkg/m.bin"
    assert abs_s.physical_path == "pkg/n.bin"
