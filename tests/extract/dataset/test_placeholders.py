# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A placeholder is not a claim: ``unknown``, ``NOASSERTION``, ``N/A`` or
blank text is no dataset licence name or link, version, creator or download
location, in a Croissant file and in a dataset card; a download location
must also be a URL.

See also: tests/extract/dataset/test_licence.py (the licence rules),
tests/extract/dataset/test_values.py (the shared checks).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.dataset import read_croissant, read_dataset_card
from pitloom.extract.dataset.licence import dataset_licence
from pitloom.extract.dataset.values import is_placeholder, stated_url

_LINK = "https://example.org/licence"
_PLACEHOLDERS = ["unknown", "UNKNOWN", " Unknown ", "NOASSERTION", "N/A", "n/a"]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("text", _PLACEHOLDERS)
def test_is_placeholder(text: str) -> None:
    assert is_placeholder(text)


@pytest.mark.parametrize("text", ["MIT", "NONE", "N/A licence", "other", "", "NA"])
def test_is_not_placeholder(text: str) -> None:
    assert not is_placeholder(text)


@pytest.mark.parametrize(
    ("value", "name", "link", "text"),
    [
        ("other", "other", None, None),  # a name of "other" says nothing
        ("other", "Other", _LINK, _LINK),
        ("other", "N/A", None, None),
        ("other", "n/a", "NOASSERTION", None),
        ("other", "unknown", _LINK, _LINK),
        ("other", "Acme", "N/A", "Acme"),
        ("other", "N/A", "unknown", None),
        ("other", " ", "", None),  # blank
        ("other", "Acme", _LINK, f"Acme ({_LINK})"),  # real: kept as stated
        ("N/A", "Acme", _LINK, None),  # a placeholder is no `other`
        ("n/a", None, None, None),
        ("MIT", "N/A", "N/A", "MIT"),  # name and link are for `other` only
    ],
)
def test_the_licence_of_other_needs_a_real_name_or_link(
    value: str, name: str | None, link: str | None, text: str | None
) -> None:
    licence = dataset_licence(value, source="s", name=name, link=link)
    assert (licence.text if licence else None) == text


def test_a_placeholder_in_a_licence_list_is_dropped() -> None:
    licence = dataset_licence(["N/A", "MIT", "unknown", "mit", "other"], source="s")
    assert licence is not None and licence.text == "MIT" and licence.further is None
    assert dataset_licence(["N/A", "unknown"], source="s") is None


def _croissant(tmp_path: Path, **fields: Any) -> Any:
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"name": "ds", **fields}), encoding="utf-8")
    return read_croissant(path)


@pytest.mark.parametrize("placeholder", [*_PLACEHOLDERS, "", "   ", None, [], [None]])
@pytest.mark.parametrize("field", ["version", "creator", "url", "license"])
def test_a_croissant_placeholder_states_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    field: str,
    placeholder: Any,
) -> None:
    """The field stays unset and the provenance gets no entry, silently:
    the source never had a value."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        meta = _croissant(tmp_path, **{field: placeholder})
    attribute = {"url": "download_url", "creator": "creator"}.get(field, field)
    assert getattr(meta, attribute) is None
    assert set(meta.provenance) == {"name"}
    assert not _warnings(caplog)


def test_a_croissant_creator_node_with_a_placeholder_name(tmp_path: Path) -> None:
    for creator in ({"@type": "Person", "name": "N/A"}, [{"name": "unknown"}]):
        assert _croissant(tmp_path, creator=creator).creator is None
    meta = _croissant(tmp_path, creator=[{"name": "n/a"}, {"name": "Ada"}])
    assert meta.creator is None  # the first that states something decides
    assert _croissant(tmp_path, creator={"name": "Ada"}).creator == "Ada"


@pytest.mark.parametrize(
    "url", ["https://example.org/d.csv", "s3://bucket/key", "hf://datasets/o/d"]
)
def test_a_croissant_url_is_kept(tmp_path: Path, url: str) -> None:
    meta = _croissant(tmp_path, url=f" {url} ", version="1.0.0", creator="Ada")
    assert (meta.download_url, meta.version, meta.creator) == (url, "1.0.0", "Ada")
    assert meta.provenance["download_url"].endswith("Field: url")


@pytest.mark.parametrize(
    "url",
    ["see the website", "example.org/data", "https://", "http:/x", "ht tp://x/y",
     "://x", "http://[::1", "https://x/\x00", 5, ["https://a", "https://b"]],
)  # fmt: skip
def test_a_croissant_non_url_is_not_a_download_location(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, url: Any
) -> None:
    """Text that is no URL (or no text) is dropped with one ``WARNING:``:
    the source did state it."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = _croissant(tmp_path, url=url, license="MIT")
    assert meta.download_url is None and "download_url" not in meta.provenance
    assert meta.license == "MIT"  # the other fields stay
    (message,) = _warnings(caplog)
    assert "field url is " in message


def test_stated_url_is_silent_for_nothing_and_placeholders() -> None:
    assert [stated_url(v, "s", "url") for v in (None, "", "N/A", ["unknown"])] == [
        None
    ] * 4


@pytest.mark.parametrize("field", ["version", "license"])
@pytest.mark.parametrize("placeholder", ["unknown", "N/A", "NOASSERTION", ""])
def test_a_card_placeholder_states_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    field: str,
    placeholder: str,
) -> None:
    (tmp_path / "README.md").write_text(
        f"---\n{field}: '{placeholder}'\npretty_name: X\n---\n", encoding="utf-8"
    )
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        meta = read_dataset_card(tmp_path)
    assert meta is not None
    assert getattr(meta, field) is None
    assert set(meta.provenance) == {"name"}
    assert not _warnings(caplog)


def test_a_card_other_with_placeholder_name_and_link(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "---\nlicense: other\nlicense_name: N/A\nlicense_link: unknown\n---\n",
        encoding="utf-8",
    )
    meta = read_dataset_card(tmp_path)
    assert meta is not None and meta.license is None
    (tmp_path / "README.md").write_text(
        "---\nlicense: other\nlicense_name: N/A\nlicense_link: https://x.org/l\n---\n",
        encoding="utf-8",
    )
    meta = read_dataset_card(tmp_path)
    assert meta is not None and meta.license == "https://x.org/l"
    assert meta.provenance["license"].endswith("Field: license, license_link")
