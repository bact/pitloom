# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a reader logs reaches stderr only through the scanner: under the
stable ``FORMAT=``/``FILE=`` prefix, escaped, and without the temporary
copy's path or name.

See also: :mod:`tests.extract.scanner.test_scanner` (the policy) and
:mod:`tests.extract.scanner.test_scanner_wheel_security` (the producer).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import contextlib
import io
import logging
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_ai_model
from pitloom.extract.scanner import (
    ModelCandidate,
    UsageSource,
    attach_usage_references,
    discover_ai_models,
)
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import write_model_wheel
from tests.warning_helpers import logged_warnings

_READ = "pitloom.extract.scanner.read_ai_model"
_PT = b"\x80\x02N."  # a raw-pickle body: the extension alone decides the format
_TMP_WIN = PureWindowsPath("C:/Users/x/AppData/Local/Temp/pitloom-model-scan-ab/0.pt")


def _candidate(
    materialized: Path, sniff: Mock | None = None, read_path: Path | None = None
) -> ModelCandidate:
    return ModelCandidate(
        distribution_path="demo/real.pt",
        physical_path="demo/real.pt",
        sniff=sniff or Mock(return_value=b""),
        materialize=lambda: contextlib.nullcontext(materialized),
        read_path=read_path,
    )


_SPELLINGS: dict[str, Callable[[Path], Exception]] = {
    "errno-repr": lambda p: OSError(2, "x", str(p)),
    "raw": lambda p: ValueError(f"cannot read {p}"),
    "posix": lambda p: ValueError(f"cannot read {p.as_posix()}"),
}


@pytest.mark.parametrize("spelling", _SPELLINGS)
def test_a_windows_style_temp_path_is_scrubbed_in_every_spelling(
    spelling: str, caplog: pytest.LogCaptureFixture
) -> None:
    """``str(OSError)`` doubles a Windows path's backslashes (its repr)."""
    path = cast(Path, _TMP_WIN)
    error = _SPELLINGS[spelling](path)
    assert "pitloom-model-scan" in str(error)  # not vacuous
    with patch(_READ, side_effect=error):
        discover_ai_models([_candidate(path, Mock(return_value=_PT))])
    (message,) = logged_warnings(caplog)
    assert "pitloom-model-scan" not in message
    assert "AppData" not in message
    assert "demo/real.pt" in message


def test_the_sniff_and_usage_branches_scrub_the_read_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project file's read error names its absolute location (for
    ``--allow-build``, a temporary extraction directory)."""
    target = tmp_path / "pitloom-build-and-read-x" / "m.pt"
    denied = PermissionError(13, "Permission denied", str(target))
    candidate = _candidate(target, Mock(side_effect=denied), read_path=target)
    assert not discover_ai_models([candidate])
    messages = logged_warnings(caplog)
    assert len(messages) == 1
    assert "Permission denied" in messages[0]
    assert str(tmp_path) not in messages[0]
    assert "demo/real.pt" in messages[0]

    def _open() -> Any:
        raise denied

    source = UsageSource("demo/use.py", "demo/use.py", _open, read_path=target)
    caplog.clear()
    attach_usage_references([], [source])
    (message,) = logged_warnings(caplog)
    assert str(tmp_path) not in message
    assert "Permission denied" in message


def test_reader_records_are_relogged_under_the_stable_prefix(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def reader(path: Path, **_kwargs: Any) -> Any:
        log = logging.getLogger("pitloom.extract.ai_model.pytorch")
        log.warning("Failed to inspect x in Source: %s: %s", path.name, "a\n::error::b")
        log.debug("read %s", path)
        raise ValueError("boom")

    with patch(_READ, reader):
        discover_ai_models(
            [_candidate(Path(tempfile.gettempdir()) / "0.pt", Mock(return_value=_PT))]
        )
    names = {r.name for r in caplog.records}
    assert names == {"pitloom.extract.scanner"}  # nothing under a reader's name
    relayed, failed = logged_warnings(caplog)
    assert relayed.startswith("FORMAT=pytorch FILE=demo/real.pt: ")
    assert "Source: real.pt:" in relayed
    assert "0.pt" not in relayed
    assert "\n" not in relayed
    assert failed.startswith("FORMAT=pytorch FILE=demo/real.pt: failed to extract")


def _hostile_zip(
    members: dict[str, bytes], patch_member: Callable[[bytearray], None]
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    data = bytearray(buf.getvalue())
    patch_member(data)
    return bytes(data)


def _bad_crc(data: bytearray) -> None:
    i = data.find(b"PK\x01\x02")
    data[i + 16 : i + 20] = b"\0\0\0\0"
    j = data.find(b"PK\x03\x04")
    data[j + 14 : j + 18] = b"\0\0\0\0"


def _encrypted(data: bytearray) -> None:
    data[data.find(b"PK\x01\x02") + 8] |= 1
    data[data.find(b"PK\x03\x04") + 6] |= 1


_EVIL = "a\n::error title=pwned::forged\nWARNING: fake"
_CASES = {
    "pt-bad-crc": ("demo/real-name.pt", {f"{_EVIL}/data.pkl": _PT}, _bad_crc),
    "pt-encrypted": ("demo/real-name.pt", {f"{_EVIL}/data.pkl": _PT}, _encrypted),
    "pt2-bad-json": (
        "demo/real-name.pt2",
        {
            f"{_EVIL}/models/model.json": b"{not json",
            f"{_EVIL}/archive_version": b"1",
            f"{_EVIL}/data/x": b"1",
        },
        lambda data: None,
    ),
}


@pytest.mark.parametrize("case", _CASES)
def test_hostile_member_names_forge_no_line_through_any_reader(
    case: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    name, members, patch_member = _CASES[case]
    model = _hostile_zip(members, patch_member)
    wheel = write_model_wheel(tmp_path, {name: model})
    scan_wheel_for_ai_models(
        wheel,
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**7,
        trust=True,  # a .pt is gated in a wheel otherwise
    )
    messages = logged_warnings(caplog)
    assert messages  # not vacuous: a reader did warn
    for message in messages:
        assert message.startswith("FORMAT="), message
        assert f"FILE={name}: " in message
        assert "\n" not in message and "\r" not in message
    assert "0.pt" not in " ".join(messages)


def test_a_reader_called_directly_escapes_member_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``loom model`` reads the user's file with no scanner: the readers
    themselves escape what they quote."""
    path = tmp_path / "m.pt"
    path.write_bytes(_hostile_zip({f"{_EVIL}/data.pkl": _PT}, _bad_crc))
    read_ai_model(path, model_format=AiModelFormat.PYTORCH)
    (message,) = logged_warnings(caplog)
    assert "\n" not in message
    assert PurePosixPath(str(path)).name in message
