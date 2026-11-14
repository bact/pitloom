# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.url_masking`: the temporary checkout of a Git
URL, and the download directory, written ``<checkout>`` or ``<download>`` in
every message, so two runs print the same text.

See also: test_url_masking_query.py (credentials in a URL),
test_url_masking_given_path.py (a URL given as a path or in a line) and
test_url_masking_checkout.py (the temporary directories), all in this
folder.
Also: tests/extract/remote/test_git_checkout_messages.py (end to end).
"""

from __future__ import annotations

import logging
import time
from pathlib import PureWindowsPath

import pytest

from pitloom.cli.kv_output import kv_line
from pitloom.core.quote_source import quote_source
from pitloom.core.url_masking import (
    CHECKOUT_DIR_PREFIX,
    DOWNLOAD_DIR_PREFIX,
    mask_checkout,
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
