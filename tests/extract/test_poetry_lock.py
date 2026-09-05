# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``poetry.lock`` transitive-dependency parsing
(:mod:`pitloom.extract._poetry_lock`).

See also: test_poetry_parsing.py for low-level ``[tool.poetry]`` parsing,
test_poetry_pyproject.py for ``read_pyproject()`` integration; this file
covers the sibling ``poetry.lock`` extractor those don't.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._poetry_lock import (
    _pinned_dep_for_package,
    extract_poetry_lock_dependencies,
)
from pitloom.extract._pyproject import read_pyproject

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
POETRY_FIXTURE = FIXTURES / "sampleproject-poetry"
REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "poetry"
)


#: Every real ``poetry lock``-generated file carries this table --
#: `extract_poetry_lock_dependencies()` uses its presence to distinguish
#: a genuine (if empty) poetry.lock from an unrelated/truncated TOML
#: document that merely happens to be named ``poetry.lock``. Prepended
#: by `_write_lock()` below so every other test in this file, which
#: exercises `package`-list handling rather than this check itself, does
#: not need to repeat it.
_METADATA = '[metadata]\nlock-version = "2.1"\n'


def _write_lock(tmp_dir: Path, content: str) -> None:
    # Appended, not prepended: a bare top-level `key = value` line in
    # *content* (e.g. a malformed `package = "not-a-list"` test fixture)
    # would otherwise land inside the `[metadata]` table itself if
    # `_METADATA`'s `[metadata]` header came first in the file.
    (tmp_dir / "poetry.lock").write_text(content + _METADATA, encoding="utf-8")


def test_no_lock_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `_locked_dependencies.py` relies on this distinction
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
        _write_lock(tmp_path, "")

        assert extract_poetry_lock_dependencies(tmp_path) == []


def test_missing_metadata_table_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a syntactically valid but empty/truncated file with no
    `[metadata]` table at all is ambiguous -- it could be a genuine
    zero-dependency poetry.lock, or it could be some unrelated TOML
    document (hand-edited, from a different tool, truncated by a bad
    write) that merely happens to be found as `poetry.lock`. Without
    this check, the latter would be silently treated as an authoritative
    empty lock and block a genuinely usable lower-priority source (e.g.
    `pdm.lock`) in the cascade -- must return `None` instead, so a lower-
    priority source can still be tried."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "poetry.lock").write_text("", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result is None
        assert "doesn't look like a genuine poetry.lock" in caplog.text


def test_metadata_table_missing_lock_version_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `[metadata]` table present but missing/non-string `lock-version`
    is just as ambiguous as no `[metadata]` table at all."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "poetry.lock").write_text(
            '[metadata]\ncontent-hash = "abc123"\n', encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert result is None
        assert "doesn't look like a genuine poetry.lock" in caplog.text


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, "this is not [ valid toml")

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_main_group_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
        )

        result = extract_poetry_lock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]


def test_dev_only_group_package_excluded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "pytest"\nversion = "8.0.0"\ngroups = ["dev"]\n',
        )

        assert not extract_poetry_lock_dependencies(tmp_path)


def test_package_in_main_and_dev_groups_included() -> None:
    """A package listed under both `main` and another group still counts
    -- only *exclusively* non-main packages are dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
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
        _write_lock(tmp_path, '[[package]]\nname = "legacy-pkg"\nversion = "1.0.0"\n')

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
        _write_lock(
            tmp_path,
            '[[package]]\nname = "odd-pkg"\nversion = "1.0.0"\ngroups = "main"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "'groups'" in caplog.text


def test_package_table_not_a_list_returns_empty_list() -> None:
    """A ``poetry.lock`` where top-level ``package`` isn't an array of
    tables (malformed/unexpected shape) must degrade to an empty list,
    not raise."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')

        assert not extract_poetry_lock_dependencies(tmp_path)


def test_pinned_dep_for_package_non_dict_entry_returns_none() -> None:
    """A ``[[package]]`` entry that isn't a table (defensive guard against
    a malformed lock file) is skipped, not a crash."""
    assert _pinned_dep_for_package("not-a-dict") is None
    assert _pinned_dep_for_package(["still", "not", "a", "dict"]) is None


def test_malformed_package_entry_skipped() -> None:
    """A package table missing ``name``/``version`` is skipped, not a
    crash -- the rest of the lock file is still processed."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "incomplete"\n\n'
            '[[package]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["complete-pkg==2.0.0"]


def test_malformed_package_entry_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Regression: a malformed ``[[package]]`` entry (missing ``version``)
    used to be dropped with zero logging, violating "no silent
    deviations" -- it must now emit a ``WARNING:``, matching the same
    ``missing or non-string 'version'`` wording every sibling format's
    own version check uses
    (:func:`pitloom.extract._lock_common.warn_missing_version`)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[package]]\nname = "incomplete"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "missing or non-string 'version'" in caplog.text


def test_missing_name_skipped_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    """A ``[[package]]`` entry missing ``name`` is validated and warned
    about separately from a missing ``version`` -- matching every
    sibling format's own split name-then-version check ordering
    (:func:`pitloom.extract._lock_common.warn_missing_name`, tried
    before ``version`` is ever read)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[package]]\nversion = "1.0.0"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "missing or non-string 'name'" in caplog.text


def test_malformed_package_entry_empty_version_skipped() -> None:
    """Regression: an entry with ``version = ""`` (a string, but empty)
    used to pass the ``isinstance(version, str)`` check and produce an
    invalid ``name==`` pin -- parity with ``_pylock.py``/``_uv_lock.py``/
    ``_pdm_lock.py``, which all also reject an empty-string version."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[package]]\nname = "broken"\nversion = ""\n\n'
            '[[package]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["complete-pkg==2.0.0"]


def test_package_table_not_a_list_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Regression: a malformed top-level ``package`` key (not a list) used
    to degrade to an empty list with zero logging."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'package = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_poetry_lock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


@pytest.mark.parametrize("source_type", ["directory", "file", "git", "url"])
def test_non_pep508_sourced_package_excluded(
    source_type: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a poetry.lock entry resolved from a local path or VCS
    has no meaningful PyPI version pin -- it must be excluded the same way
    `_poetry_dep_to_pep508()` excludes it from direct dependencies, not
    emitted as a misleading ``name==version`` PyPI pin."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
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
        _write_lock(
            tmp_path,
            '[[package]]\nname = "private-pkg"\nversion = "1.0.0"\n'
            '[package.source]\ntype = "legacy"\nurl = "https://example.com/simple"\n',
        )

        assert extract_poetry_lock_dependencies(tmp_path) == ["private-pkg==1.0.0"]


def test_fixture_lock_excludes_dev_group_dependency() -> None:
    """Real-world fixture: `pytest`/`mypy`/`ruff` live only in
    `[tool.poetry.group.dev.dependencies]` and must not appear."""
    result = extract_poetry_lock_dependencies(POETRY_FIXTURE)

    assert result is not None
    names = {dep.split("==", maxsplit=1)[0] for dep in result}
    assert "pytest" not in names
    assert "numpy" in names


def test_read_pyproject_populates_locked_dependencies() -> None:
    """Integration: `read_pyproject()` wires `poetry.lock` parsing into
    `ProjectMetadata.locked_dependencies` with its own provenance entry."""
    metadata, _config = read_pyproject(POETRY_FIXTURE / "pyproject.toml")

    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_read_pyproject_pep621_project_with_minimal_poetry_still_reads_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a PEP 621 ``[project]``-primary layout whose
    ``[tool.poetry]`` section is present only for non-metadata settings
    (no ``name`` -- a legitimate, encouraged modern style) used to raise
    inside ``extract_poetry_metadata()``, which silently suppressed
    ``poetry.lock`` reading entirely even though the two are unrelated."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n'
            '[tool.poetry]\npackages = [{include = "pkg"}]\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
        )

        with caplog.at_level(logging.WARNING):
            metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.name == "pkg"
        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: poetry.lock | Method: resolved_lockfile"
        )
        assert "could not be parsed" in caplog.text


def test_read_pyproject_no_lock_file_leaves_locked_dependencies_empty() -> None:
    """A Poetry project with no `poetry.lock` at all gets an empty
    `locked_dependencies` and no provenance entry for it -- optional
    enrichment, never a requirement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        metadata, _config = read_pyproject(tmp_path / "pyproject.toml")

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance


def test_real_world_pendulum_hybrid_project_and_tool_poetry_tables() -> None:
    """`pendulum` declares both `[project]` (PEP 621) and `[tool.poetry]`
    -- confirms the hybrid shape resolves name/version via `[project]`
    while `poetry.lock` reading still runs."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "pendulum-3.2.0" / "pyproject.toml"
    )

    assert metadata.name == "pendulum"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_real_world_cleo_tool_poetry_only() -> None:
    """`cleo` has `[tool.poetry]` only, no `[project]` table at all."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "cleo-2.1.0" / "pyproject.toml"
    )

    assert metadata.name == "cleo"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_real_world_pastel_tool_poetry_only() -> None:
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "pastel-0.2.1" / "pyproject.toml"
    )

    assert metadata.name == "pastel"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_real_world_tomlkit_has_no_main_group_dependencies() -> None:
    """`tomlkit` is a standalone TOML library with no runtime
    dependencies -- every entry in its `poetry.lock` belongs to the
    `dev`/docs/test groups, none to `main`. A real, valid "empty resolved
    set" case: `read_pyproject()` still succeeds, leaves
    `locked_dependencies` empty, but *does* record provenance for it --
    a real, parsed ``poetry.lock`` that authoritatively resolves to zero
    ``main``-group packages is a genuine answer, not the same as no lock
    file being present at all (see ``_locked_dependencies.py``'s
    None-vs-``[]`` extractor contract)."""
    metadata, _config = read_pyproject(
        REAL_WORLD_LOCKS / "tomlkit-0.15.1" / "pyproject.toml"
    )

    assert metadata.name == "tomlkit"
    assert metadata.locked_dependencies == []
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )
