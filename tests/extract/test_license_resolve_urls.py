# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A licence URL and a value with a control or format character at an end,
read by the unpatched ``licenseid.resolve`` (the floor, 0.8.1):
the URL is its licence id, the character is dropped; both are decisions,
said at ``INFO:`` once and noted in the provenance.

See also: tests/extract/test_license_resolve.py (the other categories).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract import _license_resolve
from pitloom.extract._license import (
    classify_license,
    tag_deprecated_license_ids,
    tag_license_normalization,
)

_LOGGER = "pitloom.extract._license_resolve"


def _info(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == _LOGGER and r.levelno == logging.INFO
    ]


def test_a_licence_url_is_read_as_its_id(caplog: pytest.LogCaptureFixture) -> None:
    raw = "https://www.apache.org/licenses/LICENSE-2.0"
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        got = classify_license(raw)
    assert got is not None and (got.kind, got.value) == ("expression", "Apache-2.0")
    assert _info(caplog) == [f"LICENSE={raw!r}: read as Apache-2.0 (license_url)"]
    assert not _license_resolve.is_licence_id(raw)
    note = tag_license_normalization("P", raw, "Apache-2.0")
    assert f"Resolution-1: {raw} -> Apache-2.0 (license_url)" in note
    assert "Method: licenseid_resolution" in note


def test_a_url_of_a_deprecated_id_is_decided_and_noted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = "https://www.gnu.org/licenses/gpl-3.0.html"
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        got = classify_license(raw)
    assert got is not None and (got.kind, got.value) == ("expression", "GPL-3.0")
    assert _info(caplog) == [f"LICENSE={raw!r}: read as GPL-3.0 (license_url)"]
    note = tag_deprecated_license_ids(
        tag_license_normalization("P", raw, "GPL-3.0"), "GPL-3.0"
    )
    assert f"Resolution-1: {raw} -> GPL-3.0 (license_url)" in note
    assert note.endswith(
        " | Deprecated-License-Id: GPL-3.0 (GPL-3.0-only or GPL-3.0-or-later)"
    )


@pytest.mark.parametrize("raw", ["MIT​", "\x1bMIT"], ids=["zwsp", "esc"])
def test_a_control_or_format_character_at_an_end_is_dropped(
    raw: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        got = classify_license(raw)
    assert got is not None and (got.kind, got.value) == ("expression", "MIT")
    assert _info(caplog) == [f"LICENSE={raw!r}: read as MIT (trim)"]
    assert " -> MIT (trim)" in tag_license_normalization("P", raw, "MIT")
