# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wording of the ``id-registry`` config hint `id generate`/`id import` log
after creating a registry the project does not declare: "add to" when the
config table sets no ``id-registry``, "change ... to" when it already sets
a different one (pasting a second key would make ``pyproject.toml``
invalid TOML).

See also: test_cli_id_setup_cfg_hint_quoting.py (the setup.cfg value
quoting), test_cli_id_config_errors.py (when the hint is suppressed).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser

_PYPROJECT = '[project]\nname = "demo"\nversion = "0.1.0"\n'
_SETUP_CFG = "[metadata]\nname = demo\nversion = 0.1.0\n"
_EMPTY_SBOM = (
    '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld", "@graph": []}'
)

#: (config file, its contents with a different declared key or none,
#: the expected hint's tail after "to use this registry, ").
_CASES = {
    "pyproject-add": (
        "pyproject.toml",
        _PYPROJECT,
        'add to [tool.pitloom] in pyproject.toml: id-registry = "new.json"',
    ),
    "pyproject-change": (
        "pyproject.toml",
        _PYPROJECT + '\n[tool.pitloom]\nid-registry = "old.json"\n',
        "change id-registry in [tool.pitloom] in pyproject.toml to: "
        'id-registry = "new.json"',
    ),
    "setup-cfg-add": (
        "setup.cfg",
        _SETUP_CFG,
        "add to [tool:pitloom] in setup.cfg: id-registry = new.json",
    ),
    "setup-cfg-change": (
        "setup.cfg",
        _SETUP_CFG + "\n[tool:pitloom]\nid-registry = old.json\n",
        "change id-registry in [tool:pitloom] in setup.cfg to: id-registry = new.json",
    ),
}


def _hints(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if "to use this registry" in r.getMessage()
    ]


def _run_id(tmp_path: Path, command: str) -> int:
    registry = str(tmp_path / "new.json")
    if command == "generate":
        argv = ["id", "generate", "--project-dir", str(tmp_path), "-o", registry]
    else:
        sbom = tmp_path / "external.spdx3.json"
        sbom.write_text(_EMPTY_SBOM, encoding="utf-8")
        argv = ["id", "import", str(sbom), "--id-registry", registry]
    return _run_id_command(_build_parser().parse_args(argv))


@pytest.mark.parametrize("command", ["generate", "import"])
@pytest.mark.parametrize(
    ("config", "contents", "tail"), _CASES.values(), ids=list(_CASES)
)
def test_hint_adds_or_changes_the_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    command: str,
    config: str,
    contents: str,
    tail: str,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / config).write_text(contents, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level("INFO"):
        assert _run_id(tmp_path, command) == 0

    assert _hints(caplog) == [f"ID registry: to use this registry, {tail}"]
