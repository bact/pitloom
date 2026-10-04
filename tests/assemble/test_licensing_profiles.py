# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.assemble.spdx3._licensing_profiles`: the one rule
that puts ``simpleLicensing``/``expandedLicensing`` in ``profileConformance``,
and that every builder (project, model, deployed, fragment merge) uses it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import create_autospec

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _licensing_profiles
from pitloom.assemble.spdx3._licensing_profiles import (
    apply_licensing_profiles,
    licensing_profiles,
)
from pitloom.assemble.spdx3.document import build, build_model
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._license_graph import deployed, merged_fragment, onnx_model

_P = spdx3.ProfileIdentifierType
_NO_ASSERTION_LICENSE = (
    spdx3.expandedlicensing_IndividualLicensingInfo.NoAssertionLicense
)
_CI = spdx3.CreationInfo(
    specVersion="3.0.1",
    created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    createdBy=["https://x/1#A"],
)


def _text(value: str) -> spdx3.simplelicensing_SimpleLicensingText:
    return spdx3.simplelicensing_SimpleLicensingText(
        spdxId="https://x/1#L", creationInfo=_CI, simplelicensing_licenseText=value
    )


def _rel(
    to: str, rel_type: str = spdx3.RelationshipType.hasDeclaredLicense
) -> spdx3.Relationship:
    return spdx3.Relationship(
        spdxId="https://x/1#R",
        from_="https://x/1#P",
        to=[to],
        relationshipType=rel_type,
        creationInfo=_CI,
    )


def _annotation(subject: str) -> spdx3.Annotation:
    return spdx3.Annotation(
        spdxId="https://x/1#N",
        subject=subject,
        annotationType=spdx3.AnnotationType.other,
        statement="s",
        creationInfo=_CI,
    )


def _custom_license() -> spdx3.expandedlicensing_CustomLicense:
    return spdx3.expandedlicensing_CustomLicense(
        spdxId="https://x/1#C",
        creationInfo=_CI,
        name="c",
        simplelicensing_licenseText="text",
    )


_BOTH = [_P.simpleLicensing, _P.expandedLicensing]


@pytest.mark.parametrize(
    ("objects", "expected"),
    [
        ([], []),
        ([_rel("https://x/1#Q", spdx3.RelationshipType.dependsOn)], []),
        ([_text("MIT")], [_P.simpleLicensing]),
        ([_text("NOASSERTION")], [_P.simpleLicensing]),
        (
            [
                spdx3.simplelicensing_LicenseExpression(
                    spdxId="https://x/1#E",
                    creationInfo=_CI,
                    simplelicensing_licenseExpression="MIT",
                )
            ],
            [_P.simpleLicensing],
        ),
        # A licence stated only as an individual: no element at all.
        (
            [_rel(_NO_ASSERTION_LICENSE)],
            [_P.simpleLicensing, _P.expandedLicensing],
        ),
        (
            [
                _rel(
                    spdx3.IndividualElement.NoAssertionElement,
                    spdx3.RelationshipType.hasConcludedLicense,
                )
            ],
            [_P.simpleLicensing],
        ),
        ([_annotation(_NO_ASSERTION_LICENSE)], _BOTH),
        ([_custom_license()], _BOTH),
        (
            [_text("MIT"), _custom_license()],
            [_P.simpleLicensing, _P.expandedLicensing],
        ),
    ],
    ids=[
        "none",
        "unrelated-relationship",
        "text",
        "noassertion-text",
        "expression",
        "individual-only",
        "core-individual",
        "annotation-on-expanded-individual",
        "expanded-element",
        "both",
    ],
)
def test_licensing_profiles(
    objects: list[spdx3.SHACLObject], expected: list[str]
) -> None:
    assert licensing_profiles(objects) == expected


def _project(license_name: str | None) -> Spdx3JsonExporter:
    project = ProjectMetadata(name="p", version="1.0", license_name=license_name)
    return build(DocumentModel(project=project, creation_metadata=CreationMetadata()))


def _model(license_id: str | None) -> Spdx3JsonExporter:
    return build_model(onnx_model(license_id), CreationMetadata())


def _conformance(exporter: Spdx3JsonExporter) -> list[str]:
    doc = next(
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    )
    return list(doc.profileConformance or [])


#: One case per surface: (builder, profiles it must produce).
_SURFACES: list[tuple[str, Callable[[Path], Spdx3JsonExporter], list[str]]] = [
    # No licence stated: no licence relationship, no licensing profile.
    ("project-undeclared", lambda _: _project(None), []),
    ("project-declared", lambda _: _project("MIT"), [_P.simpleLicensing]),
    # An individual brings both profiles.
    ("project-noassertion", lambda _: _project("NOASSERTION"), _BOTH),
    ("model-noassertion", lambda _: _model("NOASSERTION"), _BOTH),
    ("model-unknown", lambda _: _model("unknown"), _BOTH),
    ("model-none-licence", lambda _: _model("NONE"), _BOTH),
    ("model-none", lambda _: _model(None), []),
    ("deployed-empty", lambda _: deployed(None), []),
    ("deployed-unlicensed", lambda _: deployed({}), []),
    ("deployed-package", lambda _: deployed({"License": "MIT"}), [_P.simpleLicensing]),
    ("merge-none", lambda p: merged_fragment(p, None), []),
    (
        "merge-noassertion-individual",
        lambda p: merged_fragment(p, "expandedlicensing_NoAssertionLicense"),
        [_P.simpleLicensing, _P.expandedLicensing],
    ),
]


@pytest.mark.parametrize(
    ("build_fn", "expected"),
    [pytest.param(b, e, id=i) for i, b, e in _SURFACES],
)
def test_licensing_profiles_by_surface(
    tmp_path: Path, build_fn: Callable[[Path], Spdx3JsonExporter], expected: list[str]
) -> None:
    got = [
        p
        for p in _conformance(build_fn(tmp_path))
        if p in (_P.simpleLicensing, _P.expandedLicensing)
    ]
    assert got == expected


@pytest.mark.parametrize("build_fn", [pytest.param(b, id=i) for i, b, _ in _SURFACES])
def test_every_surface_uses_the_shared_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build_fn: Callable[[Path], Spdx3JsonExporter],
) -> None:
    """Drift guard: with the helper's answer replaced, every builder shows
    the replacement, so none computes licensing profiles by itself."""
    monkeypatch.setattr(
        _licensing_profiles,
        "licensing_profiles",
        create_autospec(
            _licensing_profiles.licensing_profiles, return_value=[_P.security]
        ),
    )
    got = _conformance(build_fn(tmp_path))
    assert _P.security in got
    assert _P.simpleLicensing not in got
    assert _P.expandedLicensing not in got


def test_profile_order_is_fixed() -> None:
    """Known profiles come in rank order; unknown ones follow, by IRI."""
    doc = spdx3.SpdxDocument(
        spdxId="https://x/1#D",
        creationInfo=_CI,
        profileConformance=[
            _P.security,
            _P.dataset,
            _P.build,
            _P.ai,
            _P.software,
            _P.core,
        ],
    )
    apply_licensing_profiles(doc, [_text("MIT"), _custom_license()])
    assert list(doc.profileConformance) == [
        _P.core,
        _P.software,
        _P.simpleLicensing,
        _P.expandedLicensing,
        _P.ai,
        _P.dataset,
        _P.build,
        _P.security,
    ]
    assert _P.build < _P.security  # the IRI order the test relies on


def test_direct_build_and_fragment_merge_give_one_order() -> None:
    """A project built with an AI model and the same project merged with an
    ``ai_AIPackage`` fragment list their profiles identically."""
    project = ProjectMetadata(name="p", version="1.0", license_name="MIT")
    model = onnx_model(None)
    direct = _conformance(
        build(
            DocumentModel(
                project=project,
                creation_metadata=CreationMetadata(),
                ai_models=[model],
            )
        )
    )
    merged = build(DocumentModel(project=project, creation_metadata=CreationMetadata()))
    fixtures = Path(__file__).parent.parent / "fixtures" / "fragments"
    merge_fragments(
        fixtures, [FragmentConfig(path="ai-model-fragment.spdx3.json")], merged
    )
    assert direct == [_P.core, _P.software, _P.simpleLicensing, _P.ai]
    assert _conformance(merged) == direct
