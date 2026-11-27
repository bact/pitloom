# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The remote generators refuse a bad choice or URL argument with a coded
error before anything is fetched: ``generate_git_sbom(sbom_kind=)``,
``generate_pypi_sbom(kind=)`` and the PyPI URL itself.

See also: tests/assemble/test_generate_pypi.py and
tests/assemble/test_generate_git_url.py (the routes themselves).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest

from pitloom.assemble import (
    generate_git_project_sbom,
    generate_git_sbom,
    generate_pypi_sbom,
)
from pitloom.assemble._generators_git import GIT_SBOM_KINDS
from pitloom.assemble._generators_pypi import PYPI_FILE_KINDS
from pitloom.messages import CodedTypeError, CodedValueError
from pitloom.messages.config import EXPECTED

_GIT = "https://github.com/o/r"
_PYPI = "https://pypi.org/project/demo/"


def _no_fetch(*_a: object, **_k: object) -> None:
    raise AssertionError("fetched")


@pytest.fixture(name="never_fetch")
def _never_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refusal comes before any fetch."""
    monkeypatch.setattr("pitloom.assemble._generators_git.fetch_git_project", _no_fetch)
    monkeypatch.setattr("pitloom.assemble._generators_pypi.fetch_pypi_file", _no_fetch)


@pytest.mark.parametrize(
    ("call", "error", "text"),
    [
        (
            lambda: generate_git_sbom(_GIT, sbom_kind="nope"),
            CodedValueError,
            "sbom_kind: must be one of auto, model, project, got a string 'nope'",
        ),
        (
            lambda: generate_git_sbom(_GIT, sbom_kind=cast(Any, 3)),
            CodedTypeError,
            "sbom_kind: must be one of auto, model, project, got an integer 3",
        ),
        (
            lambda: generate_pypi_sbom(_PYPI, kind="egg"),
            CodedValueError,
            "kind: must be one of sdist, wheel, got a string 'egg'",
        ),
        (
            lambda: generate_pypi_sbom(_PYPI, kind=None),
            CodedTypeError,
            "kind: must be one of sdist, wheel, got None",
        ),
        (
            lambda: generate_pypi_sbom(cast(Any, None)),
            CodedTypeError,
            "url: must be a string, got None",
        ),
    ],
    ids=["git-kind", "git-kind-type", "pypi-kind", "pypi-kind-type", "pypi-url-type"],
)
@pytest.mark.usefixtures("never_fetch")
def test_a_bad_choice_or_url_type_is_option_invalid(
    call: Callable[[], Any], error: type[Exception], text: str
) -> None:
    with pytest.raises(error) as raised:
        call()
    assert getattr(raised.value, "pitloom_code", None) == "option-invalid"
    assert text in str(raised.value)
    # A wrong type is a TypeError, a refused value a ValueError (#557).
    assert isinstance(raised.value, TypeError) is (error is CodedTypeError)


@pytest.mark.usefixtures("never_fetch")
@pytest.mark.parametrize(
    "call",
    [generate_pypi_sbom, generate_git_sbom, generate_git_project_sbom],
    ids=["pypi", "git", "git-project"],
)
@pytest.mark.parametrize("url", ["", "   "], ids=["empty", "blank"])
def test_an_empty_url_is_option_invalid(call: Callable[..., Any], url: str) -> None:
    """Refused as any empty argument is, never an internal error (an empty
    URL field cannot be written)."""
    with pytest.raises(CodedValueError) as raised:
        call(url, offline=True)
    assert raised.value.pitloom_code == "option-invalid"
    assert f"url: must be a non-empty string, got a string {url!r}" in str(raised.value)


@pytest.mark.usefixtures("never_fetch")
@pytest.mark.parametrize(
    "call", [generate_git_sbom, generate_git_project_sbom], ids=["git", "git-project"]
)
def test_a_git_url_of_another_type_is_option_invalid(call: Callable[..., Any]) -> None:
    with pytest.raises(CodedTypeError) as raised:
        call(None, offline=True)
    assert raised.value.pitloom_code == "option-invalid"
    assert "url: must be a string, got None" in str(raised.value)


@pytest.mark.usefixtures("never_fetch")
def test_a_bad_pypi_url_is_refused_before_an_option_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``pypi-url-invalid`` comes first: no option warns against a URL that
    is then refused."""
    with pytest.raises(CodedValueError) as raised:
        generate_pypi_sbom("https://example.com/x", project_dir=".", offline=True)
    assert raised.value.pitloom_code == "pypi-url-invalid"
    assert not [r for r in caplog.records if r.name.startswith("pitloom")]


@pytest.mark.parametrize(
    ("expected", "choices"),
    [("one-of-sbom-kind", GIT_SBOM_KINDS), ("one-of-pypi-kind", PYPI_FILE_KINDS)],
    ids=["git", "pypi"],
)
def test_a_choice_text_lists_the_generators_choices(
    expected: str, choices: frozenset[str]
) -> None:
    assert EXPECTED[expected] == "one of " + ", ".join(sorted(choices))
