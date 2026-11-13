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
    DOWNLOAD_DIR_PREFIX,
    mask_checkout,
    masked_given_path,
    sanitize_url,
    sanitize_url_credentials,
    url_without_credentials,
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


_DOWNLOAD = f"{DOWNLOAD_DIR_PREFIX}k2p9_x1z"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            f"/tmp/{_DOWNLOAD}/x-1.0-py3-none-any.whl",
            "<download>/x-1.0-py3-none-any.whl",
        ),
        (
            str(PureWindowsPath("C:/Temp") / _DOWNLOAD / "x-1.0.tar.gz"),
            "<download>\\x-1.0.tar.gz",
        ),
        (f"'/tmp/{_DOWNLOAD}' and {_DIR}", "'<download>' and <checkout>"),
        (f"/tmp/{_DOWNLOAD}/{CHECKOUT_DIR_PREFIX}ab12cd34", "<checkout>"),
        (f"/home/u/{DOWNLOAD_DIR_PREFIX}fix/a", f"/home/u/{DOWNLOAD_DIR_PREFIX}fix/a"),
        (f"https://h/{_DOWNLOAD}/x.whl", f"https://h/{_DOWNLOAD}/x.whl"),
        (f"/tmp/{_DOWNLOAD}x/a", f"/tmp/{_DOWNLOAD}x/a"),
    ],
    ids=["posix", "windows", "both", "nested", "other-name", "url", "longer-name"],
)
def test_the_download_directory_is_masked(text: str, expected: str) -> None:
    assert mask_checkout(text) == expected
    assert mask_checkout(mask_checkout(text)) == expected


_SPACED = PureWindowsPath("C:/Users/John Smith/AppData/Local/Temp")


@pytest.mark.parametrize(
    ("prefix", "placeholder"),
    [(DOWNLOAD_DIR_PREFIX, "<download>"), (CHECKOUT_DIR_PREFIX, "<checkout>")],
    ids=["pypi", "git"],
)
@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{path}", "{ph}\\x.whl"),
        ("reading {path} now", "reading {ph}\\x.whl now"),
        ("read '{path}'", "read '{ph}\\x.whl'"),
        ("FILE={path}", "FILE={ph}\\x.whl"),
        ("copy /a/b to {path}", "copy /a/b to {ph}\\x.whl"),
        ("a\n{path}", "a\n{ph}\\x.whl"),
    ],
    ids=["alone", "in-text", "quoted", "key", "after-a-path", "new-line"],
)
def test_a_path_with_spaces_is_masked_from_its_root(
    prefix: str, placeholder: str, template: str, expected: str
) -> None:
    """A temporary directory under a user folder with a space: the whole
    path is masked, never the part before the space (the user's name)."""
    path = str(_SPACED / f"{prefix}abcd1234" / "x.whl")
    masked = mask_checkout(template.format(path=path))
    assert masked == expected.format(ph=placeholder)
    assert "John" not in masked


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "/home/J S/t/pitloom-pypi-abcd1234/x y",
            "<download>/x y",
        ),
        (
            "failed to read /tmp/pitloom-git-abcd1234/a ok",
            "failed to read <checkout>/a ok",
        ),
        ("see John Smith/pitloom-pypi-abcd1234/x", "see John <download>/x"),
        (
            "\\\\srv\\J S\\pitloom-pypi-abcd1234\\x",
            "<download>\\x",
        ),
        (
            "copy /a/b to /tmp/pitloom-git-abcd1234/x",
            "copy /a/b to <checkout>/x",
        ),
        (
            "see /etc/x 'John Smith/pitloom-pypi-abcd1234/x'",
            "see /etc/x 'John <download>/x'",
        ),
    ],
    ids=["posix-space", "word-at-root", "no-root", "unc", "after-a-path", "quote"],
)
def test_the_path_start(text: str, expected: str) -> None:
    assert mask_checkout(text) == expected


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
        ("https://h/r?oauth=1&Monkey=2&keyName=3&passport=4", None),
        ("https://h/r?id=abc&path=/key", None),
        ("pkg &key=value ;keyboard=1", None),
    ],
    ids=[
        "private",
        "mixed-case",
        "fragment",
        "encoded-name",
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
    ("given", "shown"),
    [
        ("https:/user:SECRET@h/x", "https://***:***@h/x"),
        ("https:/h/x?token=SECRET", "https://h/x?token=***"),
        (
            "/cwd/https:/h/x?a=1&access_token=SECRET",
            "/cwd/https://h/x?a=1&access_token=***",
        ),
        ("https:/h/x#access_token=SECRET", "https://h/x#access_token=***"),
        ("https:\\\\h\\x?token=SECRET", "https://h/x?token=***"),
        (r"D:\a\https:\u:SECRET@h\x", r"D:\a\https://***:***@h/x"),
        (
            "ftp:/u:SECRET@h/x-1-py3-none-any.whl",
            "ftp://***:***@h/x-1-py3-none-any.whl",
        ),
        ("git+https:/h/r?private_token=SECRET", "git+https://h/r?private_token=***"),
        ("ssh:/u:SECRET@h/r", "ssh://***:***@h/r"),
        ("HTTPS:/h/x?token=SECRET", "HTTPS://h/x?token=***"),
        # Nothing to mask: the text as given, separators and all.
        ("https:/h/x?q=1", "https:/h/x?q=1"),
        (r"https:\h\x", r"https:\h\x"),
        (r"C:\dir\x?token=SECRET", r"C:\dir\x?token=SECRET"),
        ("a:/x?token=SECRET", "a:/x?token=SECRET"),
        ("dir/x.whl", "dir/x.whl"),
        # A value runs over a space or a line break, to a delimiter or quote.
        ("https:/h/x?token=SEC RET&a=1", "https://h/x?token=***&a=1"),
        ("https:/h/x?token=SEC\nRET", "https://h/x?token=***"),
        # A digit before the scheme is not part of it.
        ("1https://u:SECRET@h", "1https://***:***@h"),
        # After ``://`` a backslash is the password's; after ``:\`` it may
        # be, so the userinfo runs to the last ``@``.
        ("https://u:SEC\\RET@h/", "https://***:***@h/"),
        ("https:\\u:SEC\\RET@h\\x", "https://***:***@h/x"),
        ("https:\\h\\p@q", "https://***:***@q"),
        # Each URL of a message, each to the quote closing it.
        (
            "invalid choice: 'https:/u:SECRET@h' (choose from 'a@b', 'c')",
            "invalid choice: 'https://***:***@h' (choose from 'a@b', 'c')",
        ),
        (
            "'https://h/?token=SECRET' and \"ftp:/u:SECRET@h\" 'ab:/x'",
            "'https://h/?token=***' and \"ftp://***:***@h\" 'ab:/x'",
        ),
        ("'https:/u:SECRET@h", "'https://***:***@h"),
    ],
    ids=[
        "userinfo",
        "query-token",
        "access-token-after-amp",
        "fragment-token",
        "windows-backslashes",
        "windows-under-a-drive",
        "ftp",
        "git-plus-https",
        "ssh",
        "upper-case-scheme",
        "nothing-to-mask",
        "nothing-to-mask-windows",
        "windows-drive-is-no-scheme",
        "one-letter-is-no-scheme",
        "plain-path",
        "value-over-a-space",
        "value-over-a-newline",
        "digit-before-scheme",
        "backslash-in-password",
        "windows-backslash-in-password",
        "windows-at-in-path",
        "quoted-in-a-message",
        "two-quoted-urls",
        "unclosed-quote",
    ],
)
def test_a_url_given_as_a_path_is_masked(given: str, shown: str) -> None:
    """``Path`` collapses ``//`` to ``/`` (and Windows writes ``\\``):
    the URL is read back with ``://`` so its query and userinfo are masked,
    any scheme of two or more characters; a drive letter is not a scheme."""
    assert masked_given_path(given) == shown


@pytest.mark.parametrize("make", [Path, PureWindowsPath], ids=["native", "windows"])
def test_a_url_through_a_path_is_masked(
    make: type[Path] | type[PureWindowsPath],
) -> None:
    """What argparse's ``Path`` makes of a URL is masked on every platform."""
    given = str(make("https://h/x?token=SECRET&f=x-1-py3-none-any.whl"))
    assert "//" not in given
    assert "SECRET" not in masked_given_path(given)


@pytest.mark.parametrize(
    "text",
    [
        "https://" + "a" * 1_000_000 + "?" + "x=1&" * 250_000,
        "https://h/?" + "aB" * 500_000 + "=1",
        "https:\\" + "@\\" * 330_000,
        "https:/" + "?" + "a" * 1_000_000,
        "'ab:/=" * 160_000,
    ],
    ids=["long-query", "long-camel-name", "windows-ats", "long-name", "many-urls"],
)
def test_a_given_path_is_masked_in_linear_time(text: str) -> None:
    """A text of a million characters is masked in linear time: about 0.1 s
    here, and a quadratic masker takes minutes; the bound leaves room for
    coverage tracing on a loaded runner."""
    started = time.perf_counter()
    masked_given_path(text)
    assert time.perf_counter() - started < 1


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
