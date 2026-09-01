# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for src/pitloom/_sbom_format.py."""

from __future__ import annotations

from pitloom._sbom_format import (
    _RECOMMENDED_EXTENSIONS,
    _VALIDATED_FORMATS,
    _detect_sbom_format,
)


def test_validated_formats_is_subset_of_recommended_extensions() -> None:
    """Every format with a registered validator must also have a
    recommended-extension entry -- a validator for a format Pitloom can't
    even name a canonical extension for would be a contradiction.

    Deliberately NOT the reverse: `_RECOMMENDED_EXTENSIONS` is allowed to
    know about a format `_VALIDATED_FORMATS` doesn't support yet (see the
    reference table in _sbom_format.py) -- that's the whole reason the two
    are kept as independent literals instead of one derived from the
    other.

    The subset check alone is vacuous -- true even for an emptied
    _VALIDATED_FORMATS -- so it's paired with a non-empty, specific
    membership check that would fail if the set were ever accidentally
    cleared or derived down to nothing.
    """
    assert _VALIDATED_FORMATS <= _RECOMMENDED_EXTENSIONS.keys()
    assert "spdx3-jsonld" in _VALIDATED_FORMATS


def test_detect_sbom_format_unrecognized_returns_none() -> None:
    assert _detect_sbom_format(b"not json at all") is None
    assert _detect_sbom_format(b'{"no_context_or_graph": true}') is None


def test_detect_sbom_format_recognizes_spdx3_jsonld() -> None:
    assert _detect_sbom_format(b'{"@context": "x", "@graph": []}') == "spdx3-jsonld"
