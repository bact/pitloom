# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helper for the vendored real-world sdist fixtures under
``tests/fixtures/real-world-projects/``.

Each fixture directory holds a project's real, published sdist archive
(vendored once, offline -- no network access at test time) plus an
``expected.json`` sidecar recording its declared build backend, license,
and the real published wheel's file list (captured once when the fixture
was added, the wheel itself never committed). One shared extraction
helper here, rather than duplicating "open the sdist archive, find the
one top-level directory inside it" per test file -- every backend's
discovery test needs the exact same two lines.

See also: ``tests/fixtures/real-world-projects/README.md`` for the
per-project table and provenance; ``working-docs/implementation/
backend-file-discovery-validation.md`` for the validation policy these
fixtures satisfy.
"""

from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

REAL_WORLD_ROOT = Path(__file__).parent / "real-world-projects"


def iter_real_world_fixtures() -> list[tuple[str, Path]]:
    """Return ``(backend, project_dir)`` for every vendored real-world
    fixture, sorted for stable test-collection order."""
    return [
        (backend_dir.name, project_dir)
        for backend_dir in sorted(REAL_WORLD_ROOT.iterdir())
        if backend_dir.is_dir()
        for project_dir in sorted(backend_dir.iterdir())
        if (project_dir / "expected.json").exists()
    ]


def load_expected(project_dir: Path) -> dict[str, Any]:
    """Load a fixture's ``expected.json`` sidecar."""
    data: dict[str, Any] = json.loads(
        (project_dir / "expected.json").read_text(encoding="utf-8")
    )
    return data


def sdist_available(project_dir: Path) -> bool:
    """Whether *project_dir*'s vendored sdist archive is actually present
    on disk.

    ``tests/fixtures/real-world-projects/`` (like the rest of
    ``tests/fixtures/``) is excluded from Pitloom's own published sdist
    (see ``pyproject.toml``'s ``[tool.hatch.build.targets.sdist]``) --
    intentionally, to avoid redistributing vendored third-party source
    in a release artifact. A test consuming these fixtures needs this
    check so it skips cleanly (not errors) when run from a tree that
    doesn't have them, e.g. a downstream packager's rebuild-from-sdist
    QA pass. ``expected.json`` itself is small and first-party, so its
    presence alone (used by :func:`iter_real_world_fixtures` for stable
    test-collection/parametrize IDs) doesn't imply the sdist is there
    too -- this checks the actual archive file.
    """
    manifest = load_expected(project_dir)
    sdist_filename: str = manifest["sdist_filename"]
    return (project_dir / sdist_filename).is_file()


def extract_sdist(project_dir: Path, dest: Path) -> Path:
    """Extract the vendored sdist under *project_dir* into *dest*
    (typically a test's ``tmp_path``), returning the extracted project
    root -- the single top-level directory every sdist archive contains.

    Pure local extraction, no network access: the archive itself was
    already vendored into the repo when the fixture was added.
    """
    manifest = load_expected(project_dir)
    sdist_path = project_dir / manifest["sdist_filename"]

    if sdist_path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(sdist_path) as tar:
            top = tar.getnames()[0].split("/", maxsplit=1)[0]
            tar.extractall(dest, filter="data")
    elif sdist_path.suffix == ".zip":
        with zipfile.ZipFile(sdist_path) as zip_file:
            top = zip_file.namelist()[0].split("/", maxsplit=1)[0]
            # zipfile has no tarfile-style extraction filter; safe here
            # regardless, since every archive under real-world-projects/
            # is one this repo vendored itself from PyPI, never
            # attacker-controlled input.
            zip_file.extractall(dest)  # nosec B202
    else:
        raise ValueError(f"Unsupported sdist archive format: {sdist_path}")

    return dest / top


def expected_distribution_paths(manifest: dict[str, Any]) -> set[str] | None:
    """Return the real wheel's non-metadata distribution paths that a
    backend-aware ``discover()`` is expected to reproduce, or ``None``
    when the fixture's ``known_gaps`` is ``"ALL"`` (discovery is
    environment-dependent for this fixture and not asserted at all --
    see its ``known_gaps_note``).

    Excludes ``<name>-<version>.dist-info/*`` (no discoverer includes
    metadata files) and any path listed in ``known_gaps`` (compiled
    artifacts, VCS-generated files -- legitimately outside what static
    discovery can ever see, documented per-fixture in ``known_gaps_note``).
    """
    if manifest.get("known_gaps") == "ALL":
        return None

    wheel_files: list[str] = manifest.get("wheel_files") or []
    known_gaps = set(manifest.get("known_gaps") or [])

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
        if f not in known_gaps
        and not (dist_info_prefix and f.startswith(dist_info_prefix))
    }
