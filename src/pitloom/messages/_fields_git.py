# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values only the Git URL lines name: the git command, the branch, tag
or commit a URL names and its kind, the subdirectories that hold a project, and
a git command line as run.

See also: :mod:`pitloom.messages._fields` (every field, these included) and
:mod:`pitloom.messages._git` (the lines).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_tables import REF_KINDS
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import free_text, plain_text

#: The Git URL lines' fields.
GIT_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "command": Field(
            r"[a-z][a-z-]*",
            plain_text,
            "<command>",
            "the git command that was stopped or failed (`clone`, `fetch`, "
            "`ls-remote`, `checkout`)",
        ),
        "command_line": Field(
            r".+",
            free_text,
            "<command-line>",
            "a git command line as run, the credentials of a URL in it taken "
            "out; escaped when it holds a control character",
            free=True,
        ),
        "folders": Field(
            r".+",
            free_text,
            "<directories>",
            "the subdirectories that hold a Python project, comma-separated, "
            "`and N more` after the last one shown; a name in quotes, "
            "escaped, when it holds a control character",
            free=True,
        ),
        "ref": Field(
            r".+",
            free_text,
            "<ref>",
            "a branch, tag or commit as the URL names it; escaped when it "
            "holds a control character",
            free=True,
        ),
        "ref_kind": Field(
            "|".join(re.escape(kind) for kind in REF_KINDS),
            plain_text,
            "<ref-kind>",
            "what the URL names: " + ", ".join(f"`{kind}`" for kind in REF_KINDS),
        ),
    }
)
