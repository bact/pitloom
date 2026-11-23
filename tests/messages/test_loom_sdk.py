# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The loom SDK's lines (``caller-info-unreadable``, ``model-file-missing``,
``reference-not-found/dataset``): a hostile dataset or model name and an
exception's text stay one trusted, masked line of bounded length.

See also: :mod:`pitloom.messages._loom_sdk`,
:mod:`tests.core.test_loom_sdk_lines` (each line in a ``loom.run`` block).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging

import pytest

from pitloom.logging_config import CODE_ATTR
from pitloom.messages import emit, trusted_message
from pitloom.messages._field_writers import NAME_CHARACTERS
from pitloom.messages.datasets import (
    CALLER_INFO_LINE,
    CALLER_INFO_UNREADABLE,
    LOOM_SDK_PREFIX,
    MODEL_FILE_MISSING,
)
from pitloom.messages.fragments import REFERENCE_NOT_FOUND_DATASET

_LOG = logging.getLogger("pitloom.loom_sdk_test")
_SECRET = "pw-s3cr3t"
_HOSTILE = [
    "a\nWARNING: forged [model-file-missing]",
    "\x1b[31mred\x1b[0m",
    f"https://u:{_SECRET}@example.org/x",
    "x" * 1_000_000,
    'O\'Brien "Q"',
    # masked before the cut, which falls just before the '@': cut first, the
    # user information would no longer read as one
    "x" * 481 + f"https://u:{_SECRET}@example.org/x",
]
_IDS = ["newline", "ansi", "credential", "1mb", "quotes", "credential-at-cut"]


def _printed(caplog: pytest.LogCaptureFixture) -> str:
    (record,) = [r for r in caplog.records if r.name == _LOG.name]
    return f"{record.levelname}: {record.getMessage()} [{getattr(record, CODE_ATTR)}]"


def _assert_safe(printed: str) -> None:
    assert printed.startswith(f"WARNING: {LOOM_SDK_PREFIX}")
    assert "\n" not in printed and "\x1b" not in printed and _SECRET not in printed
    assert trusted_message(printed) is not None


@pytest.mark.parametrize("name", _HOSTILE, ids=_IDS)
def test_hostile_dataset_names_stay_one_cut_line(
    caplog: pytest.LogCaptureFixture, name: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(
            _LOG,
            REFERENCE_NOT_FOUND_DATASET,
            logging.WARNING,
            dataset=name,
            dataset_input=name,
        )
    printed = _printed(caplog)
    _assert_safe(printed)
    assert len(printed) < 2 * NAME_CHARACTERS + 300


@pytest.mark.parametrize("name", _HOSTILE, ids=_IDS)
def test_hostile_model_names_stay_one_cut_line(
    caplog: pytest.LogCaptureFixture, name: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(_LOG, MODEL_FILE_MISSING, logging.WARNING, entity=name, path="m.pt")
    printed = _printed(caplog)
    _assert_safe(printed)
    assert len(printed) < NAME_CHARACTERS + 300


@pytest.mark.parametrize(
    ("dataset", "wanted", "shown"),
    [
        (None, None, "add_output_dataset(None) names input_datasets=None,"),
        ("out", "in", "add_output_dataset('out') names input_datasets='in',"),
    ],
    ids=["none", "names"],
)
def test_a_dataset_without_a_name_is_shown_as_none(
    caplog: pytest.LogCaptureFixture,
    dataset: str | None,
    wanted: str | None,
    shown: str,
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(
            _LOG,
            REFERENCE_NOT_FOUND_DATASET,
            logging.WARNING,
            dataset=dataset,
            dataset_input=wanted,
        )
    printed = _printed(caplog)
    assert shown in printed
    assert trusted_message(printed) is REFERENCE_NOT_FOUND_DATASET


@pytest.mark.parametrize("text", _HOSTILE, ids=_IDS)
def test_a_hostile_failure_stays_one_cut_line(
    caplog: pytest.LogCaptureFixture, text: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        emit(
            _LOG,
            CALLER_INFO_UNREADABLE,
            logging.WARNING,
            line=CALLER_INFO_LINE,
            failure=RuntimeError(text),
        )
    printed = _printed(caplog)
    _assert_safe(printed)
    assert len(printed) < 1000
