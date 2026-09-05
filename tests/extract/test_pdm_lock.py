# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PDM ``pdm.lock`` resolved-dependency parsing
(:mod:`pitloom.extract._pdm_lock`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`).

See also: test_poetry_lock.py/test_uv_lock.py for the sibling lock
extractors this module's tests mirror in shape;
test_locked_dependencies.py for the cascade mechanism's own tests,
including the priority-order-consistency regression this format's
below-``poetry.lock`` rank exercises.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._pdm_lock import extract_pdm_lock_dependencies
from pitloom.extract.project import read_project

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pdm"
)


def _write_lock(tmp_dir: Path, body: str = "") -> None:
    (tmp_dir / "pdm.lock").write_text(body, encoding="utf-8")


def test_no_lock_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `_locked_dependencies.py` relies on this distinction
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


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "this is not [ valid toml")

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_package_key_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_pdm_lock_dependencies(tmp_path)

        assert not result
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


# --- read_project() cascade integration -----------------------------------


def test_read_project_populates_locked_dependencies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'groups = ["default"]\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pdm.lock | Method: resolved_lockfile"
        )


def test_read_project_pdm_lock_never_overrides_poetry_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: `pdm.lock` ranks *below* `poetry.lock` in the shared
    priority order -- when both are present (an unusual but possible
    project layout), `poetry.lock`'s already-applied result must win,
    and `pdm.lock` must never silently override it. This is the exact
    class of bug a naive "first entry with data wins" cascade would
    introduce once a lower-than-`poetry.lock`-ranked format is added."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "poetry.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            '[metadata]\nlock-version = "2.1"\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n',
        )

        with caplog.at_level(logging.WARNING):
            metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: poetry.lock | Method: resolved_lockfile"
        )
        assert "supersedes" not in caplog.text


def test_read_project_pdm_lock_used_when_no_poetry_lock_present() -> None:
    """A non-Poetry project (no `[tool.poetry]` at all, so `poetry.lock`
    was never applied) still gets `pdm.lock`'s data normally -- the
    priority-order gate only blocks *actual* higher-ranked data, not the
    mere possibility of it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.28.1"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pdm.lock | Method: resolved_lockfile"
        )


def test_read_project_uv_lock_still_overrides_pdm_lock() -> None:
    """`uv.lock` outranks `pdm.lock` -- confirm adding `pdm.lock` to the
    cascade didn't disturb the existing higher-priority entries."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "uv.lock").write_text(
            'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: uv.lock | Method: resolved_lockfile"
        )


# --- real-world fixtures ---------------------------------------------------


def test_real_world_pdm() -> None:
    """`pdm-project/pdm` -- PDM's own package (self-hosting case)."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "pdm-2.29.0")

    assert metadata.name == "pdm"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert "httpx" in names
    assert "coverage" not in names  # test-group only
    assert metadata.provenance["locked_dependencies"] == (
        "Source: pdm.lock | Method: resolved_lockfile"
    )


def test_real_world_unearth() -> None:
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "unearth-0.18.3")

    assert metadata.name == "unearth"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert "anyio" in names
    assert "sphinx" not in names  # doc-group only, per the unearth pdm.lock sample
