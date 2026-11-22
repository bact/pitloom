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
    BOOL,
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


def test_an_entry_gguf_py_wrote_is_named_by_its_hub_id(tmp_path: Path) -> None:
    """gguf-py writes a card's ``teknium/OpenHermes-2.5`` as the title
    ``OpenHermes 2.5``, the titled owner, a version guessed from the name
    and the model-path URL: the dataset is the Hub id, at its page, and the
    made-up organisation and version are not read."""
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "OpenHermes 2.5"),
        _text("general.dataset.0.organization", "Teknium"),
        _text("general.dataset.0.version", "2.5"),
        _text("general.dataset.0.author", "Ann"),  # not gguf-py's: read
        _text(
            "general.dataset.0.repo_url",
            "http://huggingface.co/teknium/OpenHermes-2.5",
        ),
    )
    data = meta.datasets[0].metadata
    assert (data.name, data.download_url, data.version, data.creator) == (
        "teknium/OpenHermes-2.5",
        "https://huggingface.co/datasets/teknium/OpenHermes-2.5",
        None,
        "Ann",
    )
    assert data.provenance["name"] == _HUB
    assert data.provenance["download_url"] == _HUB
    assert meta.properties["general.dataset.0.name"] == "OpenHermes 2.5"


@pytest.mark.parametrize(
    ("organization", "version", "creator", "read_version"),
    [
        ("Allenai", "2", None, "2"),  # the titled owner; 2 is not in the id
        ("AI2", "c4", "AI2", None),  # a word of the name part is gguf-py's
    ],
    ids=["titled-owner", "name-word"],
)
def test_only_what_gguf_py_derives_from_the_id_is_left_out(
    tmp_path: Path,
    organization: str,
    version: str,
    creator: str | None,
    read_version: str | None,
) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "C4"),
        _text("general.dataset.0.organization", organization),
        _text("general.dataset.0.version", version),
        _text("general.dataset.0.repo_url", "https://huggingface.co/allenai/c4"),
    )
    data = meta.datasets[0].metadata
    assert (data.creator, data.version) == (creator, read_version)


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://huggingface.co/datasets/teknium/OpenHermes-2.5/",
        "https://HuggingFace.co/datasets/c4",  # a legacy id, any host case
    ],
    ids=["dataset-page", "legacy-id"],
)
def test_a_hub_dataset_page_names_the_dataset_by_its_hub_id(
    tmp_path: Path, repo_url: str
) -> None:
    """A dataset page is a dataset whatever the entry's name; its stated
    fields are the writer's own, so all are read."""
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "Anything"),
        _text("general.dataset.0.organization", "Allenai"),
        _text("general.dataset.0.repo_url", repo_url),
    )
    data = meta.datasets[0].metadata
    name = repo_url.rstrip("/").split("/datasets/")[1]
    assert (data.name, data.download_url, data.creator) == (name, repo_url, "Allenai")
    assert data.provenance == {
        "name": _HUB,
        "download_url": f"{_SOURCE} | Field: general.dataset.0.repo_url",
        "creator": f"{_SOURCE} | Field: general.dataset.0.organization",
    }


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://huggingface.co/papers/2301.00001",  # the name is not its title
        "https://huggingface.co/allenai/d",  # a model page, not gguf-py's
        "https://huggingface.co:abc/allenai/c4",  # a port, even unparsable
        "https://huggingface.co:99999/allenai/c4",
        "https://huggingface.co:443/allenai/c4",
        "https://huggingface.co./allenai/c4",
        "ftp://huggingface.co/allenai/c4",
        "https://huggingface.co/allenai",  # one segment: a model, if anything
        "https://huggingface.co/allenai/c4/tree/main",
        "https://huggingface.co/datasets/a/b/c",
        "https://huggingface.co/datasets/",
        "https://huggingface.co/allenai/c4?x=1",
        "https://huggingface.co/allenai/c4#x",
        "https://u@huggingface.co/allenai/c4",
        "https://hf.co/allenai/c4",
        "https://huggingface.co/datasets/a--b/c",  # no Hub id
    ],
)
def test_any_other_repo_url_is_kept_as_written(tmp_path: Path, repo_url: str) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "C4"),
        _text("general.dataset.0.organization", "Allenai"),
        _text("general.dataset.0.repo_url", repo_url),
    )
    data = meta.datasets[0].metadata
    assert (data.name, data.download_url, data.creator) == ("C4", repo_url, "Allenai")


@pytest.mark.parametrize(
    "listed",
    ["AllenAI/C4", "https://huggingface.co/datasets/allenai/c4"],
    ids=["hub-id", "dataset-page"],
)
def test_a_hub_repo_url_and_the_spec_array_give_one_dataset(
    tmp_path: Path, listed: str
) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 1),
        _text("general.dataset.0.name", "C4"),
        _text("general.dataset.0.repo_url", "https://huggingface.co/allenai/c4"),
        _listed(listed),
    )
    assert _names(meta) == ["allenai/c4"]
    assert meta.provenance["datasets"] == _NUMBERED


def test_a_listed_dataset_page_is_named_by_its_hub_id(tmp_path: Path) -> None:
    page, model = "https://huggingface.co/datasets/o/d", "https://huggingface.co/o/d"
    meta = _read(tmp_path, _listed(page, model))
    assert _names(meta) == ["o/d", model]  # a model-path link is kept as written
    hub, other = (ref.metadata for ref in meta.datasets)
    assert (hub.download_url, other.download_url) == (page, model)
    assert hub.provenance == {
        "name": f"{_LISTED} | Method: hub_dataset_id",
        "download_url": _LISTED,
    }


@pytest.mark.parametrize(
    "words",
    ["c4", "OpenHermes-2.5", "ultrachat_200k", "open-orca", "v2-beta", "LLaMA-v1.5-x"],
)
def test_the_title_is_gguf_py_s(words: str) -> None:
    """Drift guard: Pitloom's copy of ``Metadata.id_to_title``."""
    metadata = pytest.importorskip("gguf.metadata")
    title = metadata.Metadata.id_to_title(words)
    assert _gguf_datasets.gguf_py_title(words) == title


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


def test_entry_fields_are_read_as_their_kind(tmp_path: Path) -> None:
    """A version may be a number; a creator must be text, and a blank or
    non-text ``author`` gives way to ``organization``."""
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 2),
        _text("general.dataset.0.name", "a"),
        _number("general.dataset.0.version", 2),
        _number("general.dataset.0.author", 5),
        _text("general.dataset.0.organization", "Org"),
        _text("general.dataset.1.name", "b"),
        _text("general.dataset.1.author", "  "),
        _text("general.dataset.1.organization", "Org"),
    )
    first, second = (ref.metadata for ref in meta.datasets)
    assert (first.version, first.creator, second.creator) == ("2", "Org", "Org")


def test_the_first_numbered_entry_of_a_name_is_kept(tmp_path: Path) -> None:
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 2),
        _text("general.dataset.0.name", "d"),
        _text("general.dataset.0.version", "1"),
        _text("general.dataset.1.name", "d"),
        _text("general.dataset.1.version", "2"),
    )
    assert _names(meta) == ["d"]
    assert meta.datasets[0].metadata.version == "1"


def test_the_last_entry_a_count_names_is_read(tmp_path: Path) -> None:
    """The count is bounded by the file's fields (here 5, with the
    reader's header fields), never below the ids it names."""
    meta = _read(
        tmp_path,
        _number("general.dataset.count", 5),
        _text("general.dataset.4.name", "d"),
    )
    assert _names(meta) == ["d"]


def test_a_huge_count_reads_no_more_ids_than_the_file_has_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = _gguf_datasets._numbered_entry  # pylint: disable=protected-access

    def spy(fields: dict[str, object], index: int, *rest: str) -> object:
        calls.append(index)
        return real(fields, index, *rest)

    monkeypatch.setattr(_gguf_datasets, "_numbered_entry", spy)
    _read(tmp_path, _number("general.dataset.count", 0xFFFFFFFF))
    assert 0 < len(calls) < 10


def test_a_listed_name_keeps_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    raw = b"d\xff"
    pair = array(STRING, 1, struct.pack("<Q", len(raw)) + raw, key=b"general.datasets")
    meta = _read(tmp_path, pair)
    assert _names(meta) == ["d\udcff"]


def test_a_plain_http_link_is_a_download_location(tmp_path: Path) -> None:
    meta = _read(tmp_path, _listed("http://x.org/d"))
    assert meta.datasets[0].metadata.download_url == "http://x.org/d"


def test_the_real_cap_keeps_a_thousand(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        meta = _read(tmp_path, _listed(*(f"d{i}" for i in range(1001))))
    assert len(meta.datasets) == 1000
    assert "1000-dataset GGUF-datasets cap" in logged_warnings(caplog)[0]


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
        (
            kv(b"general.dataset.count", BOOL, b"\x01"),
            _text("general.dataset.0.name", "d"),
        ),
        (_text("general.dataset.0.name", "d"),),  # no count: no entries
        (array(UINT32, 1, struct.pack("<I", 1), key=b"general.datasets"),),
        (array(STRING, 0, key=b"general.datasets"),),
    ],
    ids=[
        "huge-count",
        "text-count",
        "bool-count",
        "no-count",
        "number-array",
        "empty-array",
    ],
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
