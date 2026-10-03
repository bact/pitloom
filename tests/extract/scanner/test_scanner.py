# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the surface-agnostic AI model scanner policy.

Uses fake candidates and sources, so no project layout is involved.

See also: :mod:`tests.extract.scanner.test_scanner_project` for the project producer,
:mod:`tests.assemble.test_ai_model_order` for order through the SBOM.
"""

# pylint: disable=missing-function-docstring
# pylint: disable=too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import contextlib
import io
import itertools
import logging
import zlib
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract.ai_model import SNIFF_BYTES
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
_GGUF = AiModelFormat.GGUF.magic or b""
_NPY = AiModelFormat.NUMPY.magic or b""


def _cand(
    dist: str,
    phys: str | None = None,
    header: bytes = b"\x08",  # no signature: admits only ONNX and HDF5 suffixes
    materialize: Callable[[], AbstractContextManager[Path]] | None = None,
    sniff: Mock | None = None,
) -> ModelCandidate:
    return ModelCandidate(
        distribution_path=dist,
        physical_path=phys or dist,
        sniff=sniff or Mock(return_value=header),
        materialize=materialize or (lambda: contextlib.nullcontext(Path("unused"))),
    )


class _Broken(io.BytesIO):
    """A stream whose ``read`` fails after a successful open."""

    def read(self, size: int | None = -1) -> bytes:
        raise zlib.error("corrupt member")


def _src(
    dist: str, phys: str | None = None, data: bytes | BaseException = b""
) -> UsageSource:
    def _open() -> AbstractContextManager[io.BytesIO]:
        if isinstance(data, zlib.error):
            return _Broken()
        if isinstance(data, BaseException):
            raise data
        return io.BytesIO(data)

    return UsageSource(distribution_path=dist, physical_path=phys or dist, open=_open)


def _meta(
    fmt: AiModelFormat = AiModelFormat.ONNX, name: str | None = None
) -> AiModelMetadata:
    meta = AiModelMetadata(format_info=AiModelFormatInfo(model_format=fmt))
    meta.format_info.file_name = name
    return meta


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


# --- discovery: candidate filter and format decision -----------------------


@pytest.mark.parametrize(
    ("dist", "phys", "found", "file_name"),
    [
        ("pkg/model.npy", "assets/weights.dat", True, "model.npy"),
        ("pkg/MODEL.NPY", "x", True, "MODEL.NPY"),
        ("pkg/model.tar.npy", "x", True, "model.tar.npy"),
        ("a b/é ü.bin", "x", True, "é ü.bin"),
        ("pkg\\model.npy", "x", True, "pkg\\model.npy"),  # POSIX names only
        ("pkg/model.dat", "assets/model.npy", False, ""),  # physical is ignored
        ("pkg/model.npy.bak", "pkg/model.npy", False, ""),
        ("pkg/weights.npy.py", "x", False, ""),
        ("pkg/.npy", "x", False, ""),
        ("pkg/d.npy/file", "x", False, ""),
    ],
)
def test_discover_filters_on_distribution_suffix(
    dist: str, phys: str, found: bool, file_name: str
) -> None:
    sniff = Mock(return_value=_NPY)
    with patch(_READ, autospec=True, return_value=_meta(AiModelFormat.NUMPY)):
        models = discover_ai_models([_cand(dist, phys, sniff=sniff)])
    assert [m.format_info.file_name for m in models] == ([file_name] if found else [])
    assert sniff.called == found  # a filtered-out candidate is never sniffed


@pytest.mark.parametrize(
    ("dist", "header", "expected"),
    [
        ("pkg/model.onnx", _GGUF + b"\0" * 20, AiModelFormat.GGUF),
        ("pkg/model.npy", _GGUF, AiModelFormat.GGUF),
        ("pkg/model.bin", _NPY + b"\0" * 20, AiModelFormat.NUMPY),
        ("pkg/model.onnx", b"\x08\x01\x12\x04", AiModelFormat.ONNX),
        ("pkg/model.NPZ", b"PK\x03\x04", AiModelFormat.NUMPY),
        ("pkg/model.gguf", (_GGUF + b"\0" * 20)[:SNIFF_BYTES], AiModelFormat.GGUF),
    ],
)
def test_discover_passes_detected_format_to_reader(
    dist: str, header: bytes, expected: AiModelFormat
) -> None:
    """Magic beats the extension; the decided format is what gets read."""
    with patch(_READ, autospec=True, return_value=_meta()) as reader:
        discover_ai_models([_cand(dist, header=header)])
    assert reader.call_args.kwargs["model_format"] == expected


_PAIRS = [("pkg/b.onnx", "b"), ("pkg/a.onnx", "z"), ("pkg/a.onnx", "y")]
# Sorted by distribution path, then by the stable physical path.
_SORTED = [("pkg/a.onnx", "y"), ("pkg/a.onnx", "z"), ("pkg/b.onnx", "b")]


def _paths(models: list[AiModelMetadata]) -> list[tuple[str | None, str | None]]:
    return [
        (m.format_info.file_path_relative, m.format_info.physical_path) for m in models
    ]


@pytest.mark.parametrize("order", [_PAIRS, [_PAIRS[1], _PAIRS[0], _PAIRS[2]]], ids=str)
@pytest.mark.parametrize("as_iterator", [False, True], ids=["list", "iterator"])
def test_discover_sorts_by_distribution_then_physical_path(
    order: list[tuple[str, str]], as_iterator: bool
) -> None:
    """Any input order; a tie on distribution path breaks on physical path."""
    cands = [_cand(dist, phys) for dist, phys in order]
    assert [(c.distribution_path, c.physical_path) for c in cands] != _SORTED
    with patch(_READ, autospec=True, side_effect=lambda *a, **k: _meta()):
        found = discover_ai_models(iter(cands) if as_iterator else cands)
    assert _paths(found) == _SORTED


def test_discover_sort_is_by_code_point_and_keeps_duplicates() -> None:
    """Plain ``str`` order (upper before lower) and no dedupe of a repeat."""
    names = ["b/m.onnx", "a/m.onnx", "B/m.onnx", "b/m.onnx"]
    with patch(_READ, autospec=True, side_effect=lambda *a, **k: _meta()):
        found = discover_ai_models([_cand(n) for n in [*names, "skip.txt"]])
    assert [m.format_info.file_path_relative for m in found] == sorted(names)
    assert sorted(names) != names  # not vacuous
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert discover_ai_models([]) == []


def test_discover_warnings_follow_sorted_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reads (so warnings) run in sorted order, not just the returned list."""
    cands = [_cand("pkg/b.onnx", "src/b"), _cand("pkg/a.onnx", "src/a")]
    with patch(_READ, autospec=True, side_effect=ValueError("bad")):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            discover_ai_models(cands)
    assert file_values(_warnings(caplog)) == ["src/a", "src/b"]


# --- discovery: paths and failures -----------------------------------------


@pytest.mark.parametrize("error", [None, ImportError("numpy")], ids=["read", "stub"])
def test_discover_sets_stable_paths_on_record_and_stub(
    caplog: pytest.LogCaptureFixture, error: Exception | None
) -> None:
    cand = _cand("pkg/model.npy", "assets/weights.dat", header=_NPY)
    with patch(
        _READ, autospec=True, return_value=_meta(AiModelFormat.NUMPY), side_effect=error
    ):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            found = discover_ai_models([cand])
    assert len(found) == 1
    info = found[0].format_info
    assert info.model_format == AiModelFormat.NUMPY
    assert info.file_name == "model.npy"
    assert info.file_path_relative == "pkg/model.npy"
    assert info.physical_path == "assets/weights.dat"
    assert file_values(_warnings(caplog)) == (["assets/weights.dat"] if error else [])
    assert len(_warnings(caplog)) == (1 if error else 0)


def _materialize_raises() -> AbstractContextManager[Path]:
    raise OSError("cannot copy")


@pytest.mark.parametrize("failure", ["reader-value", "reader-os", "materialize"])
def test_discover_read_failure_keeps_a_stub_and_warns_once_with_stable_path(
    caplog: pytest.LogCaptureFixture, failure: str
) -> None:
    materialize = {"materialize": _materialize_raises}.get(failure)
    error = {"reader-value": ValueError("bad"), "reader-os": OSError("io")}.get(failure)
    with patch(_READ, autospec=True, return_value=_meta(), side_effect=error):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            found = discover_ai_models(
                [_cand("pkg/model.onnx", "src/pkg/model.onnx", materialize=materialize)]
            )
    # pylint: disable-next=unbalanced-tuple-unpacking
    (stub,) = found
    assert stub.format_info.model_format == AiModelFormat.ONNX
    assert stub.format_info.physical_path == "src/pkg/model.onnx"
    assert not stub.inputs and not stub.properties
    (message,) = _warnings(caplog)
    assert message.startswith("FORMAT=onnx ")
    assert "failed to extract metadata" in message
    assert file_values([message]) == ["src/pkg/model.onnx"]


@pytest.mark.parametrize(
    "error", [PermissionError(13, "denied"), OSError(5, "io")], ids=["perm", "io"]
)
@pytest.mark.parametrize(
    ("dist", "fmt"),
    [("m.npy", "numpy"), ("m.bin", "unknown"), ("m.zip", "unknown")],
)
def test_discover_unreadable_sniff_warns_once_and_skips(
    caplog: pytest.LogCaptureFixture, error: OSError, dist: str, fmt: str
) -> None:
    sniff = Mock(side_effect=error)
    with patch(_READ, autospec=True) as reader:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            found = discover_ai_models(
                [_cand(f"pkg/{dist}", f"src/{dist}", sniff=sniff)]
            )
    assert not found
    reader.assert_not_called()
    (message,) = _warnings(caplog)
    assert message.startswith(f"FORMAT={fmt} ")
    assert file_values([message]) == [f"src/{dist}"]


def test_discover_non_oserror_from_sniff_propagates() -> None:
    """Only ``OSError`` is a read failure; a producer bug is not swallowed."""
    with pytest.raises(RuntimeError):
        discover_ai_models([_cand("m.bin", sniff=Mock(side_effect=RuntimeError))])


def test_discover_failure_does_not_stop_later_candidates() -> None:
    reader = Mock(side_effect=[ValueError("bad"), _meta()])
    with patch(_READ, reader):
        found = discover_ai_models([_cand("a/m.onnx"), _cand("b/m.onnx")])
    assert [m.format_info.file_path_relative for m in found] == ["a/m.onnx", "b/m.onnx"]
    assert reader.call_count == 2


# --- usage attachment -------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "matches"),
    [
        (b'load("model.onnx")', True),
        (b"\xef\xbb\xbfload('model.onnx')\r\n", True),  # BOM, CRLF
        (b"my_model.onnx", True),  # substring heuristic: no word boundary
        (b"model.onnx.bak", True),
        (b"print(1)", False),
        (b"model_onnx", False),
        (b"MODEL.ONNX", False),
        (b"", False),
    ],
)
def test_attach_matches_file_name_as_substring(content: bytes, matches: bool) -> None:
    meta = _meta(name="model.onnx")
    attach_usage_references([meta], [_src("pkg/use.py", data=content)])
    assert meta.usage_files == (["pkg/use.py"] if matches else [])


def test_attach_records_each_source_once_per_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    a, b = _meta(name="a.onnx"), _meta(name="big_a.onnx")
    empty, no_name = _meta(name=""), _meta(name=None)  # neither may match
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        attach_usage_references(
            [empty, a, b, no_name],
            [
                _src("x/one.py", data=b"a.onnx a.onnx"),
                _src("x/two.py", data=b"big_a.onnx"),
            ],
        )
    assert not _warnings(caplog)
    assert a.usage_files == ["x/one.py", "x/two.py"]  # "a.onnx" in "big_a.onnx"
    assert b.usage_files == ["x/two.py"]
    assert empty.usage_files == no_name.usage_files == []


@pytest.mark.parametrize(
    "dists",
    [["pkg/y.py", "pkg/x.py", "pkg/x.py"], ["pkg/x.py", "pkg/y.py", "pkg/x.py"]],
    ids=str,
)
def test_attach_usage_files_sorted_and_deduplicated(dists: list[str]) -> None:
    sources = [_src(d, data=b"w.npy") for d in dists]
    assert dists != sorted(dists)  # not vacuous
    meta = _meta(name="w.npy")
    attach_usage_references([meta], sources)
    assert meta.usage_files == ["pkg/x.py", "pkg/y.py"]


def test_attach_sorts_and_dedupes_preexisting_usage_files() -> None:
    meta = _meta(name="w.npy")
    meta.usage_files = ["pkg/z.py", "pkg/x.py"]
    attach_usage_references([meta], [_src("pkg/x.py", data=b"w.npy")])
    assert meta.usage_files == ["pkg/x.py", "pkg/z.py"]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (("pkg/b.py", "src/b"), ("pkg/a.py", "src/a")),
        (("pkg/a.py", "z"), ("pkg/a.py", "y")),
    ],
    ids=["distribution", "tie-break"],
)
def test_attach_read_warnings_follow_sorted_source_order(
    caplog: pytest.LogCaptureFixture,
    first: tuple[str, str],
    second: tuple[str, str],
) -> None:
    sources = [_src(*first, data=OSError("x")), _src(*second, data=OSError("x"))]
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        attach_usage_references([], sources)
    assert file_values(_warnings(caplog)) == [second[1], first[1]]


@pytest.mark.parametrize(
    ("dist", "phys", "read"),
    [
        ("pkg/use.py", "tools/use.txt", True),  # distribution name decides
        ("pkg/use.txt", "x.py", False),
        ("pkg/USE.PY", "x.py", False),
        ("pkg/use.pyi", "x.py", False),
        ("pkg/use.py.bak", "x.py", False),
        ("pkg/.py", "x", True),
    ],
)
def test_attach_py_filter_uses_distribution_path(
    dist: str, phys: str, read: bool
) -> None:
    meta = _meta(name="model.onnx")
    opener = Mock(return_value=contextlib.nullcontext(io.BytesIO(b"model.onnx")))
    attach_usage_references([meta], [UsageSource(dist, phys, opener)])
    assert opener.called == read
    assert meta.usage_files == ([dist] if read else [])


@pytest.mark.parametrize(
    "bad",
    [OSError("gone"), PermissionError(13, "no"), zlib.error("x"), b"\xff\xfe", b"\x80"],
    ids=["os", "perm", "zlib-on-read", "non-utf8", "lone-continuation"],
)
@pytest.mark.parametrize("models", [True, False], ids=["models", "no-models"])
def test_attach_read_error_warns_once_and_continues(
    caplog: pytest.LogCaptureFixture, bad: bytes | BaseException, models: bool
) -> None:
    meta = _meta(name="model.onnx")
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        attach_usage_references(
            [meta] if models else [],
            [
                _src("pkg/a.py", "src/pkg/a.py", data=bad),
                _src("pkg/b.py", "src/pkg/b.py", data=b"model.onnx"),
            ],
        )
    (message,) = _warnings(caplog)
    assert "could not read for usage scanning" in message
    assert file_values([message]) == ["src/pkg/a.py"]
    assert meta.usage_files == (["pkg/b.py"] if models else [])


# --- scan_ai_models ---------------------------------------------------------


def test_scan_consumes_generators_once_and_discovers_before_scanning() -> None:
    calls: list[str] = []

    def _candidates() -> Iterator[ModelCandidate]:
        calls.append("candidates")
        yield _cand("pkg/model.onnx")

    def _sources() -> Iterator[UsageSource]:
        calls.append("sources")
        yield _src("pkg/use.py", data=b'open("model.onnx")')

    with patch(_READ, autospec=True, return_value=_meta()):
        found = scan_ai_models(
            _candidates(), _sources(), scan_usage=True, usage_hint=lambda: False
        )
    assert calls == ["candidates", "sources"]
    assert [m.usage_files for m in found] == [["pkg/use.py"]]


def test_scan_attaches_usage_to_import_error_stub() -> None:
    with patch(_READ, autospec=True, side_effect=ImportError("x")):
        found = scan_ai_models(
            [_cand("pkg/model.onnx")],
            [_src("pkg/use.py", data=b"model.onnx")],
            scan_usage=True,
            usage_hint=lambda: False,
        )
    assert [m.usage_files for m in found] == [["pkg/use.py"]]


def test_scan_empty_inputs() -> None:
    for usage, hint in itertools.product((True, False), repeat=2):
        answer = Mock(return_value=hint)
        empties: list[Iterable[Any]] = [[], iter(())]
        for empty in empties:
            assert not scan_ai_models(empty, empty, scan_usage=usage, usage_hint=answer)


@pytest.mark.parametrize(
    ("usage", "models", "asked", "printed"),
    [
        (True, True, False, False),  # the setting is on: nothing to hint at
        (False, False, False, False),  # no model found: nothing to count
        (False, True, True, True),
    ],
    ids=["usage-on", "no-models", "would-print"],
)
def test_usage_hint_is_asked_only_when_it_would_print(
    caplog: pytest.LogCaptureFixture,
    usage: bool,
    models: bool,
    asked: bool,
    printed: bool,
) -> None:
    """The hint may claim a once-per-run slot, so it is not called eagerly."""
    hint = Mock(return_value=True)
    candidates = [_cand("pkg/model.onnx")] if models else []
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    with patch(_READ, autospec=True, return_value=_meta()):
        scan_ai_models(candidates, [], scan_usage=usage, usage_hint=hint)
    assert hint.called is asked
    assert any("pass --scan-model-usage" in r.getMessage() for r in caplog.records) is (
        printed
    )


def test_a_hint_answering_no_stays_silent(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    with patch(_READ, autospec=True, return_value=_meta()):
        scan_ai_models(
            [_cand("pkg/model.onnx")],
            [],
            scan_usage=False,
            usage_hint=lambda: False,
        )
    assert not caplog.records
