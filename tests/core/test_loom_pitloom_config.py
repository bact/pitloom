# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``loom.run(pitloom_config=...)``: only an explicit config is
read, of it only the registry, its update switch and the dataset hash
ceiling, and a declared-but-bad config fails before the run starts.

See also: tests/core/test_loom_dataset.py (the datasets the ceiling caps),
tests/core/test_config.py (the key's parsing).
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.core.config import PitloomConfig
from pitloom.id_registry import DATASET_PACKAGE_TYPE
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_CONTENT = b"12345"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered project holding ``t.txt`` (5 bytes) and ``cfg/``; the
    calling script is not captured."""
    (tmp_path / "t.txt").write_bytes(_CONTENT)
    (tmp_path / "cfg").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return tmp_path


def _write_config(path: Path, body: str) -> Path:
    path.write_text(f"[tool.pitloom]\n{body}", encoding="utf-8")
    return path


def _package(output: Path) -> dict[str, Any]:
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    (package,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    return dict(package)


@pytest.mark.parametrize(
    ("form", "ceiling", "hashed"),
    [
        ("object", 4, False),
        ("str", 4, False),
        ("path", 4, False),
        ("path", 5, True),
    ],
    ids=["object", "str", "path", "path-exact"],
)
def test_config_ceiling_reaches_dataset_hashing(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    form: str,
    ceiling: int,
    hashed: bool,
) -> None:
    """Any form of config sets the ceiling: a file one byte over it gets a
    package with no hash, no file and one ``WARNING:`` naming the key; a
    file of exactly the ceiling is hashed. Other keys loom does not read
    are silent."""
    config_file = _write_config(
        project / "cfg" / "loom.toml",
        f'max-dataset-hash-bytes = {ceiling}\ncreation-comment = "x"\n',
    )
    configs: dict[str, PitloomConfig | str | Path] = {
        "object": PitloomConfig(max_dataset_hash_bytes=ceiling),
        "str": "cfg/loom.toml",
        "path": config_file,
    }
    config = configs[form]
    output = project / "out.json"

    with caplog.at_level(logging.WARNING):
        with loom.run(output, pitloom_config=config):
            loom.add_dataset("t.txt")

    package = _package(output)
    warnings = [r.getMessage() for r in caplog.records]
    if hashed:
        assert package["verifiedUsing"][0]["hashValue"] == (
            hashlib.sha256(_CONTENT).hexdigest()
        )
        assert not warnings
    else:
        assert "verifiedUsing" not in package
        (warning,) = warnings
        assert "max-dataset-hash-bytes" in warning
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    files = [e for e in graph if e["type"] == "software_File"]
    assert len(files) == int(hashed)


@pytest.mark.parametrize(
    ("config", "needle"),
    [
        ("cfg/missing.toml", "not found"),
        ("cfg/bad.toml", "config file"),
        ("cfg/zero.toml", "must be a positive integer"),
        ("cfg/bool.toml", "must be an integer"),
        (PitloomConfig(max_dataset_hash_bytes=0), "positive integer"),
        (PitloomConfig(max_dataset_hash_bytes=True), "pitloom_config"),
        ("cfg/unreadable.toml", "Permission denied"),
    ],
    ids=["missing", "bad-toml", "zero", "bool", "obj-zero", "obj-bool", "unreadable"],
)
def test_bad_config_fails_before_the_run(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: PitloomConfig | str,
    needle: str,
) -> None:
    """A config that is missing, unreadable or invalid raises
    ``ValueError`` on entering the run: nothing is written and no run is
    left active."""
    (project / "cfg" / "bad.toml").write_text("[tool.pitloom\n", encoding="utf-8")
    _write_config(project / "cfg" / "zero.toml", "max-dataset-hash-bytes = 0\n")
    _write_config(project / "cfg" / "bool.toml", "max-dataset-hash-bytes = true\n")
    if config == "cfg/unreadable.toml":

        def _denied(path: Path, source: str) -> PitloomConfig:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))

        monkeypatch.setattr("pitloom._loom_active_run.load_config_file", _denied)
    output = project / "out.json"

    with pytest.raises(ValueError, match=needle):
        with loom.run(output, pitloom_config=config):
            pass  # pragma: no cover - never entered

    assert not output.exists()
    assert loom._active_run is None  # pylint: disable=protected-access


def test_registry_argument_beats_the_config(project: Path) -> None:
    """``id_registry=`` wins: the config's own registry, which would not
    load, is not read."""
    _write_config(project / "cfg" / "loom.toml", 'id-registry = "missing.json"\n')
    registry = make_registry(
        {(DATASET_PACKAGE_TYPE, "t.txt"): (f"{_NS}#DatasetPackage-4", None)}
    )
    output = project / "out.json"
    with loom.run(output, id_registry=registry, pitloom_config="cfg/loom.toml"):
        loom.add_dataset("t.txt")
    assert _package(output)["spdxId"] == f"{_NS}#DatasetPackage-4"


@pytest.mark.parametrize(
    ("config", "registry_dir"),
    [("cfg/loom.toml", "cfg"), (PitloomConfig(id_registry="reg.json"), ".")],
    ids=["file-relative", "object-cwd-relative"],
)
def test_config_registry_path_resolves(
    project: Path, config: PitloomConfig | str, registry_dir: str
) -> None:
    """A config file's relative ``id-registry`` is from the file's own
    directory; an in-memory config's, from the current directory."""
    _write_config(project / "cfg" / "loom.toml", 'id-registry = "reg.json"\n')
    make_registry(
        {(DATASET_PACKAGE_TYPE, "t.txt"): (f"{_NS}#DatasetPackage-6", None)},
        path=project / registry_dir / "reg.json",
    )
    output = project / "out.json"
    with loom.run(output, pitloom_config=config):
        loom.add_dataset("t.txt")
    assert _package(output)["spdxId"] == f"{_NS}#DatasetPackage-6"


@pytest.mark.parametrize("update", [True, False], ids=["update", "keep"])
def test_update_switch_is_kept_for_the_run(project: Path, update: bool) -> None:
    """``update-id-registry`` is read into the run (it decides whether a
    model is registered: tests/core/test_loom_model.py)."""
    _write_config(
        project / "cfg" / "loom.toml",
        f"update-id-registry = {str(update).lower()}\n",
    )
    with loom.run(project / "out.json", pitloom_config="cfg/loom.toml") as run:
        assert run.update_id_registry is update


def test_project_config_is_never_read_implicitly(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """With no ``pitloom_config=``, the current directory's
    ``pyproject.toml`` is not read: its registry (which would not load) and
    its ceiling (which would cap the dataset) have no effect."""
    (project / "pyproject.toml").write_text(
        '[tool.pitloom]\nid-registry = "missing.json"\nmax-dataset-hash-bytes = 1\n',
        encoding="utf-8",
    )
    output = project / "out.json"
    with caplog.at_level(logging.WARNING):
        with loom.run(output) as run:
            loom.add_dataset("t.txt")
            assert run.update_id_registry is True  # the default
    assert "verifiedUsing" in _package(output)
    assert not caplog.records


def test_config_file_without_a_table_names_pitloom_config(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The no-table warning names loom's own argument, not ``--config``."""
    (project / "cfg" / "empty.toml").write_text("[tool.other]\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        with loom.run(project / "out.json", pitloom_config="cfg/empty.toml"):
            pass
    (message,) = [
        r.getMessage() for r in caplog.records if "empty.toml" in r.getMessage()
    ]
    assert " pitloom_config file has no [tool.pitloom] table" in message
    assert "--config" not in message
