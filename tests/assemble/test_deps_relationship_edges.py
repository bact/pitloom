# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the defensive ``if <relationship>:`` guards in
``pitloom.assemble.spdx3.deps.add_dependencies`` and
``add_phantom_dependencies``.

See also: test_deps_enrichment_pypi_fallback.py,
test_deps_enrichment_originator_license.py, test_deps_enrichment_prefetch.py,
test_deps_enrichment_names_versions.py -- this module's siblings.

``build_relationship`` (``pitloom.core.models``) returns ``None`` when its
``from_id`` is ``None`` -- a defensive guard for a caller that couldn't
resolve an endpoint's id. Every relationship built here derives its
``from_id`` from a real, always-populated ``spdxId``, except the top-level
``main_package_spdx_id`` parameter, which a caller *could* pass as ``None``.
These tests exercise that guard directly (via a ``None`` id) and, for the
one relationship whose endpoint can never itself be ``None`` in practice
(the phantom-dependency file containment edge), via a targeted monkeypatch
of ``build_relationship`` in the calling module's namespace.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps as deps_module
from pitloom.assemble.spdx3.deps import add_dependencies, add_phantom_dependencies
from pitloom.core.models import (
    _clear_doc_counters,
    build_relationship,
    compute_doc_uuid,
)
from pitloom.core.project import PhantomDependency
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _make_ci


def test_add_dependencies_none_main_package_id_skips_relationship() -> None:
    """A ``None`` ``main_package_spdx_id`` makes ``build_relationship``
    return ``None`` for the ``dependsOn`` edge; ``add_dependencies`` must
    skip adding it (rather than raise) and keep processing the dependency
    package itself."""
    doc_uuid = compute_doc_uuid("norelid", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    add_dependencies(
        ["somepkg==1.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        None,  # type: ignore[arg-type]
        ci,
        "norelid",
        doc_uuid,
        exporter,
        offline=True,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    assert any(p.name == "somepkg" for p in packages)
    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    assert not any(
        r.relationshipType == spdx3.RelationshipType.dependsOn for r in relationships
    )


def test_add_phantom_dependencies_none_main_package_id_skips_depends_on() -> None:
    """Same guard as above, for ``add_phantom_dependencies``' ``dependsOn``
    edge. Also uses a phantom dependency with no ``digest_sha256`` to
    exercise the "no hash to assert" branch in the same pass."""
    doc_uuid = compute_doc_uuid("phantomnorelid", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    phantom = PhantomDependency(name="libfoo", file_path="pkg/libfoo.so")

    add_phantom_dependencies(
        [phantom],
        None,  # type: ignore[arg-type]
        {},
        ci,
        "phantomnorelid",
        doc_uuid,
        exporter,
    )

    packages = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    dep = next(p for p in packages if p.name == "libfoo")
    assert not dep.verifiedUsing
    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    assert not any(
        r.relationshipType == spdx3.RelationshipType.dependsOn for r in relationships
    )


def test_add_phantom_dependencies_skips_falsy_file_containment_relationship(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the file-containment ``Relationship`` build itself returns a
    falsy value (defensive guard, mirrors the ``dependsOn`` guard above),
    ``add_phantom_dependencies`` must skip adding it without raising --
    exercised by patching ``build_relationship`` in the calling module
    (``pitloom.assemble.spdx3.deps``) to return ``None`` only for the
    ``contains`` relationship type, delegating to the real implementation
    otherwise so the ``dependsOn`` edge still builds normally."""

    def _fake_build_relationship(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("rel_type") == spdx3.RelationshipType.contains:
            return None
        return build_relationship(*args, **kwargs)

    monkeypatch.setattr(deps_module, "build_relationship", _fake_build_relationship)

    doc_uuid = compute_doc_uuid("phantomfilerel", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    main_pkg = spdx3.software_Package(
        spdxId="http://spdx.org/spdxdocs/main-pkg",
        name="phantomfilerel",
        creationInfo=ci,
    )
    exporter.add_package(main_pkg)
    phantom = PhantomDependency(
        name="libfoo", file_path="pkg/libfoo.so", digest_sha256="a" * 64
    )

    add_phantom_dependencies(
        [phantom],
        "http://spdx.org/spdxdocs/main-pkg",
        {"pkg/libfoo.so": "http://spdx.org/spdxdocs/file-1"},
        ci,
        "phantomfilerel",
        doc_uuid,
        exporter,
    )

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    assert any(
        r.relationshipType == spdx3.RelationshipType.dependsOn for r in relationships
    )
    assert not any(
        r.relationshipType == spdx3.RelationshipType.contains for r in relationships
    )
