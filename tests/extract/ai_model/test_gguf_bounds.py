# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A GGUF header through Pitloom's adapter: which failures refuse the file
(``model-unreadable``, a read error) and what a header read in part records
and says (``over-cap``).

See also: :mod:`tests.extract.ai_model.formats.test_gguf_header` (the
reader's own bounds) and :mod:`pitloom.extract.ai_model._gguf_bounds`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import struct
from pathlib import Path

import pytest

from pitloom.extract.ai_model import _gguf_bounds
from pitloom.extract.ai_model.formats import Limits
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from tests.extract.ai_model.gguf_builders import (
    ARRAY,
    STRING,
    UINT8,
    array,
    gguf_file,
    gguf_with_tensors,
    kv,
    string,
    tensor_info,
)
from tests.warning_helpers import logged_warnings

pytestmark = pytest.mark.platform  # files, a memory map

_GGUF_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels" / "gguf"
_EMPTY = struct.pack("<Q", 0)


@pytest.fixture(autouse=True)
def _needs_gguf() -> None:
    pytest.importorskip("gguf")


def _write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "m.gguf"
    path.write_bytes(data)
    return path


# -- refused ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (gguf_file(10**6, 0), "GGUF header declares 1000000 tensors"),
        (gguf_file(0, 2**40), f"GGUF header declares {2**40} key/value pairs"),
        (
            gguf_file(0, 1, array(STRING, 1000), tail=64),
            "GGUF array of 1000 elements, more than the file holds",
        ),
    ],
    ids=["tensors", "pairs", "array"],
)
def test_a_count_beyond_the_file_is_unreadable(
    tmp_path: Path, data: bytes, reason: str
) -> None:
    with pytest.raises(ModelLimitExceeded) as excinfo:
        read_gguf(_write(tmp_path, data))
    assert excinfo.value.reason == reason


@pytest.mark.parametrize("reader", ["accepts-4", "unknown"])
def test_a_version_the_gguf_package_reads_and_the_reader_does_not_is_refused(
    reader: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: the version may not be bounded."""
    gguf_reader = pytest.importorskip("gguf.gguf_reader")
    if reader == "accepts-4":
        monkeypatch.setattr(gguf_reader, "READER_SUPPORTED_VERSIONS", [2, 3, 4])
    else:  # the package's own list cannot be found
        monkeypatch.delattr(gguf_reader, "READER_SUPPORTED_VERSIONS")
    path = _write(tmp_path, b"GGUF" + struct.pack("<IQQ", 4, 0, 0))
    with pytest.raises(ModelLimitExceeded, match="version 4"):
        read_gguf(path)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"GGUF" + struct.pack("<IQQ", 1, 0, 0), "version 1"),
        (b"not a gguf file at all, but longer than a header", "magic"),
        (b"", "shorter than a GGUF header"),
        (gguf_file(0, 1, kv(b"k", 99, b"\0" * 8)), "unknown value type"),
        # GGUFReader read the cut value as an empty array: a TypeError escaped
        (gguf_file(0, 1, kv(b"general.alignment", 4, b"")), "truncated"),
        (gguf_file(0, 1, kv(b"GGUF.version", UINT8, b"\0")), "duplicate key"),
        (
            gguf_with_tensors([tensor_info("a", (8,))], data_bytes=31),
            "tensor 'a' data runs past the end",
        ),
        (
            gguf_with_tensors([tensor_info("q", (33,), ggml_type=2)], data_bytes=64),
            "no whole number of 32-element blocks",
        ),
    ],
    ids=[
        "version-1",
        "not-gguf",
        "empty",
        "unknown-type",
        "value-cut",
        "pseudo-key",
        "data-cut",
        "partial-block",
    ],
)
def test_a_malformed_file_is_a_read_failure(
    tmp_path: Path, data: bytes, reason: str
) -> None:
    with pytest.raises(ValueError, match=f"Failed to read GGUF file .*{reason}"):
        read_gguf(_write(tmp_path, data))


def test_a_tensor_type_the_gguf_package_does_not_know_is_read(tmp_path: Path) -> None:
    """Its data is not sized, so it need not be in the file; the shape counts.
    (``GGUFReader`` refused a removed type such as ``Q4_0_4_4``.)"""
    path = _write(tmp_path, gguf_with_tensors([tensor_info("a", (4, 8), ggml_type=31)]))
    assert read_gguf(path).parameter_count == 32


def test_an_unreadable_file_is_a_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, gguf_file(0, 0))

    def denied(_path: Path, _keep: dict[str, int]) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("pitloom.extract.ai_model.gguf.load_gguf_header", denied)
    with pytest.raises(ValueError, match="Failed to read GGUF file .*denied"):
        read_gguf(path)


@pytest.mark.parametrize("fixture", sorted(_GGUF_FIXTURES.glob("*.gguf")), ids=str)
def test_every_real_gguf_is_read_whole(
    fixture: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta = read_gguf(fixture)
    assert meta.architecture
    assert not logged_warnings(caplog)


# -- read in part ----------------------------------------------------------


@pytest.fixture
def _tight(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = Limits(max_gguf_skipped_elements=3, max_gguf_parsed=40)
    monkeypatch.setattr(_gguf_bounds, "GGUF_LIMITS", limits)


def _partial(key: bytes, n_strings: int) -> bytes:
    """A name, a fully hopped array ``a``, then an array *key* of
    *n_strings* strings and a later pair; one tensor."""
    body = (
        kv(b"general.name", STRING, string("m"))
        + array(STRING, 2, _EMPTY * 2, key=b"a")
        + array(STRING, n_strings, _EMPTY * n_strings, key=key)
        + kv(b"later", UINT8, b"\0")
    )
    return gguf_with_tensors([tensor_info("t", (2,))], 4, body, data_bytes=8)


@pytest.mark.usefixtures("_tight")
def test_a_header_over_a_bound_keeps_what_was_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta = read_gguf(_write(tmp_path, _partial(b"s", 2)))
    assert meta.name == "m"
    assert meta.properties["a.length"] == "2"
    assert meta.properties["s.length"] == "2"  # declared: its end not reached
    assert "later" not in meta.properties
    assert meta.parameter_count is None
    assert "Evidence" not in meta.provenance["properties.a.length"]
    assert meta.provenance["properties.s.length"] == (
        "Source: m.gguf | Field: s | Method: array_length | Evidence: declared"
    )
    (warning,) = logged_warnings(caplog)
    assert warning == (
        f"FORMAT=gguf FILE={tmp_path / 'm.gguf'}: larger than the 3-element "
        "GGUF-skipped-element cap; s length as declared; later fields and the "
        "tensor shapes not read"
    )


@pytest.mark.usefixtures("_tight")
def test_a_key_in_the_warning_is_escaped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    read_gguf(_write(tmp_path, _partial(b"s\nx", 2)))
    (warning,) = logged_warnings(caplog)
    assert "\n" not in warning
    assert "; 's\\nx' length as declared;" in warning


@pytest.mark.usefixtures("_tight")
def test_a_header_within_its_bounds_is_read_whole(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One string fewer: the same file, read whole."""
    meta = read_gguf(_write(tmp_path, _partial(b"s", 1)))
    assert meta.properties["later"] == "0"
    assert meta.parameter_count == 2
    assert not logged_warnings(caplog)


def test_a_bound_in_the_tensor_infos_keeps_every_field(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_gguf_bounds, "GGUF_LIMITS", Limits(max_gguf_parsed=8))
    body = kv(b"general.name", STRING, string("m"))
    path = _write(tmp_path, gguf_with_tensors([tensor_info("t", (2,))], 1, body))
    meta = read_gguf(path)
    assert meta.name == "m"
    assert meta.parameter_count is None
    (warning,) = logged_warnings(caplog)
    assert warning.endswith(
        "larger than the 8-unit GGUF-header cap; tensor shapes not read; "
        "parameter count not recorded"
    )


def test_a_key_over_its_bound_names_the_pair(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_gguf_bounds, "GGUF_LIMITS", Limits(max_gguf_string_bytes=4))
    body = kv(b"abc", UINT8, b"\0") + kv(b"abcde", UINT8, b"\0")
    with caplog.at_level(logging.WARNING):
        meta = read_gguf(_write(tmp_path, gguf_file(0, 2, body)))
    assert meta.properties["abc"] == "0"
    (warning,) = logged_warnings(caplog)
    assert warning.endswith(
        "larger than the 4-byte GGUF-string cap; fields from pair 2 on and the "
        "tensor shapes not read"
    )


def test_an_empty_key_is_named_by_its_pair(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    deep = struct.pack("<IQ", ARRAY, 1) * 4 + struct.pack("<IQ", UINT8, 1) + b"\0"
    read_gguf(_write(tmp_path, gguf_file(0, 1, kv(b"", ARRAY, deep))))
    (warning,) = logged_warnings(caplog)
    assert warning.endswith(
        "GGUF-array-nesting cap; fields from pair 1 on and the tensor shapes not read"
    )


def test_a_string_value_over_its_bound_names_its_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_gguf_bounds, "GGUF_LIMITS", Limits(max_gguf_string_bytes=4))
    read_gguf(_write(tmp_path, gguf_file(0, 1, kv(b"k", STRING, string("abcde")))))
    (warning,) = logged_warnings(caplog)
    assert warning.endswith("; fields from k on and the tensor shapes not read")
