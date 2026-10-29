# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`pitloom id generate -e NAME:dataset_DatasetPackage` hashes at most
``--max-dataset-hash-bytes``, else the project's own
``max-dataset-hash-bytes``, else 4 GiB.

See also: tests/cli/test_cli_id_entity_key.py (the pins),
tests/core/test_loom_pitloom_config.py (the same cap in `loom.Run`).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser
from pitloom.id_registry import AI_PACKAGE_TYPE, DATASET_PACKAGE_TYPE, IdRegistry

_CONTENT = b"0123456789"
_SHA = hashlib.sha256(_CONTENT).hexdigest()
_DS = ":" + DATASET_PACKAGE_TYPE
_PYPROJECT = '[project]\nname = "p"\nversion = "1"\n\n[tool.pitloom]\n{body}\n'
_SETUP_CFG = "[metadata]\nname = p\nversion = 1\n\n[tool:pitloom]\n{body}\n"


def _generate(
    proj: Path, spec: str, *flags: str, registry: str = "reg.json"
) -> tuple[int, list[tuple[str, str | None]]]:
    """Run ``id generate -e SPEC`` with *flags*: the exit code and the
    non-file entries saved (name, sha256)."""
    path = proj.parent / registry
    args = _build_parser().parse_args(
        ["id", "generate", "--project-dir", str(proj), "-o", str(path)]
        + ["-e", spec, *flags]
    )
    code = _run_id_command(args)
    entries = IdRegistry.load(path).elements.items() if path.exists() else []
    return code, sorted(
        (k[1], entry.sha256) for k, entry in entries if k[0] != "software_File"
    )


@pytest.fixture(name="proj")
def _proj(tmp_path: Path) -> Path:
    """A project with ``data/t.txt`` (10 bytes)."""
    proj = tmp_path / "proj"
    (proj / "data").mkdir(parents=True)
    (proj / "data" / "t.txt").write_bytes(_CONTENT)
    return proj


@pytest.mark.parametrize(
    ("config", "flag", "hashed"),
    [
        (None, None, True),
        ("pyproject", None, True),
        (None, "10", True),
        (None, "9", False),
        ("pyproject:9", None, False),
        ("setup.cfg:9", None, False),
        ("pyproject:9", "10", True),
        ("setup.cfg:9", "10", True),
        ("pyproject:10", "9", False),
    ],
    ids=[
        "default",
        "key-absent",
        "flag-exact",
        "flag-over",
        "pyproject-key",
        "setup-cfg-key",
        "flag-beats-pyproject",
        "flag-beats-setup-cfg",
        "flag-tightens",
    ],
)
def test_ceiling_cascade(
    proj: Path,
    caplog: pytest.LogCaptureFixture,
    config: str | None,
    flag: str | None,
    hashed: bool,
) -> None:
    """The 10-byte dataset is hashed at a ceiling of 10 or more and else
    pinned with no hash and one INFO; the flag beats the project's key
    (``pyproject.toml`` or ``setup.cfg``), which beats the 4 GiB default
    (the key was ignored before)."""
    if config is not None:
        kind, _, number = config.partition(":")
        body = f"max-dataset-hash-bytes = {number}" if number else ""
        name, template = (
            ("pyproject.toml", _PYPROJECT)
            if kind == "pyproject"
            else ("setup.cfg", _SETUP_CFG)
        )
        (proj / name).write_text(template.format(body=body), encoding="utf-8")
    flags = ("--max-dataset-hash-bytes", flag) if flag else ()

    with caplog.at_level(logging.INFO, logger="pitloom"):
        code, entries = _generate(proj, "data/t.txt" + _DS, *flags)

    assert code == 0
    assert entries == [("data/t.txt", _SHA if hashed else None)]
    infos = [r for r in caplog.records if "pinned without SHA-256" in r.getMessage()]
    assert len(infos) == int(not hashed)
    assert all(r.levelno == logging.INFO for r in infos)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "x"])
def test_flag_refuses_a_non_positive_integer(
    proj: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    """``0`` is an error, not "unlimited": exit 2, argparse's message."""
    with pytest.raises(SystemExit) as exit_info:
        _generate(proj, "data/t.txt" + _DS, "--max-dataset-hash-bytes", value)

    assert exit_info.value.code == 2
    assert "argument --max-dataset-hash-bytes: " in capsys.readouterr().err


@pytest.mark.parametrize(
    ("spec", "flags", "code"),
    [
        ("data/t.txt" + _DS, (), 1),
        ("data/t.txt" + _DS, ("--max-dataset-hash-bytes", "10"), 0),
        ("data/t.txt:" + AI_PACKAGE_TYPE, (), 0),
    ],
    ids=["dataset", "dataset-with-flag", "model"],
)
def test_project_config_is_read_only_for_a_dataset_without_a_flag(
    proj: Path,
    capsys: pytest.CaptureFixture[str],
    spec: str,
    flags: tuple[str, ...],
    code: int,
) -> None:
    """A project config that cannot be read fails ``-e`` of a dataset with
    no flag (one ``ERROR:``, the ceiling is not guessed); a flag, or an
    entity that is no dataset, needs no ceiling and does not read it."""
    (proj / "pyproject.toml").write_text(
        _PYPROJECT.format(body="max-dataset-hash-bytes = 0"), encoding="utf-8"
    )

    assert _generate(proj, spec, *flags)[0] == code

    err = capsys.readouterr().err
    assert ("max-dataset-hash-bytes" in err) is (code == 1)
