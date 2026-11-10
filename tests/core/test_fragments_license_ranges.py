# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment merge rejects a ``hasDeclaredLicense``/``hasConcludedLicense``
whose ``from`` is no ``software_SoftwareArtifact`` or whose ``to`` is no
``AnyLicenseInfo`` (a bare ``SimpleLicensingText`` is not one).

See also: :mod:`pitloom.assemble.spdx3._fragments_license_ranges`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests._license_graph import (
    fragment_graph,
    license_node,
    text_wrapper_node,
    write_fragment,
)

_NS = "https://spdx.org/spdxdocs/frag"
_PKG = f"{_NS}#P"
_AGENT = f"{_NS}#A"
_EXPR = f"{_NS}#Expr"
_TEXT = f"{_NS}#Text"
_WRAPPER = f"{_NS}#Wrapper"
_NO_ASSERTION = "expandedlicensing_NoAssertionLicense"


def _merge(tmp_path: Path, rel_type: str, source: str, target: str) -> None:
    elements = [
        {"type": "software_Package", "spdxId": _PKG, "name": "p"},
        license_node(_EXPR, "expression", "MIT"),
        license_node(_TEXT, "text", "Acme terms"),
        text_wrapper_node(_WRAPPER, _TEXT),
        {
            "type": "Relationship",
            "spdxId": f"{_NS}#R",
            "from": source,
            "to": [target],
            "relationshipType": rel_type,
        },
    ]
    write_fragment(tmp_path / "f.spdx3.json", fragment_graph(elements))
    ci = spdx3.CreationInfo(
        _id="_:ci",
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=["https://spdx.org/agent1"],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(
        spdx3.SpdxDocument(
            spdxId="https://spdx.org/spdxdocs/main", name="m", creationInfo=ci
        )
    )
    merge_fragments(tmp_path, [FragmentConfig(path="f.spdx3.json")], exporter)


@pytest.mark.parametrize("rel_type", ["hasDeclaredLicense", "hasConcludedLicense"])
@pytest.mark.parametrize(
    ("source", "target"),
    [(_PKG, _EXPR), (_PKG, _WRAPPER), (_PKG, _NO_ASSERTION)],
    ids=["expression", "text-through-expression", "individual"],
)
def test_a_licence_relationship_in_range_merges(
    tmp_path: Path, rel_type: str, source: str, target: str
) -> None:
    _merge(tmp_path, rel_type, source, target)


@pytest.mark.parametrize("rel_type", ["hasDeclaredLicense", "hasConcludedLicense"])
@pytest.mark.parametrize(
    ("source", "target", "end"),
    [(_PKG, _TEXT, "to"), (_AGENT, _EXPR, "from")],
    ids=["to-is-a-bare-text", "from-is-no-artifact"],
)
def test_a_licence_relationship_out_of_range_is_rejected(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    rel_type: str,
    source: str,
    target: str,
    end: str,
) -> None:
    """Only one end is wrong in each case, so each end's check is needed."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FragmentMergeError, match="wrong type") as raised:
            _merge(tmp_path, rel_type, source, target)
    assert code_of(raised.value) == "license-relationship-invalid"
    (record,) = [r for r in caplog.records if r.name.startswith("pitloom.assemble")]
    assert getattr(record, CODE_ATTR) == "license-relationship-invalid"
    # Only the wrong end is named, by the verb of its line.
    verb = {"to": "goes to", "from": "starts at"}[end]
    assert record.getMessage().startswith(f"RELATIONSHIP={_NS}#R: a licence ")
    wrong = target if end == "to" else source
    assert f"relationship {verb} {wrong}, " in record.getMessage()


def test_a_dangling_end_is_the_dangling_check_not_this_one(tmp_path: Path) -> None:
    with pytest.raises(FragmentMergeError, match="dangling"):
        _merge(tmp_path, "hasDeclaredLicense", _PKG, f"{_NS}#Nowhere")


def test_a_relationship_of_another_type_is_not_checked(tmp_path: Path) -> None:
    """``dependsOn`` a text is no licence relationship."""
    _merge(tmp_path, "dependsOn", _PKG, _TEXT)


def test_in_range_ends_are_the_documented_types() -> None:
    """Drift guard: the check's expected classes are the spec's ones."""
    assert issubclass(
        spdx3.simplelicensing_LicenseExpression, spdx3.simplelicensing_AnyLicenseInfo
    )
    assert not issubclass(
        spdx3.simplelicensing_SimpleLicensingText, spdx3.simplelicensing_AnyLicenseInfo
    )
    assert issubclass(spdx3.software_Package, spdx3.software_SoftwareArtifact)
    ends: Any = (spdx3.ai_AIPackage, spdx3.dataset_DatasetPackage, spdx3.software_File)
    assert all(issubclass(e, spdx3.software_SoftwareArtifact) for e in ends)
