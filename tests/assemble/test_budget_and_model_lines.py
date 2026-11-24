# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which file a model's warning names (the ``FORMAT=``/``FILE=`` pair), and
when the metadata budget says it left every key out.

See also: tests/assemble/test_annotation_metadata_truncation.py (the budget)
and tests/assemble/test_ai_package_revision.py (the release time).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging

import pytest

from pitloom.assemble.spdx3.document import build_model
from pitloom.assemble.spdx3.provenance import build_source_metadata_annotation
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.logging_config import CODE_ATTR
from tests._author_routes import CREATED

from .conftest import _DOC_NAME, _DOC_UUID, _make_ci

_SUBJECT = "urn:doc#ai_AIPackage-1"
_RLO = "\u202e"


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR, None)}]"
        for r in caplog.records
        if r.levelno >= logging.WARNING
    ]


def _budget_lines(
    caplog: pytest.LogCaptureFixture, metadata: dict[str, object], budget: int
) -> list[str]:
    with caplog.at_level(logging.WARNING):
        ann = build_source_metadata_annotation(
            _SUBJECT,
            "gguf",
            metadata,
            _make_ci(),
            _DOC_NAME,
            _DOC_UUID,
            max_metadata_bytes=budget,
            where="m.gguf",
        )
    assert ann is not None
    return _lines(caplog)


def test_every_key_left_out_names_the_file_a_caller_passes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The budget keeps the envelope but drops every key: the line names
    the model file, as the budget line that leaves the annotation out does."""
    metadata: dict[str, object] = {"k1": "x" * 40, "k2": "y" * 40, "k3": "z" * 40}
    assert _budget_lines(caplog, metadata, 230) == [
        "WARNING: FORMAT=gguf FILE=m.gguf: larger than the 230-byte "
        "max-source-metadata-bytes cap; every metadata key left out of the "
        "artifact-metadata annotation [over-cap]"
    ]


def test_a_partial_drop_does_not_say_every_key_was_left_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One key too large for the budget, two that fit: the annotation says
    it is truncated, the log says nothing (no key kept is not the case)."""
    metadata: dict[str, object] = {
        "general.architecture": "llama",
        "block_count": 32,
        "tokens": [f"token_{i}" for i in range(2000)],
    }
    assert _budget_lines(caplog, metadata, 500) == []


def _info(**paths: str) -> AiModelFormatInfo:
    return AiModelFormatInfo(model_format=AiModelFormat.GGUF, **paths)


@pytest.mark.parametrize(
    ("info", "url", "named"),
    [
        (
            _info(
                physical_path="src/p/phys.gguf",
                file_path_relative="p/rel.gguf",
                file_name="base.gguf",
            ),
            "https://example.com/m",
            "src/p/phys.gguf",
        ),
        (
            _info(file_path_relative="p/rel.gguf", file_name="base.gguf"),
            "https://example.com/m",
            "p/rel.gguf",
        ),
        (_info(file_name="base.gguf"), "https://example.com/m", "base.gguf"),
        (_info(), "https://example.com/m", "https://example.com/m"),
        (_info(), None, "the-model"),
    ],
    ids=["physical-path", "relative-path", "file-name", "url", "name"],
)
def test_a_model_warning_names_its_file_by_the_first_of_five_spellings(
    caplog: pytest.LogCaptureFixture,
    info: AiModelFormatInfo,
    url: str | None,
    named: str,
) -> None:
    model = AiModelMetadata(
        name="the-model", format_info=info, url=url, release_time="yesterday"
    )
    with caplog.at_level(logging.WARNING):
        build_model(model, CREATED)
    assert _lines(caplog) == [
        f"WARNING: FORMAT=gguf FILE={named}: release time is not ISO 8601; "
        "left out [model-field-invalid]"
    ]


def test_a_blank_release_time_states_none_and_a_bad_one_is_said_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        build_model(AiModelMetadata(name="m", release_time=""), CREATED)
    assert not _lines(caplog)
    with caplog.at_level(logging.WARNING):
        build_model(AiModelMetadata(name="m", release_time=" "), CREATED)
    assert len(_lines(caplog)) == 1


def test_an_escaped_name_names_the_format_then_the_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = AiModelMetadata(
        name=f"evil{_RLO}name", format_info=_info(physical_path="m.gguf")
    )
    with caplog.at_level(logging.WARNING):
        build_model(model, CREATED)
    assert _lines(caplog) == [
        "WARNING: FORMAT=gguf FILE=m.gguf: invisible or bidi control "
        "characters written as \\uXXXX in name [text-unsafe]"
    ]
