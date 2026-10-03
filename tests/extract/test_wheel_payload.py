# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel's SBOM lists its payload only: ``payload_files`` drops the wheel's
own ``.dist-info`` and ``merkle_root_of_files`` hashes what is left.

See also: tests/assemble/test_wheel_payload_surfaces.py (every wheel surface).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pitloom.core.models import get_wheel_files, merkle_root_of_files
from pitloom.core.project import ProjectFile
from pitloom.extract.wheel import payload_files

_WHEEL = "demo-1.0-py3-none-any.whl"
_DI = "demo-1.0.dist-info/"


def _files(*paths: str) -> list[ProjectFile]:
    return [ProjectFile(p, p, hashlib.sha256(p.encode()).hexdigest()) for p in paths]


@pytest.mark.parametrize(
    ("wheel", "paths", "kept"),
    [
        pytest.param(
            _WHEEL,
            [f"{_DI}METADATA", f"{_DI}licenses/x", f"{_DI}sboms/s.json", "demo/a.py"],
            ["demo/a.py"],
            id="own-dist-info-incl-nested-dropped",
        ),
        pytest.param(
            _WHEEL,
            [f"{_DI}RECORD", "demo/vendored-1.0.dist-info/METADATA", "demo/a.py"],
            ["demo/vendored-1.0.dist-info/METADATA", "demo/a.py"],
            id="vendored-dist-info-kept",
        ),
        pytest.param(
            "My.Pkg-1.0.0-py3-none-any.whl",
            ["my_pkg-1.0.dist-info/METADATA", "my_pkg/a.py"],
            ["my_pkg/a.py"],
            id="name-normalised",
        ),
        pytest.param(
            _WHEEL,
            ["demo-1.0.dist-info-extra/x", f"{_DI}WHEEL", "demo/a.py"],
            ["demo-1.0.dist-info-extra/x", "demo/a.py"],
            id="prefix-needs-trailing-slash",
        ),
        pytest.param(
            _WHEEL,
            ["demo/a.py", "demo/b.py"],
            ["demo/a.py", "demo/b.py"],
            id="no-dist-info-unchanged",
        ),
        pytest.param(
            _WHEEL,
            ["a-1.0.dist-info/METADATA", "b-1.0.dist-info/METADATA", "x.py"],
            ["a-1.0.dist-info/METADATA", "b-1.0.dist-info/METADATA", "x.py"],
            id="two-candidates-unchanged",
        ),
    ],
)
def test_payload_files(wheel: str, paths: list[str], kept: list[str]) -> None:
    result = payload_files(_files(*paths), wheel)

    assert [f.distribution_path for f in result] == kept
    # Not vacuous: the dropped cases really started with more.
    assert len(result) <= len(paths)


def _reference_root(digests: list[bytes]) -> str:
    """Pairwise ``sha256(left + right)``; an odd last node is promoted."""
    level = digests
    while len(level) > 1:
        level = [
            hashlib.sha256(level[i] + level[i + 1]).digest()
            if i + 1 < len(level)
            else level[i]
            for i in range(0, len(level), 2)
        ]
    return level[0].hex()


def test_merkle_root_of_no_files_is_none() -> None:
    assert merkle_root_of_files([]) is None


def test_merkle_root_of_one_file_is_its_digest() -> None:
    (only,) = _files("demo/a.py")
    assert merkle_root_of_files([only]) == only.digest_sha256


def test_merkle_root_sorts_by_distribution_path_not_physical_path() -> None:
    a = ProjectFile("z-raw", "demo/a.py", hashlib.sha256(b"a").hexdigest())
    b = ProjectFile("a-raw", "demo/b.py", hashlib.sha256(b"b").hexdigest())
    expected = _reference_root([bytes.fromhex(str(f.digest_sha256)) for f in (a, b)])

    assert merkle_root_of_files([b, a]) == merkle_root_of_files([a, b]) == expected
    # Not vacuous: physical-path order would have given the other root.
    assert expected != _reference_root(
        [bytes.fromhex(str(f.digest_sha256)) for f in (b, a)]
    )


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_merkle_root_matches_reference_for_any_leaf_count(count: int) -> None:
    files = _files(*(f"demo/f{i}.py" for i in range(count)))
    expected = _reference_root([bytes.fromhex(str(f.digest_sha256)) for f in files])

    assert merkle_root_of_files(reversed(files)) == expected


def test_source_walk_and_wheel_roots_agree(tmp_path: Path) -> None:
    """``get_wheel_files()`` keeps its own root computation; the wheel
    surfaces use ``merkle_root_of_files``. One source tree must give the same
    root both ways, or the hook's and an embed's package hashes drift."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n'
        '[tool.hatch.build.targets.wheel]\npackages = ["demo"]\n',
        encoding="utf-8",
    )
    package = tmp_path / "demo"
    package.mkdir()
    for name in ("__init__.py", "a.py", "b.py", "c.py", "d.py"):
        (package / name).write_text(f"# {name}\n", encoding="utf-8")

    root, files, cleanup = get_wheel_files(tmp_path, assume_backend="hatchling")
    cleanup()

    assert len(files) == 5  # an odd count too: not vacuous
    assert root == merkle_root_of_files(files)
