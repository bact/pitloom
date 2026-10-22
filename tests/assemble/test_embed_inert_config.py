# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``[tool.pitloom]`` keys an embed with ``--project-dir`` never acts on get
one ``INFO:`` each (the flags of the same names warn).

See also: tests/core/test_inert_options.py (the table) and
tests/plugins/test_hatch_build.py (the Hatchling hook, same wording).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.config import read_pitloom_config
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.inert_options import HOOK, configured_options, settle_inert
from pitloom.embed import embed_wheel_sbom

from .conftest import _make_dummy_wheel

_BOTH = "update-id-registry = true\ndescribe-relationship = true\n"


def _project(root: Path, keys: str) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "demo_pkg"\nversion = "1.0.0"\n[tool.pitloom]\n{keys}',
        encoding="utf-8",
    )
    return root


def _notes(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == level and "has no effect" in r.getMessage()
    ]


@pytest.mark.parametrize(
    ("keys", "overrides", "info", "warn"),
    [
        (_BOTH, ConfigOverrides(), 2, 0),
        ("", ConfigOverrides(), 0, 0),
        (
            "update-id-registry = false\ndescribe-relationship = false\n",
            ConfigOverrides(),
            0,
            0,
        ),
        (_BOTH, ConfigOverrides(update_id_registry=True), 1, 1),
        (_BOTH, ConfigOverrides(describe_relationship=False), 1, 1),
    ],
    ids=["both", "none", "false-agrees", "flag-wins-1", "flag-wins-2"],
)
def test_embed_notes_a_configured_key_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    keys: str,
    overrides: ConfigOverrides,
    info: int,
    warn: int,
) -> None:
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo_pkg", "1.0.0")
    project = _project(tmp_path / "proj", keys)
    with caplog.at_level(logging.INFO):
        embed_wheel_sbom(wheel, project_dir=project, overrides=overrides)
    assert len(_notes(caplog, logging.INFO)) == info
    assert len(_notes(caplog, logging.WARNING)) == warn


def test_configured_options_reads_only_what_is_set(tmp_path: Path) -> None:
    config = read_pitloom_config(
        _project(tmp_path / "p", "describe-relationship = false") / "pyproject.toml"
    )
    assert configured_options(config) == {}
    on = read_pitloom_config(
        _project(tmp_path / "q", "describe-relationship = true") / "pyproject.toml"
    )
    assert configured_options(on) == {"describe_relationship": True}


def test_the_hook_row_notes_at_info(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        settle_inert(HOOK, "p", {"update_id_registry": True}, level=logging.INFO)
    assert [r.levelno for r in caplog.records] == [logging.INFO]


@pytest.mark.parametrize(
    ("flag", "name"),
    [
        ("--no-update-id-registry", "update-id-registry"),
        ("--describe-relationship", "describe-relationship"),
    ],
)
def test_the_cli_flag_and_the_same_key_note_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    flag: str,
    name: str,
) -> None:
    """``embed-wheel --project-dir`` with a flag and its own key set: the
    flag's ``WARNING:`` only, not the same line again as an ``INFO:``; the
    other key still gets its ``INFO:``."""
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo_pkg", "1.0.0")
    project = _project(tmp_path / "proj", _BOTH)
    monkeypatch.setattr(
        "sys.argv",
        ["loom", "embed-wheel", str(wheel), "--project-dir", str(project), flag],
    )
    with caplog.at_level(logging.INFO):
        assert __main__.main() == 0
    warned = _notes(caplog, logging.WARNING)
    noted = _notes(caplog, logging.INFO)
    assert len(warned) == 1 and f"--{name}" in warned[0]
    assert len(noted) == 1 and f"--{name}" not in noted[0]
