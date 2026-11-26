# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One dataset referenced more than once: its references become one dataset
with all its roles.

Two references name one dataset when :func:`~pitloom.core.dataset_names.
dataset_key` gives the same key. The first reference's values win; a later
one only fills a field the first leaves unset, with that field's provenance.
A field both set to different values keeps the first, with one warning per
field and model (:class:`~pitloom.messages.datasets.DatasetModel`), a field
a reference's route already said
(:attr:`~pitloom.core.dataset_metadata.DatasetReference.said_conflicts`)
not again. A list or text field is unset when empty:
:class:`~pitloom.core.dataset_metadata.DatasetMetadata` does not tell an
empty list from an absent one.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
from dataclasses import dataclass
from typing import Any

from pitloom.core.dataset_metadata import (
    FOLLOWER_FIELDS,
    DatasetMetadata,
    DatasetReference,
    is_placeholder,
)
from pitloom.core.dataset_names import dataset_key, log_one_dataset
from pitloom.messages.datasets import DatasetModel, warn_dataset_conflict

log = logging.getLogger(__name__)

__all__ = ["MergedDataset", "merge_dataset_into", "merge_dataset_references"]

#: Fields that identify the dataset or record where values came from; never
#: filled or compared field by field.
_NOT_MERGED = frozenset({"name", "provenance"}) | frozenset(FOLLOWER_FIELDS.values())


@dataclass
class MergedDataset:
    """One dataset and every role the model has to it."""

    #: The first reference's metadata, with the gaps the others fill.
    metadata: DatasetMetadata
    #: Each role once, in the order the references listed them.
    roles: list[str]
    #: Every spelling of the name that was merged, the first one first.
    names: list[str]


def _is_unset(value: Any) -> bool:
    """Whether a source stated nothing for *value*: ``None``, an empty text
    or list, or a placeholder (``noAssertion``, ``unknown``, ``N/A``), which is
    not a claim and so does not block a later reference that states the
    field."""
    if isinstance(value, str):
        return not value.strip() or is_placeholder(value)
    return value is None or value == []


def _fill(target: DatasetMetadata, other: DatasetMetadata, field_name: str) -> None:
    """Copy *field_name* (with its follower and provenance) from *other*; a
    provenance *target* held for the value it replaces goes."""
    for name in (field_name, FOLLOWER_FIELDS.get(field_name)):
        if name is not None:
            setattr(target, name, copy.deepcopy(getattr(other, name)))
    if field_name in other.provenance:
        target.provenance[field_name] = other.provenance[field_name]
    else:
        target.provenance.pop(field_name, None)


def _differ(field_name: str, mine: Any, theirs: Any) -> bool:
    """Whether two set values of *field_name* state different things; the
    download location of a Hub id is spelled as its id is."""
    if field_name == "download_url":
        return str(mine).casefold() != str(theirs).casefold()
    return bool(mine != theirs)


def merge_dataset_into(
    target: DatasetMetadata,
    other: DatasetMetadata,
    warned: set[str],
    model: DatasetModel,
    *,
    say_on: logging.Logger = log,
) -> None:
    """Fill the unset fields of *target* from *other*, a reference of
    *model* to the same dataset; warn once of each field (not in *warned*,
    which this updates) both set to different values: the first is kept.
    The warning is logged on *say_on* (a model reader passes its own
    logger, so a model scan relays it naming the model's stable path)."""
    for item in dataclasses.fields(DatasetMetadata):
        if item.name in _NOT_MERGED:
            continue
        mine, theirs = getattr(target, item.name), getattr(other, item.name)
        if _is_unset(theirs):
            continue
        if _is_unset(mine):
            _fill(target, other, item.name)
        elif _differ(item.name, mine, theirs) and item.name not in warned:
            warned.add(item.name)
            warn_dataset_conflict(say_on, model, target.name, item.name)


def _said_conflicts(references: list[DatasetReference]) -> dict[str, set[str]]:
    """The fields already said to conflict for each dataset (by
    :func:`~pitloom.core.dataset_names.dataset_key`): the union of
    :attr:`~pitloom.core.dataset_metadata.DatasetReference.said_conflicts`
    over its references, whichever comes first."""
    said: dict[str, set[str]] = {}
    for reference in references:
        key = dataset_key(reference.metadata.name)
        said.setdefault(key, set()).update(reference.said_conflicts)
    return said


def merge_dataset_references(
    references: list[DatasetReference], *, model: DatasetModel
) -> list[MergedDataset]:
    """*references*, all of *model*, with those of one dataset merged, in
    order of first appearance; a conflict is said once per dataset and
    field, never for a field a reference's route already said. The inputs
    are not changed."""
    merged: dict[str, MergedDataset] = {}
    warned = _said_conflicts(references)
    for reference in references:
        key = dataset_key(reference.metadata.name)
        known = merged.get(key)
        if known is None:
            merged[key] = MergedDataset(
                copy.deepcopy(reference.metadata),
                [reference.role],
                [reference.metadata.name],
            )
            continue
        if reference.role not in known.roles:
            known.roles.append(reference.role)
        if reference.metadata.name not in known.names:
            log_one_dataset(known.names[0], reference.metadata.name)
            known.names.append(reference.metadata.name)
        merge_dataset_into(known.metadata, reference.metadata, warned[key], model)
    return list(merged.values())
