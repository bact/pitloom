# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The free-text author fields of core metadata (``Author``,
``Author-email``, a dependency's ``Maintainer`` pair): a field split by a
guess (``author-ambiguous``), an address entry that is not one valid
email address (``author-invalid``), and a project directory whose
declared authors an embed could not read (``project-unreadable``). Only
a ``pyproject.toml`` authors list keeps each author apart; every other
route reads these fields.

See also: :mod:`pitloom.messages._authors_say` (the helpers that say
them), :mod:`pitloom.extract.authors` (the reading) and
:mod:`pitloom.messages.authors` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

#: Why a name field is cut only next to an address.
_NAME_CUT: Final = (
    "split into %(entry_count)s next to an address; a name field is never "
    "cut between names"
)
#: Why an address field split may be wrong.
_ADDRESS_CUT: Final = (
    "split into %(entry_count)s on ',' or ';'; an address field cannot tell a "
    "list from one name holding a comma"
)

#: A project's name field (``Author``) cut next to the addresses it holds.
NAME_SPLIT_LINE: Final = Line(
    level="WARNING", template=f"AUTHOR=%(authors)s: {_NAME_CUT}"
)
#: A project's address field (``Author-email``) cut on ``,`` or ``;``.
ADDRESS_SPLIT_LINE: Final = Line(
    level="WARNING", template=f"AUTHOR_EMAIL=%(authors)s: {_ADDRESS_CUT}"
)
#: A project's name field read as one author though it holds ``,``, ``;``
#: or ``and``.
ONE_AUTHOR_LINE: Final = Line(
    level="INFO",
    template="AUTHOR=%(authors)s: read as one author; it may list several",
)
#: The first dependency of a document whose name field was cut.
DEPENDENCY_NAME_SPLIT_LINE: Final = Line(
    level="WARNING",
    template=f"PACKAGE=%(package)s %(author_key)s=%(authors)s: {_NAME_CUT}; "
    "%(dependency_count)s split in all",
)
#: The first dependency of a document whose address field was cut.
DEPENDENCY_ADDRESS_SPLIT_LINE: Final = Line(
    level="WARNING",
    template=f"PACKAGE=%(package)s %(author_key)s=%(authors)s: {_ADDRESS_CUT}; "
    "%(dependency_count)s split in all",
)

#: Where only one author per entry is read, for the advice.
_ONE_BY_ONE: Final = (
    "Only authors listed in pyproject.toml (a project directory or an sdist "
    "that has one) are read one by one; a wheel's METADATA, an sdist's "
    "PKG-INFO, a setup.cfg or setup.py author and a dependency's record are "
    "free text."
)

AUTHOR_AMBIGUOUS: Final = Message(
    code="author-ambiguous",
    condition="ambiguous",
    lines=(
        NAME_SPLIT_LINE,
        ADDRESS_SPLIT_LINE,
        ONE_AUTHOR_LINE,
        DEPENDENCY_NAME_SPLIT_LINE,
        DEPENDENCY_ADDRESS_SPLIT_LINE,
    ),
    summary="A free-text author field (core metadata Author or Author-email, "
    "a setup.cfg or setup.py author, a dependency's author or maintainer "
    "record) was read by a guess. An address field is a list, split on ',' "
    "and ';', though one name may hold a comma ('Doe, Jane'); a name field "
    "is one author, cut only next to the complete mailboxes it holds. The "
    "INFO line is a name field read as one author though it holds ',', ';' "
    "or 'and' ('Doe, Jane' and 'Ann and Bob' cannot be told from lists). "
    "For dependencies, one line per document names the first field split "
    "and how many dependencies were.",
    did="Recorded each entry of the split as its own author (or the name "
    "field as one author, for the INFO line); the SBOM is written.",
    effect="weaker",
    actor="user",
    advice="Tell the user which field was split and how, as the line says. "
    f"{_ONE_BY_ONE} They list each author in [project] authors of "
    "pyproject.toml and generate from the project or an sdist. A dependency's "
    "record is its maintainers' to fix. Do not edit the project's metadata "
    f"for them; {ASK_FIRST}",
    subject_key="AUTHOR",
    since=_SINCE,
)

#: An address field's entry that is not one valid email address.
EMAIL_INVALID_LINE: Final = Line(
    level="WARNING",
    template="AUTHOR_EMAIL=%(authors)s: not one valid email address; not recorded",
)
#: The same, several entries.
EMAIL_INVALID_COUNT_LINE: Final = Line(
    level="WARNING",
    template="AUTHOR_EMAIL=%(authors)s: not one valid email address; "
    "%(entry_count)s not recorded",
)
#: A name field's mailbox that is not one valid email address.
NAME_INVALID_LINE: Final = Line(
    level="WARNING",
    template="AUTHOR=%(authors)s: not one valid email address; not recorded",
)
#: The same, several entries.
NAME_INVALID_COUNT_LINE: Final = Line(
    level="WARNING",
    template="AUTHOR=%(authors)s: not one valid email address; %(entry_count)s "
    "not recorded",
)

AUTHOR_INVALID: Final = Message(
    code="author-invalid",
    condition="invalid",
    lines=(
        EMAIL_INVALID_LINE,
        EMAIL_INVALID_COUNT_LINE,
        NAME_INVALID_LINE,
        NAME_INVALID_COUNT_LINE,
    ),
    summary="An entry of a project's free-text author field (an Author-email "
    "entry, or a mailbox in Author with '<' or '@') is not one valid email "
    "address: its address is not of the form local@domain, text follows a "
    "valid address ('Ann <a@x.org> extra', 'a@x.org trailing'), or one "
    "mailbox holds two addresses. "
    "The line shows the entries, the first few when several, and how many.",
    did="Recorded no address for the entry; a display name stated before "
    "its '<' is kept as an author with no address. The SBOM is written.",
    effect="thinner",
    actor="user",
    advice="Tell the user which entries are not one valid email address, as "
    "the line says. They correct the address in the project's metadata and "
    f"generate again. Do not edit the metadata for them; {ASK_FIRST}",
    subject_key="AUTHOR_EMAIL",
    since=_SINCE,
)

#: ``embed-wheel --project-dir``: the project's metadata, read for its
#: declared authors, could not be read.
PROJECT_UNREADABLE_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: project metadata not read; authors from the wheel "
    "METADATA; %(failure)s",
)

PROJECT_UNREADABLE: Final = Message(
    code="project-unreadable",
    condition="unreadable",
    lines=(PROJECT_UNREADABLE_LINE,),
    summary="An embed with a project directory (embed-wheel --project-dir, "
    "wheel --embed with --project-dir, the library's embed_wheel_sbom) "
    "reads the project's metadata only for its declared authors, which keep "
    "their order there; the metadata could not be read: a configuration or "
    "metadata file that does not parse, is not UTF-8 or cannot be opened. "
    "The line gives what was reported.",
    did="Took the authors from the wheel's METADATA: authors with an address "
    "come first, and name-only authors joined into one Author field are read "
    "as one. The SBOM is embedded.",
    effect="thinner",
    actor="user",
    advice="Tell the user which project directory could not be read and why, "
    "as the line says. They fix the project's metadata and embed again. Do "
    f"not edit the project for them; {ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

ENTRIES: Final = (AUTHOR_AMBIGUOUS, AUTHOR_INVALID, PROJECT_UNREADABLE)
