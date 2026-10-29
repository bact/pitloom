# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message ratchet: the number of emission sites in ``src/pitloom`` that
say no catalogued message (no `` [code]``) may only fall, per module and in
total.

A new uncoded site raises its module's count and fails the first test: give
the message a code in :mod:`pitloom.messages`. A coded or removed site lowers
the count below the baseline and fails it too, so the gain is written down:
regenerate the baseline (the failure says how) and commit it.

See also: ``scripts/message_inventory/`` (the tool and what counts),
``tests/fixtures/message-inventory/`` (the baseline),
``tests/scripts/message_inventory/`` (the tool's own tests).
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

import pytest

from tests._message_inventory import REPO_ROOT, load

#: Sites already coded: (file, emitter) of the Git LFS pointer families and of
#: ``over-cap`` (the catalogue's helper, a wrapper of it, and the raises).
CODED_SITES = [
    ("src/pitloom/core/lfs_pointer.py", "emit"),
    ("src/pitloom/core/lfs_pointer.py", "raise"),
    ("src/pitloom/extract/scanner.py", "emit"),
    ("src/pitloom/extract/scanner.py", "warn_over_cap"),
    ("src/pitloom/extract/authors.py", "warn_field_cap"),
    ("src/pitloom/extract/project/sdist.py", "raise"),
    ("src/pitloom/extract/remote/_git_run.py", "raise"),
]


@pytest.fixture(name="records", scope="module")
def records_fixture() -> list[dict[str, Any]]:
    """Every emission site of the repository's own ``src/pitloom``."""
    return load().inventory(REPO_ROOT)  # type: ignore[no-any-return]


def test_no_module_gains_or_silently_loses_an_uncoded_site(
    records: list[dict[str, Any]],
) -> None:
    mi = load()
    text = (REPO_ROOT / mi.BASELINE_PATH).read_text(encoding="utf-8")
    problems = mi.compare(mi.parse_baseline(text), mi.uncoded_counts(records))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("file", "emitter"),
    CODED_SITES,
    ids=[
        "emit",
        "raise",
        "scanner-emit",
        "over-cap",
        "over-cap-wrapper",
        "over-cap-sdist",
        "over-cap-git",
    ],
)
def test_the_tool_sees_the_catalogued_sites_as_coded(
    records: list[dict[str, Any]], file: str, emitter: str
) -> None:
    sites = [r for r in records if r["file"] == file and r["emitter"] == emitter]
    assert any(r["coded"] for r in sites)
    assert any(load().in_scope(r) for r in sites if r["coded"])


def test_every_over_cap_call_is_a_coded_site_in_scope(
    records: list[dict[str, Any]],
) -> None:
    """The catalogue's helper says ``over-cap`` at every call, a wrapper's
    call too: each is a site the ratchet counts, and coded, so no count
    rose when the helper moved into the catalogue."""
    sites = [r for r in records if r["helper"] in ("warn_over_cap", "warn_field_cap")]
    assert len(sites) > 30  # the scan finds them
    assert all(r["coded"] and load().in_scope(r) for r in sites)


@pytest.mark.parametrize(
    "file", ["src/pitloom/core/evidence.py", "src/pitloom/core/provenance.py"]
)
def test_a_programming_error_is_out_of_scope(
    records: list[dict[str, Any]], file: str
) -> None:
    """An ``InternalError`` raise is no message to a user: the ratchet does
    not count it, and the baseline does not rise for it."""
    internal = [
        r
        for r in records
        if r["file"] == file and r.get("exc_class") == "InternalError"
    ]
    assert internal and not any(load().in_scope(r) for r in internal)


def test_the_documented_command_runs_the_ratchet() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "scripts.message_inventory", "--check"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout == b""
