# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers for tests that compare JSON text byte for byte."""

from __future__ import annotations


def without_token_whitespace(text: str) -> str:
    """*text* without the spaces and line breaks outside JSON strings.

    For indented RFC 8785 text this is the compact canonical text again.
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in " \n":
            continue
        out.append(char)
    return "".join(out)
