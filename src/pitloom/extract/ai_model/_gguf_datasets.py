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

``quantize.imatrix.dataset`` (written by ``llama-quantize``) names the
calibration text of an importance matrix, not training data: it is never a
dataset here, and stays in ``properties``.

See also: :mod:`pitloom.extract.ai_model.gguf` (the reader) and
:mod:`pitloom.core.dataset_names` (one name per dataset, the count cap).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from pitloom.core.ai_metadata import model_cap
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.dataset_names import MAX_CARD_DATASETS, distinct_dataset_names
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


def _numbered_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> DatasetMetadata | None:
    """The dataset of entry *index*: named by its ``name``, else its
    ``repo_url``; ``None`` (silently) when it states neither."""
    repo_url = stated_url(
        fields.get(_entry_key(index, "repo_url")),
        file_name,
        _entry_key(index, "repo_url"),
    )
    name_key = _entry_key(index, "name")
    name = stated_text(fields.get(name_key))
    if name is None:
        name, name_key = repo_url, _entry_key(index, "repo_url")
    if name is None:
        return None
    meta = DatasetMetadata(
        name=name, provenance={"name": provenance_segment(source, "Field", name_key)}
    )
    if repo_url:
        meta.download_url = repo_url
        meta.provenance["download_url"] = provenance_segment(
            source, "Field", _entry_key(index, "repo_url")
        )
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
    used: list[str] = []

    def names() -> Iterator[str]:
        for index in range(_entry_count(fields)):
            meta = _numbered_entry(fields, index, source, file_name)
            if meta is not None:
                if not used:
                    used.append(_ENTRY_PREFIX + "<id>.*")
                found.setdefault(meta.name, meta)
                yield meta.name
        for listed_text in _listed_names(listed):
            text = listed_text.strip()
            if text and text not in found:
                if DATASETS_KEY not in used:
                    used.append(DATASETS_KEY)
                found[text] = _listed_entry(text, source, file_name)
            yield text

    kept = distinct_dataset_names(names(), model_cap(GGUF_DATASETS_CAP, "gguf"), where)
    if not kept:
        return [], None
    datasets = [DatasetReference(role="trainedOn", metadata=found[n]) for n in kept]
    return datasets, provenance_segment(source, "Field", ", ".join(used))
