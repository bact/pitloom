# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Real ``--allow-build`` build-and-read discovery against the vendored
``uv_build`` sdist fixtures.

Unlike ``test_models_wheel_real_world.py`` (fast, offline, exercises
every *static* ``discover()`` against a real published wheel's file
list), ``test_build_and_read_matches_real_wheel`` below actually invokes
PyPA ``build`` -- a real PEP 517 build in an isolated venv, installing
``uv_build`` from the network -- so it's marked
``@pytest.mark.pypi_network`` (opts out of ``tests/conftest.py``'s
default socket block) and is slow (creates a venv, installs
build-requires, runs the real ``uv-build`` binary).

Every fixture here was verified empirically (2026-09-15, per the
roadmap plan for this feature, then extended the same day with a wider
real-world sweep -- see
``working-docs/implementation/allow-build-validation.md``'s
"``--allow-build`` build-and-read" round) to produce a byte-for-byte
exact match against its real published wheel's non-``.dist-info`` file
list -- zero known gaps for any of them. If a future ``uv_build``
release for a vendored version changes its build output, this test's
exact-match assertion is expected to catch that as a failure, not
silently mask it via a ``known_gaps`` allowance the way the fast-path
fixtures do.

``test_default_discovery_fails_loudly_for_module_name_mismatch`` below
is the fast, offline counterpart pinning the *other* half of the
django-model-import fixture's story: its ``known_gaps_note`` documents
that the DEFAULT (non-``--allow-build``) fallback doesn't just diverge
imprecisely (as rendercv's over-inclusion does) but fails outright with
zero files -- a real Hatchling limitation this test locks in as an
expected, loudly-``WARNING:``-logged failure, not a silent one.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core._models_wheel_dispatch import _discover_included_files
from pitloom.core._models_wheel_types import (
    DEFAULT_BUILD_TIMEOUT_SECONDS,
    BuildSettings,
)
from tests.fixtures.real_world import (
    REAL_WORLD_ROOT,
    extract_sdist,
    load_expected,
    sdist_available,
)

UV_BUILD_FIXTURES = [
    project_dir
    for project_dir in sorted((REAL_WORLD_ROOT / "uv_build").iterdir())
    if (project_dir / "expected.json").exists()
]
FIXTURE_IDS = [project_dir.name for project_dir in UV_BUILD_FIXTURES]


def _expected_non_dist_info_paths(manifest: dict[str, object]) -> set[str]:
    """The real wheel's file list minus its own ``.dist-info/*`` entries
    -- build-and-read never reproduces those (see
    ``pitloom.extract._license``'s docstring). Deliberately does not
    consult the manifest's ``known_gaps``/``known_gaps_note`` fields:
    those describe the *static* discovery fast path's fixture-level
    skip, not this real-build path's own (independently verified, see
    module docstring) empty gap set."""
    wheel_files: list[str] = (
        manifest.get("wheel_files") or []  # type: ignore[assignment]
    )
    dist_info_prefix = next(
        (
            f.split(".dist-info/", maxsplit=1)[0] + ".dist-info/"
            for f in wheel_files
            if ".dist-info/" in f
        ),
        None,
    )
    return {
        f
        for f in wheel_files
        if not (dist_info_prefix and f.startswith(dist_info_prefix))
    }


@pytest.mark.pypi_network
@pytest.mark.parametrize("project_dir", UV_BUILD_FIXTURES, ids=FIXTURE_IDS)
def test_build_and_read_matches_real_wheel(project_dir: Path, tmp_path: Path) -> None:
    if not sdist_available(project_dir):
        pytest.skip(
            f"{project_dir.name}: vendored sdist not present (excluded from "
            "Pitloom's own sdist -- run from a full git checkout to "
            "exercise this test)"
        )

    manifest = load_expected(project_dir)
    expected = _expected_non_dist_info_paths(manifest)
    extracted_root = extract_sdist(project_dir, tmp_path)

    included, cleanup = _discover_included_files(
        extracted_root,
        assume_backend="uv_build",
        build=BuildSettings(isolated=True, timeout=DEFAULT_BUILD_TIMEOUT_SECONDS),
    )
    try:
        discovered = {f.distribution_path for f in included}
    finally:
        cleanup()

    missing = expected - discovered
    extra = discovered - expected
    assert not missing, f"in real wheel but not discovered: {sorted(missing)}"
    assert not extra, f"discovered but not in real wheel: {sorted(extra)}"


def test_default_discovery_fails_loudly_for_module_name_mismatch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fast, offline (no ``--allow-build``, no real build, no network):
    the django-model-import fixture's ``[tool.uv.build-backend]
    module-name = ["djangomodelimport"]`` doesn't match what Hatchling's
    zero-config heuristic would guess from the project name
    (``django_model_import``) -- confirmed via manual `loom project`
    (see the fixture's own ``known_gaps_note``) to make the DEFAULT
    fallback fail outright with zero files, not just diverge
    imprecisely the way rendercv's over-inclusion does. Pins this as a
    loud, ``WARNING:``-logged failure (both the generic "not
    backend-aware" warning and Hatchling's own specific "no directory
    that matches the name of your project" one), not a silent one.

    Note this is *not* the ``None``-vs-``[]`` distinction CLAUDE.md's
    "Recurring bug patterns" section describes: ``_models_wheel_hatchling
    .discover()`` genuinely returns ``None`` here, but
    ``_discover_with_no_static_module()``'s own Hatchling-fallback call
    site (``_models_wheel_dispatch.py``) coerces it via ``... or []``
    before ``_discover_included_files`` ever returns -- a pre-existing
    pattern, not something this test changes -- so ``included == []``
    below is an authoritative-looking empty list, and this test's only
    real signal that discovery genuinely failed is the pair of
    ``WARNING:`` lines asserted below, not the return value's shape."""
    project_dir = next(
        p for p in UV_BUILD_FIXTURES if p.name == "django-model-import-0.9.0"
    )
    if not sdist_available(project_dir):
        pytest.skip(
            f"{project_dir.name}: vendored sdist not present (excluded from "
            "Pitloom's own sdist -- run from a full git checkout to "
            "exercise this test)"
        )

    extracted_root = extract_sdist(project_dir, tmp_path)

    # Deliberately no assume_backend here (unlike other tests in this
    # module) -- this fixture's real pyproject.toml has a [project]
    # table, and _discover_included_files needs to see that (by reading
    # it for real, the same way every production caller does) to know
    # the doomed Hatchling fallback is worth attempting at all, rather
    # than skipping straight past it (see
    # _discover_with_no_static_module's own [project]-table guard).
    with caplog.at_level(logging.WARNING):
        included, cleanup = _discover_included_files(extracted_root)
    try:
        assert included == []
    finally:
        cleanup()

    assert "not yet backend-aware" in caplog.text
    assert "Hatchling file discovery failed" in caplog.text
    assert "no directory that matches the name of your project" in caplog.text
