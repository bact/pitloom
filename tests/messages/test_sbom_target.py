# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SBOM-target entries (``project-or-model-not-found``,
``model-ambiguous``): each line reads back as its entry, a value of the
wrong shape is refused, and the error names the folder quoted.

See also: tests/extract/test_model_target.py (the resolver that says them)
and tests/messages/test_model_stub.py (a neighbouring family).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from pitloom.messages import (
    MODEL_AMBIGUOUS,
    NO_SBOM_TARGET,
    CodedValueError,
    Message,
    _sbom_target,
    emit,
    trusted_message,
)
from tests._message_drift import TEST_LOGGER_PREFIX, raised_as

_LOG = logging.getLogger(f"{TEST_LOGGER_PREFIX}sbom_target")


def test_the_module_has_its_two_codes() -> None:
    assert [m.code for m in _sbom_target.ENTRIES] == [
        "project-or-model-not-found",
        "model-ambiguous",
    ]
    assert {m.since for m in _sbom_target.ENTRIES} == {"0.24.0"}
    assert all(m.effect == "not-written" for m in _sbom_target.ENTRIES)


@pytest.mark.parametrize(
    ("message", "line"),
    [
        (
            NO_SBOM_TARGET,
            "ERROR: SBOM generation failed: 'models': no Python project "
            "(pyproject.toml, setup.cfg or setup.py) and no AI model file of a "
            "supported format; name a project folder or a model file "
            "[project-or-model-not-found]",
        ),
        (
            MODEL_AMBIGUOUS,
            "INFO: FILE=sub/a.gguf: one of several AI model files [model-ambiguous]",
        ),
        (
            MODEL_AMBIGUOUS,
            "ERROR: 'https://example.org/o/r/tree/main/m': several AI model files "
            "(2 files); name one file [model-ambiguous]",
        ),
    ],
    ids=["none", "candidate", "ambiguous"],
)
def test_a_printed_line_is_trusted_as_its_entry(message: Message, line: str) -> None:
    assert trusted_message(line) is message


@pytest.mark.parametrize(
    "line",
    [
        # an unquoted path, a count that is no count, another level
        "ERROR: models: no Python project (pyproject.toml, setup.cfg or "
        "setup.py) and no AI model file of a supported format; name a project "
        "folder or a model file [project-or-model-not-found]",
        "ERROR: 'm': several AI model files (1 files); name one file [model-ambiguous]",
        "WARNING: FILE=a.gguf: one of several AI model files [model-ambiguous]",
    ],
    ids=["unquoted", "count", "level"],
)
def test_a_line_out_of_its_shapes_is_not_trusted(line: str) -> None:
    assert trusted_message(line) is None


def test_the_errors_name_the_folder_quoted() -> None:
    none = CodedValueError(NO_SBOM_TARGET, path="m d")
    assert str(none).startswith("'m d': no Python project (") and raised_as(
        none, NO_SBOM_TARGET
    )
    several = CodedValueError(MODEL_AMBIGUOUS, path="m", count=3)
    assert str(several) == "'m': several AI model files (3 files); name one file"
    assert raised_as(several, MODEL_AMBIGUOUS)


@pytest.mark.parametrize(
    ("values"),
    [{"file": None}, {"file": "a", "count": 2}],
    ids=["file-none", "extra-count"],
)
def test_a_value_out_of_shape_is_refused_when_said(
    values: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(ValueError):
        emit(_LOG, MODEL_AMBIGUOUS, logging.INFO, **values)
    assert not caplog.records
