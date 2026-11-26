# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Loom ID registry file Pitloom cannot use: JSON that is no registry
(``registry-malformed``), a key the format does not have
(``registry-unknown-key``), another format version
(``registry-wrong-format``), and a project root the file cannot record
(``registry-unusable``). As an ``ERROR`` nothing is written; each ``ERROR``
line has a ``WARNING`` twin, said when a run whose SBOM is already built
re-reads the file to save the ids it added
(:func:`~pitloom.messages._registry_save_say.say_save_failure`).

A registry file that cannot be read, is not UTF-8, is not valid JSON or is
not a JSON object says ``file-unreadable``, ``file-unreadable/not-utf8`` and
``json-malformed``, read ``for the ID registry`` (a file read as UTF-16
or UTF-32 that does not decode: ``json-malformed``).

See also: :mod:`pitloom.id_registry._format` (the reader and writer),
:mod:`pitloom.messages.id_registry` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message, warning_twins

_SINCE: Final = "0.25.0"

#: The literal prefix of every line about the ID registry.
REGISTRY_PREFIX: Final = "ID registry: "
#: The subject of every line about one registry file.
_SUBJECT: Final = f"{REGISTRY_PREFIX}FILE=%(file)s: "
#: The registry file version Pitloom reads and writes
#: (:data:`pitloom.id_registry._types._REGISTRY_VERSION`; a drift test holds
#: them equal).
REGISTRY_VERSION: Final = 4
#: The largest id counter (:data:`pitloom.id_registry._counters.MAX_ID_NUMBER`;
#: a drift test holds them equal).
MAX_COUNTER: Final = 9007199254740991
#: The runs that save the ids they added after their SBOM is built.
SAVE_SURFACES: Final = (
    "loom generate (a project, wheel or environment), project, wheel and "
    "env, the library's generate_project_sbom, generate_wheel_sbom, "
    "generate_env_sbom and the PyPI and Git URL functions that call them, "
    "and loom.Run"
)
#: What a command, the hook and the library do for every line here.
_DID: Final = (
    "As an ERROR, wrote nothing. The command exits 1 (the Action step "
    "fails), the build hook fails the build, and the library raises "
    "ValueError carrying the code. 'loom id' writes no registry, and every "
    "other command writes no SBOM. The file is left as it is. As a WARNING, "
    f"a run whose SBOM is already built ({SAVE_SURFACES}) read the file "
    "again to save the ids it added: nothing is saved and the SBOM stands; "
    "the next run mints those ids again."
)


def _line(condition: str) -> Line:
    """The ``ERROR`` line naming the registry file, then *condition*."""
    return Line(level="ERROR", template=f"{_SUBJECT}{condition}")


#: A JSON object of the file names one key twice.
DUPLICATE_KEY_LINE: Final = _line("duplicate key %(name)s")
#: No ``namespace``, or one that is not a non-empty string.
NO_NAMESPACE_LINE: Final = _line("missing a valid 'namespace'")
#: A ``namespace`` that is not a namespace IRI; the reason after it.
NAMESPACE_LINE: Final = _line("'namespace' %(namespace_problem)s: %(namespace)s")
#: A key the format needs that the file lacks.
MISSING_KEY_LINE: Final = _line("missing %(name)s")
#: An ``id_counters`` key that is no id prefix.
COUNTER_PREFIX_LINE: Final = _line("'id_counters' key %(name)s is not an id prefix")
#: An ``id_counters`` value out of range.
COUNTER_NUMBER_LINE: Final = _line(
    f"'id_counters' %(name)s: %(value)s is not a whole number from 1 to {MAX_COUNTER}"
)
#: ``id_counters`` that is not an object.
COUNTERS_LINE: Final = _line("'id_counters' is not an object")
#: A ``project_root`` that is not a relative POSIX path.
PROJECT_ROOT_LINE: Final = _line(
    "'project_root' %(value)s is not a relative POSIX path (relative to the "
    "registry file's directory)"
)
#: ``elements`` that is not an object.
ELEMENTS_LINE: Final = _line("malformed entry: 'elements' is not an object")
#: One type's table of ``elements`` that is not an object.
TYPE_TABLE_LINE: Final = _line(
    "malformed entry: elements %(element_type)s is not an object"
)
#: Why the ID registry cannot hold a name: its file is UTF-8. Said of a
#: registry file that holds one (here) and of a name given to it
#: (``text-malformed/registry``).
UNENCODABLE: Final = "cannot be encoded as UTF-8 (lone surrogate)"
#: A key or ``spdxId`` holding a lone surrogate (a JSON ``\ud800`` escape).
UNENCODABLE_LINE: Final = _line(f"%(registry_part)s %(value)s {UNENCODABLE}")
#: Two keys that are one once normalised (NFC, a package's version).
DUPLICATE_ENTRY_LINE: Final = _line("two %(element_type)s entries for %(name)s")
#: An entry that is not an object.
ENTRY_LINE: Final = _line("malformed entry: %(element_type)s %(name)s is not an object")
#: An entry whose ``spdxId`` is not a non-empty string.
SPDX_ID_LINE: Final = _line(
    "malformed entry: %(element_type)s %(name)s: 'spdxId' must be a non-empty string"
)
#: An entry whose ``sha256`` is present but not a non-empty string.
SHA256_LINE: Final = _line(
    "malformed entry: %(element_type)s %(name)s: 'sha256' must be a non-empty "
    "string, or left out"
)
#: No id left to mint: a held counter or id at the largest number.
MINT_LINE: Final = _line("no %(name)s id left to mint in %(namespace)s")

REGISTRY_MALFORMED: Final = Message(
    code="registry-malformed",
    condition="malformed",
    lines=warning_twins(
        (
            DUPLICATE_KEY_LINE,
            NO_NAMESPACE_LINE,
            NAMESPACE_LINE,
            MISSING_KEY_LINE,
            COUNTER_PREFIX_LINE,
            COUNTER_NUMBER_LINE,
            COUNTERS_LINE,
            PROJECT_ROOT_LINE,
            ELEMENTS_LINE,
            TYPE_TABLE_LINE,
            UNENCODABLE_LINE,
            DUPLICATE_ENTRY_LINE,
            ENTRY_LINE,
            SPDX_ID_LINE,
            SHA256_LINE,
            MINT_LINE,
        )
    ),
    summary="An ID registry file is a JSON object but not a registry: a "
    "key named twice, a namespace, id counter, project root or entry of the "
    "wrong shape, a key the format needs missing, two entries for one key, "
    "or a key or spdxId holding a lone surrogate (a \\ud800 escape). Most "
    "often a hand edit or a merge of two versions of the file. A counter a "
    "save would write out of range says the same, before the file is "
    "written; so does a mint past the largest id, which only a counter or "
    "an id edited to near it reaches.",
    did=_DID,
    effect="not-written",
    actor="user",
    advice="Tell the user which registry file is malformed and what is "
    "wrong, as the line says. They fix the edit, or restore the file from "
    "version control, and run again; deleting it loses every id it pins. Do "
    f"not edit, restore or delete the file for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: Top-level keys the format does not have.
UNKNOWN_TOP_KEY_LINE: Final = _line("unknown top-level key(s): %(name)s")
#: Keys an entry may not have.
UNKNOWN_ENTRY_KEY_LINE: Final = _line(
    "malformed entry: %(element_type)s %(name)s has unknown key(s): %(value)s"
)

REGISTRY_UNKNOWN_KEY: Final = Message(
    code="registry-unknown-key",
    condition="unknown-key",
    lines=warning_twins((UNKNOWN_TOP_KEY_LINE, UNKNOWN_ENTRY_KEY_LINE)),
    summary="An ID registry file holds a key its format does not have, at "
    "the top level or in an entry. The version is checked first, so a "
    "registry from a newer Pitloom says registry-wrong-format instead: the "
    "key comes from a hand edit or another tool.",
    did=_DID,
    effect="not-written",
    actor="user",
    advice="Tell the user which registry file holds which unknown key, as "
    "the line says. They remove the key (or restore the file from version "
    "control) and run again. Do not edit the file for them; " + ASK_FIRST,
    subject_key="FILE",
    since=_SINCE,
)

#: A registry of another format version.
VERSION_LINE: Final = _line(
    f"version %(value)s, expected {REGISTRY_VERSION} (no migration support)"
)

REGISTRY_WRONG_FORMAT: Final = Message(
    code="registry-wrong-format",
    condition="wrong-format",
    lines=warning_twins((VERSION_LINE,)),
    summary=f"An ID registry file is of another format version than "
    f"{REGISTRY_VERSION}, the one Pitloom reads: an older one (a version 3 "
    "file from Pitloom 0.21, whose package keys hold no version, or a version "
    "2 one), a newer one from a later Pitloom, or none at all (no 'version', "
    "or one that is not a whole number). It is never migrated. The line "
    "states the version found.",
    did=_DID,
    effect="not-written",
    actor="user",
    advice="Tell the user which registry file cannot be read and the "
    "version the line states; what helps depends on it. Older than "
    f"{REGISTRY_VERSION}: to keep its ids, they delete it and run 'loom id "
    "import' on the last SBOM a run made with it ('loom id generate' alone "
    "mints new ids for everything). Newer: the file comes from a later "
    "Pitloom; they upgrade Pitloom and keep the file, which is not to be "
    "deleted. None, or not a whole number: most often a hand edit; they "
    "restore the file from version control. Deleting it loses every id it "
    f"pins. Do not delete, restore or upgrade anything for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: A project root with no relative path from the registry file's directory.
NO_RELATIVE_ROOT_LINE: Final = _line(
    "project root %(path)s has no path relative to the file's directory; %(failure)s"
)
#: A project root whose relative path would not load back.
ROOT_NOT_STORABLE_LINE: Final = _line(
    "project root %(path)s cannot be stored as %(value)s"
)

REGISTRY_UNUSABLE: Final = Message(
    code="registry-unusable",
    condition="unusable",
    lines=warning_twins((NO_RELATIVE_ROOT_LINE, ROOT_NOT_STORABLE_LINE)),
    summary="An ID registry file cannot record its project root: the file "
    "stores the root relative to its own directory, and there is no such "
    "path (on Windows, the file and the project on two drives) or it would "
    "not load back. Said when the registry is saved.",
    did="Saved nothing: the registry file is not written or changed. As an "
    "ERROR, 'loom id' exits 1 and IdRegistry.save raises ValueError carrying "
    f"the code. As a WARNING ({SAVE_SURFACES}, whose SBOM is already "
    "built), the SBOM stands and the ids the run added are not saved.",
    effect="none",
    actor="user",
    advice="Tell the user that the registry file cannot record where the "
    "project is, as the line says. A registry file inside the project always "
    "works: the root is then stored as '.' or '..' steps. With no relative "
    "path (two Windows drives), a file on the project's drive works too; a "
    "root that cannot be stored (a backslash in a directory name between the "
    "file and the project) is fixed only by a file inside the project. They "
    f"name such a file and run again. Do not move files for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

ENTRIES: Final = (
    REGISTRY_MALFORMED,
    REGISTRY_UNKNOWN_KEY,
    REGISTRY_WRONG_FORMAT,
    REGISTRY_UNUSABLE,
)
