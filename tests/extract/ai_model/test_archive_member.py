# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A member inside a model archive is read through one bounded reader, so a
small archive that inflates to gigabytes cannot exhaust memory -- in a
project scan or a wheel scan alike.

See also: :mod:`pitloom.extract.ai_model.archive_member`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import io
import struct
import tracemalloc
import zipfile
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import archive_member, read_ai_model
from pitloom.extract.ai_model import numpy as numpy_reader
from pitloom.extract.ai_model.archive_member import (
    ArchiveMemberTooLarge,
    read_archive_member,
)
from pitloom.extract.scanner import discover_ai_models
from pitloom.extract.scanner_project import project_candidates
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import write_model_wheel
from tests.warning_helpers import logged_warnings

_CAP = 1024
_INFLATED = 40 * 1024 * 1024  # what a few kilobytes of deflate inflates to


@pytest.fixture(autouse=True, name="low_cap")
def fixture_low_cap(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(archive_member, "MAX_ARCHIVE_MEMBER_BYTES", _CAP)
    return _CAP


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _bomb(head: bytes = b"[", tail: bytes = b"]") -> bytes:
    return head + b" " * _INFLATED + tail


_MODELS: dict[str, tuple[str, dict[str, bytes], str]] = {
    "keras": (
        "m.keras",
        {"metadata.json": b"{}", "config.json": _bomb()},
        "config.json",
    ),
    "keras-metadata": ("m.keras", {"metadata.json": _bomb()}, "metadata.json"),
    "pt": ("m.pt", {"archive/data.pkl": _bomb(b"\x80\x02", b".")}, "archive/data.pkl"),
    "pt2-model-json": (
        "m.pt2",
        {"archive/models/model.json": _bomb(), "archive/version": b"1"},
        "archive/models/model.json",
    ),
    "pt2-version": ("m.pt2", {"version": _bomb(b"1", b"")}, "version"),
    "pt2-archive-version": (
        "m.pt2",
        {"archive/archive_version": _bomb(b"1", b""), "archive/data/x": b"1"},
        "archive/archive_version",
    ),
    "pt2-extra": (
        "m.pt2",
        {"archive/extra/name": _bomb(b"n", b""), "archive/version": b"1"},
        "archive/extra/name",
    ),
    "pt2-metadata-json": (
        "m.pt2",
        {"metadata.json": _bomb(), "archive/version": b"1"},
        "metadata.json",
    ),
}


@pytest.mark.parametrize("case", _MODELS)
def test_a_bomb_member_is_one_warning_and_a_kept_model_in_a_wheel(
    case: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    name, members, member = _MODELS[case]
    wheel = write_model_wheel(tmp_path, {f"demo/{name}": _zip(members)})
    tracemalloc.start()
    try:
        (model,) = scan_wheel_for_ai_models(
            wheel, scan_usage=False, usage_hint=lambda: False, max_bytes=10**9
        )
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < _INFLATED // 4  # never held the inflated member
    assert model.format_info.file_path_relative == f"demo/{name}"
    assert not model.provenance  # format-only
    (message,) = logged_warnings(caplog)
    assert message.startswith("FORMAT=")
    assert f"FILE=demo/{name}: archive member {member} larger than {_CAP} bytes" in (
        message
    )


def test_a_bomb_member_in_a_project_file_is_the_same_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    name, members, member = _MODELS["keras"]
    (tmp_path / name).write_bytes(_zip(members))
    files = [ProjectFile(physical_path=name, distribution_path=name)]
    (model,) = discover_ai_models(project_candidates(tmp_path, files))
    assert model.format_info.file_path_relative == name
    (message,) = logged_warnings(caplog)
    assert f"FILE={name}: archive member {member} larger than" in message


def test_members_up_to_the_cap_are_still_read(tmp_path: Path) -> None:
    config = b'{"class_name": "Sequential", "config": {"name": "m"}}'
    assert len(config) < _CAP
    path = tmp_path / "m.keras"
    path.write_bytes(_zip({"metadata.json": b"{}", "config.json": config}))
    meta = read_ai_model(path, model_format=AiModelFormat.KERAS)
    assert meta.type_of_model == "Sequential"


@pytest.mark.parametrize("size", [_CAP, _CAP + 1], ids=["at-cap", "over-cap"])
def test_the_cap_is_inclusive(size: int) -> None:
    zf = zipfile.ZipFile(io.BytesIO(_zip({"x": b"a" * size})))
    if size <= _CAP:
        assert len(read_archive_member(zf, "x")) == size
    else:
        with pytest.raises(ArchiveMemberTooLarge) as excinfo:
            read_archive_member(zf, "x")
        assert excinfo.value.member == "x"
        assert excinfo.value.limit == _CAP


def test_the_npy_v3_header_length_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy.lib.format as fmt  # pylint: disable=import-outside-toplevel

    monkeypatch.delattr(fmt, "_read_array_header", raising=False)
    stream = io.BytesIO(struct.pack("<I", _CAP + 1) + b"{" * 10)
    with pytest.raises(ArchiveMemberTooLarge):
        numpy_reader._shim_read_array_header(stream, (3, 0))


def test_no_reader_reads_an_inner_member_unbounded() -> None:
    """Every inner-member read in the readers goes through the bounded
    helper; a new ``zf.read(...)``/``zf.open(...)`` needs the same."""
    root = Path(archive_member.__file__).parent
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(root.glob("*.py"))
        if path.name != "archive_member.py"
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1)
        # numpy.py reads only an .npy header, bounded by its own length check.
        if path.name != "numpy.py"
        and any(call in line for call in ("zf.read(", "zf.open(", "zip.open("))
    ]
    assert not offenders, offenders


def test_the_bomb_fixtures_are_really_over_the_cap(low_cap: int) -> None:
    for _, members, member in _MODELS.values():
        data = zipfile.ZipFile(io.BytesIO(_zip(members))).getinfo(member).file_size
        assert data > low_cap * 1000
