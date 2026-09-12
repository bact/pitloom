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

import json
import tempfile
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

from pitloom.extract._pipfile_lock import extract_pipfile_lock_dependencies
from pitloom.extract._pipfile_lock_hashes import (
    _entry_pinned_version,
    _hash_candidates,
    _index_by_name_and_version,
    extract_pipfile_lock_hashes,
)

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pipfile"
)


def _write_lock(tmp_dir: Path, default_section: dict[str, object]) -> None:
    (tmp_dir / "Pipfile.lock").write_text(
        json.dumps({"_meta": {"pipfile-spec": 6}, "default": default_section}),
        encoding="utf-8",
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


def test_default_section_wrong_type_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "Pipfile.lock").write_text(
            json.dumps({"_meta": {"pipfile-spec": 6}, "default": "not-a-dict"}),
            encoding="utf-8",
        )
        assert extract_pipfile_lock_hashes(tmp_path, []) is None


def test_locked_dependency_not_a_single_exact_pin_skipped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            {"requests": {"hashes": ["sha256:" + "a" * 64], "version": "==2.31.0"}},
        )
        hashes = extract_pipfile_lock_hashes(tmp_path, ["requests>=2.0"])
        assert hashes == {}


def test_entry_pinned_version_non_string_returns_none() -> None:
    assert _entry_pinned_version({"version": 123}) is None
    assert _entry_pinned_version({}) is None


def test_entry_pinned_version_invalid_specifier_returns_none() -> None:
    assert _entry_pinned_version({"version": "not a specifier !!!"}) is None


def test_hash_candidates_non_list_returns_empty() -> None:
    assert _hash_candidates("not-a-list") == []
    assert _hash_candidates(None) == []


def test_index_by_name_and_version_skips_malformed_entries() -> None:
    section: dict[Any, Any] = {
        123: {"version": "==1.0"},  # non-string name key
        "badentry": "not-a-dict",
        "norange": {"version": ">=1.0"},  # not a single exact pin
        "good": {"version": "==1.0"},
    }
    index = _index_by_name_and_version(section)
    assert list(index.keys()) == [("good", "1.0")]
