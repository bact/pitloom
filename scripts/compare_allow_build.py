# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Compare ``loom project`` with vs. without ``--allow-build``.

A manual-verification tool (see CLAUDE.md's "Manual CLI integration
checks" section), not a pytest test -- run it by hand against a real
project (or vendored sdist fixture) whenever ``--allow-build``/
``--no-build-isolation`` or backend file-discovery dispatch
(``pitloom.core._models_wheel_dispatch``/``_models_wheel_hatchling``/
``_models_wheel_build_and_read``) changes. Answers three questions no
pytest suite covers end to end:

1. Does a registered backend's static discovery ever get bypassed for a
   real build when it already succeeded? (It must not -- see
   ``_models_wheel_dispatch.py``'s "must never be reached when the
   static discoverer already succeeded" invariant.)
2. For a backend with no static module (currently: uv_build), how does
   the Hatchling-heuristic fallback's file list actually differ from a
   real PEP 517 build's? (Extra files, missing files, or both?)
3. When an ``expected.json`` fixture with a real published wheel's file
   list is available (``tests/fixtures/real-world-projects/*/*/
   expected.json``), does ``--allow-build`` actually reproduce it?

Usage::

    python scripts/compare_allow_build.py PROJECT_PATH [PROJECT_PATH...]
    python scripts/compare_allow_build.py --fixture uv_build/rendercv-2.8
    python scripts/compare_allow_build.py --fixture flit/tomli-2.4.1 \\
        --fixture pdm/typer-0.27.2

PROJECT_PATH may be a project directory or an sdist archive
(``.tar.gz``/``.zip``) -- an archive is extracted to a temp directory
first. ``--fixture BACKEND/NAME`` is shorthand for the matching
``tests/fixtures/real-world-projects/BACKEND/NAME/NAME.tar.gz`` (or
``.zip``) archive, and implies ``--expected`` at that fixture's own
``expected.json`` if one exists and ``--expected`` wasn't given
explicitly.

Runs ``python -m pitloom project`` twice per project (with and without
``--allow-build``) via subprocess -- never imports Pitloom in-process,
so it exercises the same real CLI path a user would. Needs Pitloom
installed with its "build" extra (``pip install -e ".[build]"``) to
exercise ``--allow-build`` for a backend with no static module; without
it, that half degrades to Pitloom's own "build extra not installed"
failure path, which this script still reports rather than crashing on.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "real-world-projects"


def _extract_archive(archive: Path, dest: Path) -> Path:
    """Extract *archive* into *dest*, returning the single top-level
    directory it contained (every sdist tarball/zip here has exactly
    one)."""
    if archive.suffixes[-2:] == [".tar", ".gz"] or archive.suffix == ".tgz":
        with tarfile.open(archive) as tf:
            tf.extractall(dest, filter="data")  # noqa: S202 -- trusted, local fixture
    elif archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)  # noqa: S202 -- trusted, local fixture
    else:
        raise ValueError(f"Don't know how to extract {archive}")
    top_level = [p for p in dest.iterdir() if p.is_dir()]
    if len(top_level) != 1:
        raise ValueError(
            f"Expected exactly one top-level directory in {archive}, "
            f"found {[p.name for p in top_level]}"
        )
    return top_level[0]


def _resolve_fixture_archive(fixture: str) -> Path:
    """Resolve ``BACKEND/NAME`` to its vendored sdist archive path."""
    fixture_dir = FIXTURES_ROOT / fixture
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"No fixture directory at {fixture_dir}")
    candidates = list(fixture_dir.glob("*.tar.gz")) + list(fixture_dir.glob("*.zip"))
    if len(candidates) != 1:
        raise FileNotFoundError(
            f"Expected exactly one sdist archive in {fixture_dir}, "
            f"found {[c.name for c in candidates]}"
        )
    return candidates[0]


def _run_loom_project(
    project_dir: Path, output_path: Path, *, allow_build: bool
) -> tuple[int, str]:
    """Run ``python -m pitloom project`` against *project_dir*, returning
    ``(returncode, stderr)``. Uses ``python -m pitloom`` rather than the
    ``loom``/``pitloom`` console scripts so this script works from any
    checkout that has Pitloom installed (editable or not) without
    depending on PATH."""
    cmd = [
        sys.executable,
        "-m",
        "pitloom",
        "project",
        str(project_dir),
        "-o",
        str(output_path),
        "--creation-datetime",
        "2026-01-01T00:00:00Z",
    ]
    if allow_build:
        cmd.append("--allow-build")
    # Outer timeout must exceed Pitloom's own --build-timeout default
    # (1200s) so a slow-but-legitimate build isn't killed here first.
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=1500, check=False
    )
    return proc.returncode, proc.stderr


def _files_by_kind(sbom_path: Path, kind: str) -> set[str]:
    """Every ``software_File`` entry's ``name`` (distribution path) with
    ``software_fileKind == kind`` -- ``"file"`` to compare against a real
    wheel's file list (excludes ``"directory"`` entries, which SPDX3
    legitimately uses to model package directories -- not a discovery
    bug, see the docstring above)."""
    with open(sbom_path, encoding="utf-8") as f:
        sbom = json.load(f)
    graph = sbom.get("@graph", [])
    return {
        e["name"]
        for e in graph
        if e.get("type") == "software_File" and e.get("software_fileKind") == kind
    }


def _print_set_diff(label: str, only_in_a: set[str], only_in_b: set[str]) -> None:
    if not only_in_a and not only_in_b:
        print(f"  {label}: identical")
        return
    if only_in_a:
        print(f"  {label}: {len(only_in_a)} only in the first set")
        for path in sorted(only_in_a)[:20]:
            print(f"    - {path}")
        if len(only_in_a) > 20:
            print(f"    ... and {len(only_in_a) - 20} more")
    if only_in_b:
        print(f"  {label}: {len(only_in_b)} only in the second set")
        for path in sorted(only_in_b)[:20]:
            print(f"    + {path}")
        if len(only_in_b) > 20:
            print(f"    ... and {len(only_in_b) - 20} more")


# pylint: disable-next=too-many-locals
def compare_one(
    project_dir: Path, workdir: Path, *, expected_path: Path | None
) -> bool:
    """Run both variants for *project_dir*, print a report, and return
    ``True`` iff nothing looked wrong (both runs succeeded and, when
    *expected_path* is given, ``--allow-build`` exactly matched it)."""
    print(f"\n=== {project_dir.name} ===")
    ok = True

    without_path = workdir / "without.json"
    with_path = workdir / "with.json"

    rc_without, stderr_without = _run_loom_project(
        project_dir, without_path, allow_build=False
    )
    rc_with, stderr_with = _run_loom_project(project_dir, with_path, allow_build=True)

    invoked_build = "invoking a real PEP 517 build" in stderr_with
    print(f"  without --allow-build: rc={rc_without}")
    print(f"  with    --allow-build: rc={rc_with}, real build invoked={invoked_build}")

    if rc_without != 0 or rc_with != 0:
        print("  FAILED: a run exited non-zero -- see stderr below")
        print("  --- stderr (without) ---")
        print(stderr_without)
        print("  --- stderr (with) ---")
        print(stderr_with)
        return False

    without_files = _files_by_kind(without_path, "file")
    with_files = _files_by_kind(with_path, "file")

    print(f"  file counts: without={len(without_files)} with={len(with_files)}")
    _print_set_diff(
        "without vs. with --allow-build",
        without_files - with_files,
        with_files - without_files,
    )

    if not invoked_build and without_files != with_files:
        # A registered backend's static discoverer already succeeded --
        # build_and_read_wheel() must never even run in that case (see
        # _models_wheel_dispatch.py's invariant), so the two file sets
        # must be identical, not merely similar.
        print(
            "  WARNING: no real build was invoked, but the file lists "
            "differ -- this should never happen when static discovery "
            "already succeeded."
        )
        ok = False

    if expected_path is not None and not invoked_build:
        # expected.json holds the real PUBLISHED wheel's file list, which
        # may include platform-specific build artifacts (compiled
        # extensions, etc.) that neither static discovery NOR a real
        # local build here would ever reproduce byte-for-byte -- a static
        # discoverer already succeeded, so no real build even ran, which
        # means this comparison would be testing static-discovery
        # accuracy against a published wheel's build environment, not
        # --allow-build's own mechanism. Skip it rather than report a
        # misleading discrepancy.
        print(
            "  (expected.json cross-check skipped: static discovery "
            "already succeeded, no real build ran to compare against it)"
        )
    elif expected_path is not None:
        with open(expected_path, encoding="utf-8") as f:
            expected: dict[str, Any] = json.load(f)
        real_files = set(expected["wheel_files"])
        real_comparable = {
            f
            for f in real_files
            if "licenses/" in f or not f.split("/", 1)[0].endswith(".dist-info")
        }
        matches = with_files == real_comparable
        print(
            f"  --allow-build vs. real published wheel "
            f"({len(real_comparable)} comparable entries): "
            f"{'EXACT MATCH' if matches else 'DIFFERS'}"
        )
        if not matches:
            _print_set_diff(
                "--allow-build vs. real wheel",
                with_files - real_comparable,
                real_comparable - with_files,
            )
            ok = False

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Project directory or sdist archive (.tar.gz/.zip) to compare.",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        metavar="BACKEND/NAME",
        help=(
            "Compare a vendored real-world fixture, e.g. uv_build/rendercv-2.8 "
            "(resolves to tests/fixtures/real-world-projects/BACKEND/NAME/*.tar.gz "
            "or .zip). Repeatable."
        ),
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help=(
            "expected.json with a 'wheel_files' list to cross-check "
            "--allow-build's result against a real published wheel. Only "
            "meaningful with a single target; --fixture auto-resolves its "
            "own expected.json when this is omitted."
        ),
    )
    args = parser.parse_args()

    if not args.paths and not args.fixture:
        parser.error("pass at least one PROJECT_PATH or --fixture")

    all_ok = True
    with tempfile.TemporaryDirectory(prefix="pitloom-compare-allow-build-") as tmp:
        tmp_root = Path(tmp)

        for i, path in enumerate(args.paths):
            expected_path = args.expected if len(args.paths) == 1 else None
            workdir = tmp_root / f"path-{i}"
            workdir.mkdir()
            if path.is_dir():
                project_dir = path
            else:
                project_dir = _extract_archive(path, workdir / "extracted")
            all_ok &= compare_one(project_dir, workdir, expected_path=expected_path)

        for i, fixture in enumerate(args.fixture):
            workdir = tmp_root / f"fixture-{i}"
            workdir.mkdir()
            archive = _resolve_fixture_archive(fixture)
            project_dir = _extract_archive(archive, workdir / "extracted")
            expected_path = args.expected
            if expected_path is None:
                candidate = FIXTURES_ROOT / fixture / "expected.json"
                if candidate.is_file():
                    expected_path = candidate
            all_ok &= compare_one(project_dir, workdir, expected_path=expected_path)

    print()
    print("RESULT:", "OK" if all_ok else "DISCREPANCIES FOUND")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
