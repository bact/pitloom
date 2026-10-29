# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency name/version parsing and PURL/installed
enrichment in SPDX 3 SBOMs.

See also: test_deps_enrichment_originator_license.py,
test_deps_enrichment_pypi_fallback.py, test_deps_enrichment_prefetch.py --
the siblings for the rest of dependency enrichment;
test_deps_enrichment_purl_license.py, the other cause of "Package
identifiers missing" (a missing no-version PURL fallback) and a
silently-discarded license relationship.

Covers one cause of "Package identifiers missing": name parsing.
"""

# pylint: disable=protected-access
# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging

import pytest

from pitloom.assemble.spdx3 import deps_installed as deps_mod
from pitloom.assemble.spdx3.deps import (
    _parse_dep_name,
    _resolve_version,
)
from pitloom.core.provenance import parse_provenance_value

# ---------------------------------------------------------------------------
# _parse_dep_name -- environment markers and multi-clause specifiers
# ---------------------------------------------------------------------------


def test_parse_dep_name_strips_environment_marker() -> None:
    """A marker's own ``==`` comparison must not be mistaken for the
    specifier's version operator.

    Real case: ``auditwheel>=6.7.0; sys_platform == 'linux'`` (a dependency
    in Pitloom's own ``pyproject.toml``) must give ``auditwheel``, not the
    garbled ``"auditwheel>=6.7.0; sys_platform"``.
    """
    assert _parse_dep_name("auditwheel>=6.7.0; sys_platform == 'linux'") == "auditwheel"


def test_parse_dep_name_strips_python_version_marker() -> None:
    assert _parse_dep_name("tomli>=2.4.1; python_version<'3.11'") == "tomli"


def test_parse_dep_name_handles_multi_clause_specifier() -> None:
    """A later clause's operator must not be matched ahead of an earlier one.

    Real case: ``py-spdx-license>=0.0.1,<1`` must give ``py-spdx-license``,
    not ``"py-spdx-license<1,"``, after ``packaging.Requirement`` reorders
    the specifier set.
    """
    assert _parse_dep_name("py-spdx-license>=0.0.1,<1") == "py-spdx-license"
    assert _parse_dep_name("pyyaml>=6.0.3,<7") == "pyyaml"


def test_parse_dep_name_plain_specifier_still_works() -> None:
    assert _parse_dep_name("hatchling>=1.29.0") == "hatchling"


def test_an_unparsed_name_forges_no_provenance_segment() -> None:
    """A requirement with no name at its start is kept whole: its ``|``
    must not add an ``Evidence:`` segment to the metadata provenance."""
    name = _parse_dep_name("| Evidence: not_measured")
    assert "|" in name
    source = deps_mod.package_provenance_source("PyPI JSON API", name)
    assert source == "Source: PyPI JSON API | Package: / Evidence: not_measured"
    assert "evidence" not in parse_provenance_value(source)
    assert _parse_dep_name("numpy==1.24.0") == "numpy"
    assert _parse_dep_name("click") == "click"


# ---------------------------------------------------------------------------
# _resolve_version -- a marker's "==" must not be mistaken for a version pin
# ---------------------------------------------------------------------------


def test_resolve_version_ignores_marker_equality() -> None:
    """A marker's ``sys_platform == 'linux'`` comparison is not a pin: an
    uninstalled, unpinned dependency resolves to ``"unknown"``."""
    version, note = _resolve_version(
        "not-installed-xyz", "not-installed-xyz>=1.0; sys_platform == 'linux'"
    )
    assert version == "unknown"
    assert note is None


def test_resolve_version_extracts_real_pin() -> None:
    version, note = _resolve_version("not-installed-xyz", "not-installed-xyz==2.5.0")
    assert version == "2.5.0"
    assert note is None


def test_resolve_version_multi_clause_no_pin_is_unknown() -> None:
    version, _ = _resolve_version("not-installed-xyz", "not-installed-xyz>=0.1,<1")
    assert version == "unknown"


def test_resolve_version_extracts_arbitrary_equality_pin() -> None:
    """PEP 440 arbitrary-equality '===' pins resolve to their version, like
    '==' pins."""
    version, note = _resolve_version("not-installed-xyz", "not-installed-xyz===1.0")
    assert version == "1.0"
    assert note is None


def test_resolve_version_falls_back_to_naive_split_for_unparseable_dep() -> None:
    """A dependency string packaging.Requirement can't parse at all still
    recovers a best-effort pinned version via a naive '==' substring split,
    distinct from the marker case the Requirement-based path handles."""
    # A stray space makes this invalid PEP 508, but packaging.Requirement
    # not being able to parse it doesn't mean a version can't be recovered.
    version, note = _resolve_version("not installed", "not installed==2.0")
    assert version == "2.0"
    assert note is None

    version_arb, note_arb = _resolve_version(
        "not installed", "not installed===2021.01.01-legacy"
    )
    assert version_arb == "2021.01.01-legacy"
    assert note_arb is None


def test_resolve_version_exact_pin_wins_over_mismatched_installed_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exact ``==`` pin (e.g. a resolved ``poetry.lock``
    entry) is authoritative even when a *different* version of the same
    package happens to be installed in Pitloom's own execution
    environment -- that environment has no relationship to the target
    project's environment and must never silently override a real pin."""
    monkeypatch.setattr(deps_mod, "get_package_version", lambda _name: "3.19")

    version, note = _resolve_version("idna", "idna==3.7")

    assert version == "3.7"
    assert note is None


def test_resolve_version_falls_back_to_installed_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The installed-environment lookup still applies -- as a fallback --
    for the common case where the constraint doesn't pin an exact version."""
    monkeypatch.setattr(deps_mod, "get_package_version", lambda _name: "2.32.0")

    version, note = _resolve_version("requests", "requests>=2.0")

    assert version == "2.32.0"
    assert note == "Version resolved: Build-time environment (importlib.metadata)"


def test_resolve_version_uses_locked_version_over_installed_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per GEMINI.md ("Explicit pin beats local environment"): when a lock
    file pins an exact version for a dependency declared with a range,
    the lock pin is authoritative and Pitloom's host environment is never
    consulted."""
    monkeypatch.setattr(
        deps_mod,
        "get_package_version",
        lambda _name: pytest.fail("host environment should not be consulted"),
    )

    version, note = _resolve_version(
        "requests", "requests>=2.0", locked_version="2.31.0"
    )

    assert version == "2.31.0"
    assert note == "Version resolved: Project lock file"


def test_resolve_version_warns_when_locked_version_violates_declared_constraint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When a lock file's pinned version does not satisfy the declared constraint,
    a warning is logged explaining the lockfile version overrides the constraint."""
    with caplog.at_level(logging.WARNING):
        version, note = _resolve_version(
            "requests", "requests<2.0", locked_version="2.31.0"
        )

    assert version == "2.31.0"
    assert note == "Version resolved: Project lock file"
    assert "does not satisfy declared constraint" in caplog.text
    assert "requests<2.0" in caplog.text


def test_resolve_version_exact_pin_wins_over_conflicting_locked_version(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When a dependency declares an exact pin (requests==2.30.0), that pin
    is authoritative and wins outright over a conflicting locked version (2.31.0),
    emitting a warning about the conflict."""
    with caplog.at_level(logging.WARNING):
        version, note = _resolve_version(
            "requests", "requests==2.30.0", locked_version="2.31.0"
        )

    assert version == "2.30.0"
    assert note is None
    assert "conflicts with declared exact pin '2.30.0'" in caplog.text
    assert "'2.31.0'" in caplog.text


def test_resolve_version_exact_pin_matching_locked_version_emits_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When a dependency's exact pin matches the locked version, no conflict warning
    is emitted."""
    with caplog.at_level(logging.WARNING):
        version, note = _resolve_version(
            "requests", "requests==2.30.0", locked_version="2.30.0"
        )

    assert version == "2.30.0"
    assert note is None
    assert "conflicts with declared exact pin" not in caplog.text
