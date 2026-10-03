# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Copying a model out of an untrusted wheel: bounded, cleaned up, and
never leaking a temporary path or a forged log line.

See also: :mod:`tests.extract.scanner.test_scanner_wheel` (the producer's
behaviour), tests/build_and_read_shared.py (the signal helpers).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import importlib
import io
import re
import signal
import struct
import sys
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from pitloom._embed_build_sbom import EmbedFileCache
from pitloom.assemble import generate_wheel_sbom
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.embed import embed_wheel_sbom
from pitloom.extract import scanner_wheel
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.assemble.embed_surfaces_shared import run_cli
from tests.build_and_read_shared import (
    deliver_sigterm,
    spied_raise_signal,
    use_sys_tmp,
)
from tests.warning_helpers import logged_warnings

_NAME = "demo/model.safetensors"
_SCAN_PREFIX = "pitloom-model-scan-"
_CEILING = 1000
# Evaluated at import on every platform: signals are POSIX-only here.
_POSIX = sys.platform != "win32"
_Scan = Callable[..., list[Any]]


def _scan(wheel: Path, max_bytes: int = 10**7) -> list[Any]:
    return scan_wheel_for_ai_models(
        wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=max_bytes
    )


def _assert_format_only_stub(model: Any) -> None:
    """The model stays listed, with its file and format and nothing read."""
    assert model.format_info.model_format == AiModelFormat.SAFETENSORS
    assert model.format_info.file_path_relative == _NAME
    assert model.format_info.file_name == "model.safetensors"
    assert model.format_info.physical_path == _NAME
    assert model.name is None and not model.properties and not model.provenance


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return logged_warnings(caplog)


def test_declared_size_over_the_ceiling_is_refused_before_any_copy(
    tmp_path: Path, copies: list[Path], caplog: pytest.LogCaptureFixture
) -> None:
    wheel = write_model_wheel(tmp_path, {_NAME: safetensors_bytes(4096)})
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = _scan(wheel, _CEILING)
    _assert_format_only_stub(model)
    (message,) = _messages(caplog)
    assert re.search(r"\d+ bytes exceeds the 1000-byte scan ceiling", message)
    assert _NAME in message
    assert not copies


class _Stream(io.RawIOBase):
    """A member stream that outgrows what its header declared."""

    def __init__(self, total: int) -> None:
        self._data = safetensors_bytes() + b"\0" * total

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        chunk, self._data = self._data[: len(buffer)], self._data[len(buffer) :]
        buffer[: len(chunk)] = chunk
        return len(chunk)


def test_a_stream_longer_than_declared_stops_at_the_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    copies: list[Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """CPython bounds a lying central directory itself; the running counter
    must not depend on that, so the stream is faked (kills: no counter)."""
    wheel = write_model_wheel(tmp_path, {_NAME: safetensors_bytes()})
    real_open = zipfile.ZipFile.open

    def lying_open(self: zipfile.ZipFile, name: Any, *a: Any, **k: Any) -> Any:
        if getattr(name, "filename", name) == _NAME:
            return _Stream(50 * _CEILING)
        return real_open(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", lying_open)
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = _scan(wheel, _CEILING)
    _assert_format_only_stub(model)
    (message,) = _messages(caplog)
    assert "read more than 1000 bytes, over the 1000-byte scan ceiling" in message
    (copy,) = copies
    assert not copy.exists()


def _patch_central(wheel: Path, field: int, value: bytes) -> None:
    """Overwrite *value* at byte *field* of the first central header."""
    data = bytearray(wheel.read_bytes())
    start = data.index(b"PK\x01\x02")
    data[start + field : start + field + len(value)] = value
    wheel.write_bytes(bytes(data))


def test_a_lying_central_size_ends_in_one_failed_to_extract_warning(
    tmp_path: Path, copies: list[Path], caplog: pytest.LogCaptureFixture
) -> None:
    wheel = write_model_wheel(tmp_path, {_NAME: safetensors_bytes(200_000)})
    _patch_central(wheel, 24, struct.pack("<I", 100_000))  # uncompressed size
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = _scan(wheel)
    _assert_format_only_stub(model)
    (message,) = _messages(caplog)
    assert "failed to extract metadata" in message
    (copy,) = copies
    assert not copy.exists()
    assert str(copy.parent) not in message


def _member(wheel: Path, flag_bits: int = 0, method: int = 0) -> Path:
    """A one-member wheel whose central header claims *flag_bits*/*method*
    (``zipfile`` refuses to write either)."""
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(_NAME, safetensors_bytes(64))
    _patch_central(wheel, 8, struct.pack("<H", flag_bits))
    _patch_central(wheel, 10, struct.pack("<H", method))
    return wheel


def _corrupt_deflate(wheel: Path) -> Path:
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_NAME, safetensors_bytes(2000) + bytes(range(256)) * 400)
        info = zf.infolist()[0]
    data = bytearray(wheel.read_bytes())
    middle = info.header_offset + 30 + len(_NAME) + info.compress_size // 2
    data[middle : middle + 40] = b"\xff" * 40
    wheel.write_bytes(bytes(data))
    return wheel


try:  # zipfile reads Zstandard members (method 93) from Python 3.14 on
    importlib.import_module("compression.zstd")
    _HAS_ZSTD = True
except ImportError:
    _HAS_ZSTD = False


@pytest.mark.parametrize(
    ("build", "copied"),
    [
        (lambda p: _member(p, flag_bits=0x1), False),  # encrypted
        # 99 (WinZip AES): no decompressor on any Python version
        (lambda p: _member(p, method=99), False),
        (_corrupt_deflate, True),  # fails mid-copy
        pytest.param(  # garbage where a zstd frame belongs: ZstdError
            lambda p: _member(p, method=93),
            False,
            marks=pytest.mark.skipif(not _HAS_ZSTD, reason="no compression.zstd"),
        ),
    ],
    ids=["encrypted", "unsupported-method", "corrupt-deflate", "corrupt-zstd"],
)
def test_a_damaged_member_is_one_warning_and_leaves_no_file(
    tmp_path: Path,
    copies: list[Path],
    caplog: pytest.LogCaptureFixture,
    build: Callable[[Path], Path],
    copied: bool,
) -> None:
    # The header read of an encrypted or unsupported member fails, so the
    # format is not confirmed; a member that fails mid-copy is a confirmed
    # model whose read failed.
    assert len(_scan(build(tmp_path / "w.whl"))) == copied
    (message,) = _messages(caplog)
    assert _NAME in message
    assert bool(copies) is copied  # unreadable: never opened a file
    assert not any(c.exists() for c in copies)


def test_a_member_that_fails_to_open_for_the_copy_leaves_no_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    copies: list[Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The header read works, the copy's open then fails (an encrypted or
    unsupported member is caught by the header read; this is the copy's own
    guarantee): the member opens before any file is made."""
    wheel = write_model_wheel(tmp_path, {_NAME: safetensors_bytes()})
    real_open = zipfile.ZipFile.open
    calls: list[str] = []

    def second_open_fails(self: zipfile.ZipFile, name: Any, *a: Any, **k: Any) -> Any:
        calls.append(getattr(name, "filename", name))
        if calls.count(_NAME) > 1:
            raise RuntimeError("File is encrypted")
        return real_open(self, name, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "open", second_open_fails)
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = _scan(wheel)
    _assert_format_only_stub(model)
    assert calls.count(_NAME) == 2  # not vacuous: the copy's open was reached
    (message,) = _messages(caplog)
    assert "failed to extract metadata" in message
    assert not copies


def test_a_failed_copy_error_does_not_name_the_temporary_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def disk_full(file: Any, *_a: Any, **_k: Any) -> Any:
        raise OSError(28, "No space left on device", str(file))

    monkeypatch.setattr(scanner_wheel, "open", disk_full, raising=False)
    wheel = write_model_wheel(tmp_path, {_NAME: safetensors_bytes()})
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = _scan(wheel)
    _assert_format_only_stub(model)
    (message,) = _messages(caplog)
    assert "No space left on device" in message
    assert _SCAN_PREFIX not in message
    assert tempfile.gettempdir() not in message


def test_each_copy_is_deleted_before_the_next_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not left for the directory's removal: a big wheel would otherwise
    hold every model on disk at once."""
    wheel = write_model_wheel(
        tmp_path,
        {
            "demo/a.safetensors": safetensors_bytes(),
            "demo/b.safetensors": safetensors_bytes(),
        },
    )
    listings: list[list[str]] = []

    def read(path: Path, **_kwargs: Any) -> Any:
        listings.append(sorted(p.name for p in path.parent.iterdir()))
        return AiModelMetadata(
            format_info=AiModelFormatInfo(model_format=AiModelFormat.SAFETENSORS)
        )

    monkeypatch.setattr("pitloom.extract.scanner.read_ai_model", read)
    assert len(_scan(wheel)) == 2
    assert listings == [["0.safetensors"], ["1.safetensors"]]


def test_temporary_names_are_index_and_suffix_only(
    tmp_path: Path, copies: list[Path]
) -> None:
    hostile = "demo/we ird\t:na'me\u202e.SafeTensors"
    wheel = write_model_wheel(
        tmp_path, {hostile: safetensors_bytes(), _NAME: safetensors_bytes()}
    )
    assert len(_scan(wheel)) == 2
    assert len(copies) == 2
    for copy in copies:
        assert re.fullmatch(r"\d+\.safetensors", copy.name), copy
        assert copy.parent.name.startswith(_SCAN_PREFIX)
        assert not copy.exists()
        assert not copy.parent.exists()


def test_a_hostile_member_name_forges_no_log_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "loom.toml"
    config.write_text("[tool.pitloom]\nmax-model-extract-bytes = 64\n", "utf-8")
    forged = "demo/a\nERROR: forged\r\nWARNING: forged.safetensors"
    wheel = write_model_wheel(tmp_path / "d", {forged: safetensors_bytes(4096)})
    out = tmp_path / "out.json"
    run_cli(
        ["wheel", str(wheel), "--offline", "-o", str(out), "--config", str(config)],
        monkeypatch,
    )
    lines = capsys.readouterr().err.splitlines()
    ceiling = [line for line in lines if "scan ceiling" in line]
    assert len(ceiling) == 1
    assert ceiling[0].startswith("WARNING: FORMAT=")
    assert not [line for line in lines if line.startswith("ERROR:")]
    assert all(line.startswith(("WARNING: ", "INFO: ")) for line in lines if line)
    assert "forged" in out.read_text(encoding="utf-8")  # the SBOM keeps the name


@pytest.fixture(name="sys_tmp")
def fixture_sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


def _scan_dirs(sys_tmp: Path) -> list[Path]:
    return [d for d in sys_tmp.iterdir() if d.name.startswith(_SCAN_PREFIX)]


@pytest.fixture(name="sigterm_in_read")
def fixture_sigterm_in_read(
    monkeypatch: pytest.MonkeyPatch, sys_tmp: Path
) -> Iterator[list[list[Path]]]:
    """Deliver SIGTERM while a model copy exists; yields the scan dirs seen
    at that moment, and those left when the process is re-signalled."""
    seen: list[list[Path]] = []
    left: list[list[Path]] = []

    def read(*_a: Any, **_k: Any) -> None:
        seen.append(_scan_dirs(sys_tmp))
        deliver_sigterm()
        pytest.fail("the signal did not end the scan")

    monkeypatch.setattr("pitloom.extract.scanner.read_ai_model", read)
    with spied_raise_signal(monkeypatch) as spy:
        spy.side_effect = lambda signum: left.append(_scan_dirs(sys_tmp))
        yield seen
        assert left == [[]]
        spy.assert_called_once_with(signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


@pytest.mark.skipif(not _POSIX, reason="signal handling is POSIX-only here")
@pytest.mark.parametrize("nested", [False, True], ids=["alone", "in-embed-batch"])
def test_sigterm_during_a_read_removes_the_scan_dir(
    tmp_path: Path,
    sys_tmp: Path,
    sigterm_in_read: list[list[Path]],
    nested: bool,
) -> None:
    wheel = write_model_wheel(tmp_path / "d", {_NAME: safetensors_bytes()})
    with pytest.raises(SystemExit) as excinfo:
        if nested:
            with EmbedFileCache() as cache:
                embed_wheel_sbom(wheel, file_cache=cache)
        else:
            generate_wheel_sbom(wheel, offline=True)
    assert excinfo.value.code == 128 + signal.SIGTERM
    assert sigterm_in_read and sigterm_in_read[0], "no scan dir during the read"
    assert not _scan_dirs(sys_tmp)


def test_no_model_creates_no_temporary_directory(tmp_path: Path, sys_tmp: Path) -> None:
    wheel = write_model_wheel(tmp_path / "d", {"demo/use.py": b"x = 1\n"})
    with mock.patch("tempfile.mkdtemp", autospec=True) as mkdtemp:
        assert not _scan(wheel)
    mkdtemp.assert_not_called()
    assert not _scan_dirs(sys_tmp)
