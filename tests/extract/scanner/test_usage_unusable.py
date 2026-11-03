# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``usage-unusable``: a ``.PY`` source is not read, and said once
when a model was found.

See also: tests/extract/scanner/test_usage_unparseable.py (a ``.py`` file that
cannot be parsed) and :mod:`pitloom.messages._usage_unusable`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.extract.scanner import UsageSource, attach_usage_references
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import USAGE_UNUSABLE, trusted_message
from tests._message_drift import record_problem

_LOGGER_NAME = "pitloom.extract.scanner"


def _meta(name: str = "model.onnx") -> AiModelMetadata:
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name=name,
            file_path_relative=f"pkg/{name}",
            physical_path=f"src/pkg/{name}",
        )
    )


def _unread(dist: str) -> UsageSource:
    """A source whose content must never be opened."""

    def _open() -> Iterator[bytes]:
        raise AssertionError(f"{dist} was opened")

    return UsageSource(
        distribution_path=dist,
        physical_path=f"src/{dist}",
        open=_open,  # type: ignore[arg-type]
    )


def test_a_py_source_in_capitals_is_warned_of_and_not_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = _meta()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([model], [_unread("pkg/RUN.PY")])

    assert not model.usage_files
    (record,) = caplog.records
    text = (
        "FILE=src/pkg/RUN.PY: not scanned for usage; only a .py extension is "
        "read as Python"
    )
    assert record.levelno == logging.WARNING
    assert record.getMessage() == text
    assert getattr(record, CODE_ATTR) == USAGE_UNUSABLE.code
    assert record_problem(record) is None
    assert trusted_message(f"WARNING: {text} [{USAGE_UNUSABLE.code}]") is USAGE_UNUSABLE


@pytest.mark.parametrize(
    ("dist", "said"),
    [
        ("pkg/RUN.PY", True),
        ("pkg/run.Py", True),
        ("pkg/run.pY", True),
        ("pkg/run.pyc", False),
        ("pkg/run.pyw", False),
        ("pkg/run.PYI", False),
        ("pkg/PY", False),
        ("pkg/run.txt", False),
    ],
    ids=["upper", "title", "mixed", "pyc", "pyw", "pyi", "bare", "txt"],
)
def test_only_a_name_ending_in_py_in_other_case_is_said(
    caplog: pytest.LogCaptureFixture, dist: str, said: bool
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([_meta()], [_unread(dist)])
    assert len(caplog.records) == int(said)


def test_without_a_model_a_py_source_in_capitals_stays_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([], [_unread("pkg/RUN.PY")])
    assert not caplog.records


def test_each_py_source_in_capitals_is_said_once_in_path_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = [_unread("pkg/B.PY"), _unread("pkg/A.PY")]
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        attach_usage_references([_meta("a.onnx"), _meta("b.onnx")], sources)
    assert [r.getMessage().partition(":")[0] for r in caplog.records] == [
        "FILE=src/pkg/A.PY",
        "FILE=src/pkg/B.PY",
    ]
