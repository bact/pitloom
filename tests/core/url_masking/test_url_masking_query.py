# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.url_masking`: credentials in a URL in free
text (:func:`sanitize_url_credentials`), in a text that is one URL
(:func:`sanitize_url`, :func:`url_without_credentials`), and the module's
import contract.

See also: test_url_masking_query.py (credentials in a URL),
test_url_masking_given_path.py (a URL given as a path or in a line) and
test_url_masking_checkout.py (the temporary directories), all in this
folder.
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

import pytest

import pitloom.core.url_masking
from pitloom.core.url_masking import (
    sanitize_url,
    sanitize_url_credentials,
    url_without_credentials,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://h/r?private_token=S&h=main", "https://h/r?private_token=***&h=main"),
        ("https://h/r?a=1&Access_Token=S#f", "https://h/r?a=1&Access_Token=***#f"),
        ("https://h/r#access_token=S", "https://h/r#access_token=***"),
        (
            "https://h/r?to%6Ben=S&db-password=P",
            "https://h/r?to%6Ben=***&db-password=***",
        ),
        # The punctuation ending a sentence or quotation is not the value's.
        ("URL=https://h/r?token=S: offline", "URL=https://h/r?token=***: offline"),
        ("'https://h/r?X-Amz-Signature=S'.", "'https://h/r?X-Amz-Signature=***'."),
        ("https://h/r?token=S:x", "https://h/r?token=***"),
        # Names that only contain a secret word, and text that is no URL.
        ("https://h/r?author=1&monkey=2&design=3&tokenizer=4", None),
        ("https://h/r?oauth=1&Monkey=2&keyName=3&passport=4", None),
        ("https://h/r?id=abc&path=/key", None),
        ("pkg &key=value ;keyboard=1", None),
    ],
    ids=[
        "private",
        "mixed-case",
        "fragment",
        "encoded-name",
        "colon-after",
        "quote-after",
        "colon-inside",
        "lookalikes",
        "lookalike-words",
        "plain",
        "no-url",
    ],
)
def test_a_secret_named_query_value_is_redacted(
    text: str, expected: str | None
) -> None:
    """The name is matched whole (or by its ending), not as a substring, and
    only inside a URL."""
    assert sanitize_url_credentials(text) == (expected or text)


@pytest.mark.parametrize(
    "name",
    [
        *("token", "key", "apikey", "secret", "password", "passwd", "pass"),
        *("pwd", "pw", "sig", "signature", "jwt", "credential", "credentials"),
        *("x_token", "x-token", "x_secret", "x-secret", "x_key", "x-key"),
        *("x_password", "x-password", "x_signature", "x-signature"),
        *("auth", "authorization", "x-auth", "x_sig", "x-credential"),
        *("accessToken", "apiKey", "X-Amz-Credential", "X-Amz-Signature"),
        *("ACCESS_TOKEN", "a" * 70 + "_token", "x_passwd", "x-jwt"),
    ],
)
def test_every_secret_name_and_ending_is_redacted(name: str) -> None:
    assert sanitize_url_credentials(f"https://h/r?{name}=S") == (
        f"https://h/r?{name}=***"
    )


def test_the_query_secret_match_is_linear() -> None:
    """A server's stderr is sanitised after git exits, so its time is not
    bounded by the git timeout: a 400 KB name must not take quadratic time."""
    start = time.monotonic()
    sanitize_url_credentials("https://h/?" + "token" * 80_000)
    assert time.monotonic() - start < 5


def test_sanitize_url_credentials_redacts_user_and_password() -> None:
    assert (
        sanitize_url_credentials("https://user:password123@example.com/repo.git")
        == "https://***:***@example.com/repo.git"
    )
    assert (
        sanitize_url_credentials("git+ssh://token@gitlab.com/repo.git")
        == "git+ssh://***:***@gitlab.com/repo.git"
    )
    assert (
        sanitize_url_credentials("Error fetching https://token:secret@pypi.org/simple")
        == "Error fetching https://***:***@pypi.org/simple"
    )
    assert (
        sanitize_url_credentials("https://example.com/plain/url")
        == "https://example.com/plain/url"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://u:p@ss@h/x", "https://***:***@h/x"),
        ("https://u:p@ss@h", "https://***:***@h"),
        ("https://:pw@h/x", "https://***:***@h/x"),
        (
            "see https://u:a@b@h/p and mail me@x.org",
            "see https://***:***@h/p and mail me@x.org",
        ),
        ("https://h/p@q?x=a@b#f@g", "https://h/p@q?x=a@b#f@g"),
        ("https://h:8080/x", "https://h:8080/x"),
        ("https://u:p?ss@h/", "https://***:***@h/"),
        ("https://u:p#ss@h/", "https://***:***@h/"),
    ],
    ids=[
        "at-in-password",
        "no-path",
        "empty-user",
        "text-around",
        "at-after-path",
        "port",
        "question-mark-in-password",
        "hash-in-password",
    ],
)
def test_sanitize_url_credentials_masks_up_to_the_last_at_of_the_authority(
    text: str, expected: str
) -> None:
    assert sanitize_url_credentials(text) == expected


@pytest.mark.parametrize(
    "path",
    [r"D:\a\https:\user:SECRET@huggingface.co\o\m", "/cwd/https:/user:SECRET@h/o/m"],
    ids=["windows", "posix"],
)
def test_sanitize_url_redacts_a_url_a_path_normalisation_collapsed(path: str) -> None:
    """``https://u:p@h`` becomes ``https:/u:p@h`` (POSIX) or ``https:\\u:p@h``
    (Windows) when it is read as a path."""
    assert "SECRET" not in sanitize_url(path)


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://h/p?a=1&token=Zq'V39&b=2", "https://h/p?a=1&token=***&b=2"),
        ('https://h/p?token=Zq"V34', "https://h/p?token=***"),
        ("https://h/p?token=SEC RET;x=1", "https://h/p?token=***;x=1"),
        ("https://h/p?a=b'c#sig=S", "https://h/p?a=b'c#sig=***"),
    ],
    ids=["single-quote", "double-quote", "space", "kept"],
)
def test_sanitize_url_masks_a_secret_value_to_its_delimiter(
    url: str, shown: str
) -> None:
    """In a text that is one URL a value ends at ``&``, ``;``, ``#`` or the
    end only: a quote is a character of it (RFC 3986 allows one)."""
    assert sanitize_url(url) == shown


_FIRST_IMPORT = """
import sys
sys.path.insert(0, sys.argv[1])
import importlib
for name in sys.argv[2:]:
    importlib.import_module(name)
assert sys.modules["pitloom.core.url_masking"].mask_checkout("x") == "x"
print("ok")
"""


@pytest.mark.parametrize(
    "modules",
    [
        ["pitloom.core.url_masking", "pitloom.logging_config"],
        ["pitloom.logging_config", "pitloom.core.url_masking"],
    ],
    ids=["masking-first", "logging-first"],
)
def test_either_module_can_be_imported_first(modules: list[str]) -> None:
    """:mod:`pitloom.logging_config` uses the masking module, which must not
    import it back, whichever is imported first."""
    root = Path(pitloom.core.url_masking.__file__).parents[2]
    result = subprocess.run(  # nosec B603
        [sys.executable, "-I", "-c", _FIRST_IMPORT, str(root), *modules],
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout.decode().split() == ["ok"]


def test_every_public_function_is_exported() -> None:
    """A public function of the package (one other modules import) is in
    its ``__all__``."""
    module = pitloom.core.url_masking
    public = {
        name
        for name, value in vars(module).items()
        if not name.startswith("_")
        and callable(value)
        and getattr(value, "__module__", "") == module.__name__
    }
    assert "url_without_credentials" in public
    assert public <= set(module.__all__)


def test_the_masking_package_imports_the_standard_library_only() -> None:
    """Every module of the package imports the standard library or the
    package's own submodules."""
    package = Path(pitloom.core.url_masking.__file__).parent
    imported: set[str] = set()
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
    own = "pitloom.core.url_masking."
    outside = {name.partition(".")[0] for name in imported if not name.startswith(own)}
    assert imported and outside <= set(sys.stdlib_module_names)


@pytest.mark.parametrize(
    ("url", "kept"),
    [
        ("https://u:SECRET@h/o/r.git", "https://h/o/r.git"),
        ("https://SECRET@h:8080/r", "https://h:8080/r"),
        ("https://u:p@ss@SECRET@h/r", "https://h/r"),
        ("https://h/r?private_token=SECRET", "https://h/r?private_token=***"),
        ("https://h/r", "https://h/r"),
    ],
    ids=["user-password", "token-port", "at-in-password", "query", "none"],
)
def test_the_url_kept_on_disk_has_no_credentials(url: str, kept: str) -> None:
    assert url_without_credentials(url) == kept
