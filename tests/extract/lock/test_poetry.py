# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``poetry.lock`` transitive-dependency parsing
(:mod:`pitloom.extract.lock.poetry`).

See also: test_poetry_parsing.py for low-level ``[tool.poetry]`` parsing,
test_poetry_pyproject.py for ``read_pyproject()`` integration; this file
covers the sibling ``poetry.lock`` extractor those don't, and
test_poetry_integration.py reads it from fixture and real-world projects.
"""

# Explicit `== []`/`== {}` keeps the None-vs-empty distinction.
# pylint: disable=use-implicit-booleaness-not-comparison

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract.lock.poetry import (
    _main_group_package_or_none,
    extract_poetry_lock_dependencies,
)
from tests.extract.lock.poetry_lock_shared import write_lock


def test_no_lock_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `cascade.py` relies on this distinction
    to let a lower-priority source apply when this one is truly absent."""
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_poetry_lock_dependencies(Path(tmp)) is None


def test_valid_lock_with_no_packages_returns_empty_list_not_none() -> None:
    """A `poetry.lock` with zero packages is a real, valid answer (its
    `[metadata]` table -- always present in a genuine poetry.lock, even
    an empty one -- proves it's not just some unrelated/truncated TOML
    file) -- must be `[]`, not `None`, so the cascade treats it as a
    winning (if empty) result rather than "not present"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(tmp_path, "")

        assert extract_poetry_lock_dependencies(tmp_path) == []


def test_missing_metadata_table_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A syntactically valid but empty/truncated file with no `[metadata]` table
    is ambiguous (a zero-dependency poetry.lock, or unrelated TOML found
    under that name): it returns `None`, so a lower-priority source (e.g.
    `pdm.lock`) can still be tried."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "poetry.lock").write_text("", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result is None
        assert "doesn't look like a genuine poetry.lock" in caplog.text


@pytest.mark.parametrize(
    "metadata_body",
    [
        pytest.param('content-hash = "abc123"\n', id="missing"),
        pytest.param("lock-version = 2\n", id="non-string"),
    ],
)
def test_metadata_table_missing_lock_version_returns_none_and_warns(
    metadata_body: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A `[metadata]` table present but missing/non-string `lock-version`
    is just as ambiguous as no `[metadata]` table at all -- a present but
    wrong-shaped value (e.g. an int instead of a string) must not pass
    more easily than the key being absent entirely."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "poetry.lock").write_text(
            f"[metadata]\n{metadata_body}", encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result is None
        assert "doesn't look like a genuine poetry.lock" in caplog.text


def test_malformed_toml_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(tmp_path, "this is not [ valid toml")

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result is None
        assert "Failed to parse" in caplog.text


def test_main_group_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
        )

        result = extract_poetry_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_dev_only_group_package_excluded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "pytest"\nversion = "8.0.0"\ngroups = ["dev"]\n',
        )

        assert not extract_poetry_lock_dependencies(tmp_path)


def test_dev_only_group_non_registry_sourced_package_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A package that is both dev-only-group and non-registry-sourced is
    dropped with no warning: it is excluded either way, so warning about its
    source type is noise. Mirrors `pylock.py`'s
    `test_marker_excluded_non_registry_sourced_package_is_silent`, for
    `_main_group_package_or_none`'s own ordering."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "dev-only-vcs"\nversion = "0.1.0"\n'
            'groups = ["dev"]\n[package.source]\ntype = "git"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert caplog.text == ""


def test_package_in_main_and_dev_groups_included() -> None:
    """A package listed under both `main` and another group still counts
    -- only *exclusively* non-main packages are dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "shared-pkg"\nversion = "1.0.0"\n'
            'groups = ["main", "dev"]\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["shared-pkg==1.0.0"]


def test_missing_groups_key_defaults_to_main() -> None:
    """Older ``poetry.lock`` schema versions may lack a ``groups`` key
    entirely -- treat that as the default (``main``), not "exclude"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(tmp_path, '[[package]]\nname = "legacy-pkg"\nversion = "1.0.0"\n')

        assert extract_poetry_lock_dependencies(tmp_path) == ["legacy-pkg==1.0.0"]


def test_malformed_groups_field_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `groups` field present but not a list (a bare string, say) is a
    malformed entry, not ordinary "not in main group" filtering -- must
    warn like every other malformed-field case, not silently disappear
    the same way a routine non-main-group package does."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "odd-pkg"\nversion = "1.0.0"\ngroups = "main"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "'groups'" in caplog.text


def test_legacy_poetry_category_main_and_dev() -> None:
    """Poetry 1.x locks use category = "main"|"dev" instead of groups.
    category = "main" must be included, while category = "dev" must be excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "runtime-pkg"\nversion = "1.0.0"\n'
            'category = "main"\n\n'
            '[[package]]\nname = "dev-pkg"\nversion = "2.0.0"\n'
            'category = "dev"\n',
        )

        result = extract_poetry_lock_dependencies(tmp_path)
        assert result == ["runtime-pkg==1.0.0"]


def test_legacy_poetry_malformed_category_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-string 'category' (corrupted/hand-edited lock) is skipped with a
    WARNING:, as a malformed 'groups' field is."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "bad-category-pkg"\nversion = "1.0.0"\n'
            'category = ["main"]\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result == []
        assert "'category' is list, expected a string" in caplog.text


def test_optional_package_excluded() -> None:
    """A package with optional = true is an extra, not a default runtime
    dependency -- must be excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'optional = true\ngroups = ["main"]\n',
        )

        assert not extract_poetry_lock_dependencies(tmp_path)


def test_conflicting_versions_for_same_package_warns_and_excludes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When a package is locked at multiple conflicting versions under main group,
    warn_conflicting_versions is emitted and the package is skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.32.0"\ngroups = ["main"]\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "conflicting versions" in caplog.text


def test_equivalent_versions_for_same_package_not_conflicted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31"\ngroups = ["main"]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
        )

        result = extract_poetry_lock_dependencies(tmp_path)
        assert result == ["requests==2.31"]


def test_main_group_package_or_none_non_dict_entry_returns_none() -> None:
    """A ``[[package]]`` entry that isn't a table (defensive guard against
    a malformed lock file) is skipped, not a crash."""
    assert _main_group_package_or_none("not-a-dict") is None
    assert _main_group_package_or_none(["still", "not", "a", "dict"]) is None


def test_malformed_package_entry_skipped() -> None:
    """A package table missing ``name``/``version`` is skipped, not a
    crash -- the rest of the lock file is still processed."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "incomplete"\n\n'
            '[[package]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["complete-pkg==2.0.0"]


def test_malformed_package_entry_warns(caplog: pytest.LogCaptureFixture) -> None:
    """A malformed ``[[package]]`` entry (missing ``version``) emits a
    ``WARNING:`` with the ``missing or non-string 'version'`` wording of every
    sibling format
    (:func:`pitloom.extract.lock._common.warn_missing_version`)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(tmp_path, '[[package]]\nname = "incomplete"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "missing or non-string 'version'" in caplog.text


def test_missing_name_skipped_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    """A ``[[package]]`` entry missing ``name`` is validated and warned
    about separately from a missing ``version`` -- matching every
    sibling format's own split name-then-version check ordering
    (:func:`pitloom.extract.lock._common.warn_missing_name`, tried
    before ``version`` is ever read)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(tmp_path, '[[package]]\nversion = "1.0.0"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "missing or non-string 'name'" in caplog.text


def test_malformed_package_entry_empty_version_skipped() -> None:
    """An entry with ``version = ""`` (a string, but empty) is rejected, not
    emitted as an invalid ``name==`` pin; ``pylock.py``/``uv.py``/``pdm.py``
    reject it too."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "broken"\nversion = ""\n\n'
            '[[package]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["complete-pkg==2.0.0"]


def test_package_table_not_a_list_warns(caplog: pytest.LogCaptureFixture) -> None:
    """A malformed top-level ``package`` key (not a list) degrades to an empty
    list with a ``WARNING:``."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(tmp_path, 'package = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result is None
        assert "expected a list" in caplog.text


@pytest.mark.parametrize("source_type", ["directory", "file", "git", "url"])
def test_non_pep508_sourced_package_excluded(
    source_type: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A poetry.lock entry resolved from a local path or VCS has no meaningful
    PyPI version pin: it is excluded, not emitted as ``name==version``."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "local-dep"\nversion = "0.1.0"\n'
            f'[package.source]\ntype = "{source_type}"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "local-dep" in caplog.text


def test_legacy_source_package_still_included() -> None:
    """A package resolved from a private/secondary index (``source.type =
    "legacy"``) still has a real, meaningful version pin -- unlike
    directory/file/git/url sources, it must not be excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_lock(
            tmp_path,
            '[[package]]\nname = "private-pkg"\nversion = "1.0.0"\n'
            '[package.source]\ntype = "legacy"\nurl = "https://example.com/simple"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["private-pkg==1.0.0"]
