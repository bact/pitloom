# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for merge_fragments()'s required=True enforcement.

See also: test_fragments_merge.py (the rest of merge_fragments()'s
behavior -- split out once this file grew past the project's file-size
soft limit).
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.fragments import (
    FragmentMergeError,
    _missing_fragment_message,
    merge_fragments,
)
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter


def test_required_fragment_missing_raises_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A required=True fragment that's missing on disk must raise
    FragmentMergeError naming its path, and log a WARNING matching
    _missing_fragment_message(..., required=True) first -- both the
    warning and the raise are part of the contract."""
    exporter = Spdx3JsonExporter()
    frag = FragmentConfig(path="missing-required.spdx3.json", required=True)
    expected_warning = _missing_fragment_message(tmp_path / frag.path, required=True)

    with caplog.at_level("WARNING", logger="pitloom.assemble.spdx3.fragments"):
        with pytest.raises(FragmentMergeError, match="missing-required.spdx3.json"):
            merge_fragments(tmp_path, [frag], exporter)

    assert any(r.message == expected_warning for r in caplog.records)


def test_required_fragment_unparseable_raises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A required=True fragment that exists but fails to parse must also
    raise FragmentMergeError, via the read-failure path not the
    missing-file path -- and log a WARNING built from
    _fragment_read_failure_message(..., required=True)."""
    frag_path = tmp_path / "broken-required.spdx3.json"
    frag_path.write_text("not valid json{{{")
    exporter = Spdx3JsonExporter()
    frag = FragmentConfig(path="broken-required.spdx3.json", required=True)

    with caplog.at_level("WARNING", logger="pitloom.assemble.spdx3.fragments"):
        with pytest.raises(FragmentMergeError, match="broken-required.spdx3.json"):
            merge_fragments(tmp_path, [frag], exporter)

    assert any(
        r.message.startswith(f"Failed to read SBOM fragment '{frag_path}': ")
        and r.message.endswith("-- merge will fail.")
        for r in caplog.records
    )


def test_required_fragment_missing_raises_even_when_nothing_merged(
    tmp_path: Path,
) -> None:
    """A required fragment missing when it's the *only* configured fragment
    (so merged_any stays False) must still raise; gating the required-check
    on merged_any would swallow exactly this scenario."""
    exporter = Spdx3JsonExporter()
    frag = FragmentConfig(path="only-and-missing.spdx3.json", required=True)

    with pytest.raises(FragmentMergeError, match="only-and-missing.spdx3.json"):
        merge_fragments(tmp_path, [frag], exporter)


def test_permission_denied_fragment_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permission-denied fragment path must not crash merge_fragments()
    with an unhandled PermissionError. Path.exists() only swallows
    ENOENT/ENOTDIR/EBADF/ELOOP -- any other OSError (e.g. EACCES)
    propagates uncaught -- so merge_fragments() must classify a fragment's
    presence via _fragment_is_missing() rather than calling
    Path.exists() directly."""
    frag_path = tmp_path / "denied.spdx3.json"
    frag_path.write_text('{"@graph": []}')
    exporter = Spdx3JsonExporter()
    frag = FragmentConfig(path="denied.spdx3.json")

    real_stat = Path.stat

    def fake_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == frag_path:
            raise PermissionError(errno.EACCES, "Permission denied")
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fake_stat)

    merge_fragments(tmp_path, [frag], exporter)


def test_two_missing_required_fragments_both_named_in_error(tmp_path: Path) -> None:
    """Two required fragments both missing must both be named in the raised
    error -- the loop collects every failure before raising once, rather
    than stopping at the first."""
    exporter = Spdx3JsonExporter()
    fragments = [
        FragmentConfig(path="first-missing.spdx3.json", required=True),
        FragmentConfig(path="second-missing.spdx3.json", required=True),
    ]

    with pytest.raises(FragmentMergeError) as exc_info:
        merge_fragments(tmp_path, fragments, exporter)

    message = str(exc_info.value)
    assert "first-missing.spdx3.json" in message
    assert "second-missing.spdx3.json" in message
