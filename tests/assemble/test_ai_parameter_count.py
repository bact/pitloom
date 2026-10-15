# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's parameter count is the ``ai_hyperparameter`` entry
``parameters``, sorted among the others (``quantization`` first), and the
package ``comment`` says so in one line whenever the entry is written.

See also: :mod:`tests.assemble.test_ai_originators` (the originators),
:mod:`tests.core.test_model_parameters` (the count's own checks).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from enum import IntEnum
from typing import Any

import pytest

from pitloom.assemble.spdx3.document import build, build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.model_parameters import (
    MAX_PARAMETER_COUNT,
    PARAMETER_COUNT_KEY,
    PARAMETER_COUNT_NOTE,
    PARAMETER_COUNT_PROVENANCE_KEY,
)
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from tests.warning_helpers import logged_warnings

_CREATION = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
_WHERE = "FORMAT=gguf FILE=m.gguf: "
_SKIPPED = "parameter count not recorded"
_PROVENANCE = {
    PARAMETER_COUNT_PROVENANCE_KEY: "Source: m.gguf | Field: tensor_infos",
    "name": "Source: m.gguf | Field: general.name",
}
_Graph = list[dict[str, Any]]


def _model(count: object = None, **kwargs: Any) -> AiModelMetadata:
    return AiModelMetadata(
        name="m",
        parameter_count=count,  # type: ignore[arg-type]  # hand-built on purpose
        format_info=AiModelFormatInfo(
            file_name="m.gguf", model_format=AiModelFormat.GGUF
        ),
        **kwargs,
    )


def _package(graph: _Graph) -> dict[str, Any]:
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    return package


def _single(model: AiModelMetadata, fmt: str = "annotation") -> _Graph:
    exporter = build_model(model, _CREATION, provenance=ProvenanceConfig(format=fmt))
    graph: _Graph = json.loads(exporter.to_json())["@graph"]
    return graph


def _project(model: AiModelMetadata, fmt: str = "annotation") -> _Graph:
    doc = DocumentModel(
        project=ProjectMetadata(name="p", version="1"),
        creation_metadata=_CREATION,
        ai_models=[model],
    )
    exporter = build(doc, provenance=ProvenanceConfig(format=fmt), offline=True)
    graph: _Graph = json.loads(exporter.to_json())["@graph"]
    return graph


def _entries(package: dict[str, Any]) -> list[tuple[str, str]]:
    return [(e["key"], e["value"]) for e in package.get("ai_hyperparameter", [])]


def test_the_count_is_sorted_among_hyperparameters_after_quantization() -> None:
    model = _model(7, quantization="Q4", hyperparameters={"z": 1, "a": 2, "q": 3})
    package = _package(_single(model))
    assert _entries(package) == [
        ("quantization", "Q4"),
        ("a", "2"),
        (PARAMETER_COUNT_KEY, "7"),
        ("q", "3"),
        ("z", "1"),
    ]
    assert package["comment"] == PARAMETER_COUNT_NOTE


class _Seven(IntEnum):
    SEVEN = 7


class _OddText(int):
    """An ``int`` whose ``str()`` is not its decimal digits."""

    def __str__(self) -> str:
        return "odd"


@pytest.mark.parametrize(
    "count", [_Seven.SEVEN, _OddText(7)], ids=["int-enum", "int-subclass"]
)
def test_an_int_subclass_count_is_written_as_its_integer_value(count: int) -> None:
    entries = _entries(_package(_single(_model(count))))
    assert entries == [(PARAMETER_COUNT_KEY, "7")]


@pytest.mark.parametrize("count", [MAX_PARAMETER_COUNT, 1], ids=["max", "one"])
def test_a_count_up_to_the_cap_is_written_in_decimal(count: int) -> None:
    assert _entries(_package(_single(_model(count)))) == [
        (PARAMETER_COUNT_KEY, str(count))
    ]


@pytest.mark.parametrize("count", [None, 0], ids=["none", "zero"])
def test_no_count_writes_no_entry_and_no_note_quietly(
    count: int | None, caplog: pytest.LogCaptureFixture
) -> None:
    package = _package(_single(_model(count, hyperparameters={"a": 1})))
    assert _entries(package) == [("a", "1")]
    assert "comment" not in package
    assert not logged_warnings(caplog)


@pytest.mark.parametrize(
    ("count", "reason"),
    [
        (True, "not a non-negative integer"),
        (-1, "not a non-negative integer"),
        ("7", "not a non-negative integer"),
        (10**5000, "larger than"),
    ],
    ids=["bool", "negative", "text", "huge"],
)
def test_a_hand_built_bad_count_warns_once_and_writes_nothing(
    count: object, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    package = _package(_single(_model(count, hyperparameters={"a": 1})))
    assert _entries(package) == [("a", "1")]
    assert "comment" not in package
    (message,) = logged_warnings(caplog)
    assert message.startswith(_WHERE)
    assert reason in message
    assert message.endswith(_SKIPPED)


def test_a_parameters_hyperparameter_is_replaced_by_the_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = _model(7, hyperparameters={PARAMETER_COUNT_KEY: "7B", "b": 1})
    package = _package(_single(model))
    assert _entries(package) == [("b", "1"), (PARAMETER_COUNT_KEY, "7")]
    assert package["comment"] == PARAMETER_COUNT_NOTE  # the entry is the count
    assert logged_warnings(caplog) == [
        _WHERE + "hyperparameter parameters replaced by the parameter count"
    ]


def test_without_a_count_a_parameters_hyperparameter_stays(
    caplog: pytest.LogCaptureFixture,
) -> None:
    package = _package(_single(_model(hyperparameters={PARAMETER_COUNT_KEY: "7B"})))
    assert _entries(package) == [(PARAMETER_COUNT_KEY, "7B")]
    assert "comment" not in package  # not the count: no note
    assert not logged_warnings(caplog)


_BIASES = "Known biases: b1; b2"
_PROV = "Metadata provenance: "


@pytest.mark.parametrize(
    ("fmt", "count", "lines"),
    [
        ("annotation", 7, [PARAMETER_COUNT_NOTE, _BIASES]),
        ("annotation", None, [_BIASES]),
        ("comment", 7, [PARAMETER_COUNT_NOTE, _BIASES, _PROV]),
        ("both", 7, [PARAMETER_COUNT_NOTE, _BIASES, _PROV]),
        ("both", None, [_BIASES, _PROV]),
    ],
    ids=["annotation", "annotation-no-count", "comment", "both", "both-no-count"],
)
def test_the_note_comes_first_then_biases_then_provenance(
    fmt: str, count: int | None, lines: list[str]
) -> None:
    model = _model(count, provenance=dict(_PROVENANCE))
    model.usage.known_biases = ["b1", "b2"]
    comment = _package(_single(model, fmt))["comment"]
    shown = [_PROV if line.startswith(_PROV) else line for line in comment.split("\n")]
    assert shown == lines


@pytest.mark.parametrize("fmt", ["annotation", "both"])
def test_both_routes_write_the_same_producer_count_and_comment(fmt: str) -> None:
    """Drift guard: :func:`build` and :func:`build_model` read one model the
    same way."""

    def facts(graph: _Graph) -> tuple[list[str], list[tuple[str, str]], str]:
        package = _package(graph)
        names = {e["spdxId"]: e["name"] for e in graph if "name" in e}
        return (
            [names[i] for i in package["originatedBy"]],
            _entries(package),
            package["comment"],
        )

    def model() -> AiModelMetadata:
        built = _model(
            123,
            originators=["Ann", "Org"],
            hyperparameters={"lr": 0.1},
            provenance=dict(_PROVENANCE),
        )
        built.usage.known_biases = ["b1"]
        return built

    single, project = facts(_single(model(), fmt)), facts(_project(model(), fmt))
    assert single == project
    assert single[0] == ["Ann", "Org"]
    assert (PARAMETER_COUNT_KEY, "123") in single[1]
    assert single[2].startswith(PARAMETER_COUNT_NOTE + "\nKnown biases: b1")
