# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Read the newest entries of ``CHANGELOG.md`` in every release state.

Right after a release is cut, ``## [Unreleased]`` is empty or gone; a test
that reads "the unreleased section" then reads the release just cut.

See also: :mod:`tests.test_changelog`, :mod:`tests.test_licenseid_floor_docs`.
"""

from __future__ import annotations

import re

#: One ``- `` entry, its wrapped lines included.
BULLET = re.compile(r"^- .*?(?=^- |^#|\Z)", re.M | re.S)


def newest_bullets(text: str) -> list[str]:
    """Entries of ``[Unreleased]``, else (right after a release is cut, with
    the heading empty or removed) of the newest released section."""
    _, found_heading, after = text.partition("## [Unreleased]")
    sections = (after if found_heading else text).split("\n## [")
    if not found_heading:
        sections = sections[1:]  # what precedes the first version heading
    return next((found for body in sections[:2] if (found := BULLET.findall(body))), [])
