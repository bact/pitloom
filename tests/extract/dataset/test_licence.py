# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract.dataset.licence.dataset_licence`, the one
mapping from a dataset source's licence to ``DatasetMetadata.license``.

See also: tests/extract/dataset/test_card.py (the local dataset card),
tests/core/test_loom_dataset_sources.py (loom writes it).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.extract.dataset.licence import dataset_licence

_SRC = "card.md"
_LINK = "https://example.org/terms"


@pytest.mark.parametrize(
    ("value", "name", "link", "expected"),
    [
        ("Apache-2.0", None, None, ("Apache-2.0", "license")),
        ("  MIT OR Apache-2.0 ", None, None, ("MIT OR Apache-2.0", "license")),
        ("Custom research terms", None, None, ("Custom research terms", "license")),
        (_LINK, None, None, (_LINK, "license")),
        # A name or link beside a real value: the value is the claim.
        ("MIT", "Foo", _LINK, ("MIT", "license")),
        (["cc-by-4.0"], None, None, ("cc-by-4.0", "license")),
        ({"@id": _LINK}, None, None, (_LINK, "license")),
        ("other", None, _LINK, (_LINK, "license, license_link")),
        ("Other", "Foo Licence", None, ("Foo Licence", "license, license_name")),
        (
            "OTHER",
            "Foo Licence",
            _LINK,
            (f"Foo Licence ({_LINK})", "license, license_name, license_link"),
        ),
        ("other", "unknown", _LINK, (_LINK, "license, license_link")),
        (None, None, None, None),
        (None, "Foo", _LINK, None),
        ([], None, None, None),
        ("", None, None, None),
        ("   ", None, None, None),
        ("unknown", None, None, None),
        ("UNKNOWN", None, None, None),
        ("NOASSERTION", None, None, None),
        ("noassertion", None, None, None),
        ("other", None, None, None),
        ("other", " ", "", None),
        ("other", "NOASSERTION", None, None),
    ],
    ids=[
        "expression",
        "expression-stripped",
        "free-text",
        "url",
        "value-beats-name",
        "one-item-list",
        "jsonld-node",
        "other-link",
        "other-name",
        "other-name-link",
        "other-weak-name",
        "absent",
        "absent-value-with-name",
        "empty-list",
        "empty",
        "blank",
        "unknown",
        "unknown-upper",
        "noassertion",
        "noassertion-lower",
        "other-alone",
        "other-blank-name-link",
        "other-weak-name-only",
    ],
)
def test_dataset_licence(
    caplog: pytest.LogCaptureFixture,
    value: object,
    name: object,
    link: object,
    expected: tuple[str, str] | None,
) -> None:
    """A stated licence is kept as read with its provenance; a placeholder
    or nothing is no licence; ``other`` takes the name then the link. None
    of these logs anything."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        found = dataset_licence(value, source=_SRC, name=name, link=link)
    if expected is None:
        assert found is None
    else:
        assert found is not None
        assert (found.text, found.provenance) == (
            expected[0],
            f"Source: {_SRC} | Field: {expected[1]}",
        )
    assert not caplog.records


@pytest.mark.parametrize(
    ("value", "name", "type_name", "field"),
    [
        (42, None, "int", "license"),
        (True, None, "bool", "license"),
        (["mit", "apache-2.0"], None, "list", "license"),
        ({"name": "MIT"}, None, "dict", "license"),
        ("other", ["Foo", "Bar"], "list", "license_name"),
    ],
    ids=["number", "bool", "two-items", "mapping", "other-name-list"],
)
def test_dataset_licence_wrong_type_warns(
    caplog: pytest.LogCaptureFixture,
    value: object,
    name: object,
    type_name: str,
    field: str,
) -> None:
    """A field holding no text is no licence, with one ``WARNING:`` naming
    the source, the field and the shape: the source stated something that
    cannot be recorded."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert dataset_licence(value, source=_SRC, name=name) is None
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        f"dataset metadata: {_SRC} field {field} is a {type_name}, not text; skipped"
    ]
