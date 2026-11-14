# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Two claims on one ID registry id or key: two elements, two runs, two
spellings or two types (``registry-conflict``), an element whose content is
not what its entry records (``registry-hash-conflict``), and one key that
several files or entries hold (``registry-key-ambiguous``).

See also: :mod:`pitloom.messages._registry_keys` (how an element is keyed),
:mod:`pitloom.messages.id_registry_ids` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._registry_file import REGISTRY_PREFIX
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.24.1"
#: Where an id is looked up: every surface that reads a registry.
LOOKUP_SURFACES: Final = (
    "every command that reads an ID registry (generate, project, wheel, "
    "embed-wheel, id generate, id import), the build hook, the library and "
    "loom.Run"
)


def _line(level: str, text: str) -> Line:
    """A line of *level*: the registry's prefix, then *text*."""
    return Line(level=level, template=f"{REGISTRY_PREFIX}{text}")


#: Two elements of one run claim one held id.
CLAIM_LINE: Final = _line(
    "WARNING",
    "%(spdx_id)s is registered for both %(entity)s and %(claimant)s; the "
    "second gets a new id",
)

REGISTRY_CONFLICT: Final = Message(
    code="registry-conflict",
    condition="conflict",
    lines=(CLAIM_LINE,),
    summary="Two elements of one SBOM match one ID registry entry: a stale "
    "entry outlived the element it named, or one name is pinned for two "
    "elements. One id never names two elements.",
    did=f"Said by {LOOKUP_SURFACES}. The first element in document order "
    "keeps the id; the second gets a new one. The SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which id two elements claim, as the line names "
    "them. Expected on every run after an ambiguous-name pin. Otherwise the "
    "registry holds a stale entry: 'loom id generate' re-indexes the "
    "project, or 'loom id generate -e' pins the two elements apart. Do not "
    f"edit the registry for them; {ASK_FIRST}",
    since=_SINCE,
)

#: Another run saved the id first.
CONCURRENT_LINE: Final = _line(
    "WARNING",
    "another run saved %(spdx_id)s for %(element_type)s %(entity)s first; not "
    "recording it for %(claimant)s",
)

REGISTRY_CONFLICT_CONCURRENT: Final = Message(
    code="registry-conflict/concurrent",
    condition="conflict",
    lines=(CONCURRENT_LINE,),
    summary="Two runs saved the ID registry at once and both took one id, "
    "minted from the same counter or moved to another key: the file keeps "
    "the other run's key for it.",
    did="Saved the registry with the other run's entry; this run's key for "
    "the id is not recorded. The SBOM already written keeps the id; the next "
    "run mints a new one for that key.",
    effect="none",
    actor="user",
    advice="Tell the user that another run saved the registry at the same "
    "time, as the line says. Running once more records the element under a "
    "new id; runs that share a registry are best run one at a time. Do not "
    f"run again for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A later spelling of a dataset has its own pin.
SPELLING_LINE: Final = _line(
    "WARNING",
    "dataset %(entity)s is pinned to %(spdx_id)s, but it is read as "
    "%(claimant)s, whose id is used",
)

REGISTRY_CONFLICT_SPELLING: Final = Message(
    code="registry-conflict/spelling",
    condition="conflict",
    lines=(SPELLING_LINE,),
    summary="A loom.Run script names one dataset two ways, and the ID "
    "registry pins the later spelling to another id than the first.",
    did="Used the first spelling's id for the dataset; the later spelling's "
    "pin is not used. The SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which dataset is named two ways, each pinned, as "
    "the line names them. They name it one way in the script, or drop one "
    f"pin. Do not edit the script or the registry for them; {ASK_FIRST}",
    since=_SINCE,
)

#: An element ``id import`` skips: its id is held under another key.
HELD_LINE: Final = _line(
    "INFO",
    "%(element_type)s %(entity)s not imported: its id is held under %(claimant)s",
)

REGISTRY_CONFLICT_HELD: Final = Message(
    code="registry-conflict/held",
    condition="conflict",
    lines=(HELD_LINE,),
    summary="'loom id import' meets an element whose id the registry holds "
    "under another key that no element of the SBOM moves: the held key "
    "keeps it.",
    did="Left the element out of the registry; the held key keeps the id. "
    "A run's own harvest leaves such an element out silently.",
    effect="none",
    actor="none",
    advice="Nothing to do: one id is held under one key. To key the element "
    "under its new key, the user removes the old entry first.",
    since=_SINCE,
)

#: A model's name is held only under another type.
TYPE_LINE: Final = _line(
    "WARNING",
    "%(entity)s is held under another type; minting a new spdxId",
)

REGISTRY_CONFLICT_TYPE: Final = Message(
    code="registry-conflict/type",
    condition="conflict",
    lines=(TYPE_LINE,),
    summary="A loom.Run script looks a model up by a name the ID registry "
    "holds only under another element type.",
    did="Minted a new id for the model; the entry of the other type is left "
    "as it is. The SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which name is held under another type, as the "
    "line names it. They pin the model as a model ('loom id generate -e "
    f"NAME:ai_AIPackage') or rename one. Do not edit the registry for them; "
    f"{ASK_FIRST}",
    since=_SINCE,
)

#: A loom.Run element whose content changed.
HASH_CHANGED_WARNING_LINE: Final = _line(
    "WARNING",
    "%(element_kind)s %(entity)s: its SHA-256 no longer matches the entry; "
    "minting a new spdxId",
)
#: ``id generate`` re-indexing, or ``-e``, met changed content.
HASH_CHANGED_LINE: Final = _line(
    "INFO",
    "content changed for %(entity)s; minting a new spdxId (old: %(spdx_id)s)",
)
#: A model whose gated lookup missed while its key is held.
MODEL_GATE_MISS_LINE: Final = _line(
    "INFO",
    "model %(entity)s: no registry entry records its SHA-256; a new id is used",
)

REGISTRY_HASH_CONFLICT: Final = Message(
    code="registry-hash-conflict",
    condition="conflict",
    lines=(HASH_CHANGED_WARNING_LINE, HASH_CHANGED_LINE, MODEL_GATE_MISS_LINE),
    summary="An element's content is not what its ID registry entry "
    "records: the SHA-256 differs, or (a model) the entry records none. "
    "Changed bytes are another element, so they get another id.",
    did=f"Said by {LOOKUP_SURFACES}. Minted a new id; 'loom id generate' "
    "and a saving run replace the entry. The SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which element changed, as the line names it. "
    "Expected after a retrain, a new download or an edit; if the content "
    "should not have changed, they check the file. Do not restore files for "
    f"them; {ASK_FIRST}",
    since=_SINCE,
)

#: ``id import`` replaced a gated entry with an unhashed element's id.
GATE_DROPPED_LINE: Final = _line(
    "INFO",
    "content gate dropped for %(element_type)s %(entity)s: imported id "
    "%(spdx_id)s replaces %(claimant)s",
)
#: A run's harvest kept a gated entry over an unhashed element.
GATE_KEPT_LINE: Final = _line(
    "INFO",
    "content gate kept for %(element_type)s %(entity)s: harvested id "
    "%(spdx_id)s not recorded over %(claimant)s",
)
#: A run's harvest kept a gated entry over a merged fragment's older hash.
GATE_KEPT_OLDER_LINE: Final = _line(
    "INFO",
    "content gate kept for %(element_type)s %(entity)s: element id "
    "%(spdx_id)s with an older SHA-256 not recorded over %(claimant)s",
)

REGISTRY_HASH_CONFLICT_GATE: Final = Message(
    code="registry-hash-conflict/gate",
    condition="conflict",
    lines=(GATE_DROPPED_LINE, GATE_KEPT_LINE, GATE_KEPT_OLDER_LINE),
    summary="An SBOM's element has another id than the ID registry entry "
    "that records its content's SHA-256, and the element states no hash or "
    "an older one.",
    did="'loom id import' takes the imported id and drops the entry's "
    "hash; a run's harvest keeps the entry as it is.",
    effect="none",
    actor="none",
    advice="Nothing to do: the line says which id the registry keeps.",
    since=_SINCE,
)

#: Several files hold one key once NFC-normalised.
NFC_CLASH_LINE: Final = _line(
    "WARNING",
    "%(number)s files have one key once NFC-normalised, none is indexed: %(entity)s",
)
#: One key matches several held layout aliases.
ALIAS_TIE_LINE: Final = _line(
    "INFO",
    "%(entity)s matches more than one layout alias (%(entities)s); none reused",
)
#: Names held by several elements of an imported SBOM; the outcome is
#: ``not imported`` (a run's harvest says it at DEBUG, ``not harvested``).
NAME_HELD_LINE: Final = _line(
    "INFO",
    "%(outcome)s (name held by several elements): %(entities)s",
)

REGISTRY_KEY_AMBIGUOUS: Final = Message(
    code="registry-key-ambiguous",
    condition="ambiguous",
    lines=(NFC_CLASH_LINE, ALIAS_TIE_LINE, NAME_HELD_LINE),
    summary="One ID registry key stands for several things: files whose "
    "names are one once NFC-normalised (where the file system keeps both), "
    "several held layout aliases (src/ or lib/) of one key, or one name held "
    "by several elements of an imported SBOM.",
    did="Neither stands for the key: 'loom id generate' indexes none of the "
    "files, a lookup reuses no alias, 'loom id import' imports none of the "
    "elements. Each gets an id of its own; the SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which key is ambiguous, as the line names it. "
    "They rename one of the files, or pin each element with 'loom id "
    f"generate -e'. Do not rename files for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (
    REGISTRY_CONFLICT,
    REGISTRY_CONFLICT_CONCURRENT,
    REGISTRY_CONFLICT_SPELLING,
    REGISTRY_CONFLICT_HELD,
    REGISTRY_CONFLICT_TYPE,
    REGISTRY_HASH_CONFLICT,
    REGISTRY_HASH_CONFLICT_GATE,
    REGISTRY_KEY_AMBIGUOUS,
)
