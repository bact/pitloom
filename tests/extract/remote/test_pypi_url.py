# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a PyPI URL names (:mod:`pitloom.extract.remote.pypi_url`): the two
page forms, PEP 503 and PEP 440 spellings, and every refusal, each logged as
well as raised.

See also: tests/extract/remote/test_pypi_fetch.py (the resolver).
"""

from __future__ import annotations

import logging
import re

import pytest

from pitloom.extract.remote import pypi_url
from pitloom.extract.remote.git_url import is_git_url
from pitloom.extract.remote.pypi_url import (
    PypiTarget,
    is_pypi_url,
    parse_pypi_url,
    pypi_json_url,
)
from pitloom.messages import (
    Line,
    code_of,
)
from pitloom.messages.pypi import (
    PYPI_FILE_LINK_LINE,
    PYPI_INDEX_LINE,
    PYPI_NAME_INVALID_LINE,
    PYPI_OLD_HOST_LINE,
    PYPI_URL_CREDENTIALS_LINE,
    PYPI_URL_FORM_LINE,
    PYPI_URL_INVALID,
    PYPI_URL_SCHEME_LINE,
    PYPI_VERSION_INVALID_LINE,
)

_PAGE = "https://pypi.org/project/"


@pytest.mark.parametrize(
    ("url", "canonical", "version", "page", "cut"),
    [
        (f"{_PAGE}requests/", "requests", None, f"{_PAGE}requests/", False),
        (f"{_PAGE}requests", "requests", None, f"{_PAGE}requests/", False),
        (f"{_PAGE}requests/2.31.0/", "requests", "2.31.0", None, False),
        (f"{_PAGE}requests/2.31.0", "requests", "2.31.0", None, False),
        (f"{_PAGE}Foo_Bar.baz/", "foo-bar-baz", None, f"{_PAGE}foo-bar-baz/", False),
        ("HTTPS://WWW.PyPI.org/project/x/1.0/", "x", "1.0", f"{_PAGE}x/1.0/", False),
        (f"  {_PAGE}x/  ", "x", None, f"{_PAGE}x/", False),
        (f"{_PAGE}x/?a=1#files", "x", None, f"{_PAGE}x/", True),
        (f"{_PAGE}x/1.0#history", "x", "1.0", f"{_PAGE}x/1.0/", True),
        ("https://pypi.org:443/project/x/", "x", None, f"{_PAGE}x/", False),
        (f"{_PAGE}x/v1.0rc1/", "x", "v1.0rc1", f"{_PAGE}x/v1.0rc1/", False),
        (f"{_PAGE}%78/1%2E0/", "x", "1.0", f"{_PAGE}x/1.0/", False),
        ("https://pypi.org./project/x/1.0/", "x", "1.0", None, False),
        ("https://WWW.PYPI.ORG./project/x/", "x", None, f"{_PAGE}x/", False),
    ],
    ids=[
        "project",
        "no-slash",
        "release",
        "release-no-slash",
        "pep503",
        "case-www",
        "spaces",
        "query-cut",
        "fragment-cut",
        "port-443",
        "pep440-v-prefix",
        "percent",
        "trailing-dot",
        "trailing-dot-www",
    ],
)
def test_a_page_url_is_read(
    url: str, canonical: str, version: str | None, page: str | None, cut: bool
) -> None:
    target = parse_pypi_url(url)
    assert target.canonical == canonical
    assert target.version == version
    assert target.project_url == (page or f"{_PAGE}{canonical}/{version}/")
    assert target.cut is cut
    assert is_pypi_url(url)


def test_the_name_is_kept_as_given() -> None:
    assert parse_pypi_url(f"{_PAGE}Foo_Bar/") == PypiTarget(
        name="Foo_Bar",
        canonical="foo-bar",
        version=None,
        project_url=f"{_PAGE}foo-bar/",
    )


@pytest.mark.parametrize(
    ("url", "line"),
    [
        ("http://pypi.org/project/x/", PYPI_URL_SCHEME_LINE),
        ("HTTP://pypi.org/project/x/1.0/", PYPI_URL_SCHEME_LINE),
        ("https://user:secret@pypi.org/project/x/", PYPI_URL_CREDENTIALS_LINE),
        ("https://token@pypi.org/project/x/", PYPI_URL_CREDENTIALS_LINE),
        ("https://pypi.org/user/someone/", PYPI_URL_FORM_LINE),
        ("https://pypi.org/search/?q=x", PYPI_URL_FORM_LINE),
        ("https://pypi.org/", PYPI_URL_FORM_LINE),
        ("https://pypi.org/project/", PYPI_URL_FORM_LINE),
        ("https://pypi.org/project//1.0/", PYPI_URL_FORM_LINE),
        ("https://pypi.org/project/x/1.0/files/", PYPI_URL_FORM_LINE),
        ("https://pypi.org/Project/x/", PYPI_URL_FORM_LINE),
        ("https://pypi.org:8443/project/x/", PYPI_URL_FORM_LINE),
        ("https://pypi.org:bad/project/x/", PYPI_URL_FORM_LINE),
        ("https://test.pypi.org/project/x/", PYPI_INDEX_LINE),
        ("https://TEST.PyPI.org./project/x/1.0/", PYPI_INDEX_LINE),
        ("https://upload.pypi.org/legacy/", PYPI_INDEX_LINE),
        ("https://pypi.python.org/pypi/x", PYPI_OLD_HOST_LINE),
        ("https://PyPI.Python.org./project/x/", PYPI_OLD_HOST_LINE),
        (
            "https://files.pythonhosted.org/packages/ab/cd/x-1.0-py3-none-any.whl",
            PYPI_FILE_LINK_LINE,
        ),
        ("https://FILES.PythonHosted.org./packages/x-1.0.tar.gz", PYPI_FILE_LINK_LINE),
        ("http://files.pythonhosted.org/packages/x.whl", PYPI_URL_SCHEME_LINE),
        ("http://test.pypi.org/project/x/", PYPI_URL_SCHEME_LINE),
        ("https://u@test.pypi.org/project/x/", PYPI_URL_CREDENTIALS_LINE),
        ("https://evil.example/project/x/", PYPI_URL_FORM_LINE),
        ("ftp://pypi.org/project/x/", PYPI_URL_FORM_LINE),
        ("https://pypi.org/project/-x/", PYPI_NAME_INVALID_LINE),
        ("https://pypi.org/project/a%2Fb/", PYPI_NAME_INVALID_LINE),
        ("https://pypi.org/project/x%0A/", PYPI_NAME_INVALID_LINE),
        ("https://pypi.org/project/x/latest/", PYPI_VERSION_INVALID_LINE),
        ("https://pypi.org/project/x/1.0%20/", PYPI_VERSION_INVALID_LINE),
        ("https://pypi.org/project/x/..%2F1/", PYPI_VERSION_INVALID_LINE),
        ("https://pypi.org/project/x/1." + "9" * 5000 + "/", PYPI_VERSION_INVALID_LINE),
        ("https://pypi.org/project/\u212aeras/", PYPI_NAME_INVALID_LINE),
        ("https://pypi.org/project/%E2%84%AAeras/", PYPI_NAME_INVALID_LINE),
        ("https://pypi.org/project/\u017fix/", PYPI_NAME_INVALID_LINE),
        ("https://pypi.org/project/p\u0131p/", PYPI_NAME_INVALID_LINE),
    ],
    ids=[
        "http",
        "http-upper",
        "user-password",
        "token",
        "user-page",
        "search",
        "root",
        "no-name",
        "empty-name",
        "files-page",
        "case-project",
        "port",
        "bad-port",
        "other-index",
        "other-index-dot",
        "upload-host",
        "old-host",
        "old-host-dot",
        "file-link",
        "file-link-dot",
        "file-link-http",
        "other-index-http",
        "other-index-userinfo",
        "other-host",
        "ftp",
        "bad-name",
        "slash-name",
        "newline-name",
        "word-version",
        "space-version",
        "traversal-version",
        "overlong-version",
        "kelvin",
        "kelvin-percent",
        "long-s",
        "dotless-i",
    ],
)
def test_a_url_that_is_not_read_is_refused_aloud(
    url: str, line: Line, caplog: pytest.LogCaptureFixture
) -> None:
    """Each refusal is the catalogued line, its code on the error, and a
    ``WARNING:``; a password is never shown."""
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as info:
        parse_pypi_url(url)
    assert code_of(info.value) == PYPI_URL_INVALID.code
    tail = re.split(r"%\(\w+\)s", line.template)[-1]
    assert str(info.value).endswith(tail)
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert str(info.value) in caplog.text
    assert "secret" not in caplog.text and "secret" not in str(info.value)
    assert "\n" not in str(info.value)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://pypi.org/project/x/", True),
        ("http://PYPI.ORG/anything", True),
        ("https://www.pypi.org/", True),
        ("https://u@pypi.org/project/x/", True),
        ("https://test.pypi.org/project/x/", True),
        ("https://pypi.org./project/x/", True),
        ("https://Test.PyPI.org./project/x/", True),
        ("https://pypi.python.org/pypi/x", True),
        ("http://PYPI.PYTHON.ORG./pypi/x/1.0", True),
        ("https://pypi.org.evil.example/project/x/", False),
        ("https://notpypi.org/project/x/", False),
        ("https://python.org/pypi/x", False),
        ("https://pypi.python.org.evil.example/pypi/x", False),
        ("https://files.pythonhosted.org/packages/x.whl", True),
        ("HTTP://Files.PythonHosted.ORG./packages/x.whl", True),
        ("https://files.pythonhosted.org.evil.example/x.whl", False),
        ("https://evilfiles.pythonhosted.org/x.whl", False),
        ("https://pythonhosted.org/x.whl", False),
        ("pypi.org/project/x/", False),
        ("requests", False),
        ("https://[::1/", False),
        ("", False),
        # A host spelled as a resolver maps it.
        ("https://pypi\u3002org/project/x/", True),
        ("https://pypi\uff0eorg/project/x/", True),
        ("https://pypi\uff61org/project/x/", True),
        ("https://\uff30YPI.org/project/x/", True),
        ("https://py\u00adpi.org/project/x/", True),
        ("https://pypi%2Eorg/project/x/", True),
        ("https://pypi.org%2e/project/x/", True),
        ("https://files\uff0epythonhosted.org/x.whl", True),
        ("https://pypi%2Eorg.evil.example/x/", False),
        ("https://pypi\u3002org\u3002evil.example/x/", False),
        # IDNA refuses an empty label: NFKC alone maps it.
        ("https://x..test\u3002pypi.org/project/x/", True),
        ("https://x..pypi\u3002org.evil.example/x/", False),
    ],
    ids=[
        "page",
        "http-case",
        "www",
        "userinfo",
        "test-index",
        "trailing-dot",
        "test-index-dot",
        "old-host",
        "old-host-dot",
        "suffix-host",
        "no-dot-prefix",
        "python-org",
        "old-host-suffix",
        "file-host",
        "file-host-dot",
        "file-host-suffix",
        "file-host-prefix",
        "pythonhosted-org",
        "no-scheme",
        "name",
        "bad-url",
        "empty",
        "ideographic-dot",
        "full-width-dot",
        "half-width-dot",
        "full-width-letter",
        "soft-hyphen",
        "encoded-dot",
        "encoded-trailing-dot",
        "file-host-full-width",
        "encoded-suffix-host",
        "ideographic-suffix-host",
        "empty-label",
        "empty-label-suffix-host",
    ],
)
def test_is_pypi_url(text: str, expected: bool) -> None:
    assert is_pypi_url(text) is expected


def test_a_pypi_url_is_also_a_git_url_shape() -> None:
    """Every surface must ask :func:`is_pypi_url` first: the Git test alone
    would take the page for a repository."""
    assert is_git_url(f"{_PAGE}x/")


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [
        ("x", None, "https://pypi.org/pypi/x/json"),
        ("x", "1.0", "https://pypi.org/pypi/x/1.0/json"),
        ("a/b", "../1", "https://pypi.org/pypi/a%2Fb/..%2F1/json"),
        ("x", "1.0+local", "https://pypi.org/pypi/x/1.0%2Blocal/json"),
    ],
    ids=["project", "release", "slash", "plus"],
)
def test_the_json_url_quotes_each_segment_whole(
    name: str, version: str | None, expected: str
) -> None:
    assert pypi_json_url(name, version) == expected


def test_the_json_url_follows_the_api_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pypi_url, "API_BASE", "http://127.0.0.1:9/pypi/")
    assert pypi_json_url("x", None) == "http://127.0.0.1:9/pypi/x/json"
