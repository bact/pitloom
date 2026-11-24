# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the dataset fields and lines that
tests/messages/test_datasets.py does not pin: the shape of a dataset field
and of a value-type name, the fields that take text only, and the scalars
told to be quoted.

See also: tests/messages/test_datasets.py, test_datasets_sites.py and
test_datasets_hostile.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import datetime
import logging

import pytest

from pitloom.logging_config import CODE_ATTR
from pitloom.messages import FIELDS
from pitloom.messages.datasets import NOT_TEXT, UNQUOTED_VERSION, warn_dataset_field

_LOG = logging.getLogger("pitloom.datasets_gaps_test")


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
        if r.name == _LOG.name
    ]


@pytest.mark.parametrize(
    "field",
    [
        "@type",
        "_x",
        "@",
        "License",
        "a-b",
        "a@b",
        "a_b1",
        "creator name",
        "general.dataset.0.repo_url",
        "rai:dataBiases",
    ],
)
def test_a_field_name_of_the_documented_shape_is_taken(field: str) -> None:
    assert FIELDS["dataset_field"].write(field) == field


@pytest.mark.parametrize(
    "field",
    [
        "creator name name",
        "a name b",
        " name",
        "1x",
        "-a",
        ".a",
        ":a",
        "a b",
        "a$",
        "",
        "a\nb",
    ],
)
def test_a_name_suffix_comes_once_at_the_end_and_nothing_else_starts_a_name(
    field: str,
) -> None:
    with pytest.raises(ValueError):
        FIELDS["dataset_field"].write(field)


@pytest.mark.parametrize("value", [None, b"x", 5, ["a"]])
@pytest.mark.parametrize(
    "field", ["dataset_field", "dataset_source", "dataset_spelling"]
)
def test_a_field_that_takes_text_refuses_what_is_not_text(
    field: str, value: object
) -> None:
    """Only a dataset name may be ``None`` (a dataset declared without one):
    a source, a spelling and a field are text, and never shown as ``None``."""
    with pytest.raises(ValueError):
        FIELDS[field].write(value)


# pylint: disable-next=too-few-public-methods
class _Custom:
    """A class no table names."""


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (("a",), "tuple"),
        ({"a"}, "set"),
        (b"x", "bytes"),
        (_Custom(), "object"),
    ],
    ids=["tuple", "set", "bytes", "custom"],
)
def test_the_type_a_line_names_is_one_its_shape_allows(
    caplog: pytest.LogCaptureFixture, value: object, shown: str
) -> None:
    """The line is checked against the field's shape as it is said: a type
    name the shape leaves out would not be said at all."""
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dataset_field(_LOG, NOT_TEXT, "s", "f", value)
    assert _printed(caplog) == [
        f"WARNING: dataset metadata: SOURCE='s' FIELD=f: a value of type {shown}, "
        "not text; skipped [dataset-field-invalid]"
    ]


@pytest.mark.parametrize(
    "value",
    [
        datetime.datetime(2024, 1, 1, 10, 0),
        datetime.date(2024, 1, 1),
        1,
        1.1,
        True,
    ],
    ids=["datetime", "date", "int", "float", "bool"],
)
def test_a_scalar_yaml_read_from_unquoted_text_is_told_to_be_quoted(
    caplog: pytest.LogCaptureFixture, value: object
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dataset_field(_LOG, UNQUOTED_VERSION, "s", "version", value)
    (line,) = _printed(caplog)
    assert "not text; quote it to keep it as written; skipped" in line
    assert f"a value of type {type(value).__name__}," in line
