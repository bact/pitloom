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
        ({"version": 1.1}, "version", None),
        ({"description": ["a", "b"]}, "description", None),
        ({"creator": 7}, "creator", None),
        ({"url": 5}, "download_url", None),
        ({"keywords": ["a", {"x": 1}]}, "keywords", ["a"]),
        ({_RAI_PII: {"x": 1}}, _PII, None),
        ({_RAI_PII: 1.0}, _PII, None),
        (
            {"recordSet": [{"field": [{"dataType": [5, "sc:Text"]}]}]},
            "dataset_types",
            ["text"],
        ),
    ],
    ids=[
        "float-version",
        "several-descriptions",
        "number-creator",
        "number-url",
        "node-keyword",
        "node-sensitivity",
        "float-sensitivity",
        "number-data-type",
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
        ({"description": {"@value": "d", "@language": "en"}}, "description", "d"),
        ({"description": [{"@value": "d"}]}, "description", "d"),
        ({"creator": {"name": "  "}}, "creator", None),
        ({"version": 2}, "version", "2"),
        (
            {"recordSet": [{"field": [{"dataType": "sc:ImageObject"}]},
                           {"field": [{"dataType": "sc:Text"}]}]},
            "dataset_types",
            ["image", "text"],
        ),
        ({_RAI_PII: False}, _PII, "no"),
    ],
    ids=["literal", "literal-list", "blank-creator",
         "int-version", "types-in-order", "bool-sensitivity"],
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


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b'{"name": "ds", "version": ' + b"1" * 5000 + b"}", "is not valid JSON"),
        (b"[" * 100000, "is larger than the 64-level Croissant-nesting cap"),
    ],
    ids=["huge-int", "too-deep"],
)
def test_read_croissant_unreadable_json_names_the_file(
    tmp_path: Path, body: bytes, reason: str
) -> None:
    path = tmp_path / "ds.json"
    path.write_bytes(body)
    with pytest.raises(ValueError, match=f"^Croissant source .*ds.json.* {reason}"):
        read_croissant(path)


def test_read_croissant_a_missing_file_is_named_as_croissant(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="^Cannot read Croissant source "):
        read_croissant(tmp_path / "absent.json")
