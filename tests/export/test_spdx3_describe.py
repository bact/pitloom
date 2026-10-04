# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An element or value named in a message: by type, id and name, never as a
Python object repr, so the message is the same on every run."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_describe import describe_graph_element, describe_value

_ID = "https://x/1#Package-1"


def _package(**fields: Any) -> spdx3.software_Package:
    return spdx3.software_Package(**fields)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (lambda: _package(spdxId=_ID, name="p"), f"software_Package {_ID} 'p'"),
        (lambda: spdx3.Agent(spdxId=_ID), f"Agent {_ID}"),
        (
            lambda: spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="ab"),
            "Hash(algorithm='https://spdx.org/rdf/3.0.1/terms/Core/HashAlgorithm/"
            "sha256', hashValue='ab')",
        ),
        (lambda: _package(name="p"), "software_Package(name='p')"),
        (lambda: ["a", 1], "['a', 1]"),
        (
            lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
            "2026-01-01 00:00:00+00:00",
        ),
    ],
    ids=["element", "no-name", "no-id", "element-no-id", "list", "scalar"],
)
def test_describe_value(value: Any, expected: str) -> None:
    assert describe_value(value()) == expected


@pytest.mark.parametrize(
    ("element", "expected"),
    [
        (
            {"type": "software_File", "spdxId": _ID, "name": "a.py"},
            f"software_File {_ID} 'a.py'",
        ),
        ({"name": ["x"]}, "unknown <no spdxId>"),
    ],
)
def test_describe_graph_element(element: dict[str, Any], expected: str) -> None:
    assert describe_graph_element(element) == expected
