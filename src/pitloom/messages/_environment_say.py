# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The errors of ``environment-unreadable``, each a
:class:`~pitloom.messages.CodedRuntimeError`: a library caller of
``generate_env_sbom`` catches the :class:`RuntimeError` it always did.

See also: :mod:`pitloom.messages._environment` (the entry).
"""

from __future__ import annotations

from pitloom.core.internal_error import InternalError
from pitloom.messages._emit import CodedRuntimeError
from pitloom.messages._environment import (
    ENVIRONMENT_UNREADABLE,
    EXITED_LINE,
    NOT_JSON_LINE,
    NOT_RUN_LINE,
    SHAPE_LINE,
    SHAPE_PROBLEMS,
)


def pipdeptree_exited(exit_code: int, last_output: str) -> CodedRuntimeError:
    """The error for ``pipdeptree`` exiting with *exit_code*, *last_output*
    its last line that is not blank
    (:data:`~pitloom.messages._environment.NO_OUTPUT` when none): masked,
    cut and escaped by the ``output`` field."""
    return CodedRuntimeError(
        ENVIRONMENT_UNREADABLE,
        line=EXITED_LINE,
        exit_code=exit_code,
        output=last_output,
    )


def pipdeptree_not_run(exc: OSError) -> CodedRuntimeError:
    """The error for ``pipdeptree`` that could not be started: what *exc*
    reports, never its text, which names the path."""
    return CodedRuntimeError(ENVIRONMENT_UNREADABLE, line=NOT_RUN_LINE, failure=exc)


def pipdeptree_not_json(exc: ValueError) -> CodedRuntimeError:
    """The error for ``pipdeptree`` output that *exc* (a
    :class:`json.JSONDecodeError` or :class:`UnicodeDecodeError`) says is
    not JSON."""
    return CodedRuntimeError(ENVIRONMENT_UNREADABLE, line=NOT_JSON_LINE, failure=exc)


def pipdeptree_shape(problem: str) -> CodedRuntimeError:
    """The error for JSON output that is not ``pipdeptree``'s flat list, for
    *problem*, one of :data:`SHAPE_PROBLEMS`.

    Raises:
        pitloom.core.internal_error.InternalError: *problem* is not one.
    """
    if problem not in SHAPE_PROBLEMS:
        raise InternalError(f"not a pipdeptree shape problem: {problem!r}")
    return CodedRuntimeError(ENVIRONMENT_UNREADABLE, line=SHAPE_LINE, why=problem)
