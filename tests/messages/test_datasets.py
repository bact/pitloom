# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The shared dataset entries (``dataset-field-invalid``,
``dataset-name-missing``, ``dataset-conflict``,
``dataset-conflict/spelling``), ``text-unsafe`` and
``model-field-invalid``: their lines, fields and helpers, and the
``properties`` tables against the display-text escape they name.

See also: :mod:`tests.messages.test_datasets_sites` (each call site) and
:mod:`tests.messages.test_datasets_hostile` (hostile values).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import datetime
import logging

import pytest

from pitloom.assemble.spdx3 import _display_text
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import FIELDS, MESSAGES, trusted_message
from pitloom.messages._field_tables import INPUT_KINDS, VALUE_TYPES
from pitloom.messages._fields_datasets import DATASET_VALUE_TYPES, OTHER_TYPE
from pitloom.messages._fields_text import TEXT_LABELS, TEXT_PROPERTIES
from pitloom.messages.datasets import (
    NOT_A_COUNT,
    NOT_A_URL,
    NOT_TEXT,
    UNQUOTED_VERSION,
    DatasetModel,
    say_one_dataset,
    warn_dataset_conflict,
    warn_dataset_field,
)
from pitloom.messages.text import warn_text_unsafe
from tests._message_drift import SAMPLES

_LOG = logging.getLogger("pitloom.datasets_test")
_NEW = (
    "dataset-conflict",
    "dataset-conflict/spelling",
    "dataset-field-invalid",
    "dataset-name-missing",
    "model-field-invalid",
    "text-unsafe",
)


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
        if r.name == _LOG.name
    ]


@pytest.mark.parametrize("code", _NEW)
def test_a_new_entry_reads_back_and_ships_in_0_25_0(code: str) -> None:
    entry = MESSAGES[code]
    assert entry.since == "0.25.0"
    for line in entry.lines:
        text = line.render({n: SAMPLES[n] for n in line.fields})
        assert trusted_message(f"{line.level}: {text} [{code}]") is entry


def test_the_labels_and_properties_are_the_escape_s() -> None:
    """The messages package cannot import ``assemble``: its copy of the
    labels and properties is held equal to the escape's."""
    assert set(TEXT_LABELS) == set(_display_text.LABELS)
    assert TEXT_PROPERTIES == _display_text.PROPERTIES


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (b"hi", "bytes"),
        ({"a"}, "set"),
        (("a",), "tuple"),
        (frozenset(), OTHER_TYPE),
        (object(), OTHER_TYPE),
        (datetime.date(2024, 1, 1), "date"),
        (True, "bool"),
        (None, "NoneType"),
    ],
    ids=["bytes", "set", "tuple", "frozenset", "object", "date", "bool", "none"],
)
def test_a_value_type_is_named_and_never_raises(value: object, shown: str) -> None:
    assert FIELDS["dataset_value_type"].write(value) == shown


def test_a_subclass_is_an_object() -> None:
    class Text(str):
        """A str subclass with a name of its own."""

    assert FIELDS["dataset_value_type"].write(Text("x")) == OTHER_TYPE


def test_every_lock_value_type_is_a_dataset_one() -> None:
    assert set(VALUE_TYPES) <= set(DATASET_VALUE_TYPES.values())


@pytest.mark.parametrize(
    "field",
    ["license", "general.dataset.0.repo_url", "rai:dataBiases", "creator name"],
)
def test_a_dataset_field_is_taken(field: str) -> None:
    assert FIELDS["dataset_field"].write(field) == field


@pytest.mark.parametrize("field", ["", "a b", "x\n", "creator  name", 5])
def test_anything_else_is_no_dataset_field(field: object) -> None:
    with pytest.raises(ValueError):
        FIELDS["dataset_field"].write(field)


def test_a_croissant_document_is_an_input_kind() -> None:
    assert "Croissant document" in INPUT_KINDS


def test_an_unknown_kind_is_a_programming_error() -> None:
    with pytest.raises(InternalError):
        warn_dataset_field(_LOG, "bogus", "s", "f")


@pytest.mark.parametrize(
    ("kind", "value", "end"),
    [
        (NOT_TEXT, 1, "a value of type int, not text; skipped"),
        (
            UNQUOTED_VERSION,
            datetime.date(2024, 1, 1),
            "a value of type date, not text; quote it to keep it as written; skipped",
        ),
        (UNQUOTED_VERSION, True, "quote it to keep it as written; skipped"),
        (UNQUOTED_VERSION, b"x", "a value of type bytes, not text; skipped"),
        (UNQUOTED_VERSION, ["1"], "a value of type list, not text; skipped"),
        (NOT_A_URL, None, "not a URL; skipped"),
        (NOT_A_COUNT, None, "not a whole number of zero or more; skipped"),
    ],
    ids=["text", "date", "bool", "bytes", "list", "url", "count"],
)
def test_each_kind_says_its_line(
    caplog: pytest.LogCaptureFixture, kind: str, value: object, end: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dataset_field(_LOG, kind, "s", "version", value)
    (line,) = _printed(caplog)
    assert line.endswith(f"{end} [dataset-field-invalid]")
    assert line.startswith("WARNING: dataset metadata: SOURCE='s' FIELD=version: ")


def test_the_conflict_and_spelling_lines(caplog: pytest.LogCaptureFixture) -> None:
    """A conflict names its model by its file, else by its name; the
    spelling line names no model (one dataset, whichever model reads it)."""
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        warn_dataset_conflict(_LOG, DatasetModel(file="m.gguf"), "org/name", "version")
        warn_dataset_conflict(_LOG, DatasetModel(name="Org/M"), "org/name", "license")
        warn_dataset_conflict(
            _LOG, DatasetModel(file="a b.gguf", name="M"), "org/name", "description"
        )
        say_one_dataset(_LOG, "org/name", "Org/Name")
    assert _printed(caplog) == [
        "WARNING: FILE=m.gguf DATASET='org/name' FIELD=version: references "
        "differ; kept the first [dataset-conflict]",
        "WARNING: MODEL='Org/M' DATASET='org/name' FIELD=license: references "
        "differ; kept the first [dataset-conflict]",
        "WARNING: FILE=a b.gguf DATASET='org/name' FIELD=description: references "
        "differ; kept the first [dataset-conflict]",
        "INFO: DATASET='org/name': 'Org/Name' names it too; kept the first "
        "spelling [dataset-conflict/spelling]",
    ]
    assert all(trusted_message(line) is not None for line in _printed(caplog))


@pytest.mark.parametrize(
    "named",
    [{}, {"file": ""}, {"name": ""}, {"file": "", "name": "M"}],
    ids=["none", "empty-file", "empty-name", "empty-file-and-name"],
)
def test_a_dataset_model_is_named(named: dict[str, str]) -> None:
    with pytest.raises(InternalError, match="dataset's model"):
        DatasetModel(**named)


def test_text_unsafe_needs_a_subject(caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(ValueError):
        warn_text_unsafe(_LOG, ["name"])
    with pytest.raises(ValueError):
        warn_text_unsafe(_LOG, ["no such property"], dataset="d")
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_text_unsafe(_LOG, ("license name", "comment"), format="gguf", file="m")
    assert _printed(caplog) == [
        "WARNING: FORMAT=gguf FILE=m: invisible or bidi control characters "
        "written as \\uXXXX in license name, comment [text-unsafe]"
    ]


def test_the_over_cap_advice_names_the_metadata_budget() -> None:
    advice = MESSAGES["over-cap"].advice
    assert "Four caps are settings" in advice
    assert "--max-source-metadata-bytes" in advice
