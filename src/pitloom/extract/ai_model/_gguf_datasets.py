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
``https://huggingface.co/owner/name`` as ``repo_url``; a card's link
``https://huggingface.co/<a>/<b>`` it splits the same way. An entry whose
``repo_url`` matches gguf-py's pattern and whose ``name`` is that title of
the name part was written so: the made-up organisation and version are not
read, and it is named by the Hub id, located at the dataset's page, as the
Hub route names and places a card's dataset (unless the first part is a
site area such as ``papers``). A ``repo_url`` (or ``general.datasets``
link) that is a Hub dataset page, ``https://huggingface.co/datasets/<id>``,
names the dataset by that id too. Any other link stays as written; the
stated values stay in ``properties``. A card's id with no owner gets no
``repo_url``: its titled name and guessed version cannot be told from
stated ones, and are read.

``quantize.imatrix.dataset`` (written by ``llama-quantize``) names the
calibration text of an importance matrix, not training data: it is never a
dataset here, and stays in ``properties``.

See also: :mod:`pitloom.extract.ai_model.gguf` (the reader) and
:mod:`pitloom.core.dataset_names` (one name per dataset, the count cap).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from pitloom.core.ai_metadata import model_cap
from pitloom.core.dataset_merge import merge_dataset_into
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.dataset_names import (
    MAX_CARD_DATASETS,
    DatasetIdentity,
    dataset_identity,
    dataset_key,
    distinct_datasets,
    is_hub_dataset_id,
)
from pitloom.core.provenance import provenance_segment
from pitloom.extract.ai_model._stated_text import stated_text
from pitloom.extract.dataset.values import stated_url
from pitloom.messages.datasets import DatasetModel
from pitloom.messages.files import Cap

log = logging.getLogger(__name__)

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


#: The ``repo_url`` ``gguf-py`` writes for a card's Hub id ``owner/name``,
#: and the pattern it reads a card's Hub link by (``gguf/metadata.py``).
_GGUF_PY_HUB_URL = re.compile(r"https?://huggingface\.co/([^/]+)/([^/]+)")

#: First path segments of ``huggingface.co`` that are a site area, not a
#: repository owner.
_HUB_AREAS = frozenset({"api", "blog", "collections", "docs", "papers", "spaces"})


class GgufPyId(NamedTuple):
    """The two parts ``gguf-py`` split a card's Hub link or id into."""

    owner: str
    name: str


def hub_dataset_page(url: str) -> str | None:
    """The Hub id an ``http(s)://huggingface.co/datasets/<id>`` *url* (as
    :func:`~pitloom.extract.dataset.values.stated_url` accepts it) names;
    ``None`` for any other URL (another host or port, credentials, a query,
    a fragment, a deeper path)."""
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https")  # urlsplit lower-cases it
        or parts.netloc.lower() != _HUB_HOST
        or parts.query
        or parts.fragment
    ):
        return None
    area, _, hub_id = parts.path.strip("/").partition("/")
    # a Hub id has at most one "/": a deeper path is no Hub id
    return hub_id if area == "datasets" and is_hub_dataset_id(hub_id) else None


def _gguf_py_id(repo_url: str, name: str | None) -> GgufPyId | None:
    """The Hub id ``gguf-py`` split *repo_url* into when it wrote the entry:
    its pattern matches and the stated *name* is its title of the name
    part; ``None`` otherwise."""
    match = _GGUF_PY_HUB_URL.fullmatch(repo_url)
    if match is None or name != gguf_py_title(match[2]):
        return None
    return GgufPyId(match[1], match[2])


def _hub_entry(hub_id: str, page: str | None, url_field: str) -> DatasetMetadata:
    """The dataset Hub id *hub_id* names, from a ``repo_url`` cited as
    *url_field*: located at its dataset *page* when that is the URL stated,
    else at the page derived from the id."""
    derived = provenance_segment(url_field, "Method", HUB_DATASET_ID_METHOD)
    return DatasetMetadata(
        name=hub_id,
        download_url=page or _HUB_DATASETS + hub_id,
        provenance={"name": derived, "download_url": url_field if page else derived},
    )


def _named_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> tuple[DatasetMetadata | None, GgufPyId | None]:
    """Entry *index* named and placed, and the Hub id ``gguf-py`` wrote it
    from (``None`` otherwise): by the Hub id of a dataset-page ``repo_url``
    or of one ``gguf-py`` wrote from an ``owner/name`` id, else by its
    ``name`` (then ``repo_url``, its download location); no dataset
    (silently) when it states neither."""
    url_key = _entry_key(index, "repo_url")
    repo_url = stated_url(fields.get(url_key), file_name, url_key)
    url_field = provenance_segment(source, "Field", url_key)
    name_key = _entry_key(index, "name")
    name = stated_text(fields.get(name_key))
    if repo_url is None:
        written = None
    else:
        written = _gguf_py_id(repo_url, name)
        page_id = hub_dataset_page(repo_url)
        if page_id is not None:
            return _hub_entry(page_id, repo_url, url_field), written
        if written is not None and written.owner not in _HUB_AREAS:
            hub_id = "/".join(written)
            if is_hub_dataset_id(hub_id):
                return _hub_entry(hub_id, None, url_field), written
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
    return meta, written


def _made_up(key: str, text: str, written: GgufPyId | None) -> bool:
    """Whether entry field *key*'s *text* is what ``gguf-py`` derived from
    the Hub id *written*: the owner's title as ``organization``, or words
    of the name part, ``-``-joined in their order, as ``version``."""
    if written is None:
        return False
    if key == "organization":
        return text == gguf_py_title(written.owner)
    words = iter(written.name.split("-"))
    return key == "version" and all(word in words for word in text.split("-"))


def _numbered_entry(
    fields: Mapping[str, Any], index: int, source: str, file_name: str
) -> DatasetMetadata | None:
    """The dataset of entry *index*, its name and location as
    :func:`_named_entry` gives them and its other stated fields; ``None``
    (silently) when it names none."""
    meta, written = _named_entry(fields, index, source, file_name)
    if meta is None:
        return None
    for attr, keys in _ENTRY_FIELDS:
        for key in keys:
            value = fields.get(_entry_key(index, key))
            text = stated_text(value, scalar=attr == "version")
            if text and not _made_up(key, text, written):
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


def _listed_names(listed: Sequence[str] | None) -> Iterator[str]:
    """Each element of the ``general.datasets`` array *listed*, as read
    (decoded with ``surrogateescape``); nothing when there is none."""
    if listed is not None:
        yield from listed


def _listed_entry(text: str, source: str, file_name: str) -> DatasetMetadata:
    """The dataset a ``general.datasets`` element *text* (stripped) names;
    a link is also its download location, and a Hub dataset page names the
    dataset by its Hub id."""
    entry = provenance_segment(source, "Field", DATASETS_KEY)
    url = None
    if text.lower().startswith(("https://", "http://")):
        url = stated_url(text, file_name, DATASETS_KEY)
    hub_id = hub_dataset_page(url) if url else None
    if hub_id is not None:
        return _hub_entry(hub_id, url, entry)
    meta = DatasetMetadata(name=text, provenance={"name": entry})
    if url:
        meta.download_url = url
        meta.provenance["download_url"] = entry
    return meta


def _trained_on(meta: DatasetMetadata, said: set[str] | None) -> DatasetReference:
    """The ``trainedOn`` reference to *meta*, with the fields whose
    conflict the reader *said* (``None``: none), so the assembler does not
    say them again."""
    return DatasetReference(
        role="trainedOn", metadata=meta, said_conflicts=frozenset(said or ())
    )


def read_gguf_datasets(
    fields: Mapping[str, Any],
    listed: Sequence[str] | None,
    source: str,
    where: str,
    file_name: str,
) -> tuple[list[DatasetReference], str | None]:
    """The ``trainedOn`` datasets of a GGUF file, and the provenance of the
    model's ``datasets`` field (``None`` with none).

    The numbered entries come first, then the ``general.datasets``
    elements; each dataset once by its first spelling, the name and version
    its identity (:func:`~pitloom.core.dataset_names.distinct_datasets`): one
    name at two versions is two datasets, which the assembler folds into
    one package with a ``WARNING:``. An element, which states no version,
    is another spelling of the first numbered entry of its name. A later
    entry of a kept identity fills the fields the first leaves unset, with
    a ``WARNING:`` for each that both state differently
    (:func:`~pitloom.core.dataset_merge.merge_dataset_into`, the model
    named by *file_name*, on this reader's logger so that a model scan
    relays it naming the model's stable path), recorded on its reference
    (:attr:`~pitloom.core.dataset_metadata.DatasetReference.said_conflicts`)
    so the assembler does not say it again. At most
    :data:`GGUF_DATASETS_CAP` datasets, with one ``WARNING:`` naming *where*
    when more are listed.

    Args:
        fields: The file's fields as
            :func:`~pitloom.extract.ai_model.gguf.read_gguf` reads them.
        listed: The elements of the ``general.datasets`` array of strings,
            or ``None`` when the file has none.
        source: The ``Source: <file name>`` part of the provenance.
        where: The model's path, for the over-cap warning.
        file_name: The model's file name, naming it in a URL or a conflict
            warning (a model scan names it by its stable path).
    """
    found: dict[DatasetIdentity, DatasetMetadata] = {}
    # The field each dataset came from, so the provenance names only the
    # fields of the datasets kept.
    origin: dict[DatasetIdentity, str] = {}
    warned: dict[DatasetIdentity, set[str]] = {}
    model = DatasetModel(file=file_name)
    # The version of the first numbered entry of each name: an array
    # element, which states none, is another spelling of that entry.
    first_version: dict[str, str | None] = {}

    def keep(meta: DatasetMetadata, version: str | None, field: str) -> None:
        identity = dataset_identity(meta.name, version)
        if identity in found:
            merge_dataset_into(
                found[identity],
                meta,
                warned.setdefault(identity, set()),
                model,
                say_on=log,
            )
        else:
            found[identity] = meta
            origin[identity] = field

    def entries() -> Iterator[tuple[str, str | None]]:
        for index in range(_entry_count(fields)):
            meta = _numbered_entry(fields, index, source, file_name)
            if meta is not None:
                first_version.setdefault(dataset_key(meta.name), meta.version)
                keep(meta, meta.version, _NUMBERED_FIELD)
                yield meta.name, meta.version
        named: dict[str, tuple[str, str | None]] = {}  # element text -> entry
        for listed_text in _listed_names(listed):
            text = listed_text.strip()
            if text and text not in named:
                meta = _listed_entry(text, source, file_name)
                version = first_version.get(dataset_key(meta.name))
                named[text] = (meta.name, version)
                keep(meta, version, DATASETS_KEY)
            yield named.get(text, (text, None))

    cap = model_cap(GGUF_DATASETS_CAP, "gguf")
    kept = [
        dataset_identity(*entry) for entry in distinct_datasets(entries(), cap, where)
    ]
    if not kept:
        return [], None
    datasets = [_trained_on(found[i], warned.get(i)) for i in kept]
    used = dict.fromkeys(origin[i] for i in kept)
    return datasets, provenance_segment(source, "Field", ", ".join(used))
