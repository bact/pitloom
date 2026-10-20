# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The datasets a Hub model card lists: one reference per dataset (a Hub id
in another letter case, or with other whitespace, is the same dataset), at
most :data:`~pitloom.core.dataset_names.MAX_CARD_DATASETS` of them, and a
warning about the card read that names the dataset, never a local cache
path.

See also: tests/extract/remote/test_huggingface_dataset.py (the lookups),
tests/core/test_dataset_names.py (the shared naming rules).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.core.dataset_names import MAX_CARD_DATASETS
from pitloom.extract.remote import huggingface_dataset as hub_dataset
from pitloom.extract.remote import read_huggingface
from pitloom.extract.remote.huggingface_dataset import _load_dataset_card
from tests.extract.remote.hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
)

_SHA = "89abcdef0123456789abcdef0123456789abcdef"


def _names(listed: list[str], tags: list[str] | None = None) -> list[str]:
    card = _make_card_data(datasets=listed or None)
    info = {"author": "a", "sha": "d", "tags": [f"dataset:{t}" for t in tags or []]}
    with (
        _patch_hf_calls(card_data=card, hub_info=info),
        patch.object(hub_dataset, "_load_dataset_info", return_value=None),
    ):
        return [r.metadata.name for r in read_huggingface("acme/model").datasets]


@pytest.mark.parametrize(
    ("listed", "kept"),
    [
        (["O/D", "o/d", " o/D\t"], ["O/D"]),
        (["o/d", "o/e", "O/D"], ["o/d", "o/e"]),
        (["My  corpus", "My corpus", "my corpus"], ["My  corpus", "my corpus"]),
        (["c4", "C4"], ["c4"]),  # a legacy id has no owner
        (["o/d", "", "  "], ["o/d"]),
    ],
    ids=["id-case-space", "order", "plain-name-case-matters", "legacy", "blank"],
)
def test_a_dataset_listed_twice_is_one_reference(
    listed: list[str], kept: list[str]
) -> None:
    assert _names(listed) == kept


def test_the_tag_fallback_is_deduplicated_too() -> None:
    assert _names([], tags=["o/d", "O/D", "o/e"]) == ["o/d", "o/e"]


def test_a_card_listing_too_many_datasets_is_cut_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    listed = [f"o/d{i}" for i in range(MAX_CARD_DATASETS + 5)]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        names = _names(listed)
    assert names == listed[:MAX_CARD_DATASETS]  # card order, same on every run
    (message,) = [
        r.getMessage()
        for r in caplog.records
        if "model-card-datasets" in r.getMessage()
    ]
    assert message == (
        "FORMAT=huggingface FILE=https://huggingface.co/acme/model: larger than "
        f"the {MAX_CARD_DATASETS}-dataset model-card-datasets cap; "
        f"the first {MAX_CARD_DATASETS} kept"
    )


def test_a_card_at_the_cap_is_whole_and_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    listed = [f"o/d{i}" for i in range(MAX_CARD_DATASETS)]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert _names(listed) == listed
    assert not [r for r in caplog.records if "model-card-datasets" in r.getMessage()]


def test_repeats_do_not_count_against_the_cap(
    caplog: pytest.LogCaptureFixture,
) -> None:
    listed = ["o/d", "O/D"] * MAX_CARD_DATASETS
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert _names(listed) == ["o/d"]
    assert not [r for r in caplog.records if "model-card-datasets" in r.getMessage()]


_CACHE = "/cache/hf/datasets--o--d/snapshots/89abcdef/README.md"


def _card_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    "body",
    [b"---\nlicense: mit\n" + b"x" * (1 << 21), None],
    ids=["unclosed-over-cap", "missing"],
)
def test_a_card_read_warning_names_the_dataset_not_the_cache_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes | None
) -> None:
    """A card whose frontmatter is not closed within the read cap, and one
    that cannot be opened, each warn once, by dataset id."""
    card = tmp_path / "snapshots" / "README.md"
    card.parent.mkdir()
    if body is not None:
        card.write_bytes(body)
    with patch("huggingface_hub.hf_hub_download", return_value=str(card)):
        assert _load_dataset_card("o/d", _SHA) == (None, {})
    (message,) = _card_warnings(caplog)
    assert "o/d" in message
    assert str(tmp_path) not in message and "snapshots" not in message


def test_a_download_failure_quoting_the_cache_path_is_given_by_reason() -> None:
    caplog_error = PermissionError(13, "Permission denied", _CACHE)
    with patch("huggingface_hub.hf_hub_download", side_effect=caplog_error):
        with patch.object(hub_dataset.log, "warning") as warn:
            assert _load_dataset_card("o/d", _SHA) == (None, {})
    (call,) = warn.call_args_list
    assert call.args[1:] == ("o/d", "Permission denied")
    assert _CACHE not in str(call)


def test_a_failure_without_a_path_keeps_its_message() -> None:
    with patch("huggingface_hub.hf_hub_download", side_effect=OSError("503 for o/d")):
        with patch.object(hub_dataset.log, "warning") as warn:
            _load_dataset_card("o/d", _SHA)
    assert warn.call_args.args[1:] == ("o/d", "503 for o/d")
