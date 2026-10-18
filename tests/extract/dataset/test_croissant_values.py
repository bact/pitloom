# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the values :func:`pitloom.extract.dataset.croissant.read_croissant`
accepts and refuses, and how it names a file it cannot read.

See also: tests/extract/dataset/test_croissant.py (the fields read),
tests/extract/dataset/test_values.py (the shared checks).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pitloom.extract.dataset.croissant import read_croissant

_RAI_PII = "rai:personalSensitiveInformation"
_PII = "has_sensitive_personal_information"


def test_read_croissant_escapes_lone_surrogates_and_names_its_label(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A JSON ``\\ud800`` escape is a lone surrogate no SBOM can hold: it is
    written as ``\\uXXXX``, with one ``WARNING:``; *label* names the file
    in provenance and the warning."""
    path = tmp_path / "ds.json"
    path.write_bytes(b'{"name": "ds", "description": "d\\udc00", "license": "MIT"}')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_croissant(path, label="data/ds.json")
    assert (meta.description, meta.license) == ("d\\udc00", "MIT")
    assert meta.provenance["license"] == "Source: data/ds.json | Field: license"
    (record,) = caplog.records
    assert "lone surrogates" in record.getMessage()
    assert "data/ds.json" in record.getMessage()


@pytest.mark.parametrize(
    ("fields", "attribute", "expected"),
    [
        ({"cr:totalItems": -5}, "dataset_size", None),
        (
            {"recordSet": [{"cr:totalItems": -5}, {"cr:totalItems": 2}]},
            "dataset_size",
            2,
        ),
        ({"cr:totalItems": True}, "dataset_size", None),
        ({"cr:totalItems": 1.9}, "dataset_size", None),
        ({"version": 1.1}, "version", None),
        ({"description": ["a", "b"]}, "description", None),
        ({"creator": 7}, "creator", None),
        ({"url": 5}, "download_url", None),
        ({"keywords": ["a", {"x": 1}]}, "keywords", ["a"]),
        ({_RAI_PII: {"x": 1}}, _PII, None),
    ],
    ids=[
        "negative-size",
        "negative-record-set",
        "bool-size",
        "fractional-size",
        "float-version",
        "several-descriptions",
        "number-creator",
        "number-url",
        "node-keyword",
        "node-sensitivity",
    ],
)  # fmt: skip
def test_read_croissant_refuses_a_value_of_the_wrong_shape(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fields: dict[str, object],
    attribute: str,
    expected: object,
) -> None:
    """A value the field cannot hold is absent (or left out of a list),
    with one ``WARNING:``, and no provenance."""
    path = tmp_path / "ds.json"
    path.write_text(json.dumps({"name": "ds", **fields}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_croissant(path)
    assert getattr(meta, attribute) == expected
    assert (attribute in meta.provenance) is bool(expected)
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    ("fields", "attribute", "expected"),
    [
        ({"cr:totalItems": 3.0}, "dataset_size", 3),
        ({"cr:totalItems": "12"}, "dataset_size", 12),
        ({"description": {"@value": "d", "@language": "en"}}, "description", "d"),
        ({"description": [{"@value": "d"}]}, "description", "d"),
        ({"creator": {"name": "  "}}, "creator", None),
        ({"version": 2}, "version", "2"),
        ({_RAI_PII: False}, _PII, "no"),
    ],
    ids=["integral-float", "digits", "literal", "literal-list", "blank-creator",
         "int-version", "bool-sensitivity"],
)  # fmt: skip
def test_read_croissant_accepts_each_spelling(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fields: dict[str, object],
    attribute: str,
    expected: object,
) -> None:
    path = tmp_path / "ds.json"
    path.write_text(json.dumps({"name": "ds", **fields}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_croissant(path)
    assert getattr(meta, attribute) == expected
    assert not caplog.records


def test_read_croissant_an_infinite_size_is_absent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``1e400`` reads as an infinity: no size, one ``WARNING:``, and no
    ``OverflowError`` out of a reader whose contract is ``ValueError``."""
    path = tmp_path / "ds.json"
    path.write_bytes(b'{"name": "ds", "cr:totalItems": 1e400}')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert read_croissant(path).dataset_size is None
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    "body",
    [b'{"name": "ds", "version": ' + b"1" * 5000 + b"}", b"[" * 100000],
    ids=["huge-int", "too-deep"],
)
def test_read_croissant_unparsable_json_names_the_file(
    tmp_path: Path, body: bytes
) -> None:
    path = tmp_path / "ds.json"
    path.write_bytes(body)
    with pytest.raises(ValueError, match="Croissant source .* is not valid JSON"):
        read_croissant(path)


def test_read_croissant_a_missing_file_is_named_as_croissant(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="^Cannot read Croissant source "):
        read_croissant(tmp_path / "absent.json")
