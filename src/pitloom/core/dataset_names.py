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
:data:`MAX_CARD_DATASETS` of them.

No Pitloom imports but :mod:`pitloom.logging_config`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from pitloom.logging_config import Cap, loggable, warn_over_cap

log = logging.getLogger(__name__)

__all__ = [
    "CARD_DATASETS_CAP",
    "MAX_CARD_DATASETS",
    "dataset_key",
    "distinct_dataset_names",
    "is_hub_dataset_id",
    "log_one_dataset",
]

#: The most datasets one model card may list: a dataset is a package and
#: its relationships in the SBOM, so a card listing a million is cut.
MAX_CARD_DATASETS = 1000
CARD_DATASETS_CAP = Cap(MAX_CARD_DATASETS, "dataset", "model-card-datasets")

#: A Hub repository id: an optional owner and a name, each 1-96 of
#: ``[A-Za-z0-9_.-]`` starting with a letter or digit and ending with a
#: letter, digit or ``_``, as ``huggingface_hub`` validates them (a legacy
#: dataset such as ``c4`` has no owner).
_PART = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,94}[A-Za-z0-9_])?"
_DATASET_ID_RE = re.compile(rf"(?:{_PART}/)?{_PART}")


def is_hub_dataset_id(name: str) -> bool:
    """Whether *name* is a Hub repository id; a model card's ``datasets:``
    also holds plain names, which are not looked up (nor warned of)."""
    return (
        _DATASET_ID_RE.fullmatch(name) is not None
        and "--" not in name
        and ".." not in name
        and not name.endswith(".git")
    )


def dataset_key(name: str) -> str:
    """What names one dataset: *name* with each whitespace run one space,
    in lower case when it is a Hub repository id."""
    collapsed = " ".join(name.split())
    return collapsed.lower() if is_hub_dataset_id(collapsed) else collapsed


def log_one_dataset(kept: str, spelling: str) -> None:
    """One ``INFO:`` that *spelling* was read as the dataset *kept*, which
    names it (the first spelling wins). Every route that folds two spellings
    says it through here, so none does it silently."""
    log.info(
        "dataset %s and %s name one dataset; the first spelling is kept",
        loggable(kept),
        loggable(spelling),
    )


def distinct_dataset_names(names: Iterable[str], cap: Cap, where: str) -> list[str]:
    """Each dataset of *names* once, by its first spelling, in order (names
    stripped, a blank one none), the first ``cap.limit`` of them; one
    ``WARNING:`` naming *where* when more were listed."""
    seen: dict[str, str] = {}
    cut = False
    for listed in names:
        name = listed.strip()
        key = dataset_key(name)
        if key and key in seen:
            if name != seen[key]:
                log_one_dataset(seen[key], name)
            continue
        if not key:
            continue
        if len(seen) >= cap.limit:
            cut = True
            break
        seen[key] = name
    if cut:
        warn_over_cap(log, cap, where, f"the first {cap.limit} kept")
    return list(seen.values())
