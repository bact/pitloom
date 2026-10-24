# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A field that holds an SPDX license expression only (PEP 639
``project.license``, Core Metadata ``License-Expression``, PyPI
``license_expression``, ``SPDX-License-Identifier``, GGUF
``general.license``) whose value Pitloom cannot read as one is recorded as
licence text with one ``WARNING:`` per value
(:func:`pitloom.extract._license.warn_unless_expression`); a free-text field
(``License``, ``project.license.text``) stays quiet.

See also: tests/extract/test_license_classify.py (the classification),
tests/assemble/test_license_elements_surfaces.py (the elements per surface).
"""

from __future__ import annotations

import email
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from licenseid import DatabaseNotReadyError
from pyproject_metadata import License

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3.deps_pypi import _extract_pypi_license
from pitloom.assemble.spdx3.document import build_deployed
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.extract._core_metadata import core_metadata_license_with_source
from pitloom.extract._license import classify_license, warn_unless_expression
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.extract.project._pyproject_license import (
    license_from_project_table,
    stated_pyproject_license,
)
from pitloom.extract.project.hatchling import _resolve_hatchling_license
from pitloom.extract.project.pyproject import read_pyproject
from tests._license_graph import license_elements
from tests.assemble.conftest import _FakeMetadata
from tests.extract.ai_model.gguf_builders import STRING, gguf_file, kv, string

_SAID = "not read as an SPDX license expression"
_LONG = "Apache " * 40


def _said(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and _SAID in r.getMessage()
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("MIT", None),
        ("Apache-2.0 OR MIT", None),
        ("MIT AND (Apache-2.0 WITH LLVM-exception)", None),
        ("LicenseRef-Proprietary", None),
        ("GPL-2.0", None),  # deprecated, still an expression
        ("GPL-2.0+", None),
        ("apache-2.0", None),  # SPDX ids match in any case
        ("  MIT\t", None),
        ("UNKNOWN", None),
        ("NONE", None),
        ("", None),
        ("   ", None),
        (None, None),
        ("Apache2", "LICENSE='Apache2': _ (Unknown Expression 'Apache2')"),
        ("MIT OR Foo", "LICENSE='MIT OR Foo': _ (Unknown Expression 'Foo')"),
        (" Apache2 ", "LICENSE='Apache2': _ (Unknown Expression 'Apache2')"),
        ("Apache\nLicense", "LICENSE='Apache License': _ (more than one line)"),
        (_LONG, "_ (longer than 200 characters, not parsed)"),
        ("Apache2\x1b[2J", "LICENSE='Apache2\\x1b[2J': _"),
    ],
    ids=lambda v: repr(v)[:30],
)
def test_warn_unless_expression(
    value: str | None, expected: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        for _ in range(3):  # said once per value
            warn_unless_expression(value, "License-Expression")
    said = _said(caplog)
    if expected is None:
        assert not caplog.records
        return
    (message,) = said
    assert message.startswith("FIELD=License-Expression ")
    assert message.endswith("; recorded as license text")
    head, _, tail = expected.partition("_")
    assert head in message and tail in message
    assert "\n" not in message and "\x1b" not in message
    if value == _LONG:
        assert "..." in message and len(message) < 300


@pytest.mark.parametrize("helper_first", [True, False])
def test_a_broken_expression_is_said_once_with_the_classifier_warning(
    helper_first: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """The broken-expression warning of ``classify_license`` and this one
    share a key: one line, by whichever comes first."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if helper_first:
            warn_unless_expression("MIT OR", "project.license")
        classify_license("MIT OR")
        warn_unless_expression("MIT OR", "project.license")
    (record,) = caplog.records
    assert ("FIELD=project.license" in record.getMessage()) is helper_first


def _msg(**headers: str) -> email.message.Message:
    text = "".join(f"{k.replace('_', '-')}: {v}\n" for k, v in headers.items())
    return email.message_from_string(f"Name: x\n{text}\n")


def _no_file(_name: str) -> bytes | None:
    return None


_HATCH = {"license_expression": "", "license": "", "classifiers": []}
_MIT_CLASSIFIER = ["License :: OSI Approved :: MIT License"]


@pytest.mark.parametrize(
    ("read", "field"),
    [
        (lambda v: core_metadata_license_with_source(
            _msg(License_Expression=v), "s"), "License-Expression"),
        (lambda v: _extract_pypi_license({"license_expression": v}, "s"),
         "license_expression"),
        (lambda v: stated_pyproject_license(v, [], None), "project.license"),
        (lambda v: license_from_project_table({"license": v}, _no_file),
         "project.license"),
        (lambda v: _resolve_hatchling_license(
            SimpleNamespace(**{**_HATCH, "license_expression": v}), {}),
         "project.license"),
        # Free text, or a placeholder that gives way: quiet
        (lambda v: core_metadata_license_with_source(_msg(License=v), "s"), None),
        (lambda v: core_metadata_license_with_source(
            _msg(License_Expression="UNKNOWN", License=v), "s"), None),
        (lambda v: _extract_pypi_license({"license": v}, "s"), None),
        (lambda v: stated_pyproject_license(License(v, None), [], None), None),
        (lambda v: license_from_project_table({"license": {"text": v}}, _no_file),
         None),
        (lambda v: _resolve_hatchling_license(
            SimpleNamespace(**{**_HATCH, "license": v}), {}), None),
    ],
    ids=[
        "license-expression", "pypi-expression", "pep639", "sdist-pyproject",
        "hatchling", "license", "weak-expression-then-license", "pypi-license",
        "text-table", "sdist-text-table", "hatchling-text",
    ],
)  # fmt: skip
def test_each_reader_warns_for_an_spdx_only_field_only(
    read: Any, field: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read("MIT")
        assert not caplog.records
        read("Apache2")
        read("Apache2")
    assert [m.split()[0] for m in _said(caplog)] == (
        [f"FIELD={field}"] if field else []
    )


def test_a_placeholder_pep639_value_giving_way_to_a_classifier_is_quiet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert stated_pyproject_license("UNKNOWN", _MIT_CLASSIFIER, None)[0] == (
            "MIT License"
        )
    assert not caplog.records


def test_a_pypi_record_of_another_type_is_no_licence() -> None:
    assert _extract_pypi_license({"license_expression": 5, "license": []}, "s") == (
        None,
        "s",
    )


def test_one_unknown_id_on_three_dependencies_is_said_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    doc = DocumentModel(
        project=ProjectMetadata(name="env", version="0"),
        creation_metadata=CreationMetadata(),
    )
    tree = [
        {"package": {"key": n, "package_name": n, "installed_version": "1"}}
        for n in ("a", "b", "c")
    ]
    fake = _FakeMetadata({"Version": "1", "License-Expression": "Apache2"})
    with (
        caplog.at_level(logging.WARNING, logger="pitloom"),
        patch.object(
            deps_installed, "get_pkg_metadata", autospec=True, return_value=fake
        ),
    ):
        exporter = build_deployed(doc, tree, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]
    assert [e.get("simplelicensing_licenseText") for e in license_elements(graph)] == [
        "Apache2"
    ]
    assert [m.split()[0] for m in _said(caplog)] == ["FIELD=License-Expression"]


@pytest.mark.parametrize(
    ("value", "warns"), [("apache-2.0", False), ("llama3.1", True)]
)
def test_a_gguf_general_license(
    value: str, warns: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(gguf_file(0, 1, kv(b"general.license", STRING, string(value))))
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert read_gguf(path).license == value
    assert [m.split()[0] for m in _said(caplog)] == ["FIELD=general.license"] * warns


def test_a_file_tag_on_two_files_is_said_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "p", "MIT")
    (root / "p").mkdir()
    for name in ("__init__.py", "b.py"):
        (root / "p" / name).write_text("# SPDX-License-Identifier: Apache2\n", "utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        sbom = json.loads(
            generate_project_sbom(
                root, creation_metadata=CreationMetadata(), offline=True
            )
        )
    assert [m.split()[0] for m in _said(caplog)] == ["FIELD=SPDX-License-Identifier"]
    assert sorted(_texts(sbom)) == ["Apache2", "MIT"]


def _project(root: Path, license_value: str) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "p"\nversion = "1.0"\n'
        f"license = {json.dumps(license_value)}\n",
        encoding="utf-8",
    )
    return root


def _texts(sbom: dict[str, Any]) -> list[str]:
    return [
        e.get("simplelicensing_licenseText") or e["simplelicensing_licenseExpression"]
        for e in license_elements(sbom["@graph"])
    ]


@pytest.mark.parametrize("surface", ["cli", "library"])
def test_end_to_end_the_value_is_text_with_one_warning(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _project(tmp_path / "p", "Apache2")
    out = tmp_path / "sbom.json"
    if surface == "cli":
        argv = ["loom", "project", str(root), "-o", str(out), "--offline"]
        monkeypatch.setattr(
            sys, "argv", [*argv, "--creation-datetime", "2026-01-01T00:00:00Z"]
        )
        assert main() == 0
    else:
        generate_project_sbom(
            root,
            output_path=out,
            creation_metadata=CreationMetadata(),
            offline=True,
        )
    err = capsys.readouterr().err.splitlines()
    assert [line for line in err if _SAID in line] == [
        "WARNING: FIELD=project.license LICENSE='Apache2': not read as an SPDX"
        " license expression (Unknown Expression 'Apache2'); recorded as license"
        " text"
    ]
    assert _texts(json.loads(out.read_text(encoding="utf-8"))) == ["Apache2"]


@pytest.mark.parametrize(
    ("value", "warns"), [("MIT", False), ("Apache2", True)], ids=["mit", "apache2"]
)
def test_the_licenseid_database_does_not_decide(
    value: str, warns: bool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """With no usable licenseid database a known id is still known (the
    SPDX list ships with ``py-spdx-license``), so no id turns unknown."""
    root = _project(tmp_path / "p", value)
    (root / "LICENSE").write_text("Some licence text.\n" * 20, encoding="utf-8")
    with (
        caplog.at_level(logging.WARNING, logger="pitloom"),
        patch(
            "pitloom.extract._license.AggregatedLicenseMatcher",
            side_effect=DatabaseNotReadyError("missing"),
        ),
    ):
        read_pyproject(root / "pyproject.toml")
    assert len(_said(caplog)) == int(warns)
