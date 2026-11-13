# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``usage-unparseable`` and ``usage-unparseable/mention`` during
the model-usage scan.

An unparseable Python file whose text mentions a model file name records no
``hasDataFile`` edge, logs one ``WARNING:`` (``usage-unparseable``) naming the
running Python version and the failure, and logs one ``INFO:``
(``usage-unparseable/mention``) per mentioned model. An unparseable file that
mentions no model stays silent.

See also: :mod:`pitloom.extract._usage_attach` and
:mod:`pitloom.messages._usage_unparseable`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import contextlib
import io
import logging
import tempfile
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.model_usage import ModelUsage, UsageAccess
from pitloom.extract._usage_attach import usage_models
from pitloom.extract._usage_parse import parse_python, python_version
from pitloom.extract.scanner import UsageSource, attach_usage_references
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    trusted_message,
)
from pitloom.messages.models import (
    USAGE_UNPARSEABLE,
    USAGE_UNPARSEABLE_MENTION,
)
from tests._message_drift import record_problem

_LOGGER_NAME = "pitloom.extract.scanner"


def _meta(name: str) -> AiModelMetadata:
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name=name,
            file_path_relative=f"pkg/{name}",
            physical_path=f"src/pkg/{name}",
        )
    )


def _src(dist: str, phys: str, data: bytes) -> UsageSource:
    def _open() -> AbstractContextManager[io.BytesIO]:
        return contextlib.nullcontext(io.BytesIO(data))

    return UsageSource(distribution_path=dist, physical_path=phys, open=_open)


@pytest.mark.parametrize(
    ("exc", "expected_tail"),
    [
        (
            SyntaxError("invalid syntax", ("<unknown>", 7, 1, "x = (\n")),
            "invalid syntax (line 7)",
        ),
        (SyntaxError("unexpected EOF"), "unexpected EOF"),
        (
            ValueError("source code string cannot contain null bytes"),
            "source code string cannot contain null bytes",
        ),
        (MemoryError("Parser stack overflowed"), "nested too deeply"),
        (RecursionError("maximum recursion depth exceeded"), "nested too deeply"),
    ],
    ids=["syntax-line", "syntax-no-line", "null-byte", "memory", "recursion"],
)
def test_parse_failure_warns_and_informs_without_recording_edge(
    caplog: pytest.LogCaptureFixture, exc: BaseException, expected_tail: str
) -> None:
    m1 = _meta("a.onnx")
    m2 = _meta("b.onnx")
    m3 = _meta("unmentioned.onnx")
    source = _src("pkg/bad.py", "src/pkg/bad.py", b"# mentions a.onnx and b.onnx\n")
    good = _src("pkg/good.py", "src/pkg/good.py", b'open("a.onnx")\n')

    with patch(
        "pitloom.extract._usage_attach.parse_python",
        side_effect=[exc, parse_python('open("a.onnx")\n')],
    ):
        with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
            attach_usage_references([m1, m2, m3], [source, good])

    # Unparseable file yields no edge; later valid file still scans.
    assert m1.usage_files == [ModelUsage("pkg/good.py", UsageAccess.READ)]
    assert not m2.usage_files
    assert not m3.usage_files

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(warnings) == 1
    assert len(infos) == 2
    for rec in (*warnings, *infos):
        assert record_problem(rec) is None

    py = python_version()
    warn_text = (
        f"FILE=src/pkg/bad.py: could not parse as Python {py} for usage "
        f"scanning; {expected_tail}"
    )
    assert warnings[0].getMessage() == warn_text
    assert getattr(warnings[0], CODE_ATTR) == USAGE_UNPARSEABLE.code
    assert (
        trusted_message(f"WARNING: {warn_text} [{USAGE_UNPARSEABLE.code}]")
        is USAGE_UNPARSEABLE
    )

    info_texts = [r.getMessage() for r in infos]
    assert info_texts == [
        "FILE=src/pkg/bad.py MODEL=a.onnx: model file name found; no usage "
        "relationship recorded",
        "FILE=src/pkg/bad.py MODEL=b.onnx: model file name found; no usage "
        "relationship recorded",
    ]
    assert all(getattr(r, CODE_ATTR) == USAGE_UNPARSEABLE_MENTION.code for r in infos)


def test_real_syntax_error_and_null_byte_in_source(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = _meta("model.onnx")
    sources = [
        _src("pkg/syn.py", "src/pkg/syn.py", b'open("model.onnx"\n'),
        _src("pkg/nul.py", "src/pkg/nul.py", b'x\x00 = "model.onnx"\n'),
    ]
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([model], sources)

    assert not model.usage_files
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(warnings) == 2
    assert len(infos) == 2


def test_unparseable_file_not_mentioning_any_model_stays_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Templates, Python 2 scripts or broken fixtures that do not mention a
    model file name are skipped by the pre-filter and never parsed."""
    model = _meta("model.onnx")
    template = _src("pkg/tmpl.py", "src/pkg/tmpl.py", b"def {{ name }}():\n")
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([model], [template])

    assert not model.usage_files
    assert not caplog.records


def test_same_named_models_emit_mention_once_and_escape_newlines(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two models in different directories sharing a file name emit one
    ``usage-unparseable/mention`` line per file, and a newline in the source
    path cannot forge a second log line."""
    m1 = AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name="dup.onnx",
            file_path_relative="pkg/a/dup.onnx",
            physical_path="/abs/tmp/pkg/a/dup.onnx",
        )
    )
    m2 = AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name="dup.onnx",
            file_path_relative="pkg/b/dup.onnx",
            physical_path="src/pkg/b/dup.onnx",
        )
    )
    source = _src("pkg/bad\nname.py", "src/pkg/bad\nname.py", b"open('dup.onnx'\n")
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([m1, m2], [source])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(warnings) == 1
    assert len(infos) == 1
    for rec in (*warnings, *infos):
        assert "\n" not in rec.getMessage()
        assert record_problem(rec) is None


def test_usage_models_keeps_a_temporary_physical_path_out_of_the_paths() -> None:
    """An ``--allow-build`` file has an absolute temporary ``physical_path``:
    it must not reach the model's paths, whatever the caller."""
    temp = tempfile.gettempdir().replace("\\", "/")
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name="m.onnx",
            file_path_relative="pkg/m.onnx",
            physical_path=f"{temp}/build-x/pkg/m.onnx",
        )
    )
    same = AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name="m.onnx",
            file_path_relative="pkg/m.onnx",
            physical_path="pkg/m.onnx",
        )
    )
    assert [m.paths for _, m in usage_models([meta, same])] == [
        ("pkg/m.onnx",),
        ("pkg/m.onnx",),
    ]
