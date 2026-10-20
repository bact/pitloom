# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PDM ``pdm.lock`` resolved-dependency parsing
(:mod:`pitloom.extract.lock.pdm`).

See also: test_pdm_integration.py (its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``, and the
real-world fixtures); test_poetry.py/test_uv.py for the sibling lock
extractors this module's tests mirror in shape;
test_cascade.py for the cascade mechanism's own tests, including the
priority-order consistency that this format's below-``poetry.lock`` rank
exercises.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract.lock.pdm import extract_pdm_lock_dependencies

#: Every genuine `pdm.lock` carries this table -- appended to *body* by
#: default so tests that aren't specifically about the genuineness check
#: itself don't need to repeat it.
_METADATA = '[metadata]\nlock_version = "4.5.1"\n'


def _write_lock(tmp_dir: Path, body: str = "", include_metadata: bool = True) -> None:
    content = body + _METADATA if include_metadata else body
    (tmp_dir / "pdm.lock").write_text(content, encoding="utf-8")


def test_no_lock_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `cascade.py` relies on this distinction
    to let a lower-priority source apply when this one is truly absent."""
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_pdm_lock_dependencies(Path(tmp)) is None


def test_valid_lock_with_no_packages_returns_empty_list_not_none() -> None:
    """A `pdm.lock` with zero packages is a real, valid answer -- must be
    `[]`, not `None`, so the cascade treats it as a winning (if empty)
    result rather than "not present"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "")

        assert extract_pdm_lock_dependencies(tmp_path) == []


def test_missing_metadata_table_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty/unrelated-but-parseable TOML file with no `[metadata]`
    table (this repo's `None`-vs-`[]` recurring bug pattern) must not be
    treated as "a real, empty pdm.lock" -- it could otherwise silently
    win the cascade over a genuinely usable lower-priority lock."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "", include_metadata=False)

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert result is None
        assert "doesn't look like a genuine pdm.lock" in caplog.text


@pytest.mark.parametrize(
    "metadata_body",
    [
        pytest.param('strategy = ["inherit_metadata"]\n', id="missing"),
        pytest.param("lock_version = 4\n", id="non-string"),
    ],
)
def test_metadata_table_missing_lock_version_returns_none_and_warns(
    metadata_body: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A present but wrong-shaped `lock_version` (e.g. an int instead of
    a string) must not pass more easily than the key being absent
    entirely."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            f"[metadata]\n{metadata_body}",
            include_metadata=False,
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert result is None
        assert "doesn't look like a genuine pdm.lock" in caplog.text


def test_malformed_toml_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "this is not [ valid toml")

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert result is None
        assert "Failed to parse" in caplog.text


def test_package_key_not_a_list_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert result is None
        assert "expected a list" in caplog.text


def test_default_group_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'groups = ["default"]\n',
        )

        assert extract_pdm_lock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_non_default_group_package_excluded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "pytest"\nversion = "8.0.0"\ngroups = ["test"]\n',
        )

        assert not extract_pdm_lock_dependencies(tmp_path)


def test_non_default_group_non_registry_sourced_package_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A package that is both non-default-group and non-registry-sourced is
    dropped with no warning: it is excluded either way, so warning about its
    source type is noise. Mirrors `pylock.py`'s
    `test_marker_excluded_non_registry_sourced_package_is_silent`, for
    `_default_group_package_or_none`'s own ordering."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "dev-only-vcs"\nversion = "0.1.0"\n'
            'groups = ["test"]\ngit = "some-value"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert caplog.text == ""


def test_package_in_default_and_other_group_included() -> None:
    """A package listed under both `default` and another group still
    counts -- only *exclusively* non-default packages are dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "shared-pkg"\nversion = "1.0.0"\n'
            'groups = ["default", "test"]\n',
        )

        assert extract_pdm_lock_dependencies(tmp_path) == ["shared-pkg==1.0.0"]


def test_missing_groups_key_defaults_to_default_group() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[package]]\nname = "legacy-pkg"\nversion = "1.0.0"\n')

        assert extract_pdm_lock_dependencies(tmp_path) == ["legacy-pkg==1.0.0"]


def test_malformed_groups_field_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `groups` field present but not a list is a malformed entry, not
    ordinary "not in default group" filtering -- must warn like every
    other malformed-field case (parity with poetry.lock's equivalent
    check)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "odd-pkg"\nversion = "1.0.0"\ngroups = "default"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "'groups'" in caplog.text


def test_version_validated_even_when_not_in_default_group(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed `version` on a non-default-group package still warns
    -- version validation must not be short-circuited by the group
    filter, matching poetry.lock's unconditional name/version check."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "dev-only"\ngroups = ["dev"]\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "missing or non-string 'version'" in caplog.text


def test_malformed_package_entry_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nversion = "1.0.0"\ngroups = ["default"]\n\n'
            '[[package]]\nname = "complete-pkg"\nversion = "2.0.0"\n'
            'groups = ["default"]\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert result == ["complete-pkg==2.0.0"]
        assert "malformed" in caplog.text.lower()


def test_non_dict_package_entry_warns(caplog: pytest.LogCaptureFixture) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "package = [1, 2, 3]\n")

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "malformed" in caplog.text.lower()


def test_missing_version_skipped_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path, '[[package]]\nname = "no-version"\ngroups = ["default"]\n'
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "missing" in caplog.text.lower()


@pytest.mark.parametrize("source_key", ["git", "url", "path"])
def test_non_registry_sourced_package_excluded(
    source_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            f'[[package]]\nname = "local-dep"\nversion = "0.1.0"\n'
            f'groups = ["default"]\n{source_key} = "some-value"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "local-dep" in caplog.text


def test_same_name_same_version_duplicate_entries_deduped() -> None:
    """PDM records a separate `[[package]]` entry per requested extra
    variant of the same package, always agreeing on `version` -- these
    must collapse to one `name==version`, not two, and not be treated
    as an ambiguous conflict."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\n'
            'groups = ["default"]\n\n'
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\n'
            'extras = ["socks"]\ngroups = ["default"]\n',
        )

        assert extract_pdm_lock_dependencies(tmp_path) == ["httpx==0.28.1"]


def test_same_name_different_casing_same_version_deduped() -> None:
    """Grouping compares PEP 503-canonicalized names, so a name that
    happens to be spelled differently across entries still collapses
    when the versions agree."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "Httpx"\nversion = "0.28.1"\n'
            'groups = ["default"]\n\n'
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\n'
            'groups = ["default"]\n',
        )

        assert extract_pdm_lock_dependencies(tmp_path) == ["Httpx==0.28.1"]


def test_same_name_different_casing_conflicting_versions_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "Httpx"\nversion = "1.0.0"\n'
            'groups = ["default"]\n\n'
            '[[package]]\nname = "httpx"\nversion = "2.0.0"\n'
            'groups = ["default"]\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "pinned to conflicting versions" in caplog.text


def test_same_name_conflicting_versions_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unlike the same-version extras-variant case, entries that
    genuinely disagree on version are ambiguous -- skip, don't guess."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "conflicted"\nversion = "1.0.0"\n'
            'groups = ["default"]\n\n'
            '[[package]]\nname = "conflicted"\nversion = "2.0.0"\n'
            'groups = ["default"]\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "pinned to conflicting versions" in caplog.text


def test_same_name_equivalent_versions_not_conflicted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "pkg"\nversion = "1.0"\n'
            'groups = ["default"]\n\n'
            '[[package]]\nname = "pkg"\nversion = "1.0.0"\n'
            'groups = ["default"]\n',
        )

        assert extract_pdm_lock_dependencies(tmp_path) == ["pkg==1.0"]
