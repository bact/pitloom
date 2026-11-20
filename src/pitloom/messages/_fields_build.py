# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the build and temporary-directory lines name: a build's
exit code and last output line, the process group it left running, the
signal that ended Pitloom and what was running then.

See also: :mod:`pitloom.messages._fields` (every field, these included) and
:mod:`pitloom.messages._build` (the lines).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.logging_config import one_line
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import number_text, plain_text

#: The signals that end Pitloom after a cleanup, as their names: SIGHUP is
#: POSIX only and SIGBREAK (Ctrl-Break) Windows only, so the names are
#: literals, never looked up on :mod:`signal`.
TERMINATION_SIGNALS: Final = ("SIGTERM", "SIGHUP", "SIGBREAK")

#: What may be running when a signal ends Pitloom, as the lines name it
#: (:class:`pitloom.core.build_signals.GuardedActivity`).
ACTIVITIES: Final = ("the build", "the AI model file copy", "a guarded activity")

#: The most characters of a build's output line a message shows.
OUTPUT_CHARACTERS: Final = 200


def exit_code_text(value: object) -> str:
    """An exit code, in digits; negative for a POSIX signal.

    Raises:
        ValueError: *value* is not an ``int`` (a ``bool`` is not).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"not an exit code: {value!r}")
    return str(value)


def output_text(value: object) -> str:
    """A line a build printed, third-party text: its whitespace runs one
    space, the credentials in it masked, then cut to
    :data:`OUTPUT_CHARACTERS` (``...`` after a cut), then escaped
    (:func:`~pitloom.logging_config.one_line`): masked before the cut, so a
    cut never shows the start of a credential, and before the escape, which
    would hide the word boundary a token needs.

    Raises:
        ValueError: *value* is not a ``str``.
    """
    return one_line(plain_text(value), limit=OUTPUT_CHARACTERS, ellipsis=True)


def _one_of(names: tuple[str, ...]) -> str:
    """A pattern matching exactly one of *names*."""
    return "|".join(re.escape(name) for name in names)


#: The build lines' fields.
BUILD_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "activity": Field(
            _one_of(ACTIVITIES),
            plain_text,
            "<activity>",
            "what was running when the signal came: "
            + ", ".join(f"`{name}`" for name in ACTIVITIES),
        ),
        "exit_code": Field(
            r"-?(?:0|[1-9][0-9]*)",
            exit_code_text,
            "<exit-code>",
            "the exit code of the build process: negative for a POSIX signal "
            "(`-9`), a large number for a Windows status (`3221225786`)",
        ),
        "output": Field(
            r".+",
            output_text,
            "<output>",
            "the last line the build printed that is not blank, each "
            "control character a space, a URL credential or a known token "
            f"masked, cut to {OUTPUT_CHARACTERS} characters (then `...`); "
            "escaped when it holds a "
            "character a terminal would act on; `(no output)` when it "
            "printed none",
            free=True,
        ),
        "process_group": Field(
            r"[1-9][0-9]*",
            number_text,
            "<process-group>",
            "the process group of the build (POSIX), which its leftover "
            "processes share",
        ),
        "signal": Field(
            _one_of(TERMINATION_SIGNALS),
            plain_text,
            "<signal>",
            "the signal that ended Pitloom: "
            + ", ".join(f"`{name}`" for name in TERMINATION_SIGNALS),
        ),
    }
)
