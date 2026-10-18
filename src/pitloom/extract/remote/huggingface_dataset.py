# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hub dataset repository of each dataset a Hugging Face model card
lists: what its own card and ``dataset_info()`` state, onto the dataset's
:class:`~pitloom.core.dataset_metadata.DatasetMetadata`.

Read, each 1:1 and only when stated:

* licence: the card's ``license`` (with ``license_name`` and
  ``license_link`` for ``other``), through
  :func:`~pitloom.extract.dataset.licence.dataset_licence`;
* description: the card's first prose paragraph, as for a model;
* keywords: the card's ``tags``;
* version: the revision's commit hash (``dataset_info()`` ``sha``), as for
  a model;
* creator: the repository owner (``dataset_info()`` ``author``), recorded
  as a model's owner is.

Called by :func:`~pitloom.extract.remote.huggingface.read_huggingface`
only, so a dataset is looked up exactly when its model is. A failed request
is one ``WARNING:`` and the dataset keeps its name and download URL; a field
the dataset does not state is left unset, silently.

See also: :mod:`pitloom.extract.remote.huggingface_fetch` (the model's own
Hub requests) and :mod:`pitloom.extract.dataset.card` (a local dataset card).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import model_cap
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.model_originators import REPOSITORY_OWNER_METHOD, originator_names
from pitloom.core.purl import commit_hash
from pitloom.enrich.readme import MODEL_CARD_MAX_BYTES, CardKind, read_card
from pitloom.extract.dataset.card import card_tags
from pitloom.extract.dataset.licence import (
    LICENSE_FIELD,
    LICENSE_LINK_FIELD,
    LICENSE_NAME_FIELD,
    dataset_licence,
)
from pitloom.extract.remote.huggingface_fetch import _extract_card_description
from pitloom.logging_config import (
    Cap,
    field_loss_suffix,
    loggable,
    one_line,
    warn_over_cap,
)

log = logging.getLogger(__name__)

__all__ = ["MAX_HUB_DATASET_LOOKUPS", "add_hub_dataset_metadata"]

#: The most datasets of one model looked up on the Hub: one model card can
#: list any number, and each costs two requests.
MAX_HUB_DATASET_LOOKUPS = 20
_LOOKUP_CAP = Cap(MAX_HUB_DATASET_LOOKUPS, "dataset", "Hub-dataset-lookup")

_SOURCE = "Hugging Face Hub"
_CARD_FIELD = "dataset card "
_FIELDS_SKIPPED = ("license", "description", "keywords")

#: A Hub dataset card: the dataset repository's ``README.md``.
HUB_DATASET_CARD = CardKind(
    ("README.md",),
    "Hugging Face dataset card",
    Cap(MODEL_CARD_MAX_BYTES, "byte", "dataset-card"),
    field_loss_suffix("skipped", *_FIELDS_SKIPPED),
)


def _load_dataset_info(dataset_id: str) -> dict[str, Any] | None:
    """The ``author`` and ``sha`` that ``dataset_info()`` states (``None``
    when not given); ``None``, with one ``WARNING:``, when the request
    fails."""
    try:
        # pylint: disable=import-outside-toplevel
        from huggingface_hub import dataset_info

        info = dataset_info(dataset_id)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = "Failed to load dataset_info() for %s: %s" + field_loss_suffix(
            "skipped", *_FIELDS_SKIPPED, "version", "creator"
        )
        log.warning(msg, loggable(dataset_id), one_line(exc))
        return None
    # As the Hub sent them: the readers of each check its type.
    return {"author": info.author, "sha": info.sha}


def _load_dataset_card(
    dataset_id: str, revision: str | None
) -> tuple[str | None, dict[str, Any]]:
    """The card text, within :data:`MODEL_CARD_MAX_BYTES`, and frontmatter of
    *dataset_id* at *revision*; ``(None, {})`` when the repository has no
    card (silently) or it cannot be fetched or read (one ``WARNING:``)."""
    # pylint: disable=import-outside-toplevel
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import RemoteEntryNotFoundError

    try:
        local_path = hf_hub_download(
            repo_id=dataset_id,
            filename="README.md",
            repo_type="dataset",
            revision=revision,
        )
    except RemoteEntryNotFoundError:
        return None, {}
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = "Failed to load dataset card for %s: %s" + HUB_DATASET_CARD.fields_skipped
        log.warning(msg, loggable(dataset_id), one_line(exc))
        return None, {}
    read = read_card(Path(local_path), HUB_DATASET_CARD)
    if read is None:
        return None, {}
    return read[0], read[1] or {}


#: A Hub repository id: an optional owner and a name, each 1-96 of
#: ``[A-Za-z0-9_.-]`` starting with a letter or digit (a legacy dataset such
#: as ``c4`` has no owner).
_PART = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}"
_DATASET_ID_RE = re.compile(rf"(?:{_PART}/)?{_PART}")


def _is_dataset_id(name: str) -> bool:
    """Whether *name* is a Hub repository id; a model card's ``datasets:``
    also holds plain names, which are not looked up."""
    return (
        _DATASET_ID_RE.fullmatch(name) is not None
        and "--" not in name
        and ".." not in name
    )


def _apply_card(
    meta: DatasetMetadata, text: str | None, card: dict[str, Any], where: str
) -> None:
    """Set on *meta* the licence, description and keywords *card* (the
    frontmatter) and *text* (the whole card) state."""
    licence = dataset_licence(
        card.get(LICENSE_FIELD),
        source=_SOURCE,
        name=card.get(LICENSE_NAME_FIELD),
        link=card.get(LICENSE_LINK_FIELD),
        field_prefix=_CARD_FIELD,
        where=where,
    )
    if licence is not None:
        meta.license = licence.text
        meta.provenance["license"] = licence.provenance
    description = _extract_card_description(text) if text else None
    if description:
        meta.description = description
        meta.provenance["description"] = f"Source: {_SOURCE} | Field: dataset card"
    keywords = card_tags(card.get("tags"))
    if keywords:
        meta.keywords = keywords
        meta.provenance["keywords"] = f"Source: {_SOURCE} | Field: {_CARD_FIELD}tags"


def _apply_info(meta: DatasetMetadata, info: dict[str, Any]) -> None:
    """Set on *meta* the version and creator *info* states."""
    version = commit_hash(info.get("sha"))
    if version:
        meta.version = version
        meta.provenance["version"] = f"Source: {_SOURCE} | Field: dataset_info sha"
    owners = originator_names(info.get("author"))
    if owners:
        meta.creator = owners[0]
        meta.provenance["creator"] = (
            f"Source: {_SOURCE} | Field: dataset_info author" + REPOSITORY_OWNER_METHOD
        )


def _look_up(meta: DatasetMetadata) -> None:
    """Fill *meta* from the Hub dataset repository its name is the id of."""
    dataset_id = meta.name
    info = _load_dataset_info(dataset_id)
    if info is None:
        return
    _apply_info(meta, info)
    sha = info.get("sha")
    revision = sha if isinstance(sha, str) and sha else None
    text, card = _load_dataset_card(dataset_id, revision)
    _apply_card(meta, text, card, f"Hugging Face dataset {dataset_id}")


def add_hub_dataset_metadata(datasets: list[DatasetReference], where: str) -> None:
    """Fill each of *datasets* (named by its Hub dataset id, as a model card
    gives it) from its Hub repository, in card order. A name that is not a
    repository id is not looked up; past :data:`MAX_HUB_DATASET_LOOKUPS`
    ids, the rest are not either, with one ``WARNING:`` naming *where* (the
    model). A dataset listed twice is looked up once."""
    ids = list(dict.fromkeys(r.metadata.name for r in datasets))
    ids = [i for i in ids if _is_dataset_id(i)]
    if len(ids) > MAX_HUB_DATASET_LOOKUPS:
        skipped = len(ids) - MAX_HUB_DATASET_LOOKUPS
        outcome = f"the first {MAX_HUB_DATASET_LOOKUPS} looked up, {skipped} not"
        warn_over_cap(log, model_cap(_LOOKUP_CAP, "huggingface"), where, outcome)
    allowed = set(ids[:MAX_HUB_DATASET_LOOKUPS])
    looked_up: dict[str, DatasetMetadata] = {}
    for ref in datasets:
        name = ref.metadata.name
        if name in looked_up:
            _copy_found(looked_up[name], ref.metadata)
        elif name in allowed:
            _look_up(ref.metadata)
            looked_up[name] = ref.metadata


def _copy_found(found: DatasetMetadata, meta: DatasetMetadata) -> None:
    """Give *meta* what was found for the same dataset as *found*."""
    meta.version, meta.creator = found.version, found.creator
    meta.license, meta.description = found.license, found.description
    meta.keywords = list(found.keywords)
    meta.provenance = dict(found.provenance)
