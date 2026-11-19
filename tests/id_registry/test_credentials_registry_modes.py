# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ID registry in the two ``url-credentials`` modes: a key given or a
registry file entry that holds a credential is kept with one ``WARNING:``
in ``warn`` (the default) and refused in ``refuse``; a namespace is refused
in either.

See also: tests/id_registry/test_credentials_registry.py (the ``refuse``
mode and the credential shapes).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.__main__ import main
from pitloom.id_registry import IdRegistry, resolve_registry, save_registry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of

#: A registry file is named by a path, spelt per platform.
pytestmark = pytest.mark.platform

_SECRET = "S3CRET"
_KEY = f"https://u:{_SECRET}@h.example/m"
_NS = "https://ids.example/ns"
_REGISTRY = "credentials-unsafe/registry"


def _registry_file(path: Path, key: str = _KEY) -> Path:
    elements = {key: {"spdxId": f"{_NS}#AIPackage-1"}}
    document = {
        "elements": {"ai_AIPackage": elements},
        "id_counters": {"AIPackage": 1},
        "namespace": _NS,
        "project_root": ".",
        "version": 4,
    }
    path.write_text(json.dumps(document), "utf-8")
    return path


def _codes(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [getattr(r, CODE_ATTR, "") for r in caplog.records]


@pytest.mark.parametrize("refuse", [False, True], ids=["warn", "refuse"])
def test_load_follows_the_mode(
    refuse: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _registry_file(tmp_path / "ids.json")
    before = path.read_bytes()
    with caplog.at_level(logging.WARNING):
        if refuse:
            with pytest.raises(ValueError) as caught:
                IdRegistry.load(path, refuse_credentials=True)
            assert code_of(caught.value) == _REGISTRY
        else:
            registry = IdRegistry.load(path)
            assert ("ai_AIPackage", _KEY) in registry.elements
            assert not registry.refuse_credentials
            (line,) = caplog.messages
            assert "ids.json' is loaded as it is; remove the entry" in line
    assert _codes(caplog) == ([] if refuse else [_REGISTRY])
    assert path.read_bytes() == before and _SECRET not in caplog.text


@pytest.mark.parametrize("refuse", [False, True], ids=["warn", "refuse"])
def test_register_follows_the_mode(
    refuse: bool, caplog: pytest.LogCaptureFixture
) -> None:
    registry = IdRegistry(namespace=_NS, refuse_credentials=refuse)
    with caplog.at_level(logging.WARNING):
        if refuse:
            with pytest.raises(ValueError, match="key is stored as written"):
                registry.register("ai_AIPackage", _KEY)
        else:
            assert registry.register("ai_AIPackage", _KEY).startswith(_NS)
    assert bool(registry.elements) is not refuse
    assert _codes(caplog) == ([] if refuse else [_REGISTRY])
    assert _SECRET not in caplog.text


@pytest.mark.parametrize("refuse", [False, True], ids=["warn", "refuse"])
def test_a_namespace_is_refused_in_either_mode(refuse: bool) -> None:
    with pytest.raises(ValueError) as caught:
        IdRegistry(
            namespace=f"https://u:{_SECRET}@ids.example/ns", refuse_credentials=refuse
        )
    assert code_of(caught.value) == _REGISTRY


def test_a_rebase_in_the_warn_mode_saves_over_an_entry_saved_meanwhile(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _registry_file(tmp_path / "ids.json", key="model")
    registry = IdRegistry.load(path)
    registry.register("ai_AIPackage", "new")
    _registry_file(path)
    with caplog.at_level(logging.WARNING):
        save_registry(registry)
    saved = json.loads(path.read_bytes())["elements"]["ai_AIPackage"]
    assert {_KEY, "new"} <= set(saved)
    assert _codes(caplog) == [_REGISTRY]


@pytest.mark.parametrize("held", [False, True], ids=["clean", "credentialed"])
def test_a_registry_passed_in_takes_the_runs_refuse_mode(
    held: bool, tmp_path: Path
) -> None:
    """``resolve_registry`` turns a loaded registry to the run's ``refuse``
    mode, checking its entries as a load would; never back to ``warn``."""
    path = _registry_file(tmp_path / "ids.json", key=_KEY if held else "model")
    registry = IdRegistry.load(path)
    assert resolve_registry(registry, None, tmp_path) is registry
    modes = [registry.refuse_credentials]
    if held:
        with pytest.raises(ValueError) as caught:
            resolve_registry(registry, None, tmp_path, refuse_credentials=True)
        assert code_of(caught.value) == _REGISTRY
        modes.append(registry.refuse_credentials)
        assert modes == [False, False]
    else:
        resolve_registry(registry, None, tmp_path, refuse_credentials=True)
        modes.append(registry.refuse_credentials)
        resolve_registry(registry, None, tmp_path)
        modes.append(registry.refuse_credentials)
        assert modes == [False, True, True]


def _cli(monkeypatch: pytest.MonkeyPatch, cwd: Path, *argv: str) -> int:
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return main()


def _project(tmp_path: Path, pitloom: str) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"x\n")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\nversion = '1.0'\n"
        f"[tool.pitloom]\nid-registry = 'r.json'\n{pitloom}",
        "utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("pitloom", "argv", "refused"),
    [
        ("", (), False),
        ("", ("--refuse-url-credentials",), True),
        ("url-credentials = 'refuse'\n", (), True),
        # With -o alone the working directory's config is not read, as for
        # the location; an explicit --project-dir is read.
        ("url-credentials = 'refuse'\n", ("-o", "r.json"), False),
        ("url-credentials = 'refuse'\n", ("-o", "r.json", "--project-dir", "."), True),
    ],
    ids=["default", "flag", "config", "config-with-o", "config-with-o-and-dir"],
)
def test_id_generate_e_follows_the_mode(
    pitloom: str,
    argv: tuple[str, ...],
    refused: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proj = _project(tmp_path, pitloom)
    code = _cli(
        monkeypatch, proj, "id", "generate", "-e", f"{_KEY}:ai_AIPackage", *argv, "src"
    )
    err = capsys.readouterr().err
    assert code == int(refused) and f"[{_REGISTRY}]" in err and _SECRET not in err
    assert (proj / "r.json").exists() is not refused
    level = "ERROR" if refused else "WARNING"
    assert err.startswith(f"{level}: ")


@pytest.mark.parametrize(
    ("argv", "refused"),
    [
        ((), True),
        (("-o", "r.json"), False),
        (("-o", "r.json", "--project-dir", "."), True),
    ],
    ids=["no-o", "o", "o-and-dir"],
)
def test_id_import_reads_the_mode_like_generate(
    argv: tuple[str, ...],
    refused: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The project sets ``refuse``; its registry file holds a credential."""
    proj = _project(tmp_path, "url-credentials = 'refuse'\n")
    before = _registry_file(proj / "r.json").read_bytes()
    sbom = proj / "sbom.json"
    sbom.write_text(
        '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}',
        "utf-8",
    )
    code = _cli(monkeypatch, proj, "id", "import", str(sbom), *argv)
    err = capsys.readouterr().err
    assert f"[{_REGISTRY}]" in err and _SECRET not in err
    assert err.startswith("ERROR: " if refused else "WARNING: ")
    if refused:
        assert code == 1 and (proj / "r.json").read_bytes() == before


@pytest.mark.parametrize("value", [1, "refuse", None], ids=["one", "refuse", "none"])
def test_the_registry_mode_takes_only_a_bool(value: Any, tmp_path: Path) -> None:
    path = _registry_file(tmp_path / "ids.json")
    with pytest.raises(TypeError, match="refuse_credentials must be a bool"):
        IdRegistry(namespace=_NS, refuse_credentials=value)
    with pytest.raises(TypeError, match="refuse_credentials must be a bool"):
        IdRegistry.load(path, refuse_credentials=value)


@pytest.mark.parametrize("command", ["generate", "import"])
def test_an_unreadable_project_config_with_o_is_warned_of(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``-o`` and ``--project-dir``: a project config that cannot be read
    does not fail the run, and its ``refuse`` is not applied, said so."""
    proj = _project(
        tmp_path, "url-credentials = 'refuse'\nmax-dataset-hash-bytes = 0\n"
    )
    argv = ["-e", f"{_KEY}:ai_AIPackage", "src"]
    if command == "import":
        _registry_file(proj / "r.json")
        (proj / "sbom.json").write_text('{"@graph": []}', "utf-8")
        argv = [str(proj / "sbom.json")]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        _cli(
            monkeypatch,
            proj,
            "id",
            command,
            *argv,
            "-o",
            "r.json",
            "--project-dir",
            ".",
        )
    (line,) = [
        r.getMessage()
        for r in caplog.records
        if getattr(r, CODE_ATTR, "") == "option-no-effect"
    ]
    assert ": url-credentials not read: " in line
    assert line.endswith(
        "; the warn mode applies; add --refuse-url-credentials to refuse"
    )
    assert _REGISTRY in _codes(caplog)  # the credential was kept, not refused
