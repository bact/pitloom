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
        (f"/var/folders/xy/T/{CHECKOUT_DIR_PREFIX}ab_1/x", "<checkout>/x"),
        (
            str(PureWindowsPath("C:/Temp") / f"{CHECKOUT_DIR_PREFIX}ab12" / "x.cfg"),
            "<checkout>\\x.cfg",
        ),
        ("/tmp/other/setup.cfg", "/tmp/other/setup.cfg"),
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
        "prefix-alone",
        "empty",
    ],
)
def test_the_checkout_is_masked_and_nothing_else(text: str, expected: str) -> None:
    assert mask_checkout(text) == expected
    assert mask_checkout(mask_checkout(text)) == expected


def test_every_text_a_message_goes_through_masks_it() -> None:
    path = f"{_DIR}/setup.cfg"
    assert quote_source(path) == "'<checkout>/setup.cfg'"
    assert loggable(path) == "<checkout>/setup.cfg"
    assert escape_controls(f"in {path}\n") == "in <checkout>/setup.cfg\\n"


def test_a_stderr_line_names_no_temporary_directory(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    logging.getLogger("pitloom.test").warning("Could not parse %s", quote_source(_DIR))
    err = capsys.readouterr().err
    assert CHECKOUT_DIR_PREFIX not in err and "'<checkout>'" in err


@pytest.mark.parametrize(
    "text",
    ["a" * 1_000_000, f"{CHECKOUT_DIR_PREFIX}" * 50_000, f"x{_DIR} " * 20_000],
    ids=["long-no-token", "token-prefix-repeated", "many-paths"],
)
def test_masking_is_linear(text: str) -> None:
    started = time.monotonic()
    mask_checkout(text)
    assert time.monotonic() - started < 5
