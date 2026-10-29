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
* description: the card's first prose paragraph, as for a model
  (:func:`~pitloom.extract.remote._card_description.card_description`);
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
from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import model_cap
from pitloom.core.dataset_metadata import (
    DatasetMetadata,
    DatasetReference,
)
from pitloom.core.dataset_names import dataset_key, is_hub_dataset_id
from pitloom.core.model_originators import REPOSITORY_OWNER_METHOD, originator_names
from pitloom.core.purl import commit_hash
from pitloom.enrich.readme import MODEL_CARD_MAX_BYTES, CardKind, read_card
from pitloom.extract.dataset.card import card_tags
from pitloom.extract.dataset.licence import (
    LICENSE_FIELD,
    LICENSE_LINK_FIELD,
    LICENSE_NAME_FIELD,
    apply_dataset_licence,
    dataset_licence,
    field_provenance,
)
from pitloom.extract.remote._card_description import card_description
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
        # A third party's card: whatever reading it raises fails only it.
        read = read_card(Path(local_path), HUB_DATASET_CARD, name=dataset_id)
    except RemoteEntryNotFoundError:
        return None, {}
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        msg = "Failed to load dataset card for %s: %s" + HUB_DATASET_CARD.fields_skipped
        # An OSError on a file quotes the local cache path: its reason only.
        reason: object = exc
        if isinstance(exc, OSError):
            if exc.filename:
                reason = exc.strerror or type(exc).__name__
        log.warning(msg, loggable(dataset_id), one_line(reason))
        return None, {}
    if read is None:
        return None, {}
    return read[0], read[1] or {}


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
        lister="Hugging Face dataset card",
    )
    apply_dataset_licence(meta, licence)
    description = card_description(text) if text else None
    if description:
        meta.description = description
        meta.provenance["description"] = field_provenance(_SOURCE, "dataset card")
    keywords = card_tags(card.get("tags"), where)
    if keywords:
        meta.keywords = keywords
        meta.provenance["keywords"] = field_provenance(_SOURCE, f"{_CARD_FIELD}tags")


def _apply_info(meta: DatasetMetadata, info: dict[str, Any]) -> None:
    """Set on *meta* the version and creator *info* states."""
    version = commit_hash(info.get("sha"))
    if version:
        meta.version = version
        meta.provenance["version"] = field_provenance(_SOURCE, "dataset_info sha")
    owners = originator_names(info.get("author"))
    if owners:
        meta.creator = owners[0]
        meta.provenance["creator"] = (
            field_provenance(_SOURCE, "dataset_info author") + REPOSITORY_OWNER_METHOD
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
    model). A repeat of a dataset (:func:`~pitloom.core.dataset_names.dataset_key`)
    is not looked up again: the caller lists each dataset once
    (:func:`~pitloom.core.dataset_names.distinct_dataset_names`)."""
    ids = list(dict.fromkeys(dataset_key(r.metadata.name) for r in datasets))
    ids = [i for i in ids if is_hub_dataset_id(i)]
    if len(ids) > MAX_HUB_DATASET_LOOKUPS:
        skipped = len(ids) - MAX_HUB_DATASET_LOOKUPS
        outcome = f"the first {MAX_HUB_DATASET_LOOKUPS} looked up, {skipped} not"
        warn_over_cap(log, model_cap(_LOOKUP_CAP, "huggingface"), where, outcome)
    allowed = set(ids[:MAX_HUB_DATASET_LOOKUPS])
    for ref in datasets:
        if dataset_key(ref.metadata.name) in allowed:
            _look_up(ref.metadata)
