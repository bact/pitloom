# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the wheel and embedded-SBOM lines name: an archive by
its file name, a member by its raw name, a list of members, the type of the
exception a read raised, a part of a wheel's identity and its two
declarations, a file extension, a ``--sbom-filename`` value, a count of
skipped wheels and a library's minimum version.

A member name, a ``METADATA`` value and an SBOM's value are attacker text:
each writer masks a URL's credentials, cuts and escapes a control character
itself, so no call site can forget to. A name (an archive, a member, a
listed name) is cut to
:data:`~pitloom.messages._field_writers.NAME_CHARACTERS` characters, a
declared value to :data:`~pitloom.logging_config.EXCERPT_CHARS`: masked,
then cut, then escaped, so the longest line stays under
:data:`~pitloom.messages._lines.LONGEST_LINE` and keeps its code. The cap
bounds the report only; the name is read and compared in full.

See also: :mod:`pitloom.messages._fields` (every field, these included),
:mod:`pitloom.messages._wheels`, :mod:`pitloom.messages._archive_members`
and :mod:`pitloom.messages._wheel_sboms` (the lines).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.logging_config import loggable
from pitloom.messages._field_type import QUOTED, Field
from pitloom.messages._field_writers import (
    NAME_CHARACTERS,
    NAME_CUT_MARK,
    number_text,
    plain_text,
    quoted_name_text,
)
from pitloom.messages._fields_lock import EXCERPT_MEANING, excerpt_text

#: The most names a list of members or project paths shows before ``and N
#: more``.
SHOWN_NAMES: Final = 10

#: The parts of a wheel's identity an SBOM is cross-checked on.
IDENTITY_PARTS: Final = ("name", "version")

#: How a name field shows its name.
_SHOWN_NAME: Final = (
    f"in quotes, a URL's credentials masked, cut to {NAME_CHARACTERS} "
    f"characters with `{NAME_CUT_MARK}` before the closing quote, escaped when "
    "it holds a control character"
)

_RAW_MEMBER: Final = f"as the archive stores it, {_SHOWN_NAME}"


def exception_label(exc: BaseException) -> str:
    """The type of *exc* for a message, never its text: bare for a builtin
    (``EOFError``), qualified otherwise (``zlib.error``)."""
    cls = type(exc)
    if cls.__module__ == "builtins":
        return cls.__name__
    return f"{cls.__module__}.{cls.__qualname__}"


def exception_type_text(value: object) -> str:
    """The exception *value*'s type (:func:`exception_label`), escaped.

    Raises:
        ValueError: It is not an exception.
    """
    if not isinstance(value, BaseException):
        raise ValueError(f"not an exception: {value!r}")
    return loggable(exception_label(value))


def archive_text(value: object) -> str:
    """An archive as its ``ARCHIVE=`` names it: by its file name only (the
    last component of a ``str`` or a path, as given, never resolved), never
    its directory, so a caller may pass the path it holds
    (``ZipFile.filename``, the command line's); in quotes, masked, cut and
    escaped as every name is
    (:func:`~pitloom.messages._field_writers.quoted_name_text`).

    Raises:
        ValueError: It is neither a ``str`` nor a ``str`` path (``None``,
            the ``filename`` of an in-memory ``ZipFile``, included).
    """
    raw = os.fspath(value) if isinstance(value, os.PathLike) else value
    if not isinstance(raw, str):
        raise ValueError(f"not an archive name: {value!r}")
    return quoted_name_text(os.path.basename(raw))


def quoted_names_text(value: object) -> str:
    """A list or tuple of names, each in quotes, masked and cut
    (:func:`~pitloom.messages._field_writers.quoted_name_text`),
    comma-separated in the order given, at most :data:`SHOWN_NAMES`, then
    ``and N more``; an empty one writes nothing, which the field's shape
    refuses.

    Raises:
        ValueError: It is neither (a ``str`` included), or holds anything
            but text.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"not a list: {value!r}")
    shown = ", ".join(quoted_name_text(name) for name in value[:SHOWN_NAMES])
    more = len(value) - SHOWN_NAMES
    return f"{shown} and {more} more" if more > 0 else shown


def identity_part_text(value: object) -> str:
    """One of :data:`IDENTITY_PARTS`.

    Raises:
        ValueError: It is not.
    """
    if value not in IDENTITY_PARTS:
        raise ValueError(f"not a part of a wheel's identity: {value!r}")
    return plain_text(value)


#: The wheel and embedded-SBOM lines' fields.
WHEEL_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "archive": Field(
            QUOTED,
            archive_text,
            "'<archive>'",
            "a wheel or sdist by its file name as given, never its directory; "
            f"{_SHOWN_NAME}",
        ),
        "member": Field(
            QUOTED,
            quoted_name_text,
            "'<member>'",
            f"an archive member's name {_RAW_MEMBER}",
        ),
        "later_member": Field(
            QUOTED,
            quoted_name_text,
            "'<later-member>'",
            f"the later member of the same install name, {_RAW_MEMBER}",
        ),
        "install_name": Field(
            QUOTED,
            quoted_name_text,
            "'<install-name>'",
            "the name a member installs under, separators as `/`, empty and "
            f"`.` segments dropped; {_SHOWN_NAME}",
        ),
        "members": Field(
            r".+",
            quoted_names_text,
            "<members>",
            "archive member names, each shown as a member is, "
            f"comma-separated, at most {SHOWN_NAMES} then `and N more`",
            free=True,
        ),
        "project_paths": Field(
            r".+",
            quoted_names_text,
            "<project-paths>",
            f"project paths, each shown as a member is, comma-separated, at "
            f"most {SHOWN_NAMES} then `and N more`",
            free=True,
        ),
        "exception_type": Field(
            r"\S+",
            exception_type_text,
            "<exception-type>",
            "the type of the exception a read raised, never its text: bare "
            "for a builtin (`EOFError`), qualified otherwise "
            "(`zipfile.BadZipFile`)",
        ),
        "identity_part": Field(
            "|".join(IDENTITY_PARTS),
            identity_part_text,
            "<part>",
            "the part of a wheel's identity: `name` or `version`",
        ),
        "wheel_value": Field(
            r".+",
            excerpt_text,
            "<wheel-value>",
            f"the value the wheel's METADATA states, {EXCERPT_MEANING}",
            free=True,
        ),
        "sbom_value": Field(
            r".+",
            excerpt_text,
            "<sbom-value>",
            "the value the SBOM states (its subject's name or version, or "
            f"its type), {EXCERPT_MEANING}",
            free=True,
        ),
        "extension": Field(
            r"\.[a-z0-9]+(?:\.[a-z0-9]+)*",
            plain_text,
            "<extension>",
            "the file extension recommended for an SBOM's format (`.spdx3.json`)",
        ),
        "sbom_filename": Field(
            QUOTED,
            quoted_name_text,
            "'<sbom-filename>'",
            f"the file name given as --sbom-filename, {_SHOWN_NAME}",
        ),
        "skipped": Field(
            r"0|[1-9][0-9]*",
            number_text,
            "<skipped>",
            "how many wheels were skipped",
        ),
        "minimum_version": Field(
            r"[0-9]+(?:\.[0-9]+)*",
            plain_text,
            "<minimum-version>",
            "the oldest release of a library that has what Pitloom needs (`1.29.0`)",
        ),
    }
)
