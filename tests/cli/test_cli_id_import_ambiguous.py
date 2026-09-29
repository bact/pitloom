# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom id import`` reports the names it leaves out because the SBOM holds
several elements under them.

See also: :mod:`tests.cli.test_cli_id` (the rest of ``id import``),
:mod:`tests.id_registry.test_package_ids_ambiguous` (the harvest rule).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.id_registry import PACKAGE_ENTITY_TYPE, IdRegistry
from tests.id_registry.package_ids_base import build_doc, make_doc

_PREFIX = "INFO: ID registry: not imported (name held by several elements): "


def _import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dependencies: list[str]
) -> Path:
    sbom_path = tmp_path / "demo.spdx3.json"
    sbom_path.write_text(
        build_doc(make_doc(dependencies=dependencies), None).to_json(), "utf-8"
    )
    registry_path = tmp_path / "registry.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "id", "import", str(sbom_path), "--id-registry", str(registry_path)],
    )
    assert __main__.main() == 0
    return registry_path


def test_id_import_reports_ambiguous_names_in_one_sorted_info_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Six names: an unsorted set of them is in name order only by 1/720 chance.
    names = ["zed", "yak", "xen", "wit", "vim", "foo"]
    registry_path = _import(
        monkeypatch,
        tmp_path,
        [f"{n}==1.0" for n in names] + [f"{n.title()}==2.0" for n in names] + ["bar"],
    )

    lines = [
        line for line in capsys.readouterr().err.splitlines() if "not imported" in line
    ]
    assert lines == [_PREFIX + ", ".join(sorted(names))]
    registry = IdRegistry.load(registry_path)
    assert registry.lookup_entity("foo", PACKAGE_ENTITY_TYPE) is None  # non-vacuous
    assert registry.lookup_entity("bar", PACKAGE_ENTITY_TYPE) is not None


def test_id_import_without_ambiguous_names_prints_no_such_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _import(monkeypatch, tmp_path, ["bar==1.0"])

    assert "not imported" not in capsys.readouterr().err


def test_auto_harvest_logs_each_ambiguous_name_once_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Three elements under one name are one skipped key: one DEBUG record,
    no INFO/WARNING, and no "Import:" wording outside an import."""
    exporter = build_doc(
        make_doc(dependencies=["foo==1.0", "Foo==2.0", "FOO==3.0"]), None
    )
    registry = IdRegistry.new("r")

    with caplog.at_level(logging.DEBUG, logger="pitloom.id_registry"):
        registry.harvest(exporter.object_set)

    records = [r for r in caplog.records if "several elements" in r.getMessage()]
    assert [r.levelno for r in records] == [logging.DEBUG]
    assert "Import" not in records[0].getMessage()
    assert "foo" in records[0].getMessage()
