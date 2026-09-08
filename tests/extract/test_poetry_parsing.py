# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for low-level [tool.poetry] parsing helpers.

See also: test_poetry_extract.py for extract_poetry_metadata() tests,
split out to keep this file under this repo's file-size soft limit;
test_poetry_pyproject.py for read_pyproject() poetry-fallback, fixture
integration, and license-conflict tests.
"""

import logging

import pytest

from pitloom.extract._poetry import (
    _parse_poetry_authors,
    _parse_poetry_deps,
    _poetry_constraint_to_pep440,
    _poetry_dep_to_pep508,
)

# ---------------------------------------------------------------------------
# _parse_poetry_authors
# ---------------------------------------------------------------------------


def test_parse_authors_name_and_email() -> None:
    authors = _parse_poetry_authors(["Alice Smith <alice@example.com>"])
    assert authors == [{"name": "Alice Smith", "email": "alice@example.com"}]


def test_parse_authors_name_only() -> None:
    authors = _parse_poetry_authors(["Bob Jones"])
    assert authors == [{"name": "Bob Jones"}]


def test_parse_authors_email_only() -> None:
    authors = _parse_poetry_authors(["<carol@example.com>"])
    assert authors == [{"email": "carol@example.com"}]


def test_parse_authors_multiple() -> None:
    authors = _parse_poetry_authors(
        [
            "Alice <a@example.com>",
            "Bob <b@example.com>",
        ]
    )
    assert len(authors) == 2
    assert authors[0]["name"] == "Alice"
    assert authors[1]["name"] == "Bob"


def test_parse_authors_non_string_skipped() -> None:
    authors = _parse_poetry_authors([42, None, "Valid <v@example.com>"])
    assert len(authors) == 1
    assert authors[0]["name"] == "Valid"


def test_parse_authors_empty_list() -> None:
    assert not _parse_poetry_authors([])


# ---------------------------------------------------------------------------
# _poetry_constraint_to_pep440
# ---------------------------------------------------------------------------


def test_caret_major_positive() -> None:
    assert _poetry_constraint_to_pep440("^1.2.3") == ">=1.2.3,<2.0.0"


def test_caret_major_zero() -> None:
    assert _poetry_constraint_to_pep440("^0.3.0") == ">=0.3.0,<0.4.0"


def test_caret_major_only() -> None:
    result = _poetry_constraint_to_pep440("^3")
    assert result == ">=3,<4.0.0"


def test_tilde_with_minor() -> None:
    assert _poetry_constraint_to_pep440("~1.2.3") == ">=1.2.3,<1.3.0"


def test_tilde_major_only() -> None:
    assert _poetry_constraint_to_pep440("~2") == ">=2"


def test_wildcard_returns_none() -> None:
    assert _poetry_constraint_to_pep440("*") is None


def test_empty_returns_none() -> None:
    assert _poetry_constraint_to_pep440("") is None


def test_plain_pep440_passthrough() -> None:
    assert _poetry_constraint_to_pep440(">=2.28.0") == ">=2.28.0"
    assert _poetry_constraint_to_pep440("==1.0.0") == "==1.0.0"


def test_bare_version_becomes_exact() -> None:
    assert _poetry_constraint_to_pep440("7.4.4") == "==7.4.4"
    assert _poetry_constraint_to_pep440("4.24.0.20240129") == "==4.24.0.20240129"


def test_dict_constraint_uses_version_key() -> None:
    assert (
        _poetry_constraint_to_pep440({"version": "^2.0", "optional": True})
        == ">=2.0,<3.0.0"
    )


def test_dict_constraint_missing_version() -> None:
    assert _poetry_constraint_to_pep440({"optional": True}) is None


# ---------------------------------------------------------------------------
# _poetry_dep_to_pep508
# ---------------------------------------------------------------------------


def test_dep_caret() -> None:
    assert _poetry_dep_to_pep508("requests", "^2.28.0") == "requests>=2.28.0,<3.0.0"


def test_dep_wildcard() -> None:
    assert _poetry_dep_to_pep508("numpy", "*") == "numpy"


def test_dep_plain() -> None:
    assert _poetry_dep_to_pep508("click", ">=8.0") == "click>=8.0"


def test_dep_dict_with_version() -> None:
    result = _poetry_dep_to_pep508("boto3", {"version": "^1.20", "optional": True})
    assert result == "boto3>=1.20,<2.0.0"


def test_dep_dict_path_returns_none() -> None:
    assert _poetry_dep_to_pep508("local-pkg", {"path": "../local-pkg"}) is None


def test_dep_dict_git_returns_none() -> None:
    assert _poetry_dep_to_pep508("dev-pkg", {"git": "https://github.com/x/y"}) is None


def test_dep_dict_url_returns_none() -> None:
    assert (
        _poetry_dep_to_pep508("remote-pkg", {"url": "https://example.com/x.whl"})
        is None
    )


@pytest.mark.parametrize(
    ("name", "constraint", "source"),
    [
        ("local-pkg", {"path": "../local-pkg"}, "path"),
        ("dev-pkg", {"git": "https://github.com/x/y"}, "git"),
        ("remote-pkg", {"url": "https://example.com/x.whl"}, "url"),
    ],
)
def test_dep_skip_logs_warning(
    name: str,
    constraint: dict[str, str],
    source: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: skipping a path/git/url-sourced dependency must not be
    silent -- CLAUDE.md's "no silent deviations" rule requires a WARNING:
    explaining what was dropped and why."""
    with caplog.at_level(logging.WARNING):
        result = _poetry_dep_to_pep508(name, constraint)

    assert result is None
    assert name in caplog.text
    assert source in caplog.text


def test_parse_authors_unmatched_email_bracket_skipped() -> None:
    """An entry with an unclosed '<' fails the author regex and is skipped."""
    authors = _parse_poetry_authors(["Name <unclosed", "Valid <v@example.com>"])
    assert authors == [{"name": "Valid", "email": "v@example.com"}]


# ---------------------------------------------------------------------------
# _parse_poetry_deps
# ---------------------------------------------------------------------------


def test_parse_deps_python_extracted() -> None:
    deps = {"python": "^3.10", "requests": "^2.28"}
    packages, requires_python, python_declared = _parse_poetry_deps(deps)
    assert requires_python == ">=3.10,<4.0.0"
    assert python_declared is True
    assert any("requests" in d for d in packages)
    assert not any("python" in d for d in packages)


def test_parse_deps_no_python_key() -> None:
    deps = {"click": ">=8.0"}
    packages, requires_python, python_declared = _parse_poetry_deps(deps)
    assert requires_python is None
    assert python_declared is False
    assert any("click" in d for d in packages)


def test_parse_deps_empty() -> None:
    packages, requires_python, python_declared = _parse_poetry_deps({})
    assert not packages
    assert requires_python is None
    assert python_declared is False


def test_parse_deps_not_a_dict() -> None:
    packages, requires_python, python_declared = _parse_poetry_deps("invalid")
    assert not packages
    assert requires_python is None
    assert python_declared is False


def test_parse_deps_wildcard_python_declared_but_no_constraint() -> None:
    """`python = "*"` resolves requires_python to None, but python_declared
    must still be True -- the caller needs to distinguish "declared, no
    constraint" from "not declared at all" to gate provenance correctly."""
    deps = {"python": "*"}
    packages, requires_python, python_declared = _parse_poetry_deps(deps)
    assert requires_python is None
    assert python_declared is True
    assert not packages


def test_parse_deps_skips_unrepresentable_git_dependency() -> None:
    """A git-sourced dependency converts to None and is not appended."""
    deps = {
        "dev-pkg": {"git": "https://github.com/x/y"},
        "requests": "^2.28",
    }
    packages, requires_python, python_declared = _parse_poetry_deps(deps)
    assert requires_python is None
    assert python_declared is False
    assert not any("dev-pkg" in d for d in packages)
    assert any("requests" in d for d in packages)
