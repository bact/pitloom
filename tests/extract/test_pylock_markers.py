# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for PEP 751 ``pylock.toml``'s ``dependency_groups``/``extras``
marker evaluation (:mod:`pitloom.extract._pylock`'s group/marker
filtering, including the 3-valued PEP 508 precedence evaluator).

Split out of test_pylock.py (which covers this same module's basic
per-package parsing/validation and its ``read_project()`` cascade
integration) once the marker-evaluation cluster alone grew past this
repo's own per-file line-count guidance -- see test_pylock.py's own
module docstring for the sibling-file map.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract._pylock import extract_pylock_dependencies

_LOCK_VERSION = 'lock-version = "1.0"\ncreated-by = "test"\n'


def _write_lock(tmp_dir: Path, packages: str = "") -> None:
    (tmp_dir / "pylock.toml").write_text(_LOCK_VERSION + packages, encoding="utf-8")


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


def test_reversed_operand_extra_clause_evaluated() -> None:
    """PEP 508 allows either operand order for extra comparisons --
    `'dev' == extra` (variable on the right) must evaluate identically to
    `extra == 'dev'`, and both are correctly excluded when extras is empty."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "black"\nversion = "26.1.0"\n'
            "marker = \"'dev' == extra\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == []


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


def test_default_group_canonicalized_name_matching() -> None:
    """Under PEP 735 / PEP 503, dependency group and extra names are
    case-insensitive and treat '-', '_', and '.' as equivalent.
    Verifies that 'main_deps' matches 'main-deps' and 'Dev_Group'
    matches 'dev-group'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["main-deps", "Dev_Group"]\n'
            '[[packages]]\nname = "pkg1"\nversion = "1.0.0"\n'
            "marker = \"'main_deps' in dependency_groups\"\n\n"
            '[[packages]]\nname = "pkg2"\nversion = "2.0.0"\n'
            "marker = \"'dev-group' in dependency_groups\"\n\n"
            '[[packages]]\nname = "pkg3"\nversion = "3.0.0"\n'
            "marker = \"'other-group' in dependency_groups\"\n",
        )

        assert extract_pylock_dependencies(tmp_path) == [
            "pkg1==1.0.0",
            "pkg2==2.0.0",
        ]


def test_malformed_non_string_marker_skipped_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            '[[packages]]\nname = "broken"\nversion = "1.0.0"\nmarker = 123\n',
        )

        with caplog.at_level(logging.WARNING):
            result = extract_pylock_dependencies(tmp_path)

        assert result == []
        assert "'marker' is int" in caplog.text


def test_marker_not_in_and_not_equal_operators() -> None:
    """Markers using 'not in' and '!=' operators must evaluate correctly against
    the active environment."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "included-not-in"\nversion = "1.0.0"\n'
            "marker = \"'dev' not in dependency_groups\"\n\n"
            '[[packages]]\nname = "excluded-not-in"\nversion = "1.0.0"\n'
            "marker = \"'default' not in dependency_groups\"\n\n"
            '[[packages]]\nname = "included-not-equal"\nversion = "1.0.0"\n'
            "marker = \"extra != 'dev'\"\n\n"
            '[[packages]]\nname = "excluded-equal"\nversion = "1.0.0"\n'
            "marker = \"extra == 'dev'\"\n",
        )

        deps = extract_pylock_dependencies(tmp_path)
        assert deps is not None
        assert set(deps) == {"included-not-in==1.0.0", "included-not-equal==1.0.0"}


def test_marker_invalid_operators_treated_as_unknown() -> None:
    """Clauses with invalid operators on dependency_groups (e.g. ==) or extra
    (e.g. >=) return None ("unknown") and do not exclude the package."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_lock(
            tmp_path,
            'default-groups = ["default"]\n'
            '[[packages]]\nname = "group-eq"\nversion = "1.0.0"\n'
            "marker = \"dependency_groups == 'default'\"\n\n"
            '[[packages]]\nname = "extra-gte"\nversion = "1.0.0"\n'
            "marker = \"extra >= '1.0'\"\n",
        )

        deps = extract_pylock_dependencies(tmp_path)
        assert deps is not None
        assert set(deps) == {"group-eq==1.0.0", "extra-gte==1.0.0"}
