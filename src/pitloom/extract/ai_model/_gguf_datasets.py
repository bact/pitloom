# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The training datasets a GGUF file names, in its two spellings.

The ggml spec (``docs/gguf.md``) defines ``general.datasets``, a string
array of "datasets that the model was trained upon". llama.cpp's ``gguf-py``
writes ``general.dataset.count`` and ``general.dataset.{id}.{name, author,
version, organization, description, url, doi, uuid, repo_url}`` instead,
from the model card's ``datasets``. Both are read, the numbered entries
first; each becomes a ``trainedOn`` dataset, as a Hub model card's
``datasets`` does.

``gguf-py`` turns a card's Hub id ``owner/name`` into ``name`` =
``id_to_title(name)``, ``organization`` = ``id_to_title(owner)``, a
``version`` guessed from the name, and the model-path URL
``https://huggingface.co/owner/name`` as ``repo_url``. An entry whose
``name`` is that title of its ``repo_url``'s name part was written so: it
is named by the Hub id, located at the dataset's page, as the Hub route
names and places a card's dataset, and the made-up organisation and version
are not read. A ``repo_url`` (or ``general.datasets`` link) that is a Hub
dataset page, ``https://huggingface.co/datasets/<id>``, names the dataset
by that id too. Any other link stays as written; the stated values stay in
``properties``.

``quantize.imatrix.dataset`` (written by ``llama-quantize``) names the
calibration text of an importance matrix, not training data: it is never a
dataset here, and stays in ``properties``.

See also: :mod:`pitloom.extract.ai_model.gguf` (the reader) and
:mod:`pitloom.core.dataset_names` (one name per dataset, the count cap).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from pitloom.core.ai_metadata import model_cap
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.dataset_names import (
    MAX_CARD_DATASETS,
    distinct_dataset_names,
    is_hub_dataset_id,
)
from pitloom.core.provenance import provenance_segment
from pitloom.extract.ai_model._stated_text import stated_text
from pitloom.extract.dataset.values import stated_url
from pitloom.messages.files import Cap

#: The spec's string array of dataset names or links.
DATASETS_KEY = "general.datasets"
#: llama.cpp's count of numbered dataset entries.
DATASET_COUNT_KEY = "general.dataset.count"
#: The prefix of a numbered entry's keys: ``general.dataset.<id>.<field>``.
_ENTRY_PREFIX = "general.dataset."
#: How the provenance names the numbered entries as one field.
_NUMBERED_FIELD = _ENTRY_PREFIX + "<id>.*"
#: The provenance method of a name or location derived from a Hub URL.
HUB_DATASET_ID_METHOD = "hub_dataset_id"
_HUB_HOST = "huggingface.co"
_HUB_DATASETS = "https://huggingface.co/datasets/"

#: The most datasets read from one GGUF file, as for a model card.
GGUF_DATASETS_CAP = Cap(MAX_CARD_DATASETS, "dataset", "GGUF-datasets")

#: :class:`~pitloom.core.dataset_metadata.DatasetMetadata` field -> the
#: entry keys stating it, in the order tried. ``url`` is a home page or
#: paper, not where the data is: only ``repo_url`` is a download location.
_ENTRY_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("version", ("version",)),
    ("description", ("description",)),
    ("creator", ("author", "organization")),
)


def _entry_key(index: int, field: str) -> str:
    """The key of *field* of the numbered dataset entry *index*."""
    return f"{_ENTRY_PREFIX}{index}.{field}"


_VERSION_WORD = re.compile(r"^(v\d+(?:\.\d+)*|\d.*)$")


def gguf_py_title(text: str) -> str:
    """``gguf-py``'s ``Metadata.id_to_title`` (``gguf/metadata.py``): each
    ``-``/space-separated word title-cased, unless it has a capital or is a
    version or number."""
    return " ".join(
        word.title() if word.islower() and not _VERSION_WORD.match(word) else word
        for word in text.strip().replace("-", " ").split()
    )


class HubLink(NamedTuple):
    """What a ``huggingface.co`` link names."""

    #: The Hub repository id: ``owner/name``, or a legacy ``name``.
    hub_id: str
    #: The link is the dataset's page, ``/datasets/<id>``; else it is the
    #: model-path spelling ``/<owner>/<name>``.
    page: bool


def hub_link(url: str) -> HubLink | None:
    """The Hub id an ``http(s)://huggingface.co`` *url* (as
    :func:`~pitloom.extract.dataset.values.stated_url` accepts it) names in
    its path, as a dataset page or as ``/<owner>/<name>``; ``None`` for any
    other URL (another host or port, credentials, a query, a fragment, a
    deeper path)."""
    parts = urlsplit(url)
    if (
        parts.scheme.lower() not in ("http", "https")
        or parts.netloc.lower() != _HUB_HOST
        or parts.query
        or parts.fragment
    ):
        return None
    segments = parts.path.strip("/").split("/")
    page = segments[0] == "datasets"
    owner_name = segments[1:] if page else segments
    hub_id = "/".join(owner_name)
    if len(owner_name) > 2 or (not page and len(owner_name) < 2):
        return None
    return HubLink(hub_id, page) if is_hub_dataset_id(hub_id) else None


def _written_by_gguf_py(link: HubLink, name: str | None) -> bool:
    """Whether a model-path *link* and the stated *name* are what
    ``gguf-py`` writes for a card's dataset id: *name* is the title of the
    id's name part, so the link is a dataset id, not a model's page."""
    return not link.page and name == gguf_py_title(link.hub_id.split("/")[1])


def _hub_entry(link: HubLink, repo_url: str, url_field: str) -> DatasetMetadata:
    """The dataset a Hub *link* (``repo_url``, cited as *url_field*) names:
    the Hub id, located at the dataset's page."""
    derived = provenance_segment(url_field, "Method", HUB_DATASET_ID_METHOD)
    return DatasetMetadata(
        name=link.hub_id,
        download_url=repo_url if link.page else _HUB_DATASETS + link.hub_id,
        provenance={
            "name": derived,
            "download_url": url_field if link.page else derived,
        },
    )


def _named_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> tuple[DatasetMetadata | None, HubLink | None]:
    """Entry *index* named and placed, and the ``gguf-py`` link it was
    named by (``None`` otherwise): by the Hub id of a dataset-page
    ``repo_url`` or of one ``gguf-py`` wrote, else by its ``name`` (then
    ``repo_url``, its download location); no dataset (silently) when it
    states neither."""
    url_key = _entry_key(index, "repo_url")
    repo_url = stated_url(fields.get(url_key), file_name, url_key)
    url_field = provenance_segment(source, "Field", url_key)
    name_key = _entry_key(index, "name")
    name = stated_text(fields.get(name_key))
    link = hub_link(repo_url) if repo_url else None
    if repo_url and link is not None:
        if link.page:
            return _hub_entry(link, repo_url, url_field), None
        if _written_by_gguf_py(link, name):
            return _hub_entry(link, repo_url, url_field), link
    if name is not None:
        meta = DatasetMetadata(
            name=name,
            provenance={"name": provenance_segment(source, "Field", name_key)},
        )
    elif repo_url is not None:
        meta = DatasetMetadata(name=repo_url, provenance={"name": url_field})
    else:
        return None, None
    if repo_url:
        meta.download_url = repo_url
        meta.provenance["download_url"] = url_field
    return meta, None


def _made_up(key: str, text: str, link: HubLink | None) -> bool:
    """Whether entry field *key*'s *text* is what ``gguf-py`` derived from
    the Hub id of *link*: the owner's title as ``organization``, or a word
    of the name part as ``version``. *link* is a model-path one, always
    ``owner/name``."""
    if link is None:
        return False
    owner, name = link.hub_id.split("/")
    if key == "organization":
        return text == gguf_py_title(owner)
    return key == "version" and text in name.split("-")


def _numbered_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> DatasetMetadata | None:
    """The dataset of entry *index*, its name and location as
    :func:`_named_entry` gives them and its other stated fields; ``None``
    (silently) when it names none."""
    meta, link = _named_entry(fields, index, source, file_name)
    if meta is None:
        return None
    for attr, keys in _ENTRY_FIELDS:
        for key in keys:
            value = fields.get(_entry_key(index, key))
            text = stated_text(value, scalar=attr == "version")
            if text and not _made_up(key, text, link):
                setattr(meta, attr, text)
                meta.provenance[attr] = provenance_segment(
                    source, "Field", _entry_key(index, key)
                )
                break
    return meta


def _entry_count(fields: Mapping[str, Any]) -> int:
    """``general.dataset.count`` when it is a whole number, else 0; never
    more than the file has keys, so a hostile count costs nothing."""
    count = fields.get(DATASET_COUNT_KEY)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return 0
    return min(count, len(fields))


def _listed_names(listed: Any) -> Iterator[str]:
    """Each element of the ``general.datasets`` field *listed* (a
    ``gguf.ReaderField``), decoded as the reader decodes a string; nothing
    when it is no array of strings."""
    if listed is None:
        return
    types = [str(getattr(t, "name", "")) for t in listed.types]
    if types != ["ARRAY", "STRING"]:
        return
    for index in listed.data:
        yield listed.parts[index].tobytes().decode("utf-8", errors="surrogateescape")


def _listed_entry(text: str, source: str, file_name: str) -> DatasetMetadata:
    """The dataset a ``general.datasets`` element *text* (stripped) names;
    a link is also its download location, and a Hub dataset page names the
    dataset by its Hub id."""
    entry = provenance_segment(source, "Field", DATASETS_KEY)
    url = None
    if text.startswith(("https://", "http://")):
        url = stated_url(text, file_name, DATASETS_KEY)
    link = hub_link(url) if url else None
    if url and link is not None and link.page:
        return _hub_entry(link, url, entry)
    meta = DatasetMetadata(name=text, provenance={"name": entry})
    if url:
        meta.download_url = url
        meta.provenance["download_url"] = entry
    return meta


def read_gguf_datasets(
    fields: Mapping[str, Any],
    listed: Any,
    source: str,
    where: str,
    file_name: str,
) -> tuple[list[DatasetReference], str | None]:
    """The ``trainedOn`` datasets of a GGUF file, and the provenance of the
    model's ``datasets`` field (``None`` with none).

    The numbered entries come first, then the ``general.datasets``
    elements; each dataset once by its first spelling
    (:func:`~pitloom.core.dataset_names.distinct_dataset_names`), at most
    :data:`GGUF_DATASETS_CAP` of them, with one ``WARNING:`` naming *where*
    when more are listed. Elements are decoded only as far as the cap needs.

    Args:
        fields: The file's fields as
            :func:`~pitloom.extract.ai_model.gguf.read_gguf` reads them.
        listed: The ``general.datasets`` ``gguf.ReaderField``, or ``None``;
            read here, so before the reader releases the file.
        source: The ``Source: <file name>`` part of the provenance.
        where: The model's path, for the over-cap warning.
        file_name: The model's file name, naming it in a URL warning.
    """
    found: dict[str, DatasetMetadata] = {}
    # The field each spelling came from, so the provenance names only the
    # fields of the datasets kept.
    origin: dict[str, str] = {}

    def names() -> Iterator[str]:
        for index in range(_entry_count(fields)):
            meta = _numbered_entry(fields, index, source, file_name)
            if meta is not None:
                if meta.name not in found:
                    found[meta.name] = meta
                    origin[meta.name] = _NUMBERED_FIELD
                yield meta.name
        named: dict[str, str] = {}  # element text -> the name it gives
        for listed_text in _listed_names(listed):
            text = listed_text.strip()
            if text and text not in named:
                meta = _listed_entry(text, source, file_name)
                named[text] = meta.name
                if meta.name not in found:
                    found[meta.name] = meta
                    origin[meta.name] = DATASETS_KEY
            yield named.get(text, text)

    kept = distinct_dataset_names(names(), model_cap(GGUF_DATASETS_CAP, "gguf"), where)
    if not kept:
        return [], None
    datasets = [DatasetReference(role="trainedOn", metadata=found[n]) for n in kept]
    used = dict.fromkeys(origin[n] for n in kept)
    return datasets, provenance_segment(source, "Field", ", ".join(used))
