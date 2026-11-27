# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The families of the message reference page "Builds and temporary
directories" (``build`` in :data:`~pitloom.messages.TOPIC_TITLES`): their
entries, their lines and the helpers that say them.

See also: :mod:`pitloom.messages` (the mechanism) and
:mod:`pitloom.messages._topics` (which family is on which page).
"""

from __future__ import annotations

from pitloom.messages._build import (
    ALLOW_BUILD_NAMES,
    BUILD_CODE_UNSAFE,
    BUILD_EMPTY_WHEEL_LINE,
    BUILD_EXIT_LINE,
    BUILD_FAILED,
    BUILD_INTERPRETER_LINE,
    BUILD_PROCESSES_UNSAFE,
    BUILD_TIMED_OUT_LINES,
    BUILD_TIMED_OUT_UNCONFIRMED_LINES,
    BUILD_TIMEOUT,
    BUILD_TIMEOUT_NAMES,
    BUILD_UNUSABLE_LINE,
    BUILD_WHEEL_COUNT_LINE,
    INTERRUPTED,
    INTERRUPTED_AFTER_LINE,
    INTERRUPTED_DURING_LINE,
    INTERRUPTED_ERROR_LINE,
    NO_BUILD_ISOLATION_NAMES,
    PROCESSES_KILLED_LINE,
    PROCESSES_UNCONFIRMED_LINE,
    TEMP_DIR_LEFT_LINE,
    TEMP_DIR_UNWRITABLE,
    UNSAFE_NO_MODULE_LINES,
    UNSAFE_NO_MODULE_SHARED_LINES,
    UNSAFE_STATIC_FAILED_LINES,
    UNSAFE_STATIC_FAILED_SHARED_LINES,
)
from pitloom.messages._build_say import (
    BuildFailedError,
    build_error,
    interrupted_line,
    require_codes,
    timeout_line,
    unsafe_line,
)
from pitloom.messages._fields_build import (
    ACTIVITIES,
    OUTPUT_CHARACTERS,
    TERMINATION_SIGNALS,
)
from pitloom.messages._hook import (
    HOOK_DISABLED_LINE,
    HOOK_EDITABLE_LINE,
    HOOK_NO_EFFECT,
    HOOK_NOT_WHEEL_LINE,
    HOOK_SBOM_STAGED,
)

__all__ = [
    "ALLOW_BUILD_NAMES",
    "BUILD_TIMEOUT_NAMES",
    "NO_BUILD_ISOLATION_NAMES",
    "ACTIVITIES",
    "BUILD_CODE_UNSAFE",
    "BUILD_EMPTY_WHEEL_LINE",
    "BUILD_EXIT_LINE",
    "BUILD_FAILED",
    "BUILD_INTERPRETER_LINE",
    "BUILD_PROCESSES_UNSAFE",
    "BUILD_TIMED_OUT_LINES",
    "BUILD_TIMED_OUT_UNCONFIRMED_LINES",
    "BUILD_TIMEOUT",
    "BUILD_UNUSABLE_LINE",
    "BUILD_WHEEL_COUNT_LINE",
    "HOOK_DISABLED_LINE",
    "HOOK_EDITABLE_LINE",
    "HOOK_NOT_WHEEL_LINE",
    "HOOK_NO_EFFECT",
    "HOOK_SBOM_STAGED",
    "INTERRUPTED",
    "INTERRUPTED_AFTER_LINE",
    "INTERRUPTED_DURING_LINE",
    "INTERRUPTED_ERROR_LINE",
    "OUTPUT_CHARACTERS",
    "PROCESSES_KILLED_LINE",
    "PROCESSES_UNCONFIRMED_LINE",
    "TEMP_DIR_LEFT_LINE",
    "TEMP_DIR_UNWRITABLE",
    "TERMINATION_SIGNALS",
    "UNSAFE_NO_MODULE_LINES",
    "UNSAFE_NO_MODULE_SHARED_LINES",
    "UNSAFE_STATIC_FAILED_LINES",
    "UNSAFE_STATIC_FAILED_SHARED_LINES",
    "BuildFailedError",
    "build_error",
    "interrupted_line",
    "require_codes",
    "timeout_line",
    "unsafe_line",
]
