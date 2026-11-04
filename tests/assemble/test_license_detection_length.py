# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A text shorter than a licence body is a label, not detected.

See also: test_license_detection.py (detection, mocked).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pitloom.extract import _license
from pitloom.extract._license import detect_license_from_text

#: The shortest text detection reads (``_MIN_LICENSE_TEXT_LENGTH``).
_MINIMUM = 100


# pylint: disable-next=too-few-public-methods
class _Detector:
    """Finds MIT in any text."""

    def detect(self, text: str) -> list[dict[str, object]]:
        del text
        return [{"expression": "MIT", "score": 1.0}]


@pytest.mark.parametrize(
    ("length", "expected"),
    [(_MINIMUM - 1, None), (_MINIMUM, "MIT")],
    ids=["below", "at"],
)
def test_a_text_below_the_minimum_length_is_not_detected(
    length: int, expected: str | None
) -> None:
    text = "  " + "x" * length + "\n\n"  # white space around it is not counted
    with patch.object(_license, "LicenseDetector", _Detector):
        assert detect_license_from_text(text) == expected
