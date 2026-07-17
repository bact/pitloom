# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Heuristics for extracting phantom dependencies from Python wheels."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from pitloom.core.project import PhantomDependency, ProjectFile


def _is_phantom_binary(filename: str) -> bool:
    """Determine if a filename looks like a bundled third-party binary dependency.

    A binary is considered a "phantom dependency" if it is bundled inside the wheel
    (e.g., via auditwheel, delocate, delvewheel) rather than being a project-owned
    extension module (e.g. .cpython-310-x86_64-linux-gnu.so or .pyd).
    """
    path = Path(filename)
    name = path.name

    # Pre-compiled binaries usually have these extensions.
    if not name.endswith((".so", ".dylib", ".dll")):
        # .pyd (Windows extension modules) is deliberately excluded here;
        # bundled third-party binaries on Windows are .dll.
        return False

    # Exclude typical Python extension modules (e.g. built by setuptools/hatch)
    if ".cpython-" in name or ".abi3-" in name:
        return False

    # On Windows, compiled extensions end with .pyd
    if name.endswith(".pyd"):
        return False

    # Check if it is in a known bundled dependency directory
    # - auditwheel puts them in <package>.libs/
    # - delocate puts them in <package>/.dylibs/
    # - delvewheel puts them in <package>.libs/
    parts = path.parts
    for part in parts[:-1]:
        if part.endswith(".libs") or part == ".dylibs":
            return True

    # As a fallback, any shared library that isn't an extension module
    # is a strong candidate for being a phantom dependency.
    return True


def find_phantom_dependencies(files: list[ProjectFile]) -> list[PhantomDependency]:
    """Scan a list of project files (e.g. from Hatchling or a parsed wheel)
    to find phantom binary dependencies.

    Args:
        files: List of ProjectFile objects.

    Returns:
        List of PhantomDependency objects.
    """
    phantom_deps: list[PhantomDependency] = []

    for file in files:
        if _is_phantom_binary(file.distribution_path):
            name = Path(file.distribution_path).stem
            phantom_deps.append(
                PhantomDependency(
                    name=name,
                    file_path=file.distribution_path,
                    digest_sha256=file.digest_sha256,
                    version=None,
                )
            )

    return phantom_deps


def extract_phantom_dependencies(wheel_path: Path | str) -> list[PhantomDependency]:
    """Extract a list of bundled phantom dependencies from a wheel file.

    Args:
        wheel_path: Path to the .whl file to analyze.

    Returns:
        List of PhantomDependency objects.
    """
    phantom_deps: list[PhantomDependency] = []

    with zipfile.ZipFile(wheel_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue

            if _is_phantom_binary(info.filename):
                # Calculate SHA-256 digest
                hasher = hashlib.sha256()
                with zf.open(info) as f:
                    while chunk := f.read(8192):
                        hasher.update(chunk)

                digest = hasher.hexdigest()

                # Derive a plausible name from the filename, e.g.
                # libz-1.2.11.so -> name: libz. pathlib.Path.stem only
                # strips the last extension, so a multi-dot name like
                # libz.so.1.2 won't fully reduce to "libz" -- acceptable
                # for a heuristic.
                name = Path(info.filename).stem

                phantom_deps.append(
                    PhantomDependency(
                        name=name,
                        file_path=info.filename,
                        digest_sha256=digest,
                        # A version is not reliably parseable from the
                        # filename across ecosystems, so it is left unset.
                        version=None,
                    )
                )

    return phantom_deps
