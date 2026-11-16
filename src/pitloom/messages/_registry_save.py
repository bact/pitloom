# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saving the ID registry: a registry with no file to save to
(``registry-file-missing``) and the summaries of a save (the ids it holds,
the ids it added, the stale entries it updated, the key ``-e`` stored, the
configuration hint).

A save that fails says the failure's own line, an ``ERROR`` or its
``WARNING`` twin (:func:`~pitloom.messages._registry_save_say.say_save_failure`);
a write the system refused says ``file-unwritable``.

See also: :mod:`pitloom.id_registry._persist` (the save),
:mod:`pitloom.messages.id_registry` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._registry_file import REGISTRY_PREFIX, SAVE_SURFACES
from pitloom.messages._summary import Summary
from pitloom.messages._types import Line, Message

_SINCE: Final = "0.25.0"
_TOPIC: Final = "id-registry"

#: A registry with no file, asked to save what a run added.
FILE_MISSING_LINE: Final = Line(
    level="WARNING",
    template=f"{REGISTRY_PREFIX}no file to save to; the ids this run added are "
    "not saved",
)

REGISTRY_FILE_MISSING: Final = Message(
    code="registry-file-missing",
    condition="missing",
    lines=(FILE_MISSING_LINE,),
    summary="A run that saves the ids it added to the ID registry was given "
    "a registry with no file: an IdRegistry made in memory, without a path. "
    "The CLI and the build hook always name a file.",
    did=f"Said by {SAVE_SURFACES}. The ids are used in the SBOM, which is "
    "written, but are not saved: the next run mints them again.",
    effect="none",
    actor="caller",
    advice="The caller may give the IdRegistry a path (IdRegistry.load, or "
    "IdRegistry.new with path=) to keep the ids, or turn the update off "
    "(update-id-registry = false; update_id_registry=False in the library) "
    "when an in-memory registry is meant.",
    since=_SINCE,
)

#: ``loom id generate`` and ``loom id import``: the registry just written.
HOLDS_IDS: Final = Summary(
    template=f"{REGISTRY_PREFIX}holds %(number)s id(s)",
    meaning="'loom id generate' or 'loom id import' wrote the registry; it "
    "now holds that many ids.",
    topic=_TOPIC,
)
#: A run's save added ids.
ADDED_IDS: Final = Summary(
    template=f"{REGISTRY_PREFIX}added %(number)s new id(s) to %(path)s",
    meaning="A run saved the registry with that many ids new to it, under "
    "keys new to it: neither another run's ids saved meanwhile nor a refused "
    "one count.",
    topic=_TOPIC,
)
#: A run's save changed entries but added no id.
STALE_UPDATED: Final = Summary(
    template=f"{REGISTRY_PREFIX}updated stale entries in %(path)s",
    meaning="A run saved the registry and added no id: an entry's hash "
    "changed, an id moved to its lookup key, or a stale key was released.",
    topic=_TOPIC,
)
#: ``loom id generate -e NAME`` stored under another spelling.
ENTITY_STORED_AS: Final = Summary(
    template=f"{REGISTRY_PREFIX}-e %(entity)s stored as %(name)s",
    meaning="'loom id generate -e' stored NAME under the key every lookup "
    "uses (a path key, a package's normalised NAME@VERSION), spelt otherwise "
    "than typed. Said once the registry is written.",
    topic=_TOPIC,
)
#: The configuration hint after a new registry, the table holding none.
CONFIG_HINT_ADD: Final = Summary(
    template=f"{REGISTRY_PREFIX}to use this registry, add to %(table)s in "
    "%(file)s: id-registry = %(value)s",
    meaning="'loom id' wrote a new registry the project configuration does "
    "not name: the line to add for every run to use it.",
    topic=_TOPIC,
)
#: The same, the table naming another registry.
CONFIG_HINT_CHANGE: Final = Summary(
    template=f"{REGISTRY_PREFIX}to use this registry, change id-registry in "
    "%(table)s in %(file)s to: id-registry = %(value)s",
    meaning="'loom id' wrote a new registry while the project configuration "
    "names another: the value to change it to.",
    topic=_TOPIC,
)

SUMMARIES: Final = (
    HOLDS_IDS,
    ADDED_IDS,
    STALE_UPDATED,
    ENTITY_STORED_AS,
    CONFIG_HINT_ADD,
    CONFIG_HINT_CHANGE,
)

ENTRIES: Final = (REGISTRY_FILE_MISSING,)
