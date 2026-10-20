# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.dataset_merge`."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from typing import Any

import pytest

from pitloom.core.dataset_merge import merge_dataset_references
from pitloom.core.dataset_metadata import (
    DatasetMetadata,
    DatasetReference,
    FurtherLicences,
)


def _ref(role: str, name: str = "o/d", **fields: Any) -> DatasetReference:
    return DatasetReference(role, DatasetMetadata(name=name, **fields))


@pytest.mark.parametrize(
    ("names", "datasets"),
    [
        (["o/d", "O/D"], 1),  # Hub ids are case-insensitive
        (["Squad", "squad"], 1),  # so is a legacy id without an owner
        (["a  b", "a b"], 1),  # whitespace runs collapse
        (["My Data", "my data"], 2),  # a plain name is compared as written
    ],
    ids=["hub-case", "legacy-case", "whitespace", "plain-case"],
)
def test_spellings_of_one_dataset_merge(names: list[str], datasets: int) -> None:
    merged = merge_dataset_references(
        [_ref("trainedOn", names[0]), _ref("testedOn", names[1])]
    )
    assert len(merged) == datasets
    assert merged[0].metadata.name == names[0]
    if datasets == 1:
        assert merged[0].roles == ["trainedOn", "testedOn"]
        assert merged[0].names == names


def test_roles_are_distinct_and_in_order() -> None:
    merged = merge_dataset_references(
        [_ref("testedOn"), _ref("trainedOn"), _ref("testedOn")]
    )
    assert [m.roles for m in merged] == [["testedOn", "trainedOn"]]


def test_order_of_first_appearance_is_kept() -> None:
    merged = merge_dataset_references([_ref("trainedOn", n) for n in ("b", "a", "b")])
    assert [m.metadata.name for m in merged] == ["b", "a"]


def test_gaps_are_filled_with_provenance_and_nothing_is_overwritten() -> None:
    first = _ref("trainedOn", version="1", provenance={"version": "card"})
    second = _ref(
        "testedOn",
        version="2",
        creator="C",
        keywords=["k"],
        dataset_size=0,
        provenance={"version": "other", "creator": "croissant"},
    )
    (merged,) = merge_dataset_references([first, second])
    meta = merged.metadata
    assert (meta.version, meta.creator, meta.keywords) == ("1", "C", ["k"])
    assert meta.dataset_size == 0  # a stated zero is a value, not a gap
    assert meta.provenance == {"version": "card", "creator": "croissant"}


def test_licence_is_copied_with_its_further_licences() -> None:
    further = FurtherLicences(("MIT",), "dataset card")
    (merged,) = merge_dataset_references(
        [
            _ref("trainedOn"),
            _ref("testedOn", license="GPL-3.0", further_licenses=further),
        ]
    )
    assert merged.metadata.license == "GPL-3.0"
    assert merged.metadata.further_licenses == further


def test_a_set_licence_keeps_its_own_further_licences() -> None:
    (merged,) = merge_dataset_references(
        [
            _ref("trainedOn", license="MIT"),
            _ref(
                "testedOn",
                license="GPL-3.0",
                further_licenses=FurtherLicences(("MIT",), "dataset card"),
            ),
        ]
    )
    assert (merged.metadata.license, merged.metadata.further_licenses) == ("MIT", None)


def test_conflict_warns_once_per_field_and_keeps_the_first(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    (merged,) = merge_dataset_references(
        [_ref("trainedOn", version="1"), _ref("testedOn", version="2")]
    )
    assert merged.metadata.version == "1"
    assert [r.getMessage() for r in caplog.records] == [
        "FIELD=version: references to dataset o/d differ; the first is kept"
    ]


def test_equal_values_do_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    merge_dataset_references(
        [_ref("trainedOn", version="1"), _ref("testedOn", version="1")]
    )
    assert not caplog.records


def test_inputs_are_not_changed() -> None:
    first, second = _ref("trainedOn"), _ref("testedOn", creator="C", keywords=["k"])
    merge_dataset_references([first, second])
    assert first.metadata.creator is None and first.metadata.keywords == []
    merged = merge_dataset_references([first, second])[0]
    merged.metadata.keywords.append("x")
    assert second.metadata.keywords == ["k"]


@pytest.mark.parametrize(
    ("first", "second", "kept"),
    [
        ("noAssertion", "no", "no"),  # not a claim: a later statement replaces it
        ("no", "noAssertion", "no"),  # and never replaces a statement
        ("noAssertion", None, "noAssertion"),
    ],
)
def test_no_assertion_is_not_a_claim(
    first: str, second: str | None, kept: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    (merged,) = merge_dataset_references(
        [
            _ref("trainedOn", has_sensitive_personal_information=first),
            _ref("testedOn", has_sensitive_personal_information=second),
        ]
    )
    assert merged.metadata.has_sensitive_personal_information == kept
    assert not caplog.records
