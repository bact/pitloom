# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SBOM-target entries (``target-ambiguous``,
``project-or-model-not-found``, ``model-ambiguous`` and its ``/over-cap``
variant, ``project-not-found`` and its ``/model-files`` variant): each line
reads back as its entry, a value of the wrong shape is refused, and the error
names the folder quoted.

See also: tests/extract/test_model_target.py (the resolver that says them)
and tests/messages/test_model_stub.py (a neighbouring family).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from pitloom.messages import (
    MODEL_AMBIGUOUS,
    MODEL_AMBIGUOUS_OVER_CAP,
    MODEL_FILES_LINE,
    NO_SBOM_TARGET,
    ONE_MODEL_LINE,
    PROJECT_NOT_FOUND,
    PROJECT_NOT_FOUND_LINE,
    PROJECT_NOT_FOUND_MODEL_FILES,
    TARGET_AMBIGUOUS,
    CodedFileNotFoundError,
    CodedValueError,
    Message,
    _sbom_target,
    emit,
    trusted_message,
)
from tests._message_drift import TEST_LOGGER_PREFIX, raised_as

_LOG = logging.getLogger(f"{TEST_LOGGER_PREFIX}sbom_target")


def test_the_module_has_its_codes() -> None:
    """Only the decision is said with no effect on the SBOM; every refusal
    writes none."""
    assert [m.code for m in _sbom_target.ENTRIES] == [
        "target-ambiguous",
        "project-or-model-not-found",
        "model-ambiguous",
        "model-ambiguous/over-cap",
        "project-not-found",
        "project-not-found/model-files",
    ]
    assert {m.since for m in _sbom_target.ENTRIES} == {"0.23.4"}
    assert [m.effect for m in _sbom_target.ENTRIES] == ["none"] + ["not-written"] * 5


@pytest.mark.parametrize(
    ("message", "line"),
    [
        (
            NO_SBOM_TARGET,
            "ERROR: loom project: 'models': no Python project "
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
        (
            MODEL_AMBIGUOUS_OVER_CAP,
            "ERROR: 'https://example.org/o/r/tree/main/m': more than 1000 files "
            "that could be AI models, none read; name one file "
            "[model-ambiguous/over-cap]",
        ),
        (
            TARGET_AMBIGUOUS,
            "INFO: FILE=sub/README.md: not an AI model file; reading its folder "
            "[target-ambiguous]",
        ),
        (
            TARGET_AMBIGUOUS,
            "INFO: FILE=m.gguf: the one AI model file; reading it [target-ambiguous]",
        ),
        (
            PROJECT_NOT_FOUND,
            "ERROR: loom project: No pyproject.toml, setup.cfg, or "
            "setup.py found in 'p' [project-not-found]",
        ),
        (
            PROJECT_NOT_FOUND_MODEL_FILES,
            "ERROR: No pyproject.toml, setup.cfg, or setup.py found in "
            "'https://h/o/r'; it holds files that may be AI models (a.gguf and 5 "
            "more): use 'loom model <url>' or 'loom generate <url>' "
            "[project-not-found/model-files]",
        ),
    ],
    ids=[
        "none",
        "candidate",
        "ambiguous",
        "over-cap",
        "named",
        "one",
        "project",
        "models",
    ],
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
        # the base line's code on the over-cap variant's line
        "ERROR: 'm': more than 1000 files that could be AI models, none read; "
        "name one file [model-ambiguous]",
        # the base line's code on the variant's line
        "ERROR: No pyproject.toml, setup.cfg, or setup.py found in 'p'; it holds "
        "files that may be AI models (a.gguf): use 'loom model <url>' or 'loom "
        "generate <url>' [project-not-found]",
    ],
    ids=["unquoted", "count", "level", "over-cap-code", "variant"],
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
    many = CodedValueError(MODEL_AMBIGUOUS_OVER_CAP, path="m", limit=1000)
    assert str(many) == (
        "'m': more than 1000 files that could be AI models, none read; name one file"
    )
    assert raised_as(many, MODEL_AMBIGUOUS_OVER_CAP)
    absent = CodedFileNotFoundError(
        PROJECT_NOT_FOUND, line=PROJECT_NOT_FOUND_LINE, path="m d"
    )
    assert isinstance(absent, FileNotFoundError) and raised_as(
        absent, PROJECT_NOT_FOUND
    )
    assert str(absent) == "No pyproject.toml, setup.cfg, or setup.py found in 'm d'"
    hint = MODEL_FILES_LINE.render({"path": "u", "files": "a\nb.gguf"})
    assert "('a\\nb.gguf')" in hint and "\n" not in hint


@pytest.mark.parametrize(
    ("message", "values", "complaint"),
    [
        (MODEL_AMBIGUOUS, {"file": None}, "not a path"),
        (MODEL_AMBIGUOUS, {"file": "a", "count": 2}, "name of its INFO lines"),
        (TARGET_AMBIGUOUS, {"file": "a"}, "name of its INFO lines"),
        (
            TARGET_AMBIGUOUS,
            {"file": "a", "line": MODEL_FILES_LINE},
            "not one of its INFO lines",
        ),
    ],
    ids=["file-none", "extra-count", "no-line", "other-line"],
)
def test_a_value_out_of_shape_is_refused_when_said(
    message: Message,
    values: dict[str, Any],
    complaint: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A value of the wrong shape, or a line not named (three name
    ``file``) or not the entry's, is refused before any record."""
    with pytest.raises(ValueError, match=complaint):
        emit(_LOG, message, logging.INFO, **values)
    assert not caplog.records


def test_a_chosen_line_is_said_with_its_code(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        emit(_LOG, TARGET_AMBIGUOUS, logging.INFO, line=ONE_MODEL_LINE, file="a\nb")
    assert caplog.messages == ["FILE='a\\nb': the one AI model file; reading it"]
