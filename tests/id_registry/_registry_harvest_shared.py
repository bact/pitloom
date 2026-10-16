# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers shared by test_registry_harvest.py and test_registry_harvest_content_gate.py.

See also: test_registry_harvest.py, test_registry_harvest_content_gate.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from spdx_python_model.bindings import v3_0_1 as spdx3

_NS = "https://spdx.org/spdxdocs/proj-1"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)
_SHA_A = "a" * 64
_SHA_B = "b" * 64
_E = TypeVar("_E", bound=spdx3.Element)


def _hash(value: str) -> list[spdx3.Hash]:
    return [spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=value)]


def _element(cls: type[_E], name: str, spdx_id: str, sha256: str | None = None) -> _E:
    obj = cls(spdxId=spdx_id, name=name, creationInfo=_CI)
    if sha256 is not None:
        obj.verifiedUsing = _hash(sha256)
    return obj


def _file(name: str, spdx_id: str, sha256: str | None = None) -> spdx3.software_File:
    return _element(spdx3.software_File, name, spdx_id, sha256)


def _object_set(*objects: Any) -> spdx3.SHACLObjectSet:
    object_set = spdx3.SHACLObjectSet()
    for obj in objects:
        object_set.add(obj)
    return object_set


def _compact(cls: Any) -> str:
    return str(cls(spdxId="urn:x", name="x", creationInfo=_CI).get_compact_type())
