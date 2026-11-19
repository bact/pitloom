# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying a licence value LicenseID does not read as an expression
(:func:`warn_license_refused`) or reads one in (:func:`say_license_resolved`),
and LicenseID's database missing or unusable (:func:`say_license_db_missing`,
:func:`warn_license_db_unusable`).

Each is said once per *once* key and process
(:func:`~pitloom.logging_config.log_once`): the caller keeps its own keys,
so a value said through two of its helpers is said once. No helper adds a
prefix.

See also: :mod:`pitloom.messages._license_expression` and
:mod:`pitloom.messages._license_db` (the entries).
"""

from __future__ import annotations

import logging
import os

from pitloom.logging_config import log_once
from pitloom.messages._emit import emit
from pitloom.messages._license_db import LICENSE_DB_MISSING, LICENSE_DB_UNUSABLE
from pitloom.messages._license_expression import (
    LICENSE_EXPRESSION_INVALID,
    LICENSE_EXPRESSION_MALFORMED,
    LICENSE_EXPRESSION_RESOLVED,
)


def warn_license_refused(
    log: logging.Logger, *, malformed: bool, once: str, **values: object
) -> None:
    """The one ``WARNING:`` on *log* for a licence value (*values*:
    ``license``, ``license_reason``, and ``field`` when it was read from
    one) recorded as licence text: ``license-expression-malformed`` when
    LicenseID cannot parse it (*malformed*: its category ``malformed``), else
    ``license-expression-invalid``."""
    message = LICENSE_EXPRESSION_MALFORMED if malformed else LICENSE_EXPRESSION_INVALID
    # line and extra bound by name: no value can take their place.
    emit(log, message, logging.WARNING, line=None, once=once, extra=None, **values)


def say_license_resolved(
    log: logging.Logger, *, decided: bool, once: str, **values: object
) -> None:
    """The one line on *log* for a licence value LicenseID reads an
    expression in (*values*: ``license``, ``expression``, ``steps``, and
    ``field`` when it was read from one): ``INFO:``,
    ``license-expression-invalid/resolved``, when the reading *decided*
    something beyond form; else the same text at ``DEBUG``, with no code."""
    if decided:
        emit(
            log,
            LICENSE_EXPRESSION_RESOLVED,
            logging.INFO,
            line=None,
            once=once,
            extra=None,
            **values,
        )
        return
    line = LICENSE_EXPRESSION_RESOLVED.line_for("INFO", values)
    log_once(log, logging.DEBUG, once, "%s", line.render(values))


def say_license_db_missing(
    log: logging.Logger,
    *,
    declared: bool,
    once: str,
    path: str | os.PathLike[str],
) -> None:
    """The one line on *log* that LicenseID's database is not built at
    *path*, ``license-db-missing``: ``INFO:`` when a licence is *declared*
    (only the licence-file second opinion is lost), else ``WARNING:``."""
    level = logging.INFO if declared else logging.WARNING
    emit(log, LICENSE_DB_MISSING, level, once=once, path=path)


def warn_license_db_unusable(
    log: logging.Logger, *, once: str, failure: BaseException
) -> None:
    """The one ``WARNING:`` on *log* that LicenseID's database cannot be
    used, *failure* its exception (LicenseID's words),
    ``license-db-unusable``."""
    emit(log, LICENSE_DB_UNUSABLE, logging.WARNING, once=once, failure=failure)
