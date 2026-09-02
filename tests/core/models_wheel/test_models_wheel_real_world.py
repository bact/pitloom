# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests: every backend's ``discover()`` against the vendored
real-world fixtures (``tests/fixtures/real-world-projects/``), diffed
against each fixture's real published wheel's file list.

Persists what earlier real-world-validation rounds
(``working-docs/implementation/backend-file-discovery-validation.md``)
only ever checked once, ad hoc, then discarded -- these fixtures stay in
the repo so every future change to any backend's ``discover()`` gets
checked against real packages on every test run, offline (the sdist
archives are vendored; extraction is local, no network access).

See also: tests/fixtures/real_world.py (the shared extraction/manifest
helper this file uses); tests/core/models_wheel/test_models_wheel_flit.py,
test_models_wheel_pdm.py, test_models_wheel_poetry.py,
test_models_wheel_setuptools.py for each backend's synthetic-fixture
unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core._models_wheel import _discover_included_files
from tests.fixtures.real_world import (
    expected_distribution_paths,
    extract_sdist,
    iter_real_world_fixtures,
    load_expected,
    sdist_available,
)

FIXTURES = iter_real_world_fixtures()
FIXTURE_IDS = [f"{backend}-{project_dir.name}" for backend, project_dir in FIXTURES]


@pytest.mark.parametrize(("backend", "project_dir"), FIXTURES, ids=FIXTURE_IDS)
def test_discover_matches_real_wheel(
    backend: str, project_dir: Path, tmp_path: Path
) -> None:
    """A backend-aware ``discover()`` run against a real, vendored sdist
    reproduces the real published wheel's file list, modulo
    ``.dist-info/*`` (never included by any discoverer) and each
    fixture's documented ``known_gaps`` (compiled artifacts,
    VCS-generated files -- legitimately outside static discovery's
    reach).

    Skips (not errors) when the vendored sdist archive itself isn't
    present -- ``tests/fixtures/real-world-projects/`` is excluded from
    Pitloom's own published sdist, so this test must degrade gracefully
    when run from a tree that doesn't have it (e.g. a downstream
    packager's rebuild-from-sdist QA pass), rather than failing on a
    missing file."""
    if not sdist_available(project_dir):
        pytest.skip(
            f"{project_dir.name}: vendored sdist not present (excluded from "
            "Pitloom's own sdist -- run from a full git checkout to "
            "exercise this test)"
        )

    manifest = load_expected(project_dir)
    expected = expected_distribution_paths(manifest)
    if expected is None:
        pytest.skip(f"{project_dir.name}: {manifest.get('known_gaps_note')}")

    extracted_root = extract_sdist(project_dir, tmp_path)

    included = _discover_included_files(extracted_root, assume_backend=backend)
    discovered = {f.distribution_path for f in included}

    missing = expected - discovered
    extra = discovered - expected
    assert not missing, f"in real wheel but not discovered: {sorted(missing)}"
    assert not extra, f"discovered but not in real wheel: {sorted(extra)}"
