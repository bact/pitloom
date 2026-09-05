# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``uv.lock`` resolved-dependency parsing
(:mod:`pitloom.extract._uv_lock`)'s core extraction correctness --
malformed/missing input handling, dependency-reference resolution, and
the marker-ambiguity skip policy.

See also: test_uv_lock_root_package.py (root/workspace-member package
selection), test_uv_lock_integration.py (``read_project()`` cascade
wiring and real-world fixtures), test_pylock.py/test_poetry_lock.py for
the sibling lock extractors this module's tests mirror in shape, and
test_locked_dependencies.py for the cascade mechanism's own tests.
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


def test_no_lock_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `_locked_dependencies.py` relies on this distinction
    to let a lower-priority source apply when this one is truly absent."""
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_uv_lock_dependencies(Path(tmp)) is None


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "uv.lock").write_text("this is not [ valid toml", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_package_key_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


def test_no_root_package_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A uv.lock with no `editable`/`virtual`-sourced entry has no
    identifiable project package -- nothing to resolve dependencies
    for."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "no project package found" in caplog.text


def test_empty_string_expected_name_falls_back_to_pyproject_toml() -> None:
    """`ProjectMetadata.name` is typed `str`, never `None` -- a caller
    whose own name resolution failed passes `""`, not `None`. This must
    still trigger the same `_expected_project_name()` re-read fallback
    an explicit `None` gets, not be treated as a real (if unmatched)
    workspace-member name."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "other-member"\nversion = "1.0.0"\n'
            'source = { editable = "./other" }\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        assert extract_uv_lock_dependencies(tmp_path, expected_name="") == [
            "requests==2.31.0"
        ]


def test_root_dependencies_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { editable = "." }\ndependencies = "not-a-list"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


def test_root_with_no_dependencies_key_returns_empty_list_not_none() -> None:
    """A project with zero runtime dependencies is valid, not an error --
    and must return `[]`, not `None`, so the cascade treats this lock as
    a real, winning (if empty) answer rather than "not present"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, _ROOT_HEADER)

        assert extract_uv_lock_dependencies(tmp_path) == []


def test_simple_dependency_resolved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_dependency_with_marker_but_no_inline_version_still_resolved() -> None:
    """A `marker` field alone (conditional presence, not a version
    conflict) doesn't block resolution -- same "no marker evaluation,
    include regardless" simplification as poetry.lock/pylock.toml."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "requests", '
            "marker = \"python_full_version < '3.11'\" }]\n\n"
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_malformed_top_level_package_entry_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A corrupted top-level `[[package]]` entry (not a table, or
    missing/non-string `name`) must warn like every sibling lock
    format's own malformed-entry check -- even when nothing in the
    resolved dependency graph ever references it by name, so it can't
    silently vanish with zero diagnostic."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + "dependencies = []\n\n"
            '[[package]]\nversion = "9.9.9"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert result == []
        assert "malformed" in caplog.text.lower()


def test_non_table_top_level_package_entry_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The other half of `_warn_malformed_packages()`'s check: a
    top-level `package` array entry that isn't a table at all (not just
    one missing `name`), e.g. a bare string slipped in alongside genuine
    `[[package]]` tables -- must also warn, matching every sibling
    format's own "expected a table, got %s" malformed-entry check."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "uv.lock").write_text(
            _LOCK_HEADER + 'package = ["not-a-table", '
            '{ name = "demo", version = "1.0.0", '
            'source = { editable = "." }, dependencies = [] }]\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert result == []
        assert "malformed" in caplog.text.lower()
        assert "expected a table" in caplog.text.lower()


def test_dependency_resolved_across_name_case_difference() -> None:
    """A dependency reference and the package's own top-level entry are
    two separately-literal strings in the file -- resolution must
    compare them PEP 503-canonicalized, the same as the `visited`-set
    dedup guard already does, so a differently-cased/`-`-vs-`_` name
    still resolves instead of spuriously reporting "not found"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "My_Package" }]\n\n'
            '[[package]]\nname = "my-package"\nversion = "1.2.3"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        assert extract_uv_lock_dependencies(tmp_path) == ["my-package==1.2.3"]


def test_malformed_dependency_reference_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, _ROOT_HEADER + 'dependencies = ["not-a-table"]\n')

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "malformed" in caplog.text.lower()


def test_dependency_reference_missing_name_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, _ROOT_HEADER + "dependencies = [{ extra = ['x'] }]\n")

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "malformed" in caplog.text.lower()


def test_marker_conditional_root_dependency_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An inline `version` directly on the root's own dependency
    reference means the resolved version differs per environment marker
    -- ambiguous without evaluating markers, so it's skipped, not
    guessed."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "click", version = "8.1.8", '
            'source = { registry = "https://pypi.org/simple" }, '
            "marker = \"python_full_version < '3.10'\" }]\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "marker-conditional" in caplog.text


def test_dependency_not_found_in_package_table_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path, _ROOT_HEADER + 'dependencies = [{ name = "ghost-pkg" }]\n'
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "not found" in caplog.text


def test_ambiguous_multi_version_dependency_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The same package name resolved at two different versions (e.g.
    one per Python-version marker branch) can't be picked between
    without marker evaluation -- skip both, don't guess."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "click" }]\n\n'
            '[[package]]\nname = "click"\nversion = "8.1.8"\n'
            'source = { registry = "https://pypi.org/simple" }\n\n'
            '[[package]]\nname = "click"\nversion = "8.3.1"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "2 resolved versions" in caplog.text


@pytest.mark.parametrize(
    "source_key", ["git", "url", "path", "directory", "editable", "virtual"]
)
def test_non_registry_sourced_dependency_excluded(
    source_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # A real pyproject.toml (matching _ROOT_HEADER's "demo") is
        # needed here specifically for the "editable"/"virtual"
        # source_key cases: without it, "local-dep" (also
        # editable/virtual-sourced by this test's own parametrization)
        # would be a second candidate root package indistinguishable
        # from "demo", and _find_root_package() would correctly refuse
        # to guess between them -- unrelated to what this test checks
        # (that a non-registry-sourced *dependency* is excluded).
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "local-dep" }]\n\n'
            f'[[package]]\nname = "local-dep"\nversion = "0.1.0"\n'
            f'source = {{ {source_key} = "some-value" }}\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "local-dep" in caplog.text


def test_dependency_missing_version_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            _ROOT_HEADER + 'dependencies = [{ name = "no-version" }]\n\n'
            '[[package]]\nname = "no-version"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_uv_lock_dependencies(tmp_path)

        assert not result
        assert "missing" in caplog.text.lower()


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
