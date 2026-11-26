# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for an input over a cap (:func:`warn_over_cap`),
the one for a model's metadata over its annotation budget
(:func:`warn_metadata_budget`), and reading a cap back off a record
(:func:`over_cap_of`).

See also: :mod:`pitloom.messages._over_cap` (the ``over-cap`` entry and
:class:`~pitloom.messages.files.Cap`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.core.internal_error import InternalError
from pitloom.messages._emit import emit
from pitloom.messages._over_cap import (
    BUDGET_NO_FIT_LINE,
    BUDGET_NO_KEY_LINE,
    FILE_BUDGET_NO_FIT_LINE,
    FILE_BUDGET_NO_KEY_LINE,
    KEY_LINE,
    MODEL_LINE,
    OVER_CAP,
    PACKAGE_KEY_LINE,
    Cap,
)
from pitloom.messages._types import Line

#: The LogRecord attribute holding the (cap, outcome) of an over-cap warning.
_OVER_CAP_ATTR = "pitloom_over_cap"


def _cap_line(
    cap: Cap, where: str, package: str | None
) -> tuple[Line, dict[str, object]]:
    """The line naming the input *where* over *cap*, and its subject's
    values: after the model's format, after *package* and the key, or after
    the key.

    Raises:
        pitloom.core.internal_error.InternalError: A model's cap names a
            package.
    """
    if cap.model_format is not None:
        if package is not None:
            raise InternalError("a model's cap names no package")
        return MODEL_LINE, {"format": cap.model_format, "file": where}
    if package is not None:
        return PACKAGE_KEY_LINE, {"package": package, "key": cap.subject, "name": where}
    return KEY_LINE, {"key": cap.subject, "name": where}


# One value per part of the line, then how often it is said.
# pylint: disable-next=too-many-arguments
def warn_over_cap(
    log: logging.Logger,
    cap: Cap,
    where: str,
    outcome: str = "skipped",
    *,
    once: bool = False,
    key: str | None = None,
    package: str | None = None,
) -> None:
    """The one ``WARNING:`` for an input over *cap*, ``[over-cap]``:
    *where* names the input (escaped), after its key, after *package* and
    its key (a dependency's input; never a model's), or after the model's
    format (:attr:`Cap.model_format`); *outcome* says what was read and
    what was not. *once*: once per cap and input in this process (a repeat
    is ``DEBUG``), the input known by *key* (default *package* and
    *where*) when two spellings name one input. The record carries *cap*
    and *outcome* for :func:`over_cap_of`.

    Raises:
        pitloom.core.internal_error.InternalError: *package* is given for a
            model's cap.
    """
    line, values = _cap_line(cap, where, package)
    values.update(cap.reason_values(), outcome=outcome)
    if key is None:
        key = where if package is None else f"{package}\n{where}"
    seen = f"over-cap:{cap.purpose}:{key}" if once else None
    emit(
        log,
        OVER_CAP,
        logging.WARNING,
        line=line,
        once=seen,
        extra={_OVER_CAP_ATTR: (cap, outcome)},
        frame=None,
        frame_values=None,
        **values,
    )


def warn_metadata_budget(
    log: logging.Logger, cap: Cap, where: str, keys: int | None
) -> None:
    """The one ``WARNING:`` (``[over-cap]``) that the metadata of the model
    *where* does not fit its annotation budget *cap*: even with no key, so
    the annotation is left out (*keys* ``None``), or only with all its
    *keys* left out. Named after the model's format, or by its file alone
    when the cap names none (:meth:`Cap.of_model`).

    Raises:
        pitloom.core.internal_error.InternalError: *keys* is not a count of
            one or more, or *cap* does not count bytes.
    """
    if keys is not None and (isinstance(keys, bool) or keys < 1):
        raise InternalError(f"not a count of metadata keys left out: {keys!r}")
    if cap.unit != "byte":
        raise InternalError(f"a metadata budget counts bytes, not {cap.unit!r}")
    # Each value is a field's, written by it: emit takes them as keywords.
    values: dict[str, Any] = {
        "file": where,
        "limit": cap.limit,
        "purpose": cap.purpose,
    }
    if cap.model_format is not None:
        values["format"] = cap.model_format
        line = BUDGET_NO_FIT_LINE if keys is None else BUDGET_NO_KEY_LINE
    else:
        line = FILE_BUDGET_NO_FIT_LINE if keys is None else FILE_BUDGET_NO_KEY_LINE
    if keys is not None:
        values["number"] = keys
    emit(log, OVER_CAP, logging.WARNING, line=line, **values)


def warn_archive_member_over_cap(
    log: logging.Logger, cap: Cap, archive: str | Path, member: str
) -> None:
    """:func:`warn_over_cap` for one *member* of *archive*, ``once``: named
    ``<archive file name>:<member>``, never the archive's directory (a
    built or temporary archive sits in one of this machine's), the warning
    kept once per path and member, so two archives of one name are each
    said."""
    warn_over_cap(
        log,
        cap,
        f"{Path(archive).name}:{member}",
        once=True,
        key=f"{archive}:{member}",
    )


def over_cap_of(record: logging.LogRecord) -> tuple[Cap, str] | None:
    """The cap and outcome of a record :func:`warn_over_cap` logged, so a
    caller relaying it can name the input in its own words; else ``None``."""
    found: tuple[Cap, str] | None = getattr(record, _OVER_CAP_ATTR, None)
    return found
