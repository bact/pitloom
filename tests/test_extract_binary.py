# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.binary phantom-dependency detection."""

import hashlib
import zipfile
from pathlib import Path

from pitloom.core.project import ProjectFile
from pitloom.extract.binary import (
    _is_phantom_binary,
    extract_phantom_dependencies,
    find_phantom_dependencies,
)


def test_libs_directory_so_is_detected() -> None:
    """A .so bundled under a <package>.libs/ directory (auditwheel
    convention) is a phantom dependency."""
    assert _is_phantom_binary("mypkg.libs/libfoo-abc123.so") is True


def test_dylibs_directory_dylib_is_detected() -> None:
    """A .dylib bundled under a .dylibs/ directory (delocate convention) is
    a phantom dependency."""
    assert _is_phantom_binary("mypkg/.dylibs/libbar.dylib") is True


def test_cpython_extension_module_is_not_detected() -> None:
    """A project-owned extension module (.cpython-*.so) is excluded."""
    assert _is_phantom_binary("mypkg/_native.cpython-310-x86_64-linux-gnu.so") is False


def test_pyd_file_is_not_detected() -> None:
    """A Windows extension module (.pyd) is excluded."""
    assert _is_phantom_binary("mypkg/_native.pyd") is False


def test_bare_shared_library_is_detected_as_fallback() -> None:
    """A shared library that is neither in a known bundled-dependency
    directory nor an extension module is still flagged, as the documented
    fallback heuristic."""
    assert _is_phantom_binary("mypkg/libssl.so") is True
    assert _is_phantom_binary("mypkg/foo.dll") is True
    assert _is_phantom_binary("mypkg/foo.dylib") is True


def test_non_binary_file_is_not_detected() -> None:
    """A regular source file is never a phantom dependency."""
    assert _is_phantom_binary("mypkg/__init__.py") is False


def _make_wheel_with_bundled_binary(tmp_path: Path) -> Path:
    """Build a minimal .whl containing one auditwheel-style bundled .so."""
    wheel_path = tmp_path / "pkg-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("pkg/__init__.py", "")
        zf.writestr("pkg.libs/libfoo-abc123.so", b"\x7fELF fake binary content")
    return wheel_path


def test_find_phantom_dependencies_from_project_files() -> None:
    """find_phantom_dependencies() picks out only the bundled binary among a
    mix of ProjectFile entries."""
    files = [
        ProjectFile(
            physical_path="pkg/__init__.py",
            distribution_path="pkg/__init__.py",
            digest_sha256="a" * 64,
        ),
        ProjectFile(
            physical_path="pkg.libs/libfoo-abc123.so",
            distribution_path="pkg.libs/libfoo-abc123.so",
            digest_sha256="b" * 64,
        ),
    ]

    phantom_deps = find_phantom_dependencies(files)

    assert len(phantom_deps) == 1
    assert phantom_deps[0].name == "libfoo-abc123"
    assert phantom_deps[0].file_path == "pkg.libs/libfoo-abc123.so"
    assert phantom_deps[0].digest_sha256 == "b" * 64


def test_extract_phantom_dependencies_end_to_end(tmp_path: Path) -> None:
    """extract_phantom_dependencies() finds a bundled .libs/*.so inside a
    real wheel zip and computes its SHA-256 digest."""
    wheel_path = _make_wheel_with_bundled_binary(tmp_path)

    phantom_deps = extract_phantom_dependencies(wheel_path)

    assert len(phantom_deps) == 1
    dep = phantom_deps[0]
    assert dep.name == "libfoo-abc123"
    assert dep.file_path == "pkg.libs/libfoo-abc123.so"
    assert dep.version is None

    expected_digest = hashlib.sha256(b"\x7fELF fake binary content").hexdigest()
    assert dep.digest_sha256 == expected_digest
