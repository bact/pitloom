# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one fragment reader and its stage classifier: a failure carries the
stage that raised it (``read``, ``json``, ``spdx``), never one guessed from
the exception's type afterwards (a ``JSONDecodeError``, a
``UnicodeDecodeError`` and the RFC 8785 errors are all ``ValueError``), and
a programming error or an out-of-memory is never wrapped.

Each case asserts the stage, so a classifier whose order is changed fails.

See also: tests/messages/test_fragments.py (the stage's line, one case each)
and tests/messages/test_fragments_surfaces.py (the line on every surface).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _fragments_read
from pitloom.assemble.spdx3._fragments_read import (
    parse_fragment,
    read_fragment_bytes,
    read_fragment_set,
)
from pitloom.core.internal_error import InternalError
from pitloom.messages.fragments import FragmentReadError

pytestmark = pytest.mark.platform  # bytes, encodings, an unreadable path

_AGENT = "https://e.org/a#A"
_BOM8 = b"\xef\xbb\xbf"


def _fragment(*extra: dict[str, Any]) -> dict[str, Any]:
    """A fragment of one agent, then *extra* elements."""
    return {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "CreationInfo",
                "@id": "_:c",
                "specVersion": "3.0.1",
                "created": "2024-01-01T00:00:00Z",
                "createdBy": [_AGENT],
            },
            {
                "type": "SoftwareAgent",
                "spdxId": _AGENT,
                "name": "x",
                "creationInfo": "_:c",
            },
            *extra,
        ],
    }


def _dataset(size: object) -> dict[str, Any]:
    """A dataset whose size is *size*, a number the SPDX 3 bindings accept."""
    return {
        "type": "dataset_DatasetPackage",
        "spdxId": "https://e.org/a#D",
        "name": "d",
        "creationInfo": "_:c",
        "dataset_datasetType": ["text"],
        "dataset_datasetSize": size,
    }


def _stage_of(raw: bytes) -> FragmentReadError:
    with pytest.raises(FragmentReadError) as raised:
        parse_fragment(raw, file="f.json")
    return raised.value


_GOOD = json.dumps(_fragment()).encode()


# -- the stage of each failure ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "stage", "cause"),
    [
        (b"{not json", "json", json.JSONDecodeError),
        (b"", "json", json.JSONDecodeError),
        (b'{"a": "\xc3("}', "json", UnicodeDecodeError),
        ("{}".encode("utf-16")[:-1], "json", UnicodeDecodeError),
        (b"[" * 100_000 + b"]" * 100_000, "json", RecursionError),
        (b'{"a": 1}', "spdx", TypeError),
        (b"3", "spdx", TypeError),
        (b"null", "spdx", TypeError),
        (_GOOD.replace(b"SoftwareAgent", b"NoSuchType"), "spdx", Exception),
    ],
    ids=[
        "syntax",
        "empty",
        "bad-utf8",
        "utf16-cut",
        "deep",
        "untyped-object",
        "number",
        "null",
        "unknown-type",
    ],
)
def test_each_failure_is_tagged_with_the_stage_that_raised_it(
    raw: bytes, stage: str, cause: type[Exception]
) -> None:
    error = _stage_of(raw)
    assert error.stage == stage
    assert isinstance(error.cause, cause)
    assert "\n" not in str(error)


@pytest.mark.parametrize(
    ("number", "domain_error"),
    [
        (2**53, "IntegerDomainError"),
        (2**60, "IntegerDomainError"),
        (-(2**60), "IntegerDomainError"),
        (float("inf"), "FloatDomainError"),
    ],
    ids=["2**53", "2**60", "-2**60", "inf"],
)
def test_a_number_with_no_rfc_8785_spelling_is_the_spdx_stage(
    number: float, domain_error: str
) -> None:
    """Valid JSON of a valid document, so not ``json``: the merged document
    could not be written with it. ``1e400`` is how a file spells infinity."""
    text = json.dumps(_fragment(_dataset(number)))
    raw = text.replace("Infinity", "1e400").encode()
    error = _stage_of(raw)
    assert error.stage == "spdx"
    assert type(error.cause).__name__ == domain_error


def test_the_largest_safe_integer_still_merges() -> None:
    """The boundary of the RFC 8785 check: 2**53 - 1 is the last integer."""
    raw = json.dumps(_fragment(_dataset(2**53 - 1))).encode()
    assert len(parse_fragment(raw, file="f.json").objects.objects) == 3


def test_a_top_level_array_is_an_empty_fragment_not_an_error() -> None:
    """``[]`` reads as a fragment with no element (it counts as merged): only
    an object the bindings cannot type, or a number, fails at ``spdx``."""
    assert not list(parse_fragment(b"[]", file="f.json").objects.objects)
    assert _stage_of(b'{"a": 1}').stage == "spdx"


# -- encodings the merge reads -------------------------------------------------


@pytest.mark.parametrize(
    "encode",
    [
        lambda text: _BOM8 + text.encode("utf-8"),
        lambda text: text.encode("utf-16"),
        lambda text: text.encode("utf-16-le"),
        lambda text: text.encode("utf-32"),
    ],
    ids=["utf8-bom", "utf16-bom", "utf16-le", "utf32-bom"],
)
def test_the_unicode_encodings_json_allows_merge(encode: Any, tmp_path: Path) -> None:
    """``json.loads(bytes)`` detects each of them and strips a UTF-8 BOM,
    which a decoded ``str`` would fail on."""
    raw = encode(json.dumps(_fragment()))
    path = tmp_path / "f.json"
    path.write_bytes(raw)
    assert len(read_fragment_set(path).objects) == 2
    assert len(parse_fragment(raw, file="f.json").objects.objects) == 2


def test_a_utf8_bom_is_not_an_error_where_a_decoded_str_would_be() -> None:
    raw = _BOM8 + _GOOD
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw.decode("utf-8"))  # the trap the reader avoids
    assert parse_fragment(raw, file="f.json").data["@graph"]


# -- the read stage ------------------------------------------------------------


def test_a_path_no_file_can_have_is_the_read_stage(tmp_path: Path) -> None:
    """A directory named ``x.json``: ``IsADirectoryError`` on POSIX,
    ``PermissionError`` on Windows, both stage ``read``."""
    path = tmp_path / "x.json"
    path.mkdir()
    for call in (read_fragment_bytes, read_fragment_set):
        with pytest.raises(FragmentReadError) as raised:
            call(path)
        assert raised.value.stage == "read"
        assert isinstance(raised.value.cause, OSError)


def test_a_missing_file_is_the_read_stage_too(tmp_path: Path) -> None:
    with pytest.raises(FragmentReadError) as raised:
        read_fragment_set(tmp_path / "gone.json")
    assert raised.value.stage == "read"
    assert isinstance(raised.value.cause, FileNotFoundError)


def test_the_read_of_a_good_file_is_the_bytes(tmp_path: Path) -> None:
    path = tmp_path / "f.json"
    path.write_bytes(_GOOD)
    assert read_fragment_bytes(path) == _GOOD


# -- never wrapped ---------------------------------------------------------------


def _raising(error: BaseException) -> Callable[..., Any]:
    """A callable that raises *error*, whatever it is called with."""

    def raise_it(*_args: object, **_kwargs: object) -> Any:
        raise error

    return raise_it


def _bindings_whose_deserialiser_raises(error: BaseException) -> SimpleNamespace:
    """The reader's own ``spdx3`` name, its deserialiser raising *error*."""
    deserialiser = SimpleNamespace(read=_raising(error))
    return SimpleNamespace(
        SHACLObjectSet=spdx3.SHACLObjectSet, JSONLDDeserializer=lambda: deserialiser
    )


@pytest.mark.parametrize(
    "error", [MemoryError(), InternalError("bug")], ids=["memory", "internal"]
)
def test_memory_and_internal_errors_propagate_from_the_read(
    error: BaseException,
) -> None:
    with pytest.raises(type(error)) as raised:
        path = SimpleNamespace(read_bytes=_raising(error))
        read_fragment_bytes(path)  # type: ignore[arg-type]
    assert raised.value is error


@pytest.mark.parametrize(
    "error", [MemoryError(), InternalError("bug")], ids=["memory", "internal"]
)
def test_memory_and_internal_errors_propagate_from_the_deserialiser(
    error: BaseException, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patched on the module's own name (``spdx3`` there), not on the shared
    bindings module."""

    monkeypatch.setattr(
        _fragments_read, "spdx3", _bindings_whose_deserialiser_raises(error)
    )
    with pytest.raises(type(error)) as raised:
        parse_fragment(_GOOD, file="f.json")
    assert raised.value is error


def test_any_other_error_of_the_deserialiser_is_the_spdx_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counterpart of the test above: only the two are exempt."""

    monkeypatch.setattr(
        _fragments_read, "spdx3", _bindings_whose_deserialiser_raises(KeyError("x"))
    )
    assert _stage_of(_GOOD).stage == "spdx"


# -- a lone surrogate ----------------------------------------------------------


def test_a_lone_surrogate_warns_once_after_a_successful_parse_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Said after the parse succeeds: a fragment left out says one line (its
    failure), not two."""
    lone = json.dumps(_fragment()).replace('"x"', '"x\\ud800"')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        parse_fragment(lone.encode(), file="f.json")
    assert len(caplog.records) == 1
    assert "f.json" in caplog.records[0].getMessage()
    caplog.clear()
    failing = json.dumps(_fragment(_dataset(2**60))).replace('"x"', '"x\\ud800"')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert _stage_of(failing.encode()).stage == "spdx"
    assert not caplog.records
