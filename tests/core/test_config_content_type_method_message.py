# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The refusal of a content-type method a library caller gives: its whole
text, the valid methods and the value as given.

See also:
- :mod:`tests.core.test_config_cascade` for the refusal itself, by prefix.
"""

from __future__ import annotations

import pytest

from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import ConfigOverrides, apply_overrides
from pitloom.messages import code_of

_VALID = "one of auto, extension, magika"


@pytest.mark.parametrize("value", ["Magika", " auto", "bogus"])
@pytest.mark.parametrize("source", ["override", "config"])
def test_the_refusal_names_the_methods_and_the_value_given(
    source: str, value: str
) -> None:
    """The value as written, not a label, follows the valid methods."""
    if source == "override":
        base, overrides = PitloomConfig(), ConfigOverrides(content_type_method=value)
    else:
        base, overrides = PitloomConfig(content_type_method=value), ConfigOverrides()
    with pytest.raises(ValueError) as caught:
        apply_overrides(base, overrides)
    assert str(caught.value) == (
        f"content_type_method: must be {_VALID}, got a string '{value}'"
    )
    assert code_of(caught.value) == "option-invalid"
