# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/refresh_spdx_model_snapshot.py``, which refreshes the
vendored SPDX model files."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

VERSION = "3.0.1"
# CRLF on purpose: the real schema has them, and they must survive a refresh.
BODIES = {"context": b"{}\n", "schema": b'{"a": 1}\r\n', "model": b"@prefix a: <b> .\n"}


@pytest.fixture(name="module")
def module_fixture(load_script: Callable[[str], ModuleType]) -> ModuleType:
    return load_script("refresh_spdx_model_snapshot")


def _fetch(url: str) -> bytes:
    return next(b for key, b in BODIES.items() if key in url)


def test_sources_cover_the_snapshot_files(module: ModuleType) -> None:
    files = {p.name for p in (module.SNAPSHOT_ROOT / f"v{VERSION}").iterdir()}
    assert set(module.sources(VERSION)) <= files


def test_refresh_writes_files_and_sums_byte_for_byte(
    module: ModuleType, tmp_path: Path
) -> None:
    module.refresh(VERSION, tmp_path, _fetch)
    target = tmp_path / f"v{VERSION}"
    assert (target / "spdx-json-schema.json").read_bytes() == BODIES["schema"]
    sums = (target / "SHA256SUMS").read_bytes().decode().splitlines()
    assert sums == sorted(sums, key=lambda line: line.split()[1])
    assert (
        f"{hashlib.sha256(BODIES['schema']).hexdigest()}  spdx-json-schema.json" in sums
    )
    assert b"\r" not in (target / "SHA256SUMS").read_bytes()


def test_drift_is_empty_after_refresh_and_names_changed_files(
    module: ModuleType, tmp_path: Path
) -> None:
    module.refresh(VERSION, tmp_path, _fetch)
    assert module.drifted(VERSION, tmp_path, _fetch) == []
    (tmp_path / f"v{VERSION}" / "spdx-model.ttl").write_bytes(b"changed")
    (tmp_path / f"v{VERSION}" / "spdx-context.jsonld").unlink()
    assert sorted(module.drifted(VERSION, tmp_path, _fetch)) == [
        "spdx-context.jsonld",
        "spdx-model.ttl",
    ]


@pytest.mark.parametrize("check, expected", [(True, 1), (False, 0)])
def test_main_check_reports_drift_without_writing(
    module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    check: bool,
    expected: int,
) -> None:
    monkeypatch.setattr(module, "SNAPSHOT_ROOT", tmp_path)
    argv = ["--check"] if check else []
    assert module.main(argv, _fetch) == expected
    assert (tmp_path / f"v{VERSION}" / "SHA256SUMS").exists() is (not check)
    assert ("upstream differs" in capsys.readouterr().err) is check


def test_fetch_refuses_non_https(module: ModuleType) -> None:
    with pytest.raises(ValueError, match="not an https URL"):
        module.fetch_url("file:///etc/passwd")
