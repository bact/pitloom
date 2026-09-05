# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEP 751 ``pylock.toml`` dependency parsing
(:mod:`pitloom.extract._pylock`) and its overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`).

See also: test_poetry_lock.py for the sibling ``poetry.lock`` extractor
this module's tests mirror in shape; test_locked_dependencies.py for the
cascade mechanism's own tests (priority ordering, the ``setup.py``-only
wiring, the override provenance note).
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._pylock import _pinned_dep_for_package, extract_pylock_dependencies
from pitloom.extract.project import read_project

_LOCK_VERSION = 'lock-version = "1.0"\ncreated-by = "test"\n'
#: The "no extras, no default-groups active" environment --
#: `_pinned_dep_for_package()`'s second argument, built by
#: `extract_pylock_dependencies()` itself in normal use via
#: `_default_group_environment()`; unit tests calling the helper
#: directly supply it explicitly instead.
_NO_GROUPS_ENV: dict[str, frozenset[str]] = {
    "dependency_groups": frozenset(),
    "extras": frozenset(),
}

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pylock"
)


def _write_lock(tmp_dir: Path, packages: str = "") -> None:
    (tmp_dir / "pylock.toml").write_text(_LOCK_VERSION + packages, encoding="utf-8")


def test_no_lock_file_returns_none() -> None:
    """`None` (absent/unusable), not `[]` (valid, zero dependencies) --
    the cascade in `_locked_dependencies.py` relies on this distinction
    to let a lower-priority source apply when this one is truly absent."""
    with tempfile.TemporaryDirectory() as tmp:
        assert extract_pylock_dependencies(Path(tmp)) is None


def test_valid_lock_with_no_packages_returns_empty_list_not_none() -> None:
    """A `pylock.toml` with zero resolved packages is a real, valid
    answer -- must be `[]`, not `None`, so the cascade treats it as a
    winning (if empty) result rather than "not present"."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path)

        assert extract_pylock_dependencies(tmp_path) == []


def test_malformed_toml_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            "this is not [ valid toml", encoding="utf-8"
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "Failed to parse" in caplog.text


def test_missing_lock_version_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "lock-version" in caplog.text


@pytest.mark.parametrize("lock_version", ["garbage", "1", "1.0.0", "not.a.version"])
def test_malformed_lock_version_returns_none_and_warns(
    lock_version: str, caplog: pytest.LogCaptureFixture
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            f'lock-version = "{lock_version}"\n'
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result is None
        assert "lock-version" in caplog.text


def test_unsupported_major_lock_version_returns_none_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            'lock-version = "2.0"\n'
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result is None
        assert "major version" in caplog.text


def test_newer_minor_lock_version_still_parsed_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A newer *minor* version within the same major is forward-compatible
    per PEP 751 -- read anyway, just with a warning that some content may
    be unrecognized."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            'lock-version = "1.5"\n'
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
            encoding="utf-8",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result == ["requests==2.31.0"]
        assert "newer" in caplog.text.lower()


def test_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[packages]]\nname = "requests"\nversion = "2.31.0"\n')

        assert extract_pylock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_packages_key_not_a_list_returns_empty_list_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, 'packages = "not-a-list"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "expected a list" in caplog.text


def test_pinned_dep_for_package_non_dict_entry_returns_none() -> None:
    assert _pinned_dep_for_package("not-a-dict", _NO_GROUPS_ENV) is None
    assert (
        _pinned_dep_for_package(["still", "not", "a", "dict"], _NO_GROUPS_ENV) is None
    )


def test_malformed_package_entry_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nversion = "1.0.0"\n\n'
            '[[packages]]\nname = "complete-pkg"\nversion = "2.0.0"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result == ["complete-pkg==2.0.0"]
        assert "malformed" in caplog.text.lower()


def test_missing_version_skipped_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(tmp_path, '[[packages]]\nname = "no-version"\n')

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "missing" in caplog.text.lower()


def test_version_validated_even_when_group_marker_excludes_package(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A malformed `version` on a non-default-group (marker-excluded)
    package still warns -- version validation must not be short-circuited
    by the group/marker filter, matching poetry.lock's/pdm.lock's own
    unconditional name/version check ordering."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "dev-only"\n'
            "marker = \"'dev' in dependency_groups\"\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "missing or non-string 'version'" in caplog.text


@pytest.mark.parametrize("source_key", ["vcs", "directory", "archive"])
def test_non_registry_sourced_package_excluded(
    source_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A package pinned via `vcs`/`directory`/`archive` has no meaningful
    PyPI version pin -- excluded the same way poetry.lock's equivalent
    non-registry sources are excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "local-dep"\nversion = "0.1.0"\n'
            f'[packages.{source_key}]\nurl = "https://example.com"\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert not result
        assert "local-dep" in caplog.text


def test_sdist_sourced_package_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n'
            '[packages.sdist]\nurl = "https://example.com/requests-2.31.0.tar.gz"\n',
        )

        assert extract_pylock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_non_default_group_package_excluded() -> None:
    """Regression: a package needed only for a non-default
    dependency-group (e.g. `dev`), tagged via PEP 751's `marker` field
    referencing the `dependency_groups` pseudo-environment variable, must
    not leak into `locked_dependencies` as an ordinary runtime pin --
    the same "main"/"default"-group-only policy `poetry.lock`/`pdm.lock`
    already apply, here expressed as a marker instead of a per-package
    field."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "pytz"\nversion = "2026.1"\n\n'
            '[[packages]]\nname = "pytest"\nversion = "8.0.0"\n'
            "marker = \"'dev' in dependency_groups\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == ["pytz==2026.1"]


def test_default_group_package_included_alongside_excluded_dev_group() -> None:
    """A package whose marker combines a non-default group check with an
    ordinary (unevaluated) environment condition is still excluded on the
    group check alone -- the 3-valued evaluator doesn't need to know the
    real Python version/platform to prove the group clause is false."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "black"\nversion = "26.1.0"\n'
            "marker = \"('dev' in dependency_groups) and "
            "(python_version >= '3.10')\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == []


def test_marker_operator_precedence_and_binds_tighter_than_or() -> None:
    """Regression: PEP 508 gives `and` higher precedence than `or`, but
    `Marker()._markers` doesn't nest same-precedence terms to reflect
    that -- an unparenthesized `A or B and C` is one flat list, not
    `[A, "or", [B, "and", C]]`. A naive left-to-right fold over that flat
    list would compute `(A or B) and C` instead of the correct
    `A or (B and C)`. Here `A` is an unevaluated (unknown) environment
    condition, `B` is a *true* group-membership clause (the group IS
    active), and `C` is a *false* ordinary condition -- correct PEP 508
    semantics (`A or (B and C)`) is `unknown or (True and False)` =
    `unknown or False` = unknown, so the package must still be included
    (unknown means "can't prove excluded"). The buggy left-fold instead
    computes `(unknown or True) and False` = `True and False` = False,
    wrongly excluding it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default", "dev"]\n'
            '[[packages]]\nname = "precedence-test"\nversion = "1.0.0"\n'
            "marker = \"python_version >= '3.99' or "
            "'dev' in dependency_groups and python_version < '2.0'\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == ["precedence-test==1.0.0"]


def test_marker_operator_precedence_still_excludes_when_no_or_clause_is_true() -> None:
    """The precedence fix must not become "always include": when every
    `or`-separated group provably evaluates `False` from the known
    group/extras clauses alone (no unknown clause anywhere), the package
    is still excluded."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "still-excluded"\nversion = "1.0.0"\n'
            "marker = \"'dev' in dependency_groups or "
            "'test' in dependency_groups\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == []


def test_extras_gated_package_excluded_by_default() -> None:
    """PEP 751 supports both single-use lockfiles (one fixed purpose, no
    group/extras complexity -- every package is simply included, as the
    other tests in this file already cover via `default-groups`) and
    multi-use lockfiles, which bundle multiple installable
    configurations into one file via per-package `marker` clauses on
    *both* pseudo-environment variables PEP 751 defines for this:
    `dependency_groups` (covered above) and `extras`. A package gated on
    `'<name>' in extras` must be excluded from the default resolved set
    the same way one gated on `dependency_groups` is -- Pitloom's SBOM
    represents the base/default install with no extras requested,
    consistent with every sibling format excluding optional-dependencies/
    extras from its own default resolved set (`poetry.lock`'s `main`-only
    group, `uv.lock`'s runtime-only `dependencies`, `pdm.lock`'s
    `default`-only group)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'extras = ["security"]\n'
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n\n'
            '[[packages]]\nname = "pyopenssl"\nversion = "24.0.0"\n'
            "marker = \"'security' in extras\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == ["requests==2.31.0"]


def test_package_with_no_marker_included_regardless_of_default_groups() -> None:
    """A package with no `marker` field at all is an ordinary,
    always-active runtime dependency -- unaffected by `default-groups`
    filtering."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = []\n[[packages]]\nname = "pytz"\nversion = "2026.1"\n',
        )

        assert extract_pylock_dependencies(tmp_path) == ["pytz==2026.1"]


def test_default_groups_not_a_list_warns_and_treated_as_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = "default"\n'
            '[[packages]]\nname = "pytest"\nversion = "8.0.0"\n'
            "marker = \"'default' in dependency_groups\"\n",
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result == []
        assert "'default-groups'" in caplog.text


def test_or_combined_group_clauses_evaluated() -> None:
    """The `or` branch of the 3-valued combiner
    (`_combine_group_results`) is exercised alongside the `and` branch
    tested above -- a package needed for *either* of two non-default
    groups is still excluded when neither is active."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "black"\nversion = "26.1.0"\n'
            "marker = \"'dev' in dependency_groups or 'test' in dependency_groups\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == []


def test_or_combined_group_clauses_true_when_one_group_active() -> None:
    """The `or` combiner's `True` result (at least one side proven
    true) alongside the `False` case tested above -- a package needed
    for either of two groups is included once one of them is active."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default", "test"]\n'
            '[[packages]]\nname = "black"\nversion = "26.1.0"\n'
            "marker = \"'dev' in dependency_groups or 'test' in dependency_groups\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == ["black==26.1.0"]


def test_reversed_operand_group_clause_evaluated() -> None:
    """PEP 751 always writes the group/extras variable on the *right* of
    `in` (e.g. `"'dev' in dependency_groups"`) in real output, but PEP
    508 grammar allows either operand order -- `_evaluate_group_leaf`'s
    `elif lhs_str in _GROUP_MARKER_VARIABLES` branch (variable on the
    left) must still be reachable and correct, not just the more common
    literal-on-left form tested elsewhere."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["dev"]\n'
            '[[packages]]\nname = "black"\nversion = "26.1.0"\n'
            "marker = \"dependency_groups in 'dev'\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == ["black==26.1.0"]


def test_malformed_marker_string_included_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unparseable `marker` string can't prove group membership either
    way -- treated as the same marker-blind "include" default every
    other non-group marker gets, but with a `WARNING:` (not a crash, not
    a silent unconditional include) rather than raising `InvalidMarker`
    out of the extractor."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "broken"\nversion = "1.0.0"\n'
            'marker = "not a valid marker (("\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result == ["broken==1.0.0"]
        assert "'marker'" in caplog.text


def test_read_project_populates_locked_dependencies() -> None:
    """Integration: `read_project()`'s lock cascade overlays `pylock.toml`
    parsing onto `ProjectMetadata.locked_dependencies` with its own
    provenance entry, for a plain PEP 621 project (no `[tool.poetry]`
    involved)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(tmp_path, '[[packages]]\nname = "requests"\nversion = "2.31.0"\n')

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )


def test_read_project_no_lock_file_leaves_locked_dependencies_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance


def test_read_project_pylock_takes_priority_over_poetry_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: when both a `poetry.lock` and a `pylock.toml` are
    present, PEP 751's `pylock.toml` wins -- and the override is never
    silent: it's both logged and recorded in the provenance string."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "poetry.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            '[metadata]\nlock-version = "2.1"\n',
            encoding="utf-8",
        )
        _write_lock(tmp_path, '[[packages]]\nname = "httpx"\nversion = "0.27.0"\n')

        with caplog.at_level(logging.WARNING):
            metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile "
            "| Note: supersedes poetry.lock"
        )
        assert "poetry.lock and pylock.toml" in caplog.text
        assert "pylock.toml takes priority" in caplog.text


def test_real_world_snowflake_cli() -> None:
    """`snowflakedb/snowflake-cli` -- a real, committed `pylock.toml` at
    the GitHub tag matching its PyPI release (not in the sdist itself;
    see tests/fixtures/real-world-locks/README.md)."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "snowflake-cli-3.26.0")

    assert metadata.name == "snowflake-cli"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: pylock.toml | Method: resolved_lockfile"
    )


def test_real_world_pipenv() -> None:
    """`pypa/pipenv` -- PEP 751's own reference implementation
    (`pipenv/utils/pylock.py`), and a real, committed `pylock.toml` at
    the GitHub tag matching its PyPI release."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "pipenv-2026.8.0")

    assert metadata.name == "pipenv"
    assert metadata.locked_dependencies
    assert metadata.provenance["locked_dependencies"] == (
        "Source: pylock.toml | Method: resolved_lockfile"
    )
