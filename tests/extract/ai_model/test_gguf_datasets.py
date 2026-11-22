# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""GGUF training datasets: the spec's ``general.datasets`` array and
llama.cpp's numbered ``general.dataset.<id>.*`` entries.

See also: :mod:`tests.extract.ai_model.test_gguf_producer_count` (the
producer) and :mod:`tests.extract.ai_model.gguf_builders` (the builders).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.extract.ai_model import _gguf_datasets
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.messages.files import Cap
from tests.extract.ai_model.gguf_builders import (
    STRING,
    UINT32,
    array,
    gguf_file,
    kv,
    string,
)
from tests.warning_helpers import logged_warnings

_SOURCE = "Source: m.gguf"
_NUMBERED = f"{_SOURCE} | Field: general.dataset.<id>.*"
_LISTED = f"{_SOURCE} | Field: general.datasets"


def _text(key: str, value: str) -> bytes:
    return kv(key.encode(), STRING, string(value))


def _number(key: str, value: int) -> bytes:
    return kv(key.encode(), UINT32, struct.pack("<I", value))


def _listed(*names: str) -> bytes:
    payload = b"".join(string(name) for name in names)
    return array(STRING, len(names), payload, key=b"general.datasets")


def _read(tmp_path: Path, *pairs: bytes) -> AiModelMetadata:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, len(pairs), b"".join(pairs)))
    return read_gguf(path)


def _names(meta: AiModelMetadata) -> list[str]:
    return [ref.metadata.name for ref in meta.datasets]


def test_numbered_entries_are_trained_on_datasets(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 2),
        _text("general.dataset.0.name", "Ultrachat_200K"),
        _text("general.dataset.0.organization", "Huggingfaceh4"),
        _text("general.dataset.0.author", "Jane Doe"),
        _text("general.dataset.0.version", "1.0"),
        _text("general.dataset.0.description", "Dialogues"),
        _text("general.dataset.0.url", "https://example.org/paper"),
        _text("general.dataset.0.repo_url", "https://example.org/ultrachat"),
        _text("general.dataset.1.organization", "Org"),  # no name, no repo_url
    )
    assert [ref.role for ref in meta.datasets] == ["trainedOn"]
    data = meta.datasets[0].metadata
    assert (data.name, data.creator, data.version, data.description) == (
        "Ultrachat_200K",
        "Jane Doe",  # author before organization
        "1.0",
        "Dialogues",
    )
    # repo_url is where the data is; url (a home page) is not
    assert data.download_url == "https://example.org/ultrachat"
    assert data.provenance == {
        "name": f"{_SOURCE} | Field: general.dataset.0.name",
        "download_url": f"{_SOURCE} | Field: general.dataset.0.repo_url",
        "version": f"{_SOURCE} | Field: general.dataset.0.version",
        "description": f"{_SOURCE} | Field: general.dataset.0.description",
        "creator": f"{_SOURCE} | Field: general.dataset.0.author",
    }
    assert meta.provenance["datasets"] == _NUMBERED
    # the keys stay properties too
    assert meta.properties["general.dataset.0.name"] == "Ultrachat_200K"


_HUB = f"{_SOURCE} | Field: general.dataset.0.repo_url | Method: hub_dataset_id"


@pytest.mark.parametrize(
    ("repo_url", "name", "location"),
    [
        # gguf-py's model-path spelling of the card's id: the dataset page
        (
            "https://huggingface.co/allenai/c4",
            "allenai/c4",
            "https://huggingface.co/datasets/allenai/c4",
        ),
        (
            "https://huggingface.co/datasets/teknium/OpenHermes-2.5/",
            "teknium/OpenHermes-2.5",
            "https://huggingface.co/datasets/teknium/OpenHermes-2.5/",
        ),
        (
            "https://huggingface.co/datasets/c4",
            "c4",
            "https://huggingface.co/datasets/c4",
        ),
    ],
    ids=["model-path", "dataset-page", "legacy-id"],
)
def test_a_hub_repo_url_names_the_dataset_by_its_hub_id(
    tmp_path: Path, repo_url: str, name: str, location: str
) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "C4"),  # gguf-py's title
        _text("general.dataset.0.organization", "Allenai"),
        _text("general.dataset.0.repo_url", repo_url),
    )
    data = meta.datasets[0].metadata
    assert (data.name, data.download_url, data.creator) == (name, location, "Allenai")
    assert data.provenance["name"] == _HUB
    page = repo_url == location
    assert data.provenance["download_url"] == (
        f"{_SOURCE} | Field: general.dataset.0.repo_url" if page else _HUB
    )
    assert meta.properties["general.dataset.0.name"] == "C4"


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://huggingface.co/allenai",  # one segment: a model, if anything
        "https://huggingface.co/a/b/c",
        "https://huggingface.co/datasets/a/b/c",
        "https://huggingface.co/datasets/",
        "https://huggingface.co/a/b?x=1",
        "https://huggingface.co/a/b#x",
        "https://huggingface.co:8443/a/b",
        "https://u@huggingface.co/a/b",
        "https://hf.co/a/b",
        "https://huggingface.co/a--b/c",  # no Hub id
    ],
)
def test_any_other_repo_url_is_kept_as_written(tmp_path: Path, repo_url: str) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "d"),
        _text("general.dataset.0.repo_url", repo_url),
    )
    data = meta.datasets[0].metadata
    assert (data.name, data.download_url) == ("d", repo_url)


def test_a_hub_repo_url_and_the_spec_array_give_one_dataset(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "C4"),
        _text("general.dataset.0.repo_url", "https://huggingface.co/allenai/c4"),
        _listed("AllenAI/C4"),
    )
    assert _names(meta) == ["allenai/c4"]
    assert meta.provenance["datasets"] == _NUMBERED


def test_an_entry_without_a_name_is_named_by_its_repo_url(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "  "),
        _text("general.dataset.0.organization", "Org"),
        _text("general.dataset.0.repo_url", "https://example.org/d"),
    )
    data = meta.datasets[0].metadata
    assert (data.name, data.download_url, data.creator) == (
        "https://example.org/d",
        "https://example.org/d",
        "Org",
    )
    assert data.provenance["name"] == f"{_SOURCE} | Field: general.dataset.0.repo_url"


def test_a_repo_url_that_is_no_url_is_warned_and_left_out(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(
            tmp_path,
            _number("general.dataset.count", 1),
            _text("general.dataset.0.name", "d"),
            _text("general.dataset.0.repo_url", "not a url"),
        )
    assert _names(meta) == ["d"]
    assert meta.datasets[0].metadata.download_url is None
    assert [w for w in logged_warnings(caplog) if "is not a URL" in w]


def test_the_spec_array_names_datasets_and_a_link_is_a_download_location(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(
            tmp_path,
            _listed("OpenAssistant/oasst1", " https://x.org/d ", "", "https://a b"),
        )
    assert _names(meta) == ["OpenAssistant/oasst1", "https://x.org/d", "https://a b"]
    plain, link, broken = (ref.metadata for ref in meta.datasets)
    assert plain.download_url is None  # a name is not guessed into a Hub URL
    assert link.download_url == "https://x.org/d"
    assert plain.provenance == {"name": _LISTED}
    assert link.provenance == {"name": _LISTED, "download_url": _LISTED}
    # a link with a space is a name only, with the not-a-URL warning
    assert broken.download_url is None
    assert [w for w in logged_warnings(caplog) if "is not a URL" in w]
    assert meta.provenance["datasets"] == _LISTED


def test_every_numbered_entry_is_read_in_order(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 2),
        _text("general.dataset.0.name", "a"),
        _text("general.dataset.1.name", "b"),
    )
    assert _names(meta) == ["a", "b"]
    assert meta.provenance["datasets"] == _NUMBERED


@pytest.mark.parametrize(
    ("listed", "provenance"),
    [
        (("a/b",), _NUMBERED),  # the array repeats the entry: one dataset
        (("A/B",), _NUMBERED),  # a Hub id, any case: no listed one kept
        (("A/B", "c"), f"{_NUMBERED}, general.datasets"),
    ],
    ids=["same", "case", "case-and-more"],
)
def test_both_spellings_give_each_dataset_once_numbered_first(
    tmp_path: Path, listed: tuple[str, ...], provenance: str
) -> None:
    meta = _read(
        tmp_path,
        _listed(*listed),
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "a/b"),
        _text("general.dataset.0.version", "2"),
    )
    assert _names(meta) == ["a/b", *listed[1:]]
    assert meta.datasets[0].metadata.version == "2"  # the numbered entry's
    assert meta.provenance["datasets"] == provenance


def test_imatrix_calibration_data_is_never_a_dataset(tmp_path: Path) -> None:
    meta = _read(tmp_path, _text("quantize.imatrix.dataset", "imatrix-training-3"))
    assert not meta.datasets
    assert "datasets" not in meta.provenance
    assert meta.properties["quantize.imatrix.dataset"] == "imatrix-training-3"


@pytest.mark.parametrize(
    "pairs",
    [
        # a count the file has no entries for: bounded by the keys there are
        (_number("general.dataset.count", 0xFFFFFFFF),),
        (_text("general.dataset.count", "1"), _text("general.dataset.0.name", "d")),
        (_text("general.dataset.0.name", "d"),),  # no count: no entries
        (array(UINT32, 1, struct.pack("<I", 1), key=b"general.datasets"),),
        (array(STRING, 0, key=b"general.datasets"),),
    ],
    ids=["huge-count", "text-count", "no-count", "number-array", "empty-array"],
)
def test_no_dataset_from_what_names_none_and_no_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pairs: tuple[bytes, ...]
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(tmp_path, *pairs)
    assert not meta.datasets
    assert "datasets" not in meta.provenance
    assert not logged_warnings(caplog)


def test_over_the_cap_keeps_the_first_and_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _gguf_datasets, "GGUF_DATASETS_CAP", Cap(2, "dataset", "GGUF-datasets")
    )
    with caplog.at_level(logging.WARNING):
        meta = _read(tmp_path, _listed("a", "a", "b", "c", "d"))
    assert _names(meta) == ["a", "b"]
    assert meta.provenance["datasets"] == _LISTED
    warnings = logged_warnings(caplog)
    assert len(warnings) == 1
    assert "FORMAT=gguf" in warnings[0]
    assert "2-dataset GGUF-datasets cap" in warnings[0]


def test_a_listed_name_past_the_cap_is_not_in_the_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _gguf_datasets, "GGUF_DATASETS_CAP", Cap(1, "dataset", "GGUF-datasets")
    )
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "a"),
        _listed("x"),
    )
    assert _names(meta) == ["a"]
    assert meta.provenance["datasets"] == _NUMBERED


def test_the_sbom_links_each_dataset_with_trained_on(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "d"),
        _text("general.dataset.0.repo_url", "https://example.org/d"),
        _listed("e"),
    )
    creation = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
    graph = json.loads(build_model(meta, creation).to_json())["@graph"]
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    trained = [e for e in graph if e.get("relationshipType") == "trainedOn"]
    assert [r["from"] for r in trained] == [model["spdxId"]] * 2
    datasets = [by_id[t] for r in trained for t in r["to"]]
    assert sorted(d["name"] for d in datasets) == ["d", "e"]
    (located,) = [d for d in datasets if "software_downloadLocation" in d]
    assert located["software_downloadLocation"] == "https://example.org/d"
