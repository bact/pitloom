# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying a lock file's and a lock entry's lines (:func:`say_lock_file`,
:func:`say_lock_entry`; :func:`lock_file_cap` for its ``over-cap``), a skipped
dependency by its cause (:func:`warn_skipped_dependency`,
:func:`warn_skipped_extra_entry`), an extra gate
(:func:`warn_extra_gate_ambiguous`, :func:`warn_extra_gate_unusable`,
:func:`warn_required_not_pep508`) and a direct reference
(:func:`say_direct_reference`).

A memo here is per run: a set the caller makes and passes down, never
:func:`~pitloom.logging_config.log_once`, so a second library call on
another project still says its lines. No helper adds a prefix.

See also: :mod:`pitloom.messages._lock_file`,
:mod:`pitloom.messages._lock_entry` and :mod:`pitloom.messages._dependency`
(the entries).
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, Final, Literal

from packaging.utils import canonicalize_name

from pitloom.core.internal_error import InternalError
from pitloom.log_masking import masked_text
from pitloom.logging_config import EXCERPT_CHARS, one_line
from pitloom.messages._dependency import (
    CAUSE_LINES,
    DEPENDENCY_NAME_AMBIGUOUS,
    DIRECT_REFERENCE_LINE,
    EXTRA_GATE_AMBIGUOUS,
    EXTRA_GATE_UNUSABLE,
    GATE_LINE,
    JOINED_LINE,
    REQUIRED_LINE,
    REQUIREMENT_INVALID,
    REQUIREMENT_UNUSABLE,
    SELF_GATE_LINE,
)
from pitloom.messages._emit import emit
from pitloom.messages._lock_entry import (
    LOCK_ENTRY_CONFLICT,
    LOCK_ENTRY_MALFORMED,
    LOCK_ENTRY_UNUSABLE,
)
from pitloom.messages._lock_file import (
    LOCK_FILE_CONFLICT,
    LOCK_FILE_MALFORMED,
    LOCK_FILE_UNUSABLE,
    LOCK_FILE_WRONG_FORMAT,
)
from pitloom.messages._over_cap import Cap
from pitloom.messages._templates import written
from pitloom.messages._types import Line, Message

#: What the cap on a lock file's size is named in its ``over-cap`` line.
LOCK_FILE_CAP_PURPOSE: Final = "lock-file"
#: What an ``over-cap`` line on a lock file ends in (the reader says it
#: through :func:`~pitloom.messages.files.warn_over_cap`).
LOCK_FILE_OVER_CAP_OUTCOME: Final = "no dependency pins read"

#: A per-run memo of the lines said: the caller makes one (``set()``) per
#: walk or document and passes it down.
Said = set[tuple[str, ...]]

#: The causes a skipped dependency or extra entry is said by: the keys of
#: :data:`~pitloom.messages._dependency.CAUSE_LINES`.
Cause = Literal[
    "not-pep-508",
    "marker",
    "not-convertible",
    "local-source",
    "undeclared-extra",
    "cycle",
    "undeclared-dependency",
    "unlisted-optional",
]


def _owners(*entries: Message) -> Mapping[Line, Message]:
    """Each line of *entries*, to the entry that holds it."""
    return MappingProxyType({ln: entry for entry in entries for ln in entry.lines})


_FILE_LINES: Final = _owners(
    LOCK_FILE_MALFORMED, LOCK_FILE_WRONG_FORMAT, LOCK_FILE_UNUSABLE, LOCK_FILE_CONFLICT
)
_ENTRY_LINES: Final = _owners(
    LOCK_ENTRY_MALFORMED, LOCK_ENTRY_UNUSABLE, LOCK_ENTRY_CONFLICT
)
_CAUSE_OWNERS: Final = _owners(REQUIREMENT_INVALID, REQUIREMENT_UNUSABLE)


class _CutFailure(Exception):
    """An exception's text, masked and cut to :data:`EXCERPT_CHARS`: what a
    ``failure`` field of these lines prints."""


def _cut_failure(failure: object) -> object:
    """*failure* as a lock or dependency line prints it: an exception's
    text on one line, a URL's credentials masked, then cut to
    :data:`~pitloom.logging_config.EXCERPT_CHARS` characters, ``...`` after
    it when cut (a parser's message can repeat a 3,000-character marker or
    version). An :class:`OSError` with its own description, or any value
    that is not an exception, is left for the field's writer."""
    if not isinstance(failure, BaseException) or (
        isinstance(failure, OSError) and failure.strerror
    ):
        return failure
    text = masked_text(" ".join(str(failure).split()))
    if len(text) <= EXCERPT_CHARS:
        return failure
    return _CutFailure(text[:EXCERPT_CHARS] + "...")


def _file_name(file: str | PurePath) -> str:
    """The lock as a line names it: a path's file name (``uv.lock``), a
    text as given (a name already)."""
    return file.name if isinstance(file, PurePath) else file


def _say(
    log: logging.Logger,
    owners: Mapping[Line, Message],
    shape: Line,
    file: str | PurePath | None,
    said: Said | None,
    values: dict[str, Any],
) -> None:
    """Say *shape* (a line of *owners*) at ``WARNING``, the lock named by
    *file*; once per memo *said* when given, a package known by its PEP 503
    name.

    Raises:
        pitloom.core.internal_error.InternalError: *shape* is not a line of
            *owners*.
        ValueError: A value does not have its field's shape.
    """
    message = owners.get(shape)
    if message is None:
        raise InternalError(f"not a line of this helper: {shape.template!r}")
    if file is not None:
        values = {**values, "file": _file_name(file)}
    if "failure" in values:
        values["failure"] = _cut_failure(values["failure"])
    if isinstance(values.get("why"), str):
        # A parser's message can quote a URL: masked here, before any
        # handler sees the record's arguments.
        values["why"] = one_line(values["why"])
    if said is not None:
        key_values = dict(values)
        if isinstance(key_values.get("package"), str):
            key_values["package"] = canonicalize_name(str(key_values["package"]))
        texts = written(shape.template, key_values)
        key = (
            message.code,
            shape.template,
            *(f"{k}={texts[k]}" for k in sorted(texts)),
        )
        if key in said:
            return
        said.add(key)
    emit(log, message, logging.WARNING, line=shape, **values)


def say_lock_file(
    log: logging.Logger,
    shape: Line,
    /,
    *,
    file: str | PurePath | None = None,
    said: Said | None = None,
    **values: object,
) -> None:
    """The one ``WARNING:`` on *log* for a lock file as a whole: *shape*, a
    line of a ``lock-file-*`` entry (``TOP_KEY_LIST_LINE``), with *values*
    for its other fields. *file*: the lock, named by its file name (a path's
    ``.name``; never its directory); ``None`` only for
    ``LOCK_CONFLICT_LINE``, which names the two locks as kept and dropped.
    *said*: a per-run memo; a line said before with the same values is not
    said again.

    Raises:
        pitloom.core.internal_error.InternalError: *shape* is not a line of
            a ``lock-file-*`` entry.
        ValueError: *values* are not the line's other fields, or one does
            not have its field's shape.
    """
    _say(log, _FILE_LINES, shape, file, said, dict(values))


def say_lock_entry(
    log: logging.Logger,
    shape: Line,
    /,
    *,
    file: str | PurePath | None = None,
    said: Said | None = None,
    **values: object,
) -> None:
    """The one ``WARNING:`` on *log* for one entry of a lock file, one
    dependency reference in it or one ``requirements.txt`` line: *shape*,
    a line of a ``lock-entry-*`` entry, with *values* for its other fields
    (``package``, a name that passed
    :func:`~pitloom.extract.lock.common.is_usable_name`; ``line_number``, the line
    number). *file* and *said*: as :func:`say_lock_file` (*file* ``None``
    only for ``LOCKED_VERSIONS_LINE``, which no lock file states); the memo
    knows a
    package by its PEP 503 name, so a reference met twice in one walk is
    said once. A ``why`` is put on one line, a URL's credentials masked.

    Raises:
        pitloom.core.internal_error.InternalError: *shape* is not a line of
            a ``lock-entry-*`` entry.
        ValueError: *values* are not the line's other fields, or one does
            not have its field's shape.
    """
    _say(log, _ENTRY_LINES, shape, file, said, dict(values))


def lock_file_cap(limit: int) -> Cap:
    """The cap on a lock file's size, *limit* bytes, as its ``over-cap``
    line names it."""
    return Cap(limit, "byte", LOCK_FILE_CAP_PURPOSE)


def _cause_line(cause: str, *, of_extra: bool) -> Line:
    """The line *cause* is said in, for an extra's entry or a dependency.

    Raises:
        pitloom.core.internal_error.InternalError: *cause* is not one, or
            does not apply to that kind of entry.
    """
    lines = CAUSE_LINES.get(cause)
    shape = None if lines is None else lines[1 if of_extra else 0]
    if shape is None:
        kind = "an extra's entry" if of_extra else "a dependency"
        raise InternalError(f"cause {cause!r} is not one of {kind}")
    return shape


def _cause_values(
    shape: Line, failure: BaseException | None, source_kind: str | None
) -> dict[str, Any]:
    """The optional values *shape* names, each given exactly when it does.

    Raises:
        pitloom.core.internal_error.InternalError: One is given that the
            line does not name, or one it names is not given.
    """
    values: dict[str, Any] = {}
    for name, value in (("failure", failure), ("source_kind", source_kind)):
        if (name in shape.fields) != (value is not None):
            raise InternalError(f"{name}: given for the wrong cause")
        if value is not None:
            values[name] = _cut_failure(value) if name == "failure" else value
    return values


# pylint: disable-next=too-many-arguments
def warn_skipped_dependency(
    log: logging.Logger,
    cause: Cause,
    *,
    dependency: object,
    declared_in: str,
    failure: BaseException | None = None,
    source_kind: str | None = None,
    quiet: bool = False,
) -> None:
    """The one ``WARNING:`` on *log* that the *dependency* (as declared: a
    requirement, a Poetry name) declared in *declared_in* (``Poetry``, a
    setting) is not listed, its line and code picked by *cause*:
    ``not-pep-508``, ``not-convertible`` (with
    *failure*; Poetry), ``local-source`` (with *source_kind*, ``path`` or
    ``file``; Poetry, ``requirement-unusable``) or ``unlisted-optional``
    (Poetry). Silent when *quiet* (a read whose value is discarded).

    Raises:
        pitloom.core.internal_error.InternalError: *cause* does not apply to
            a dependency, or *failure* or *source_kind* is given for a
            cause that names none, or not given for one that does.
    """
    shape = _cause_line(cause, of_extra=False)
    values = _cause_values(shape, failure, source_kind)
    if not quiet:
        emit(
            log,
            _CAUSE_OWNERS[shape],
            logging.WARNING,
            line=shape,
            dependency=dependency,
            declared_in=declared_in,
            **values,
        )


# pylint: disable-next=too-many-arguments
def warn_skipped_extra_entry(
    log: logging.Logger,
    cause: Cause,
    *,
    extra: str,
    dependency: object,
    declared_in: str,
    failure: BaseException | None = None,
    quiet: bool = False,
) -> None:
    """The one ``WARNING:`` on *log* that the entry *dependency* of *extra*,
    declared in *declared_in* (``optional-dependencies``,
    ``extras_require``, ``Poetry``), is not used, its line picked by
    *cause*: ``not-pep-508``, ``marker`` (with *failure*),
    ``undeclared-extra`` (a self-reference naming an extra not declared),
    ``cycle`` (a self-reference closing a cycle) or
    ``undeclared-dependency`` (Poetry: a name not in
    ``[tool.poetry.dependencies]``). Silent when *quiet*.

    Raises:
        pitloom.core.internal_error.InternalError: *cause* does not apply to
            an extra's entry, or *failure* is given for a cause that names
            none, or not given for one that does.
    """
    shape = _cause_line(cause, of_extra=True)
    values = _cause_values(shape, failure, None)
    if not quiet:
        emit(
            log,
            REQUIREMENT_INVALID,
            logging.WARNING,
            line=shape,
            extra_name=extra,
            dependency=dependency,
            declared_in=declared_in,
            **values,
        )


def warn_required_not_pep508(log: logging.Logger, dependency: object) -> None:
    """The one ``WARNING:`` on *log* that *dependency*, met while
    assembling the document, is not PEP 508 and is recorded as required
    (``requirement-invalid``)."""
    emit(
        log,
        REQUIREMENT_INVALID,
        logging.WARNING,
        line=REQUIRED_LINE,
        dependency=dependency,
    )


def warn_extra_gate_unusable(
    log: logging.Logger, *, package: str, dependency: object, self_reference: bool
) -> None:
    """The one ``WARNING:`` on *log* that the extra marker of *dependency*
    (as declared), a requirement on *package*, cannot be isolated: recorded
    as required, or for a *self_reference*, the extras it requests
    (``extra-gate-unusable``)."""
    emit(
        log,
        EXTRA_GATE_UNUSABLE,
        logging.WARNING,
        line=SELF_GATE_LINE if self_reference else GATE_LINE,
        package=package,
        dependency=dependency,
    )


def warn_extra_gate_ambiguous(
    log: logging.Logger, *, dependency: object, extras: Collection[str]
) -> None:
    """The one ``WARNING:`` on *log* that *dependency* needs *extras*
    together and is recorded as optional for any of them
    (``extra-gate-ambiguous``)."""
    emit(
        log,
        EXTRA_GATE_AMBIGUOUS,
        logging.WARNING,
        line=JOINED_LINE,
        dependency=dependency,
        extra_name=frozenset(extras),
    )


def say_direct_reference(log: logging.Logger, package: str, *, said: set[str]) -> None:
    """The one ``INFO:`` on *log* that *package*, a direct reference, is not
    looked up on PyPI (``dependency-name-ambiguous``): once per package, by
    its PEP 503 name, in the memo *said* the caller keeps per document. The
    caller says it only online, and never for a registry requirement."""
    key = canonicalize_name(package)
    if key in said:
        return
    said.add(key)
    emit(
        log,
        DEPENDENCY_NAME_AMBIGUOUS,
        logging.INFO,
        line=DIRECT_REFERENCE_LINE,
        package=package,
    )
