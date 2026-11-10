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

import contextlib
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.core.dataset_names import MAX_CARD_DATASETS
from pitloom.extract.remote import huggingface_dataset as hub_dataset
from pitloom.extract.remote import read_huggingface
from pitloom.extract.remote.huggingface_dataset import _load_dataset_card
from tests._unreadable import deny
from tests.extract.remote.hf_patches._hf_patches_base import (
    _make_card_data,
    _patch_hf_calls,
    fake_hub,
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
    ("body", "said"),
    [
        (
            b"---\nlicense: mit\n" + b"x" * (1 << 21),
            "FILE=o/d: larger than the 1048576-byte dataset-card cap; frontmatter "
            "not closed within it; skipped | Field(s) affected (skipped): license, "
            "description, keywords",
        ),
        (
            b"---\nlicense: mit\n---\n",
            "FILE=o/d: could not read for the Hugging Face dataset card; "
            "Permission denied",
        ),
    ],
    ids=["unclosed-over-cap", "denied"],
)
def test_a_card_read_warning_names_the_dataset_not_the_cache_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    body: bytes,
    said: str,
) -> None:
    """A card whose frontmatter is not closed within the read cap, and one
    that cannot be opened, each warn once, by dataset id."""
    card = tmp_path / "snapshots" / "README.md"
    card.parent.mkdir()
    card.write_bytes(body)
    denied = deny(card, "open", monkeypatch) if said.endswith("denied") else None
    with denied or contextlib.nullcontext():
        assert _load_dataset_card(fake_hub(card), "o/d", _SHA) == (None, {})
    (message,) = _card_warnings(caplog)
    assert message == said
    assert str(tmp_path) not in message and "snapshots" not in message


def test_a_malformed_card_is_named_by_its_kind_and_dataset(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The card's text is kept, its frontmatter used for nothing."""
    card = tmp_path / "README.md"
    card.write_bytes(b"---\nlicense: [mit\n---\nText.\n")
    assert _load_dataset_card(fake_hub(card), "o/d", _SHA) == (
        "---\nlicense: [mit\n---\nText.\n",
        {},
    )
    (message,) = _card_warnings(caplog)
    said = "FILE=o/d: Hugging Face dataset card frontmatter is not valid YAML; "
    # The parser's own text ends the line.
    assert message.startswith(said) and str(tmp_path) not in message


def test_a_card_gone_from_the_download_is_absent_and_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Absent data is quiet: no card is read, and nothing is said."""
    card = tmp_path / "snapshots" / "README.md"
    assert _load_dataset_card(fake_hub(card), "o/d", _SHA) == (None, {})
    assert not _card_warnings(caplog)


def test_a_read_failure_quoting_the_temporary_path_is_given_by_reason() -> None:
    error = PermissionError(13, "Permission denied", _CACHE)
    with (
        patch.object(hub_dataset, "read_card", side_effect=error),
        patch.object(hub_dataset.log, "warning") as warn,
    ):
        assert _load_dataset_card(fake_hub(Path(_CACHE)), "o/d", _SHA) == (None, {})
    (call,) = warn.call_args_list
    assert call.args[1:] == ("o/d", "Permission denied")
    assert _CACHE not in str(call)


def test_a_failure_without_a_path_keeps_its_message() -> None:
    with (
        patch.object(hub_dataset, "read_card", side_effect=OSError("odd for o/d")),
        patch.object(hub_dataset.log, "warning") as warn,
    ):
        _load_dataset_card(fake_hub(Path("README.md")), "o/d", _SHA)
    assert warn.call_args.args[1:] == ("o/d", "odd for o/d")
