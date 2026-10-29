# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The temporary checkout of a Git URL is written ``<checkout>`` in every
message, so two runs print the same text.

See also: tests/extract/remote/test_git_checkout_messages.py (end to end).
"""

from __future__ import annotations

import logging
import time
from pathlib import PureWindowsPath

import pytest

from pitloom.cli.kv_output import kv_line
from pitloom.core.quote_source import quote_source
from pitloom.logging_config import (
    CHECKOUT_DIR_PREFIX,
    configure_logging,
    escape_controls,
    loggable,
    mask_checkout,
)

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
