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

``gguf-py`` turns a card's Hub id ``owner/name`` into a title-cased
``name`` and the model-path URL ``https://huggingface.co/owner/name`` as
``repo_url``. A ``repo_url`` on ``huggingface.co`` naming a Hub dataset
therefore names the dataset by that id, and its download location is the
dataset's page, as the Hub route names and places a card's dataset; the
stated ``name`` stays in ``properties``.

``quantize.imatrix.dataset`` (written by ``llama-quantize``) names the
calibration text of an importance matrix, not training data: it is never a
dataset here, and stays in ``properties``.

See also: :mod:`pitloom.extract.ai_model.gguf` (the reader) and
:mod:`pitloom.core.dataset_names` (one name per dataset, the count cap).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any
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


def hub_dataset_id(url: str) -> tuple[str, bool] | None:
    """The Hub dataset id a ``huggingface.co`` *url* names, and whether
    *url* is the dataset's page (``/datasets/<id>``) rather than the
    model-path spelling ``/<owner>/<name>`` that ``gguf-py`` writes;
    ``None`` for any other URL."""
    parts = urlsplit(url)
    if (
        parts.hostname != _HUB_HOST
        or parts.port is not None
        or parts.username is not None
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
    return (hub_id, page) if is_hub_dataset_id(hub_id) else None


def _named_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> DatasetMetadata | None:
    """Entry *index* named and placed: by the Hub id of its ``repo_url``,
    else by its ``name`` (then ``repo_url``, its download location);
    ``None`` (silently) when it states neither."""
    url_key = _entry_key(index, "repo_url")
    repo_url = stated_url(fields.get(url_key), file_name, url_key)
    url_field = provenance_segment(source, "Field", url_key)
    hub = hub_dataset_id(repo_url) if repo_url else None
    if hub is not None:
        hub_id, page = hub
        derived = provenance_segment(url_field, "Method", HUB_DATASET_ID_METHOD)
        return DatasetMetadata(
            name=hub_id,
            download_url=repo_url if page else _HUB_DATASETS + hub_id,
            provenance={
                "name": derived,
                "download_url": url_field if page else derived,
            },
        )
    name_key = _entry_key(index, "name")
    name = stated_text(fields.get(name_key))
    if name is not None:
        meta = DatasetMetadata(
            name=name,
            provenance={"name": provenance_segment(source, "Field", name_key)},
        )
    elif repo_url is not None:
        meta = DatasetMetadata(name=repo_url, provenance={"name": url_field})
    else:
        return None
    if repo_url:
        meta.download_url = repo_url
        meta.provenance["download_url"] = url_field
    return meta


def _numbered_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> DatasetMetadata | None:
    """The dataset of entry *index*, its name and location as
    :func:`_named_entry` gives them and its other stated fields; ``None``
    (silently) when it names none."""
    meta = _named_entry(fields, index, source, file_name)
    if meta is None:
        return None
    for attr, keys in _ENTRY_FIELDS:
        for key in keys:
            value = fields.get(_entry_key(index, key))
            text = stated_text(value, scalar=attr == "version")
            if text:
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
    a link is also its download location."""
    entry = provenance_segment(source, "Field", DATASETS_KEY)
    meta = DatasetMetadata(name=text, provenance={"name": entry})
    if text.startswith(("https://", "http://")):
        url = stated_url(text, file_name, DATASETS_KEY)
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
        for listed_text in _listed_names(listed):
            text = listed_text.strip()
            if text and text not in found:
                found[text] = _listed_entry(text, source, file_name)
                origin[text] = DATASETS_KEY
            yield text

    kept = distinct_dataset_names(names(), model_cap(GGUF_DATASETS_CAP, "gguf"), where)
    if not kept:
        return [], None
    datasets = [DatasetReference(role="trainedOn", metadata=found[n]) for n in kept]
    used = dict.fromkeys(origin[n] for n in kept)
    return datasets, provenance_segment(source, "Field", ", ".join(used))
