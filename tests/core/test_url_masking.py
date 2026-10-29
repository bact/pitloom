# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.url_masking`: credentials in a URL, and the
temporary checkout of a Git URL written ``<checkout>`` in every message, so
two runs print the same text.

See also: tests/extract/remote/test_git_checkout_messages.py (end to end).
"""

from __future__ import annotations

import ast
import logging
import subprocess  # nosec B404
import sys
import time
from pathlib import Path, PureWindowsPath

import pytest

import pitloom.core.url_masking
from pitloom.cli.kv_output import kv_line
from pitloom.core.quote_source import quote_source
from pitloom.core.url_masking import (
    CHECKOUT_DIR_PREFIX,
    mask_checkout,
    sanitize_url,
    sanitize_url_credentials,
)
from pitloom.logging_config import configure_logging, escape_controls, loggable

_DIR = f"/tmp/{CHECKOUT_DIR_PREFIX}v6mrrlyz"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"'{_DIR}/setup.cfg' [metadata]", "'<checkout>/setup.cfg' [metadata]"),
        (
            f"DEBUG: '{_DIR}': setuptools stderr",
            "DEBUG: '<checkout>': setuptools stderr",
        ),
        (f"({_DIR})", "(<checkout>)"),
        (f"{_DIR} and {_DIR}/a", "<checkout> and <checkout>/a"),
        (f"/var/folders/xy/T/{CHECKOUT_DIR_PREFIX}ab_12345/x", "<checkout>/x"),
        (
            str(
                PureWindowsPath("C:/Temp") / f"{CHECKOUT_DIR_PREFIX}ab12cd34" / "x.cfg"
            ),
            "<checkout>\\x.cfg",
        ),
        ("/tmp/other/setup.cfg", "/tmp/other/setup.cfg"),
        # not the checkout: a worktree of that prefix, a user-given URL, a longer name
        (f"/home/u/{CHECKOUT_DIR_PREFIX}fix/a", f"/home/u/{CHECKOUT_DIR_PREFIX}fix/a"),
        (
            f"url https://h/o/{CHECKOUT_DIR_PREFIX}tools.git failed",
            f"url https://h/o/{CHECKOUT_DIR_PREFIX}tools.git failed",
        ),
        (f"{_DIR}x/a", f"{_DIR}x/a"),
        # an address is not a path: https, scp-style, with a path repeated
        (
            f"git@host:o/{CHECKOUT_DIR_PREFIX}abcd1234 refused",
            f"git@host:o/{CHECKOUT_DIR_PREFIX}abcd1234 refused",
        ),
        (
            f"https://h/{CHECKOUT_DIR_PREFIX}abcd1234/{CHECKOUT_DIR_PREFIX}wxyz9876/",
            f"https://h/{CHECKOUT_DIR_PREFIX}abcd1234/{CHECKOUT_DIR_PREFIX}wxyz9876/",
        ),
        # a path after a query's `=` or a backtick is a path
        (f"http://h/a?p={_DIR}", "http://h/a?p=<checkout>"),
        (f"see `{_DIR}/a`", "see `<checkout>/a`"),
        # text glued to the path stays
        (f"PATH={_DIR}/a,{_DIR}/b", "PATH=<checkout>/a,<checkout>/b"),
        (f"{CHECKOUT_DIR_PREFIX} alone", f"{CHECKOUT_DIR_PREFIX} alone"),
        ("", ""),
    ],
    ids=[
        "file",
        "dir",
        "bracketed",
        "twice",
        "macos",
        "windows",
        "other-path",
        "worktree-name",
        "url",
        "longer-name",
        "scp-address",
        "url-with-two",
        "query-value",
        "backticks",
        "glued",
        "prefix-alone",
        "empty",
    ],
)
def test_the_checkout_is_masked_and_nothing_else(text: str, expected: str) -> None:
    assert mask_checkout(text) == expected
    assert mask_checkout(mask_checkout(text)) == expected


def test_a_message_is_masked_and_data_is_not() -> None:
    path = f"{_DIR}/setup.cfg"
    assert quote_source(path) == "'<checkout>/setup.cfg'"
    assert escape_controls(f"in {path}\n") == "in <checkout>/setup.cfg\\n"
    # stdout KEY=VALUE data (the Action reads PITLOOM_SBOM_OUTPUT_PATH) is not a
    # message: a real path that holds the prefix is printed as it is.
    assert loggable(path) == path
    assert kv_line(PITLOOM_SBOM_OUTPUT_PATH=path) == f"PITLOOM_SBOM_OUTPUT_PATH={path}"


def test_a_stderr_line_names_no_temporary_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    logging.getLogger("pitloom.test").warning("Could not parse %s", quote_source(_DIR))
    err = capsys.readouterr().err
    assert CHECKOUT_DIR_PREFIX not in err and "'<checkout>'" in err


@pytest.mark.parametrize(
    "text",
    [
        "a" * 1_000_000,
        f"{CHECKOUT_DIR_PREFIX}" * 50_000,
        f"x{_DIR} " * 20_000,
        "https://h/" + f"{CHECKOUT_DIR_PREFIX}abcd1234/" * 200_000,
        f"{_DIR}/" * 200_000,
    ],
    ids=["long-no-token", "token-prefix-repeated", "many-paths", "one-url", "one-path"],
)
def test_masking_is_linear(text: str) -> None:
    started = time.monotonic()
    mask_checkout(text)
    assert time.monotonic() - started < 5


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
        # Names that only contain a secret word, and text that is no URL.
        ("https://h/r?author=1&monkey=2&design=3&tokenizer=4", None),
        ("https://h/r?id=abc&path=/key", None),
        ("pkg &key=value ;keyboard=1", None),
    ],
    ids=[
        "private",
        "mixed-case",
        "fragment",
        "encoded-name",
        "lookalikes",
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


def test_the_masking_module_imports_the_standard_library_only() -> None:
    tree = ast.parse(Path(pitloom.core.url_masking.__file__).read_text("utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").partition(".")[0])
    assert imported and imported <= set(sys.stdlib_module_names)
