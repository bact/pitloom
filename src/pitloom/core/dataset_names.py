# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The names of the datasets a model card lists: when two spellings are one
dataset, and how many a card may list.

A Hugging Face repository id is case-insensitive (``O/D`` is ``o/d``); any
other name is compared as written, whitespace runs apart. A card's
``datasets:`` list is read through :func:`distinct_dataset_names`, so every
reader keeps one name per dataset and no more than
:data:`MAX_CARD_DATASETS` of them. A source that states a version per entry
(GGUF) reads through :func:`distinct_datasets`, where the version is part
of the identity (:func:`dataset_identity`): two releases of one dataset stay
two.

No Pitloom imports but :mod:`pitloom.logging_config`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from pitloom.messages.datasets import say_one_dataset
from pitloom.messages.files import (
    Cap,
    warn_over_cap,
)

log = logging.getLogger(__name__)

__all__ = [
    "CARD_DATASETS_CAP",
    "MAX_CARD_DATASETS",
    "dataset_identity",
    "dataset_key",
    "distinct_dataset_names",
    "distinct_datasets",
    "is_hub_repo_id",
    "log_one_dataset",
]

#: The most datasets one model card may list: a dataset is a package and
#: its relationships in the SBOM, so a card listing a million is cut.
MAX_CARD_DATASETS = 1000
CARD_DATASETS_CAP = Cap(MAX_CARD_DATASETS, "dataset", "model-card-datasets")

#: A Hub repository id: an optional owner and a name, each 1-96 of
#: ``[A-Za-z0-9_.-]`` starting with a letter or digit and ending with a
#: letter, digit or ``_``, as ``huggingface_hub`` validates them (a legacy
#: dataset or model such as ``c4`` or ``gpt2`` has no owner).
_PART = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,94}[A-Za-z0-9_])?"
_HUB_REPO_ID_RE = re.compile(rf"(?:{_PART}/)?{_PART}")


def is_hub_repo_id(name: str) -> bool:
    """Whether *name* is a Hub repository id (a dataset's or a model's), as
    ``huggingface_hub.utils.validate_repo_id`` accepts one; a model card's
    ``datasets:`` also holds plain names, which are not looked up (nor
    warned of)."""
    return (
        _HUB_REPO_ID_RE.fullmatch(name) is not None
        and "--" not in name
        and ".." not in name
        and not name.endswith(".git")
    )


def dataset_key(name: str) -> str:
    """What names one dataset: *name* with each whitespace run one space,
    in lower case when it is a Hub repository id."""
    collapsed = " ".join(name.split())
    return collapsed.lower() if is_hub_repo_id(collapsed) else collapsed


#: What tells two dataset entries apart: the name's
#: :func:`dataset_key` and the version as stated (``None`` when none).
DatasetIdentity = tuple[str, "str | None"]


def dataset_identity(name: str, version: str | None) -> DatasetIdentity:
    """The identity of the dataset entry *name* at *version*: the same name
    at two versions is two datasets."""
    return dataset_key(name), version


def log_one_dataset(kept: str, spelling: str) -> None:
    """One ``INFO:`` that *spelling* was read as the dataset *kept*, which
    names it (the first spelling wins). Every route that folds two spellings
    says it through here, so none does it silently."""
    say_one_dataset(log, kept, spelling)


def distinct_datasets(
    entries: Iterable[tuple[str, str | None]], cap: Cap, where: str
) -> list[tuple[str, str | None]]:
    """Each dataset of the (name, version) *entries* once
    (:func:`dataset_identity`), by its first spelling, in order (names
    stripped, a blank one none), the first ``cap.limit`` of them; one
    ``WARNING:`` naming *where* when more were listed."""
    seen: dict[DatasetIdentity, tuple[str, str | None]] = {}
    said: set[tuple[str, str]] = set()
    cut = False
    for listed, version in entries:
        name = listed.strip()
        identity = dataset_identity(name, version)
        if identity in seen:
            kept = seen[identity][0]
            if name != kept and (kept, name) not in said:
                said.add((kept, name))
                log_one_dataset(kept, name)
            continue
        if not identity[0]:
            continue
        if len(seen) >= cap.limit:
            cut = True
            break
        seen[identity] = (name, version)
    if cut:
        warn_over_cap(log, cap, where, f"the first {cap.limit} kept")
    return list(seen.values())


def distinct_dataset_names(names: Iterable[str], cap: Cap, where: str) -> list[str]:
    """Each dataset of *names* (no versions) once, as
    :func:`distinct_datasets` keeps them."""
    entries = ((name, None) for name in names)
    return [name for name, _ in distinct_datasets(entries, cap, where)]
