# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The placeholder licence values a model card or file uses.

See also: tests/extract/test_license_classify.py.
"""

from __future__ import annotations

import pytest

from pitloom.extract._license_classify import is_vague_license_value


@pytest.mark.parametrize(
    ("value", "vague"),
    [
        ("other", True),
        (" Other\n", True),
        ("CUSTOM", True),
        ("proprietary", True),
        ("unknown", True),
        ("unlicensed", True),
        ("MIT", False),
        ("other-permissive", False),
        ("", False),
        (None, False),
    ],
)
def test_a_placeholder_is_vague_in_any_case(value: str | None, vague: bool) -> None:
    assert is_vague_license_value(value) is vague
