# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests for PEP 639 ``[project.license-files]`` bundling:
extraction (:func:`pitloom.extract._license.resolve_license_file_entries`)
through assembly (:mod:`pitloom.assemble.spdx3._document_files`), exercised
against the vendored real-world sdist fixtures under
``tests/fixtures/real-world-projects/setuptools/`` that actually declare
this field.

See also:
- :mod:`tests.core.models_wheel.test_models_wheel_real_world` -- the sibling
  regression test confirming no backend's static file-discovery walk
  reproduces a real wheel's ``.dist-info/licenses/*`` entries on its own,
  which is exactly the gap this feature fills at assembly time.
- ``tests/fixtures/real-world-projects/README.md`` for fixture provenance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble._generators import generate_project_sbom
from tests.fixtures.real_world import REAL_WORLD_ROOT, extract_sdist, sdist_available

CACHETOOLS_DIR = REAL_WORLD_ROOT / "setuptools" / "cachetools-7.1.8"
MARKUPSAFE_DIR = REAL_WORLD_ROOT / "setuptools" / "markupsafe-3.0.3"
REQUESTS_DIR = REAL_WORLD_ROOT / "setuptools" / "requests-2.34.2"


@pytest.mark.parametrize(
    ("fixture_dir", "expected_distribution_path"),
    [
        (CACHETOOLS_DIR, "cachetools-7.1.8.dist-info/licenses/LICENSE"),
        (MARKUPSAFE_DIR, "markupsafe-3.0.3.dist-info/licenses/LICENSE.txt"),
    ],
    ids=["cachetools", "markupsafe"],
)
def test_generated_sbom_bundles_declared_license_file(
    fixture_dir: Path, expected_distribution_path: str, tmp_path: Path
) -> None:
    """A project declaring PEP 639 ``[project.license-files]`` gets a
    ``software_File`` element at the real wheel's ``.dist-info/licenses/...``
    path, with a ``hasDeclaredLicense`` relationship pointing at the *same*
    ``SimpleLicensingText`` element the package-level license relationship
    uses (deduped, not a second license element)."""
    if not sdist_available(fixture_dir):
        pytest.skip(f"{fixture_dir.name}: vendored sdist not present")

    project_root = extract_sdist(fixture_dir, tmp_path)
    sbom_json = generate_project_sbom(project_root, offline=True)
    graph = json.loads(sbom_json)["@graph"]

    license_file = next(
        (
            n
            for n in graph
            if n.get("type") == "software_File"
            and n.get("name") == expected_distribution_path
        ),
        None,
    )
    assert license_file is not None, (
        f"no software_File element named {expected_distribution_path!r}"
    )

    sbom = next(n for n in graph if n.get("type") == "software_Sbom")
    main_package_id = sbom["rootElement"][0]
    package_declared_license_rel = next(
        n
        for n in graph
        if n.get("type") == "Relationship"
        and n.get("relationshipType") == "hasDeclaredLicense"
        and n.get("from") == main_package_id
    )
    file_declared_license_rel = next(
        (
            n
            for n in graph
            if n.get("type") == "Relationship"
            and n.get("relationshipType") == "hasDeclaredLicense"
            and n.get("from") == license_file["spdxId"]
        ),
        None,
    )
    assert file_declared_license_rel is not None
    assert file_declared_license_rel["to"] == package_declared_license_rel["to"]


def test_generated_sbom_skips_legacy_setuptools_license_files(
    tmp_path: Path,
) -> None:
    """A project using the legacy, pre-PEP-639 ``[tool.setuptools]
    license-files`` key (not the standard ``[project.license-files]``) is
    out of scope for this feature -- ``pyproject_metadata.StandardMetadata``
    only resolves the standard ``[project]`` table, so no
    ``.dist-info/licenses/...`` file element is synthesized for it, even
    though its real published wheel does bundle one (see
    ``requests-2.34.2/expected.json``'s ``wheel_files``). Documents the
    boundary rather than treating it as a bug."""
    if not sdist_available(REQUESTS_DIR):
        pytest.skip("requests-2.34.2: vendored sdist not present")

    project_root = extract_sdist(REQUESTS_DIR, tmp_path)
    sbom_json = generate_project_sbom(project_root, offline=True)
    graph = json.loads(sbom_json)["@graph"]

    assert not any(
        n.get("type") == "software_File" and "dist-info/licenses/" in n.get("name", "")
        for n in graph
    )
