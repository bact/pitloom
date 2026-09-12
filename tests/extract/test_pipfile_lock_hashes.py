# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Pipenv ``Pipfile.lock`` SHA-256 digest extraction
(:mod:`pitloom.extract._pipfile_lock_hashes`).

``Pipfile.lock``'s ``hashes`` list carries no filenames at all, so the
selected digest is the lexicographically-smallest of the ones listed,
not a wheel-preferring choice -- see the module's own docstring.
"""

import tempfile
from pathlib import Path

from packaging.utils import canonicalize_name

from pitloom.extract._pipfile_lock import extract_pipfile_lock_dependencies
from pitloom.extract._pipfile_lock_hashes import extract_pipfile_lock_hashes

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pipfile"
)

#: The lexicographically-smallest of beautifulsoup4's three listed hashes
#: in tests/fixtures/real-world-locks/pipfile/requests-html-0.10.0/Pipfile.lock.
_BEAUTIFULSOUP4_MIN_HASH = (
    "11a9a27b7d3bddc6d86f59fb76afb70e921a25ac2d6cc55b40d072bd68435a76"
)


def test_no_lock_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_pipfile_lock_hashes(Path(tmp), []) is None


def test_real_world_beautifulsoup4_min_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "requests-html-0.10.0"
    deps = extract_pipfile_lock_dependencies(project_dir)
    assert deps is not None

    hashes = extract_pipfile_lock_hashes(project_dir, deps)
    assert hashes is not None
    assert hashes[canonicalize_name("beautifulsoup4")] == _BEAUTIFULSOUP4_MIN_HASH


def test_determinism_same_lock_same_hash() -> None:
    project_dir = REAL_WORLD_LOCKS / "requests-html-0.10.0"
    deps = extract_pipfile_lock_dependencies(project_dir)
    assert deps is not None

    first = extract_pipfile_lock_hashes(project_dir, deps)
    second = extract_pipfile_lock_hashes(project_dir, deps)
    assert first == second


def test_missing_dependency_omitted_not_error() -> None:
    project_dir = REAL_WORLD_LOCKS / "requests-html-0.10.0"
    hashes = extract_pipfile_lock_hashes(project_dir, ["nonexistent-package==1.0"])
    assert hashes == {}
