# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the project-directory producer of the AI model scanner.

Real files on disk; only ``read_ai_model`` is patched where a failure is
needed. Each layout (flat, ``src/``, ``force-include`` rename and the
absolute ``--allow-build`` extraction path) must give the same result:
opened by ``physical_path``, named by ``distribution_path``, reported by a
stable project-relative path.

See also: :mod:`tests.extract.test_scanner` for the shared policy.
"""

from __future__ import annotations

import logging
import os
import shutil
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
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
_READ = "pitloom.extract.scanner.read_ai_model"
# Evaluated at import on every platform: short-circuit before POSIX-only names.
_CAN_DENY_ACCESS = sys.platform != "win32" and os.geteuid() != 0
_GGUF = b"GGUF" + struct.pack("<IQQ", 3, 0, 0)  # smallest valid GGUF

# name -> (physical_path, distribution_path); ``ABS`` is filled in per test.
_LAYOUTS: dict[str, Callable[[str, Path], tuple[str, str]]] = {
    "flat": lambda n, _t: (n, n),
    "src": lambda n, _t: (f"src/pkg/{n}", f"pkg/{n}"),
    "renamed": lambda n, _t: (f"assets/{n}.dat", f"pkg/{n}"),
    "allow-build": lambda n, t: (str(t / "extract" / "pkg" / n), f"pkg/{n}"),
}
_LAYOUT = pytest.mark.parametrize("layout", list(_LAYOUTS))


def _pf(physical_path: str, distribution_path: str | None = None) -> ProjectFile:
    return ProjectFile(
        physical_path=physical_path,
        distribution_path=distribution_path or physical_path,
        digest_sha256="0" * 64,
    )


def _put(
    tmp_path: Path, layout: str, name: str, data: bytes | None
) -> tuple[ProjectFile, str]:
    """A ``ProjectFile`` in *layout* (written when *data* is given) and the
    stable path a warning must print for it."""
    phys, dist = _LAYOUTS[layout](name, tmp_path)
    assert Path(phys).is_absolute() == (layout == "allow-build")  # not vacuous
    if data is not None:
        target = Path(phys) if layout == "allow-build" else tmp_path / "proj" / phys
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return _pf(phys, dist), (dist if layout == "allow-build" else phys)


def _scan(tmp_path: Path, *files: ProjectFile) -> Any:
    return scan_project_for_ai_models(tmp_path / "proj", list(files))


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


# --- discovery per layout ---------------------------------------------------


@_LAYOUT
def test_scan_opens_physical_and_names_by_distribution(
    tmp_path: Path, layout: str
) -> None:
    pf, stable = _put(tmp_path, layout, "model.gguf", _GGUF)
    (meta,) = _scan(tmp_path, pf)
    info = meta.format_info
    assert info.model_format == AiModelFormat.GGUF
    assert info.file_name == "model.gguf"
    assert info.file_path_relative == pf.distribution_path
    assert info.physical_path == stable
    assert not Path(info.physical_path).is_absolute()


@_LAYOUT
@pytest.mark.parametrize("error", [ImportError("x"), ValueError("x")], ids=str)
def test_scan_warnings_print_stable_paths(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, layout: str, error: Exception
) -> None:
    """``FILE=`` is project-relative, never the joined or temporary path."""
    model, model_stable = _put(tmp_path, layout, "model.gguf", _GGUF)
    py, py_stable = _put(tmp_path, layout, "gone.py", None)
    with patch(_READ, autospec=True, side_effect=error):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            _scan(tmp_path, model, py)
    assert file_values(_warnings(caplog)) == [model_stable, py_stable]


@_LAYOUT
def test_scan_usage_files_use_distribution_paths(tmp_path: Path, layout: str) -> None:
    model, _ = _put(tmp_path, layout, "model.gguf", _GGUF)
    other, _ = _put(tmp_path, layout, "other.py", b"print(1)\n")
    use, _ = _put(tmp_path, layout, "use.py", b'load("model.gguf")\n')
    (meta,) = _scan(tmp_path, model, other, use)
    assert meta.usage_files == [use.distribution_path]


@_LAYOUT
def test_scan_unreadable_python_warns_and_later_sources_still_scan(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, layout: str
) -> None:
    model, _ = _put(tmp_path, layout, "model.gguf", _GGUF)
    missing, missing_stable = _put(tmp_path, layout, "a_missing.py", None)
    bad, bad_stable = _put(tmp_path, layout, "b_bad.py", b"\xff\xfe model.gguf")
    use, _ = _put(tmp_path, layout, "c_use.py", b"model.gguf")
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        (meta,) = _scan(tmp_path, model, missing, bad, use)
    assert file_values(_warnings(caplog)) == [missing_stable, bad_stable]
    assert meta.usage_files == [use.distribution_path]


# --- which files are candidates ---------------------------------------------


@pytest.mark.parametrize(
    ("phys", "dist"),
    [
        ("README.md", "README.md"),
        ("setup.py", "setup.py"),
        ("assets/blob.npy", "demo/blob.dat"),  # renamed away from a model suffix
        ("weights.bin", "weights.bin"),  # candidate suffix, unknown content
        ("m.npy.bak", "m.npy.bak"),
    ],
)
def test_scan_non_models_are_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, phys: str, dist: str
) -> None:
    target = tmp_path / "proj" / phys
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x93NUMPY" if phys.startswith("assets") else b"not a model")
    with patch(_READ, autospec=True) as reader:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            assert not _scan(tmp_path, _pf(phys, dist))
    reader.assert_not_called()
    assert not _warnings(caplog)
    assert not _scan(tmp_path)  # empty file list


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_scan_absent_or_directory_candidate_is_one_read_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    """Absence is not a header failure (no crash, no ``could not read
    header``); the reader is the one to report it."""
    (tmp_path / "proj").mkdir()
    if kind == "directory":
        pytest.importorskip("onnx")  # a directory reaches the ONNX reader
        (tmp_path / "proj" / "m.onnx").mkdir()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        assert not _scan(tmp_path, _pf("m.onnx"))
    (message,) = _warnings(caplog)
    assert "failed to extract metadata" in message
    assert file_values([message]) == ["m.onnx"]


# --- genuine access failures ------------------------------------------------

_SUFFIX_FORMATS = [(".npy", "numpy"), (".bin", "unknown"), (".zip", "unknown")]


def _one_warning_naming(caplog: pytest.LogCaptureFixture, path: str, fmt: str) -> None:
    (message,) = _warnings(caplog)
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
    sub = tmp_path / "proj" / "sub"
    sub.mkdir(parents=True)
    target = sub / f"m{suffix}"
    target.write_bytes(b"\x93NUMPY\x01\x00")
    denied = target if deny == "file" else sub
    denied.chmod(0)
    try:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            assert not _scan(tmp_path, _pf(f"sub/m{suffix}"))
    finally:
        denied.chmod(0o700)
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
    target = tmp_path / "proj" / f"m{suffix}"
    target.parent.mkdir()
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
        assert not _scan(tmp_path, _pf(f"m{suffix}"))
    _one_warning_naming(caplog, f"m{suffix}", fmt)


# --- producers --------------------------------------------------------------


def test_project_candidates_and_sources_shape(tmp_path: Path) -> None:
    data = b"0123456789abcdef"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.bin").write_bytes(data)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "n.bin").write_bytes(data[::-1])
    abs_pf = _pf(str(tmp_path / "elsewhere" / "n.bin"), "pkg/n.bin")
    rel_pf = _pf("src/m.bin", "pkg/m.bin")
    project_dir = tmp_path / "unrelated"  # an absolute path must not join onto it

    rel_c, abs_c = project_candidates(project_dir, [rel_pf, abs_pf])
    rel_s, abs_s = project_sources(project_dir, [rel_pf, abs_pf])
    assert (rel_c.physical_path, abs_c.physical_path) == ("src/m.bin", "pkg/n.bin")
    assert (rel_c.distribution_path, abs_c.distribution_path) == (
        "pkg/m.bin",
        "pkg/n.bin",
    )
    assert (rel_s.physical_path, abs_s.physical_path) == ("src/m.bin", "pkg/n.bin")
    assert (rel_s.distribution_path, abs_s.distribution_path) == (
        "pkg/m.bin",
        "pkg/n.bin",
    )
    assert abs_c.sniff() == data[::-1][:SNIFF_BYTES]
    with abs_c.materialize() as path, abs_s.open() as fh:
        assert path == tmp_path / "elsewhere" / "n.bin"
        assert fh.read() == data[::-1]

    # Relative: joined onto the project directory; nothing is read until used.
    project_dir = tmp_path
    (rel_c,) = project_candidates(project_dir, [rel_pf])
    (rel_s,) = project_sources(project_dir, [rel_pf])
    assert rel_c.sniff() == data[:SNIFF_BYTES]
    with rel_c.materialize() as path, rel_s.open() as fh:
        assert path == tmp_path / "src" / "m.bin"
        assert fh.read() == data
    ghost = _pf("gone/x.bin", "pkg/x.bin")
    assert len(list(project_candidates(project_dir, iter([ghost])))) == 1


# --- end to end: Hatchling force-include ------------------------------------


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

    (meta,) = scan_project_for_ai_models(tmp_path, files)
    assert meta.format_info.file_name == "model.npy"
    assert meta.format_info.physical_path == "assets/weights.dat"
    assert meta.usage_files == ["pkg/use.py"]
