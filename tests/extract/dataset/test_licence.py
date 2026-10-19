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

from pitloom.core.dataset_metadata import FurtherLicences
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
        (["other"], "Foo Licence", None, ("Foo Licence", "license, license_name")),
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
        "one-item-list-other",
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
        ({"name": "MIT"}, None, "dict", "license"),
        ("other", ["Foo", "Bar"], "list", "license_name"),
        ([42, {"name": "MIT"}], None, "int", "license"),
        ([["mit"], ["apache-2.0"]], None, "list", "license"),
    ],
    ids=[
        "number",
        "bool",
        "mapping",
        "other-name-list",
        "list-of-non-text",
        "list-of-lists",
    ],
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
        f"dataset metadata: {_SRC} field {field} is of type {type_name}, "
        "not text; skipped"
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["cc-by-sa-3.0", "gfdl"], ["cc-by-sa-3.0", "gfdl"]),
        (["MIT", " apache-2.0 ", "mit", "Apache-2.0"], ["MIT", "apache-2.0"]),
        (["unknown", "", None, "NOASSERTION", "cc-by-4.0", "other"], ["cc-by-4.0"]),
        (["other", "unknown"], []),
        ([{"@id": _LINK}, "gfdl"], [_LINK, "gfdl"]),
    ],
    ids=["two", "case-duplicates", "weak-dropped", "all-weak", "jsonld-node"],
)
def test_dataset_licence_list(
    caplog: pytest.LogCaptureFixture, value: list[object], expected: list[str]
) -> None:
    """Each text of a list of several is a licence, in order and once each
    (letter case ignored), weak items and an ``other`` (no text of its own,
    even beside a name) left out, silently; the field keeps one provenance
    entry, the list after the first is :class:`FurtherLicences`."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        found = dataset_licence(
            value, source=_SRC, name="Foo", link=_LINK, lister="dataset card"
        )
    assert not caplog.records
    if not expected:
        assert found is None
        return
    assert found is not None
    assert found.provenance == f"Source: {_SRC} | Field: license"
    assert found.text == expected[0]
    further = expected[1:]
    assert found.further == (
        FurtherLicences(tuple(further), "dataset card") if further else None
    )


def test_dataset_licence_list_non_text_kept_rest(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A list mixing texts and non-texts keeps the texts and warns once."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        found = dataset_licence(["mit", 42, {"a": 1}, "gfdl"], source=_SRC)
    assert found is not None
    assert (found.text, found.further) == ("mit", FurtherLicences(("gfdl",), "source"))
    assert [r.getMessage() for r in caplog.records] == [
        f"dataset metadata: {_SRC} field license is of type int, not text; skipped"
    ]
    assert found.further is not None
    assert found.further.comment == (
        "The source lists several licences; it does not say whether they "
        "combine as AND or OR."
    )
