# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Each dataset a Hub model card lists is filled from its own Hub dataset
repository: licence, description, keywords, version and owner, as stated;
a failed request warns and keeps the dataset; the lookups are capped.

See also: tests/extract/remote/test_huggingface_dataset_surfaces.py (the
SBOM on each surface, the gate and byte identity) and
tests/extract/dataset/test_licence.py (the shared licence rules).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub.errors import RemoteEntryNotFoundError

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.extract.remote import huggingface_dataset as hub_dataset
from pitloom.extract.remote import read_huggingface
from pitloom.extract.remote.huggingface_dataset import (
    MAX_HUB_DATASET_LOOKUPS,
    _is_dataset_id,
    _load_dataset_card,
    _load_dataset_info,
)
from tests.conformance.g7ai_shared import without_licence_database
from tests.extract.remote.hf_patches._hf_patches_base import (
    HubDataset,
    _make_card_data,
    _patch_hf_calls,
)

_SHA = "89abcdef0123456789abcdef0123456789abcdef"
_LINK = "https://example.org/licence"
_LOGGER = "pitloom.extract.remote.huggingface_dataset"


@pytest.fixture(autouse=True)
def _no_licence_database() -> Iterator[None]:
    """The model licence is not canonicalised (nor its database warned of)."""
    with without_licence_database():
        yield


def _read(
    datasets: dict[str, HubDataset], listed: list[str] | None = None
) -> list[DatasetMetadata]:
    card = _make_card_data(datasets=listed or list(datasets))
    with _patch_hf_calls(card_data=card, datasets=datasets):
        return [r.metadata for r in read_huggingface("acme/model").datasets]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("card_data", "licence", "fields"),
    [
        ({"license": "ODC-By-1.0"}, "ODC-By-1.0", "license"),
        ({"license": " cc-by-4.0 "}, "cc-by-4.0", "license"),
        ({"license": "other", "license_link": _LINK}, _LINK, "license, license_link"),
        (
            {"license": "OTHER", "license_name": "Acme", "license_link": _LINK},
            f"Acme ({_LINK})",
            "license, license_name, license_link",
        ),
        ({"license": "other", "license_name": "Acme"}, "Acme", "license, license_name"),
        ({"license": "other"}, None, None),
        ({"license": "unknown"}, None, None),
        ({"license": "NOASSERTION"}, None, None),
        ({"license": ""}, None, None),
        ({"license_link": _LINK}, None, None),  # no `license`: link not read
        ({}, None, None),
    ],
    ids=[
        "spdx", "stripped", "other-link", "other-name-link", "other-name",
        "other-bare", "unknown", "noassertion", "blank", "link-only", "absent",
    ],
)  # fmt: skip
def test_the_card_licence(
    card_data: dict[str, Any],
    licence: str | None,
    fields: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (meta,) = _read({"o/d": {"card_data": card_data}})
    assert meta.license == licence
    assert meta.provenance.get("license") == (
        None
        if fields is None
        else f"Source: Hugging Face Hub | Field: dataset card {fields}"
    )
    assert not _warnings(caplog)  # absent or weak: silent


def test_every_stated_field_is_read_with_its_provenance() -> None:
    hub = {
        "info": {"author": "acme", "sha": _SHA},
        "card_text": "---\nx: 1\n---\n# Title\n\nA corpus\nof text.\n\nMore.\n",
        "card_data": {"license": "MIT", "tags": ["web", " web ", 3, "en"]},
    }
    (meta,) = _read({"o/d": hub})
    assert (meta.name, meta.download_url) == (
        "o/d",
        "https://huggingface.co/datasets/o/d",
    )
    assert (meta.version, meta.creator) == (_SHA, "acme")
    assert (meta.description, meta.keywords) == ("A corpus of text.", ["web", "en"])
    hub_field = "Source: Hugging Face Hub | Field: "
    assert meta.provenance == {
        "name": hub_field + "model card YAML (datasets)",
        "license": hub_field + "dataset card license",
        "description": hub_field + "dataset card",
        "keywords": hub_field + "dataset card tags",
        "version": hub_field + "dataset_info sha",
        "creator": hub_field + "dataset_info author | Method: repository_owner",
    }


@pytest.mark.parametrize(
    "hub",
    [
        {},
        {"info": {"sha": "main", "author": ""}, "card_text": "# Only a heading\n"},
        {"card_data": {"tags": "solo"}},
    ],
    ids=["nothing", "not-a-sha-no-owner", "one-tag-string"],
)
def test_an_unstated_field_stays_unset(
    hub: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    (meta,) = _read({"o/d": hub})
    assert (meta.version, meta.creator, meta.description, meta.license) == ((None,) * 4)
    assert meta.keywords == (["solo"] if "card_data" in hub else [])
    assert not _warnings(caplog)


def test_the_tag_fallback_datasets_are_looked_up() -> None:
    card = _make_card_data()  # no `datasets:`: the Hub's dataset:* tags
    info = {"author": "acme", "sha": "deadbeef", "tags": ["dataset:o/d"]}
    with _patch_hf_calls(
        card_data=card,
        hub_info=info,
        datasets={"o/d": {"card_data": {"license": "MIT"}}},
    ):
        (ref,) = read_huggingface("acme/model").datasets
    assert ref.metadata.license == "MIT"


def test_a_plain_name_is_not_looked_up_and_a_repeat_once() -> None:
    card = _make_card_data(datasets=["o/d", "My web corpus", "o/d"])
    with (
        _patch_hf_calls(card_data=card),
        patch.object(hub_dataset, "_load_dataset_info", return_value={}) as info,
        patch.object(
            hub_dataset, "_load_dataset_card", return_value=(None, {"license": "MIT"})
        ),
    ):
        found = [r.metadata for r in read_huggingface("acme/model").datasets]
    assert [c.args for c in info.call_args_list] == [("o/d",)]
    assert [m.license for m in found] == ["MIT", None, "MIT"]


def test_the_lookups_are_capped_in_card_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cap = MAX_HUB_DATASET_LOOKUPS
    ids = [f"o/d{i:02}" for i in range(cap + 3)]
    found = _read({i: {"card_data": {"license": "MIT"}} for i in ids}, ids)
    assert [m.license for m in found] == ["MIT"] * cap + [None] * 3
    (message,) = _warnings(caplog)
    assert "acme/model" in message and f"{cap}-dataset" in message
    assert message.endswith(f"the first {cap} looked up, 3 not")


def test_at_the_cap_nothing_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    ids = [f"o/d{i:02}" for i in range(MAX_HUB_DATASET_LOOKUPS)]
    found = _read({i: {"card_data": {"license": "MIT"}} for i in ids}, ids)
    assert all(m.license == "MIT" for m in found)
    assert not _warnings(caplog)


def _missing() -> Any:
    raise RemoteEntryNotFoundError("404", response=MagicMock(status_code=404))


@pytest.mark.parametrize(
    ("failing", "prefix"),
    [("info", "Failed to load dataset_info() for o/d: "),
     ("card", "Failed to load dataset card for o/d: ")],
    ids=["info", "card"],
)  # fmt: skip
def test_a_failed_request_warns_once_and_keeps_the_dataset(
    failing: str, prefix: str, caplog: pytest.LogCaptureFixture
) -> None:
    error = OSError("timed out")

    def info(repo_id: str, **_kw: Any) -> Any:
        if failing == "info" and repo_id == "o/d":
            raise error
        return MagicMock(author="acme", sha=_SHA)

    def download(repo_id: str, **_kw: Any) -> Any:
        if failing == "card" and repo_id == "o/d":
            raise error
        return _missing()

    card = _make_card_data(datasets=["o/d", "o/e"])
    with (
        _patch_hf_calls(card_data=card),
        patch.object(hub_dataset, "_load_dataset_info", _load_dataset_info),
        patch.object(hub_dataset, "_load_dataset_card", _load_dataset_card),
        patch("huggingface_hub.dataset_info", side_effect=info),
        patch("huggingface_hub.hf_hub_download", side_effect=download) as fetched,
    ):
        found = [r.metadata for r in read_huggingface("acme/model").datasets]
    (message,) = _warnings(caplog)
    assert message.startswith(prefix + "timed out | Field(s) affected (skipped): ")
    assert found[0].download_url == "https://huggingface.co/datasets/o/d"
    assert found[0].license is None
    # No card request after a failed info request; the other dataset is read.
    assert [c.kwargs["repo_id"] for c in fetched.call_args_list] == (
        ["o/e"] if failing == "info" else ["o/d", "o/e"]
    )
    assert found[1].creator == "acme"


def test_a_repository_without_a_card_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with patch("huggingface_hub.hf_hub_download", side_effect=lambda **_k: _missing()):
        assert _load_dataset_card("o/d", _SHA) == (None, {})
    assert not caplog.records


def test_the_card_is_read_through_the_capped_reader(tmp_path: Path) -> None:
    card = tmp_path / "README.md"
    card.write_bytes(b"---\nlicense: mit\n---\n" + b"x" * (2 * 1024 * 1024))
    download = MagicMock(return_value=str(card))
    with patch("huggingface_hub.hf_hub_download", download):
        text, data = _load_dataset_card("o/d", _SHA)
    assert data == {"license": "mit"}
    assert text is not None and len(text) == 1024 * 1024
    assert download.call_args.kwargs == {
        "repo_id": "o/d",
        "filename": "README.md",
        "repo_type": "dataset",
        "revision": _SHA,
    }


def test_a_hub_error_is_logged_on_one_escaped_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    hostile = OSError("404 for o/d\n::error::forged\u202e")
    with patch("huggingface_hub.dataset_info", side_effect=hostile):
        assert _load_dataset_info("o/d") is None
    (message,) = _warnings(caplog)
    assert "\n" not in message and "\u202e" not in message


def test_a_licence_of_the_wrong_shape_warns_naming_the_dataset(
    caplog: pytest.LogCaptureFixture,
) -> None:
    (meta,) = _read({"o/d": {"card_data": {"license": {"id": "MIT"}}}})
    assert meta.license is None
    assert _warnings(caplog) == [
        "dataset metadata: Hugging Face dataset o/d field license is of type dict, "
        "not text; skipped"
    ]


@pytest.mark.parametrize(
    ("name", "looked_up"),
    [
        ("c4", True),
        ("allenai/c4", True),
        ("o/d.v2_x-y", True),
        ("My web corpus", False),
        ("a/b/c", False),
        ("o/-d", False),
        ("o/d--e", False),
        ("o/d..e", False),
        ("o/" + "d" * 96, True),
        ("o/" + "d" * 97, False),
        ("", False),
        ("o/d_", True),
        ("o/d-", False),
        ("o/d.", False),
        ("d.", False),
        ("o./d", False),
        ("o/d.git", False),
    ],
    ids=[
        "legacy", "owner", "punctuation", "prose", "three-parts", "leading-dash",
        "double-dash", "double-dot", "longest", "too-long", "empty",
        "trailing-underscore", "trailing-dash", "trailing-dot", "legacy-trailing-dot",
        "owner-trailing-dot", "git-suffix",
    ],
)  # fmt: skip
def test_only_a_repository_id_is_looked_up(name: str, looked_up: bool) -> None:
    assert _is_dataset_id(name) is looked_up


@pytest.mark.parametrize(
    ("frontmatter", "licence"),
    [
        ("last_updated: 2024-02-30\n", None),
        ("version: " + "1" * 5000 + "\n", None),
        ("v: 0x" + "f" * 5000 + "\n", "mit"),
        ("v: " + ":".join(["1"] * 3000) + "\n", "mit"),
    ],
    ids=["impossible-date", "huge-int", "huge-hex", "huge-base-60"],
)
def test_a_card_yaml_cannot_load_fails_only_its_dataset(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    frontmatter: str,
    licence: str | None,
) -> None:
    """A third party's card is read through the real loader: one that YAML
    cannot load is one ``WARNING:``, the dataset keeps its name and URL, and
    the model SBOM is built."""
    card = tmp_path / "README.md"
    card.write_text(f"---\nlicense: mit\n{frontmatter}---\n# D\n", "utf-8")
    model_card = _make_card_data(datasets=["o/d"])
    with (
        _patch_hf_calls(card_data=model_card),
        patch.object(hub_dataset, "_load_dataset_card", _load_dataset_card),
        patch("huggingface_hub.hf_hub_download", return_value=str(card)),
    ):
        (ref,) = read_huggingface("acme/model").datasets
    assert (ref.metadata.name, ref.metadata.license) == ("o/d", licence)
    assert ref.metadata.download_url == "https://huggingface.co/datasets/o/d"
    assert len(_warnings(caplog)) == (1 if licence is None else 0)


def test_any_failure_reading_the_card_is_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    card = tmp_path / "README.md"
    card.write_text("---\nlicense: mit\n---\n", "utf-8")
    with (
        patch("huggingface_hub.hf_hub_download", return_value=str(card)),
        patch.object(hub_dataset, "read_card", side_effect=RuntimeError("boom")),
    ):
        assert _load_dataset_card("o/d", _SHA) == (None, {})
    (message,) = _warnings(caplog)
    assert message.startswith("Failed to load dataset card for o/d: boom")


def test_an_id_in_another_case_is_looked_up_once() -> None:
    """Hub ids are case-insensitive: the first spelling is looked up; a
    repeat gets the fields found, with their provenance, and keeps its own
    name and the rest of its provenance."""
    card = _make_card_data(datasets=["O/D", "o/d"])
    found = {"license": "MIT"}
    with (
        _patch_hf_calls(card_data=card),
        patch.object(hub_dataset, "_load_dataset_info", return_value={}) as info,
        patch.object(hub_dataset, "_load_dataset_card", return_value=(None, found)),
    ):
        first, second = [r.metadata for r in read_huggingface("acme/model").datasets]
    assert [c.args for c in info.call_args_list] == [("O/D",)]
    assert (second.name, second.license) == ("o/d", "MIT")
    assert second.provenance["license"] == first.provenance["license"]
    assert set(second.provenance) == {"name", "license"}
    assert second.version is None and second.description is None


def test_a_repeat_keeps_its_own_provenance_of_what_was_not_looked_up() -> None:
    found = DatasetMetadata(
        "o/d", license="MIT", provenance={"name": "card", "license": "hub"}
    )
    repeat = DatasetMetadata("O/D", provenance={"name": "readme"})
    hub_dataset._copy_found(found, repeat)  # pylint: disable=protected-access
    assert (repeat.name, repeat.license) == ("O/D", "MIT")
    assert repeat.provenance == {"name": "readme", "license": "hub"}
