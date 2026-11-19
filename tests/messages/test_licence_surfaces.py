# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence lines where a user meets them: ``loom project`` on stderr
with their ``[code]``, the library's records, the Hatchling hook, and
LicenseID's database missing or unusable (one ``WARNING:`` per process
for both, no home directory included).

See also: tests/messages/test_licences.py (the readers),
tests/test_licence_db_missing_surfaces.py (a missing database on every
surface).
"""

from __future__ import annotations

import functools
import logging
import sys
from pathlib import Path
from typing import Any

import pytest
from licenseid import LicenseDetector

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract import _license_text_match
from pitloom.extract._license_text_match import detect_license_from_text
from tests._code_records import coded
from tests.extract.conftest import make_hook

pytestmark = pytest.mark.platform

_MIT = '"License :: OSI Approved :: MIT License"'
_BSD = '"License :: OSI Approved :: BSD License"'
_TEXT = "Permission is hereby granted, free of charge, to any person " * 5


def _project(root: Path, table: str) -> Path:
    """A Hatchling project whose ``[project]`` table adds *table*."""
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        f'[project]\nname = "demo"\nversion = "1.0.0"\n{table}\n',
        encoding="utf-8",
    )
    (root / "demo").mkdir()
    (root / "demo" / "__init__.py").write_text("", encoding="utf-8")
    return root


_CLI_CASES = [
    (
        'license = "MIT OR"',
        "WARNING: FIELD=project.license LICENSE='MIT OR': malformed SPDX license "
        "expression (parse failed: Unexpected 'OR'); recorded as licence text "
        "[license-expression-malformed]",
    ),
    (
        f'license = "MIT"\nclassifiers = [{_MIT}]',
        "; kept the expression, dropped the classifiers (PEP 639 transitional "
        "state) [license-conflict]",
    ),
    (
        f"classifiers = [{_MIT}, {_BSD}]",
        ", assuming AND (they may offer a choice) [license-ambiguous]",
    ),
]


@pytest.mark.parametrize(
    ("table", "line"), _CLI_CASES, ids=["malformed", "conflict", "ambiguous"]
)
def test_loom_project_prints_the_line_with_its_code(
    table: str,
    line: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _project(tmp_path / "p", table)
    out = tmp_path / "sbom.spdx3.json"
    argv = ["loom", "project", str(root), "-o", str(out), "--offline"]
    monkeypatch.setattr(
        sys, "argv", [*argv, "--creation-datetime", "2026-01-01T00:00:00Z"]
    )
    assert main() == 0
    err = capsys.readouterr().err.splitlines()
    code = line.rpartition(" ")[2]
    assert [ln for ln in err if ln.endswith(code)] == [
        ln for ln in err if ln.endswith(line) and ln.startswith("WARNING: ")
    ]
    assert sum(ln.endswith(code) for ln in err) == 1


def test_the_library_record_carries_the_conflict_code(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "p", f'license = "MIT"\nclassifiers = [{_MIT}]')
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(
            root,
            output_path=tmp_path / "sbom.spdx3.json",
            creation_metadata=CreationMetadata(),
            offline=True,
        )
    codes = [code for code, _ in coded(caplog)]
    assert codes.count("license-conflict") == 1


def test_the_hook_says_several_classifiers_are_ambiguous(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "p", f"classifiers = [{_MIT}, {_BSD}]")
    build_data: dict[str, Any] = {}
    hook = make_hook(str(root), {})
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        hook.initialize("standard", build_data)
        hook.finalize("standard", build_data, "")
    assert [code for code, _ in coded(caplog)].count("license-ambiguous") == 1


def test_a_missing_then_unusable_database_warns_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing stated: the missing database's ``WARNING:`` and an unusable
    one's share one key, so the second is ``DEBUG``."""
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"")
    with caplog.at_level(logging.DEBUG, logger=_license_text_match.__name__):
        for path in (tmp_path / "none.db", broken):
            real = functools.partial(LicenseDetector, db_path=str(path))
            monkeypatch.setattr(_license_text_match, "LicenseDetector", real)
            assert detect_license_from_text(_TEXT) is None
    said = [r for r in caplog.records if "licenseid database" in r.getMessage()]
    assert [r.levelno for r in said] == [logging.WARNING, logging.DEBUG]
    assert coded(caplog)[0][0] == "license-db-missing"


@pytest.mark.parametrize("stated", ["MIT", None], ids=["stated", "none"])
def test_no_home_directory_is_unusable_stated_licence_or_not(
    stated: str | None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """LicenseID finds no home directory (``HOME``, ``USERPROFILE`` on
    Windows, set to nothing): a setup problem, never ``INFO:``."""
    monkeypatch.setenv("HOME", "")
    monkeypatch.setenv("USERPROFILE", "")
    with caplog.at_level(logging.INFO, logger=_license_text_match.__name__):
        assert detect_license_from_text(_TEXT, stated=stated) is None
    ((code, message),) = coded(caplog)
    assert code == "license-db-unusable"
    assert message.startswith("licenseid database cannot be used: ")
    assert "no home directory" in message
