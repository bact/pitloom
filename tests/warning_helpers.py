# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Count ``WARNING: Options: ...`` lines naming one CLI option.

A no-effect warning names an option by its spelling in
:data:`pitloom.core.inert_options.PARAM_TO_FLAG` -- both halves of a
``BooleanOptionalAction`` (``--pretty/--no-pretty``) or a glob for a
group (``--creator-*/--creation-*``). :func:`names_option` decides whether
one such spelling covers one option string as typed, so a test can count
warnings per option without restating the table.

See also: :mod:`tests.cli.test_cli_option_reach` and
:mod:`tests.cli.test_cli_no_implicit_config`, the two users.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from collections.abc import Iterable

import pytest

_OPTIONS_WARNING = re.compile(r"Options: .*?: (-\S+) has no effect ")
# ``FILE=<path>: `` -- the path may hold a Windows drive colon (``C:\x``), so
# the terminator is a colon followed by a space.
_FILE_FIELD = re.compile(r"FILE=(\S+): ")


def names_option(spelling: str, option: str) -> bool:
    """Whether the warning *spelling* (e.g. ``--pretty/--no-pretty``) names
    *option* as typed. A ``--no-`` option matches a glob for its positive
    form, so ``--no-creation-tool`` is covered by ``--creation-*``."""
    positive = f"--{option[5:]}" if option.startswith("--no-") else option
    return any(
        fnmatch.fnmatchcase(option, part) or fnmatch.fnmatchcase(positive, part)
        for part in spelling.split("/")
    )


def option_warning_spellings(messages: Iterable[str]) -> list[str]:
    """The flag spelling of every ``Options:`` no-effect message."""
    return [m.group(1) for m in map(_OPTIONS_WARNING.search, messages) if m]


def count_naming(messages: Iterable[str], option: str) -> int:
    """How many ``Options:`` no-effect messages name *option*."""
    return sum(names_option(s, option) for s in option_warning_spellings(messages))


def file_values(messages: Iterable[str]) -> list[str]:
    """The ``FILE=`` value of every message that carries one."""
    return [m.group(1) for m in map(_FILE_FIELD.search, messages) if m]


def logged_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Every ``WARNING``-level message captured so far."""
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def stderr_warnings(err: str) -> list[str]:
    """Every ``WARNING:`` line of captured stderr."""
    return [line for line in err.splitlines() if line.startswith("WARNING: ")]


def error_lines(err: str) -> list[str]:
    """Every ``ERROR:`` line of captured stderr."""
    return [line for line in err.splitlines() if line.startswith("ERROR: ")]
