# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the embedded-SBOM lines: the name and version cross-check's
results as data (:class:`IdentityMismatch`, :class:`CrossCheckGap`, which
:func:`pitloom._sbom_format.check_spdx3_name_version` returns, so that
module holds no prose), the helpers that say them, and one helper or
constructor per other line.

An *archive* is the wheel's file name (or a path, named by its last
component); a *member* the SBOM's name in the wheel as stored. The field
writers quote, mask, cut and escape the values.

See also: :mod:`pitloom.messages._wheel_sboms` (the entries).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from pitloom.core.internal_error import InternalError
from pitloom.messages._compared_value import compared_pair
from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._field_writers import cut_name
from pitloom.messages._types import Line
from pitloom.messages._wheel_sboms import (
    BOTH_PART_MISSING_LINE,
    DATETIME_NOT_RECORDABLE,
    FLOORED_LINE,
    KEPT_LINE,
    MISMATCH_ERROR_LINE,
    MISMATCH_LINE,
    NAME_CLASH_LINE,
    NO_DOCUMENT_LINE,
    NO_DOCUMENT_ROOT_LINE,
    NO_NAMED_SBOM_LINE,
    NO_SBOM_LINE,
    NO_SBOM_ROOT_LINE,
    NO_VALIDATOR_LINE,
    NO_WHEEL_IDENTITY_LINE,
    NOT_SPDX3_LINE,
    REMOVED_LINE,
    SBOM_NAME_CONFLICT,
    SBOM_PART_MISSING_LINE,
    SBOM_VERSION_INVALID_LINE,
    SEVERAL_SBOMS_LINES,
    SUBJECT_NOT_PACKAGE_LINE,
    UNKNOWN_FORMAT_LINE,
    WHEEL_PART_MISSING_LINE,
    WHEEL_SBOM_AMBIGUOUS,
    WHEEL_SBOM_CONFLICT,
    WHEEL_SBOM_CONFLICT_HELD,
    WHEEL_SBOM_MISSING,
    WHEEL_SBOM_UNUSABLE,
    WHEEL_SBOM_WRONG_FORMAT,
    WHEEL_VERSION_INVALID_LINE,
    WRONG_EXTENSION_LINE,
)

if TYPE_CHECKING:
    from pitloom.messages._wheels_say import Archive


class IdentityMismatch(NamedTuple):
    """A part of a wheel's identity its SBOM states otherwise."""

    #: ``name`` or ``version``.
    part: str
    #: What the wheel's ``METADATA`` states.
    wheel_value: str
    #: What the SBOM's subject states.
    sbom_value: str


#: The wheel's ``METADATA`` states neither a name nor a version.
GAP_NO_WHEEL_IDENTITY: Final = "no-wheel-identity"
#: The wheel's ``METADATA`` lacks the part.
GAP_WHEEL_PART_MISSING: Final = "wheel-part-missing"
#: The SBOM's subject lacks the part.
GAP_SBOM_PART_MISSING: Final = "sbom-part-missing"
#: Both lack the part.
GAP_BOTH_PART_MISSING: Final = "both-part-missing"
#: The wheel's version is not a PEP 440 version (the value).
GAP_WHEEL_VERSION_INVALID: Final = "wheel-version-invalid"
#: The SBOM's version is not a PEP 440 version (the value).
GAP_SBOM_VERSION_INVALID: Final = "sbom-version-invalid"
#: The SBOM is not SPDX 3 JSON-LD.
GAP_NOT_SPDX3: Final = "not-spdx3"
#: The SBOM has no ``SpdxDocument``.
GAP_NO_DOCUMENT: Final = "no-document"
#: The ``SpdxDocument``'s ``rootElement`` leads nowhere.
GAP_NO_DOCUMENT_ROOT: Final = "no-document-root"
#: The ``software_Sbom``'s ``rootElement`` leads nowhere.
GAP_NO_SBOM_ROOT: Final = "no-sbom-root"
#: The subject is not a package (the value: its type, as the SBOM states it).
GAP_SUBJECT_NOT_PACKAGE: Final = "subject-not-package"

#: Each cause's line, and the value field it names (``""``: none, ``part``:
#: the part of the identity).
_GAPS: Final[Mapping[str, tuple[Line, str]]] = MappingProxyType(
    {
        GAP_NO_WHEEL_IDENTITY: (NO_WHEEL_IDENTITY_LINE, ""),
        GAP_WHEEL_PART_MISSING: (WHEEL_PART_MISSING_LINE, "part"),
        GAP_SBOM_PART_MISSING: (SBOM_PART_MISSING_LINE, "part"),
        GAP_BOTH_PART_MISSING: (BOTH_PART_MISSING_LINE, "part"),
        GAP_WHEEL_VERSION_INVALID: (WHEEL_VERSION_INVALID_LINE, "wheel_value"),
        GAP_SBOM_VERSION_INVALID: (SBOM_VERSION_INVALID_LINE, "sbom_value"),
        GAP_NOT_SPDX3: (NOT_SPDX3_LINE, ""),
        GAP_NO_DOCUMENT: (NO_DOCUMENT_LINE, ""),
        GAP_NO_DOCUMENT_ROOT: (NO_DOCUMENT_ROOT_LINE, ""),
        GAP_NO_SBOM_ROOT: (NO_SBOM_ROOT_LINE, ""),
        GAP_SUBJECT_NOT_PACKAGE: (SUBJECT_NOT_PACKAGE_LINE, "sbom_value"),
    }
)

#: Every cause a :class:`CrossCheckGap` names.
GAP_CAUSES: Final = tuple(_GAPS)


class CrossCheckGap(NamedTuple):
    """Why (part of) the name and version cross-check was not made.

    Raises:
        pitloom.core.internal_error.InternalError: (from
            :meth:`line_values`)
            *cause* is not one of :data:`GAP_CAUSES`, or *part* or *value*
            is given where the cause takes none, or missing where it takes
            one.
    """

    #: One of :data:`GAP_CAUSES`.
    cause: str
    #: ``name`` or ``version``, for a ``*-part-missing`` cause.
    part: str | None = None
    #: The value the line names (a version, a type), as the source states
    #: it: any JSON value for a type, ``None`` for one not stated. ``None``
    #: for a cause that names no value.
    value: object = None

    # Any: the values go to emit()'s **values, whose other keywords are typed.
    def line_values(self) -> tuple[Line, dict[str, Any]]:
        """Its line and the values that line names, but the archive."""
        try:
            line, takes = _GAPS[self.cause]
        except KeyError:
            raise InternalError(f"no cross-check gap {self.cause!r}") from None
        takes_value = takes not in ("", "part")
        if (self.part is not None) != (takes == "part") or (
            self.value is not None and not takes_value
        ):
            raise InternalError(f"cross-check gap {self.cause!r}: wrong values")
        if takes == "part":
            return line, {"identity_part": self.part}
        return line, ({takes: self.value} if takes else {})


def warn_cross_check_gaps(
    log: logging.Logger, archive: Archive, gaps: Sequence[CrossCheckGap]
) -> None:
    """One ``WARNING:`` on *log* per gap of *gaps*, in order, for *archive*
    (``wheel-sbom-unusable``)."""
    for gap in gaps:
        line, values = gap.line_values()
        emit(
            log,
            WHEEL_SBOM_UNUSABLE,
            logging.WARNING,
            line=line,
            archive=archive,
            **values,
        )


def say_identity_mismatches(
    log: logging.Logger,
    archive: Archive,
    mismatches: Sequence[IdentityMismatch],
    *,
    level: int = logging.WARNING,
) -> None:
    """One line on *log* per mismatch of *mismatches*, in order, for
    *archive*, at *level* (``WARNING``, or ``ERROR`` for ``verify-wheel
    --fail-on-mismatch``; ``wheel-sbom-conflict``).

    Raises:
        pitloom.core.internal_error.InternalError: *level* is neither.
    """
    if level not in (logging.WARNING, logging.ERROR):
        raise InternalError(f"no wheel-sbom-conflict line at level {level}")
    line = MISMATCH_LINE if level == logging.WARNING else MISMATCH_ERROR_LINE
    for mismatch in mismatches:
        wheel_value, sbom_value = compared_pair(
            mismatch.wheel_value, mismatch.sbom_value
        )
        emit(
            log,
            WHEEL_SBOM_CONFLICT,
            level,
            line=line,
            archive=archive,
            identity_part=mismatch.part,
            sbom_value=sbom_value,
            wheel_value=wheel_value,
        )


def identity_mismatch_error(
    log: logging.Logger, archive: Archive, mismatches: Sequence[IdentityMismatch]
) -> CodedValueError:
    """The error that refuses an embed of an SBOM that is not of the wheel
    *archive*: each mismatch of *mismatches* but the last said as an
    ``ERROR`` on *log* first, the last as the error's text, so every part
    that differs is said once (``wheel-sbom-conflict``).

    Raises:
        pitloom.core.internal_error.InternalError: *mismatches* is empty.
    """
    if not mismatches:
        raise InternalError("no mismatch to refuse an embed for")
    *first, last = mismatches
    say_identity_mismatches(log, archive, first, level=logging.ERROR)
    wheel_value, sbom_value = compared_pair(last.wheel_value, last.sbom_value)
    return CodedValueError(
        WHEEL_SBOM_CONFLICT,
        line=MISMATCH_ERROR_LINE,
        archive=archive,
        identity_part=last.part,
        sbom_value=sbom_value,
        wheel_value=wheel_value,
    )


def wheel_sbom_missing(
    archive: Archive, sbom_filename: str | None = None
) -> CodedValueError:
    """The error of a wheel *archive* with no SBOM under its
    ``.dist-info/sboms/``, or none named *sbom_filename*
    (``wheel-sbom-missing``)."""
    if sbom_filename is None:
        return CodedValueError(WHEEL_SBOM_MISSING, line=NO_SBOM_LINE, archive=archive)
    return CodedValueError(
        WHEEL_SBOM_MISSING,
        line=NO_NAMED_SBOM_LINE,
        archive=archive,
        sbom_filename=sbom_filename,
    )


def wheel_sbom_ambiguous(archive: Archive, members: Sequence[str]) -> CodedValueError:
    """The error of a wheel *archive* holding the SBOMs *members* (sorted,
    two or more) and no ``--sbom-filename`` (``wheel-sbom-ambiguous``)."""
    return CodedValueError(
        WHEEL_SBOM_AMBIGUOUS,
        line=SEVERAL_SBOMS_LINES,
        archive=archive,
        number=len(members),
        members=tuple(members),
    )


def warn_wrong_extension(
    log: logging.Logger, archive: Archive, member: str, extension: str
) -> None:
    """The one ``WARNING:`` on *log*: the SBOM *member* of *archive* does
    not end in *extension*, its format's recommended one
    (``wheel-sbom-wrong-format``)."""
    emit(
        log,
        WHEEL_SBOM_WRONG_FORMAT,
        logging.WARNING,
        line=WRONG_EXTENSION_LINE,
        archive=archive,
        member=member,
        extension=extension,
    )


def warn_format_unknown(log: logging.Logger, archive: Archive, member: str) -> None:
    """The one ``WARNING:`` on *log*: the SBOM *member*'s format is not one
    Pitloom recognises, so its extension is not checked
    (``wheel-sbom-unusable``)."""
    emit(
        log,
        WHEEL_SBOM_UNUSABLE,
        logging.WARNING,
        line=UNKNOWN_FORMAT_LINE,
        archive=archive,
        member=member,
    )


def warn_no_validator(log: logging.Logger, archive: Archive, member: str) -> None:
    """The one ``WARNING:`` on *log*: no validator is registered for the
    SBOM *member*'s format, so it is not validated (``wheel-sbom-unusable``)."""
    emit(
        log,
        WHEEL_SBOM_UNUSABLE,
        logging.WARNING,
        line=NO_VALIDATOR_LINE,
        archive=archive,
        member=member,
    )


def say_held_sbom(
    log: logging.Logger, archive: Archive, member: str, *, removed: bool
) -> None:
    """The one line on *log* for another Pitloom SBOM *member* an embed
    found in *archive*: ``INFO`` when *removed* (the earlier SBOM of this
    wheel), else ``WARNING`` (kept; ``wheel-sbom-conflict/held``)."""
    level, line = (
        (logging.INFO, REMOVED_LINE) if removed else (logging.WARNING, KEPT_LINE)
    )
    emit(
        log, WHEEL_SBOM_CONFLICT_HELD, level, line=line, archive=archive, member=member
    )


def say_entry_date_floored(log: logging.Logger, archive: Archive) -> None:
    """The one ``INFO:`` on *log*: the SBOM entry of *archive* is dated
    1980-01-01, the earliest a ZIP archive can record
    (``datetime-not-recordable``)."""
    emit(log, DATETIME_NOT_RECORDABLE, logging.INFO, line=FLOORED_LINE, archive=archive)


def sbom_name_conflict(
    file: str | os.PathLike[str], path: str | os.PathLike[str]
) -> CodedValueError:
    """The build hook's error: its SBOM file name *file* is also, ignoring
    letter case, the name of the ``sbom-files`` entry *path*
    (``sbom-name-conflict``). Both are cut as every name is
    (:func:`~pitloom.messages._field_writers.cut_name`)."""
    return CodedValueError(
        SBOM_NAME_CONFLICT,
        line=NAME_CLASH_LINE,
        file=cut_name(os.fspath(file)),
        path=cut_name(os.fspath(path)),
    )
