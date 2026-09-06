# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock``'s transitive-dependency walk
(:mod:`pitloom.extract._uv_lock`)'s BFS/DFS over a resolved package's own
nested ``dependencies`` list, starting from the root package.

Split out of test_uv_lock.py (which covers this same module's basic
malformed-input handling and direct dependency-reference resolution)
once the transitive-walk cluster alone grew past this repo's own
per-file line-count guidance -- see test_uv_lock.py's own module
docstring for the sibling-file map.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._uv_lock import extract_uv_lock_dependencies

_LOCK_HEADER = 'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'

#: A minimal root/project package entry -- every test that needs one
#: root dependency composes this with its own `dependencies` block.
_ROOT_HEADER = (
    '[[package]]\nname = "demo"\nversion = "1.0.0"\nsource = { editable = "." }\n'
)


def _write_lock(tmp_dir: Path, body: str = "") -> None:
    (tmp_dir / "uv.lock").write_text(_LOCK_HEADER + body, encoding="utf-8")


def test_transitive_dependency_of_a_direct_dependency_is_included() -> None:
    """The root's own `dependencies` list is only the first layer -- a
    package it depends on can itself have further dependencies, and
    those must be walked too, not just the root's immediate list."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'dependencies = [{ name = "urllib3" }, { name = "certifi" }]\n\n'
            '[[package]]\nname = "urllib3"\nversion = "2.2.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n\n'
            '[[package]]\nname = "certifi"\nversion = "2024.2.2"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        result = extract_uv_lock_dependencies(tmp_path)

        assert result is not None
        assert set(result) == {
            "requests==2.31.0",
            "urllib3==2.2.0",
            "certifi==2024.2.2",
        }


def test_diamond_dependency_visited_only_once() -> None:
    """Two of the root's direct dependencies sharing a common transitive
    dependency must not cause that shared package to be processed (or
    emitted) twice."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "pkg-a" }, { name = "pkg-b" }]\n\n'
            '[[package]]\nname = "pkg-a"\nversion = "1.0.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'dependencies = [{ name = "shared" }]\n\n'
            '[[package]]\nname = "pkg-b"\nversion = "1.0.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'dependencies = [{ name = "shared" }]\n\n'
            '[[package]]\nname = "shared"\nversion = "0.1.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        result = extract_uv_lock_dependencies(tmp_path)

        assert result is not None
        assert result.count("shared==0.1.0") == 1


def test_nested_dependencies_not_a_list_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A resolved package's own `dependencies` key, if present at all,
    must be a list -- a malformed non-list value (but still truthy, so
    distinct from a missing key) is warned and simply not walked into
    further, not treated as a parse error for the whole file."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'dependencies = "not-a-list"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "nested 'dependencies'" in caplog.text


def test_nested_dependencies_falsy_non_list_silently_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A falsy non-list `dependencies` value (e.g. `false` -- TOML has
    no `null`, so this is the practical malformed-but-empty shape)
    behaves like a missing/empty key, not like the truthy-malformed case
    above -- no `WARNING:`, and nothing to walk into, but the package's
    own pin is still resolved."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            "dependencies = false\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "nested 'dependencies'" not in caplog.text


def test_dependency_with_no_source_table_still_included() -> None:
    """A package entry with no `source` key at all (unusual but not
    invalid) is treated the same as a registry source -- only an
    explicit non-registry key excludes it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "no-source" }]\n\n'
            '[[package]]\nname = "no-source"\nversion = "1.2.3"\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["no-source==1.2.3"]
