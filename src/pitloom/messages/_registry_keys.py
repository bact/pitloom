# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How an element is keyed and gated in the ID registry, where that is not
by its path and content: no hash to gate on (``registry-hash-missing``), no
entry (``registry-entry-missing``), no path key (``registry-path-key-unusable``),
no package identity (``registry-identity-missing``), a key moved between a
source layout and its installed path (``registry-key-moved``), and a
``loom id generate`` PATH that indexes nothing (``index-path-no-effect``).

Most are ``INFO`` decisions: the condition they answer, no one to act.

See also: :mod:`pitloom.messages._registry_conflict` (two claims on one
id), :mod:`pitloom.messages.id_registry_ids` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._registry_conflict import LOOKUP_SURFACES
from pitloom.messages._registry_file import REGISTRY_PREFIX
from pitloom.messages._summary import Summary
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"


def _line(level: str, text: str) -> Line:
    """A line of *level*: the registry's prefix, then *text*."""
    return Line(level=level, template=f"{REGISTRY_PREFIX}{text}")


#: A loom.Run element whose entry records a hash, with no content hashed.
UNHASHED_LINE: Final = _line(
    "WARNING",
    "%(element_kind)s %(entity)s: the entry records a SHA-256 but no content "
    "was hashed; minting a new spdxId",
)
#: A loom model declared without ``path=``, a registry loaded.
MODEL_NO_PATH_LINE: Final = _line(
    "WARNING", "loom model %(entity)s has no path=; looked up ungated: not hashed"
)
#: A loom model whose ``path=`` is no regular file at run exit, a registry
#: loaded (with none, ``model-file-missing``).
MODEL_NOT_A_FILE_LINE: Final = _line(
    "WARNING",
    "loom model %(entity)s: path= %(path)s is not a file at exit; looked up "
    "ungated: not hashed",
)
#: A dataset looked up with no hash.
UNGATED_LINE: Final = _line("INFO", "dataset %(entity)s looked up ungated: not hashed")
#: A hashed dataset matched a pin that records no hash.
HASHLESS_PIN_LINE: Final = _line(
    "INFO",
    "dataset %(entity)s matched a pin without SHA-256; content not checked",
)
#: ``id generate -e`` pins a dataset with no hash.
PIN_WITHOUT_HASH_LINE: Final = _line(
    "INFO", "dataset %(entity)s pinned without SHA-256: %(why)s"
)
#: ``id generate -e`` gives a hashless dataset pin its hash.
PIN_GATED_LINE: Final = _line("INFO", "dataset %(entity)s pin now gated by its SHA-256")

REGISTRY_HASH_MISSING: Final = Message(
    code="registry-hash-missing",
    condition="missing",
    lines=(
        UNHASHED_LINE,
        MODEL_NO_PATH_LINE,
        MODEL_NOT_A_FILE_LINE,
        UNGATED_LINE,
        HASHLESS_PIN_LINE,
        PIN_WITHOUT_HASH_LINE,
        PIN_GATED_LINE,
    ),
    summary="An ID registry lookup or pin has no SHA-256 to gate on: the "
    "element's content was not hashed (no file, a file gone, or over the "
    "hashing cap), or the pin records no hash. A pin given its hash later "
    "keeps its id.",
    did=f"Said by {LOOKUP_SURFACES}. An entry recording a hash is not "
    "vouched for without one: a new id is minted. Otherwise the element is "
    "looked up or pinned by its key alone, its content not checked. The "
    "SBOM is written.",
    effect="weaker",
    actor="caller",
    advice="The caller may give the element a file the run can hash (a "
    "loom path= that exists at exit, a dataset below the project root, a "
    "larger --max-dataset-hash-bytes) so its id is gated by its content.",
    since=_SINCE,
)

#: A loom.Run element the registry holds no entry for.
NOT_FOUND_LINE: Final = _line(
    "WARNING", "%(element_kind)s %(entity)s not found; minting a new spdxId"
)

REGISTRY_ENTRY_MISSING: Final = Message(
    code="registry-entry-missing",
    condition="missing",
    lines=(NOT_FOUND_LINE,),
    summary="A loom.Run script looks up an element the ID registry holds no "
    "entry for: expected on a first run, or for an element new since.",
    did="Minted a new id; a run that saves the registry records it.",
    effect="none",
    actor="none",
    advice="Nothing to do on a first run. Otherwise 'loom id generate' or a "
    "saving run records the element, and the next run reuses its id.",
    since=_SINCE,
)

#: A loom.Run file outside the registry's project root.
OUTSIDE_ROOT_LINE: Final = _line(
    "WARNING",
    "file %(entity)s is outside the project root %(root)s; minting a new spdxId",
)
#: A model or dataset keyed by its name.
NAME_KEY_LINE: Final = _line(
    "INFO", "%(element_kind)s %(entity)s keyed by its name: %(key_reason)s"
)
#: ``id import`` leaves a model under its name.
MODEL_IMPORTED_BY_NAME_LINE: Final = _line(
    "INFO",
    "model %(entity)s imported under its name: no unique file with its SHA-256",
)
#: A run's harvest leaves a hashed model out.
MODEL_NOT_RECORDED_LINE: Final = _line(
    "INFO",
    "model %(entity)s not recorded: no unique file with its SHA-256",
)
#: ``id generate -e`` stores an entity by name.
ENTITY_BY_NAME_LINE: Final = _line(
    "INFO", "-e %(entity)s stored by name: %(key_reason)s"
)
#: A document's files keyed by their path as read.
FALLBACK_KEYS_LINE: Final = _line(
    "INFO", "%(number)s file(s) keyed by their path as read: %(key_reason)s"
)

REGISTRY_PATH_KEY_UNUSABLE: Final = Message(
    code="registry-path-key-unusable",
    condition="unusable",
    lines=(
        OUTSIDE_ROOT_LINE,
        NAME_KEY_LINE,
        MODEL_IMPORTED_BY_NAME_LINE,
        MODEL_NOT_RECORDED_LINE,
        ENTITY_BY_NAME_LINE,
        FALLBACK_KEYS_LINE,
    ),
    summary="An element's path cannot key it in the ID registry: the file is "
    "outside the registry's project root or not there, not a regular file, "
    "a model with no unique file holding its SHA-256, or files whose path "
    "leads outside the root. The line says why.",
    did=f"Said by {LOOKUP_SURFACES}. Keyed the element by its name (a "
    "loom.Run file outside the root gets a new id; a hashed model with no "
    "unique file is not recorded). The SBOM is written.",
    effect="none",
    actor="none",
    advice="Nothing to do: the id stays stable under the name. A path key "
    "needs the file below the registry's project root.",
    since=_SINCE,
)

#: A package whose name or version is unknown.
IDENTITY_UNKNOWN_LINE: Final = _line(
    "INFO", "package identity unknown; not looked up or recorded"
)
#: ``id generate -e`` pins a package with no version.
NO_VERSION_LINE: Final = _line(
    "INFO",
    "-e %(entity)s stored without a version: holds only a package that states none",
)

REGISTRY_IDENTITY_MISSING: Final = Message(
    code="registry-identity-missing",
    condition="missing",
    lines=(IDENTITY_UNKNOWN_LINE, NO_VERSION_LINE),
    summary="A package has no name or version to key it by: a wheel or "
    "sdist whose metadata states none (Pitloom names it unknown), or a "
    "'loom id generate -e' package pin without '@VERSION'.",
    did="A package of unknown identity is neither looked up nor recorded: "
    "its id is the SBOM's own. A pin without a version holds only a package "
    "that states none.",
    effect="none",
    actor="none",
    advice="Nothing to do: an id is never shared by every release. A pin "
    "for one release takes 'NAME@VERSION'.",
    since=_SINCE,
)

#: Elements found through a layout alias.
ALIAS_HITS_LINE: Final = _line(
    "INFO",
    "%(number)s element(s) matched a registry key through the src/lib layout alias",
)
#: ``id generate`` moved held aliases to their own key.
ALIAS_PROMOTED_LINE: Final = _line(
    "INFO", "%(number)s key(s) promoted from a layout alias"
)
#: ``id generate``: changed content took its alias's id.
ALIAS_CHANGED_LINE: Final = _line(
    "INFO", "%(number)s key(s) of changed content took their layout alias's id"
)
#: ``id import`` wrote files under their alias.
ALIAS_IMPORTED_LINE: Final = _line(
    "INFO",
    "%(number)s file(s) imported under their layout alias: their own key "
    "holds other content",
)

REGISTRY_KEY_MOVED: Final = Message(
    code="registry-key-moved",
    condition="moved",
    lines=(
        ALIAS_HITS_LINE,
        ALIAS_PROMOTED_LINE,
        ALIAS_CHANGED_LINE,
        ALIAS_IMPORTED_LINE,
    ),
    summary="Files moved between a source layout and their installed path "
    "(src/pkg/a.py and pkg/a.py) are one file to the ID registry: a lookup "
    "through the layout alias keeps its id, and 'loom id generate' moves "
    "the entry to the file's own key.",
    did=f"Said by {LOOKUP_SURFACES}. Reused the id held under the other "
    "spelling of the path, and counted the files.",
    effect="none",
    actor="none",
    advice="Nothing to do: each file keeps one id.",
    since=_SINCE,
)

#: An explicit PATH under a directory the walk always skips.
SKIPPED_PATH_LINE: Final = _line(
    "WARNING",
    "PATH %(path)s is under a skipped directory name (%(name)s); not indexed",
)

INDEX_PATH_NO_EFFECT: Final = Message(
    code="index-path-no-effect",
    condition="no-effect",
    lines=(SKIPPED_PATH_LINE,),
    summary="A PATH given to 'loom id generate' (or IdRegistry.generate) is "
    "in a directory the file walk always skips (build/, .git/, a virtual "
    "environment), so it indexes nothing.",
    did="Indexed nothing under that PATH; the other PATHs are indexed and "
    "the registry is written.",
    effect="none",
    actor="user",
    advice="Tell the user which PATH indexes nothing and why, as the line "
    "says. They name a PATH outside the skipped directory. Do not move "
    f"files for them; {ASK_FIRST}",
    since=_SINCE,
)

#: ``id import`` keys a dataset by a path spelt otherwise than its name.
DATASET_PATH_KEY: Final = Summary(
    template=f"{REGISTRY_PREFIX}dataset %(entity)s keyed by its path: %(name)s",
    meaning="'loom id import' keys a dataset package by the path its name "
    "leads to, below the registry's root, as every run looks it up.",
    topic="id-registry-ids",
)
#: ``id import`` keys a model by the registry's file of its SHA-256.
MODEL_FILE_ENTRY_KEY: Final = Summary(
    template=f"{REGISTRY_PREFIX}model %(entity)s keyed by the registry's file "
    "with its SHA-256: %(name)s",
    meaning="'loom id import' keys a model whose file the SBOM does not list "
    "by the one file entry of the registry that records its SHA-256.",
    topic="id-registry-ids",
)

SUMMARIES: Final = (DATASET_PATH_KEY, MODEL_FILE_ENTRY_KEY)

ENTRIES: Final = (
    REGISTRY_HASH_MISSING,
    REGISTRY_ENTRY_MISSING,
    REGISTRY_PATH_KEY_UNUSABLE,
    REGISTRY_IDENTITY_MISSING,
    REGISTRY_KEY_MOVED,
    INDEX_PATH_NO_EFFECT,
)
