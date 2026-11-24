# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading one SPDX 3 JSON-LD fragment file into an object set: the one
reader of a fragment, for the merge and for ``loom fragment list``.

A failure is raised as :class:`~pitloom.messages.fragments.FragmentReadError`
tagged with the stage that raised it, never classified by the exception's
type afterwards: a :class:`json.JSONDecodeError`, a
:class:`UnicodeDecodeError` and the RFC 8785 errors are all
:class:`ValueError`. A programming error
(:class:`~pitloom.core.internal_error.InternalError`) and
:class:`MemoryError` are never wrapped.

See also: :mod:`pitloom.assemble.spdx3.fragments` (the merge) and
:func:`pitloom.messages.fragments.warn_fragment_unread` (the line a caller
says for a failure).
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
from typing import Any, NamedTuple

import rfc8785
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.internal_error import InternalError
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.messages.fragments import FragmentReadError
from pitloom.messages.text import warn_lone_surrogates

log = logging.getLogger(__name__)


class ParsedFragment(NamedTuple):
    """A fragment's JSON and its objects."""

    #: The JSON as parsed, a lone surrogate written as text.
    data: Any
    #: The SPDX 3 objects it holds.
    objects: spdx3.SHACLObjectSet


def read_fragment_bytes(fragment_path: Path) -> bytes:
    """The bytes of the fragment at *fragment_path*.

    Raises:
        pitloom.messages.fragments.FragmentReadError: Stage ``read``: the
            file could not be read (an :class:`OSError`, a path no file can
            have).
    """
    try:
        return fragment_path.read_bytes()
    except (InternalError, MemoryError):
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise FragmentReadError("read", exc) from exc


def _json_of(raw: bytes) -> tuple[Any, bool]:
    """*raw* parsed as JSON, each lone surrogate written as text, and
    whether there was one.

    ``json.loads(bytes)``, never ``json.loads(raw.decode())``: it detects
    UTF-16 and UTF-32 and strips a UTF-8 BOM, which a decoded ``str`` would
    fail on.

    Raises:
        pitloom.messages.fragments.FragmentReadError: Stage ``json``: not
            JSON, not in a Unicode encoding JSON allows, or nested deeper
            than the parser recurses.
    """
    try:
        return escape_lone_surrogates_in(json.loads(raw))
    except (InternalError, MemoryError):
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise FragmentReadError("json", exc) from exc


def parse_fragment(raw: bytes, *, file: str | os.PathLike[str]) -> ParsedFragment:
    """The fragment *raw* (the bytes of *file*, which a lone-surrogate
    ``WARNING:`` names) as JSON and as SPDX 3 objects.

    A lone surrogate in a string (``"\\ud800"``, which no UTF-8 output can
    hold) is written as text, with one ``WARNING:``. The fragment's JSON
    must also be RFC 8785 serialisable, as the merged document is: an
    integer beyond +-(2**53 - 1) (``dataset_datasetSize``) or a number past
    a double has no JCS spelling, and one such value would otherwise fail
    the whole document's serialisation.

    Raises:
        pitloom.messages.fragments.FragmentReadError: Stage ``json`` (see
            :func:`_json_of`), or stage ``spdx``: no RFC 8785 spelling, or
            the SPDX 3 bindings do not read it.
    """
    data, lone = _json_of(raw)
    try:
        rfc8785.dumps(data)
        if lone:
            raw = json.dumps(data).encode("ascii")
        objects = spdx3.SHACLObjectSet()
        spdx3.JSONLDDeserializer().read(io.BytesIO(raw), objects)
    except (InternalError, MemoryError):
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise FragmentReadError("spdx", exc) from exc
    if lone:
        warn_lone_surrogates(log, file=file)
    return ParsedFragment(data, objects)


def read_fragment_set(
    fragment_path: Path, *, file: str | os.PathLike[str] | None = None
) -> spdx3.SHACLObjectSet:
    """The objects of the fragment at *fragment_path*
    (:func:`read_fragment_bytes`, then :func:`parse_fragment`); a
    lone-surrogate ``WARNING:`` names *file*, else *fragment_path*.

    Raises:
        pitloom.messages.fragments.FragmentReadError: The read failed, at
            the stage it names.
    """
    raw = read_fragment_bytes(fragment_path)
    shown = fragment_path if file is None else file
    return parse_fragment(raw, file=shown).objects
