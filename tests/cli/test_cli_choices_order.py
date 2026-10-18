# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Option choices are listed in the same order on every run, whatever the
string hash seed (a ``frozenset`` passed to ``choices=`` is not)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.build_and_read_shared import pitloom_subprocess_env

_SEEDS = ("1", "2", "3", "4")


def _run(seed: str, *args: str) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "pitloom", "generate", *args],
        capture_output=True,
        check=False,
        env=pitloom_subprocess_env(PYTHONHASHSEED=seed),
        timeout=60,
    )
    return (done.stdout + done.stderr).decode("utf-8")


@pytest.mark.parametrize(
    ("args", "listed"),
    [
        (("--help",), "{auto,extension,magika}"),
        (("--content-type-method", "bogus"), "'auto', 'extension', 'magika'"),
        (("--creator-type", "bogus"), None),
    ],
    ids=["help", "content-type-method-error", "creator-type-error"],
)
def test_choices_do_not_depend_on_the_hash_seed(
    args: tuple[str, ...], listed: str | None
) -> None:
    outputs = {_run(seed, *args) for seed in _SEEDS}
    assert len(outputs) == 1
    if listed is not None:
        assert listed in outputs.pop()
