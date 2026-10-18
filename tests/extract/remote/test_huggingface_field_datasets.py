# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model card's ``datasets:`` key as the Hub passes it on: a list, but cards
also state one dataset as a bare string, or something that is not text."""

from __future__ import annotations

import logging

import pytest

from pitloom.extract.remote.huggingface_field import _extract_datasets


@pytest.mark.parametrize(
    ("value", "names", "warned"),
    [
        (["a/b", "c/d"], ["a/b", "c/d"], False),
        ("imdb", ["imdb"], False),  # not four one-letter datasets
        (["a/b", "a/b", " c/d "], ["a/b", "a/b", "c/d"], False),  # repeats kept
        (["a/b", None, {"x": 1}, ["y"]], ["a/b"], True),
        (5, [], True),
        (True, [], True),
        ("  ", [], False),
        (None, [], False),
    ],
)
def test_card_datasets_read_as_text(
    value: object,
    names: list[str],
    warned: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        refs = _extract_datasets({"card_data": {"datasets": value}}, [], {})
    assert [r.metadata.name for r in refs] == names
    assert bool(caplog.records) is warned
