# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A library caller's value the library cannot take: ``option-invalid``,
each a ``ValueError`` as before, now carrying the code. A document
namespace (``IdRegistry``, ``--namespace``), an empty SBOM to embed, a
creator type set after construction, a provenance format, schema or
detail (refused when the ``ProvenanceConfig`` is built, and by
``PitloomConfig.provenance``; a configuration file's unknown schema is
``config-invalid`` when parsed), and ``project_metadata`` passed without
``pitloom_config`` (``option-no-effect``).

See also: tests/messages/test_options.py (the command line's refusals).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.id_registry import IdRegistry
from pitloom.messages import code_of, trusted_message

pytestmark = pytest.mark.platform

_INVALID = "option-invalid"
_SECRET = "s3cr3t-value"


def _line(exc: BaseException) -> str:
    return f"ERROR: {exc} [{code_of(exc)}]"


_NAMESPACES = {
    "empty": ("", "namespace is empty"),
    "fragment": ("urn:x#y", "namespace must not contain '#': urn:x#y"),
    "newline-forged-line": (
        "urn:x\nERROR: forged [config-invalid]",
        "namespace has a character an IRI cannot hold: "
        "'urn:x\\nERROR: forged [config-invalid]'",
    ),
    "ansi": (
        "urn:x\x1b[31m",
        "namespace has a character an IRI cannot hold: 'urn:x\\x1b[31m'",
    ),
    "url-credential": (
        f"https://user:{_SECRET}@h.example/ns#x",
        "namespace must not contain '#': https://***:***@h.example/ns#x",
    ),
}


@pytest.mark.parametrize(("value", "text"), _NAMESPACES.values(), ids=_NAMESPACES)
def test_a_namespace_that_is_none_is_one_coded_line(value: str, text: str) -> None:
    """``IdRegistry(namespace=...)``: one line, the value last, escaped, a
    credential masked, and the code read back ours, not one it holds."""
    with pytest.raises(ValueError) as caught:
        IdRegistry.new("demo", namespace=value)
    assert str(caught.value) == text
    assert code_of(caught.value) == _INVALID
    trusted = trusted_message(_line(caught.value))
    assert trusted is not None and trusted.code == _INVALID


def test_a_huge_namespace_is_one_line_its_value_as_given() -> None:
    """A namespace is no credential (none is held, its only secret a URL's
    user part): shown whole, on one line, still trusted."""
    value = "urn:" + "x" * 1_000_000 + "#"
    with pytest.raises(ValueError) as caught:
        IdRegistry.new("demo", namespace=value)
    assert str(caught.value).startswith("namespace must not contain '#': urn:xxx")
    assert "\n" not in str(caught.value)
    assert code_of(caught.value) == _INVALID


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("", "namespace is empty"),
        ("urn:x#y", "namespace must not contain '#': urn:x#y"),
    ],
    ids=["empty", "fragment"],
)
def test_namespace_on_the_command_line_is_the_parsers_coded_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str,
    text: str,
) -> None:
    """``loom id generate --namespace``: argparse's ``argument --namespace:``
    line with the catalogue's text after it, exit 2, nothing written."""
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "ids.json"
    argv = ["loom", "id", "generate", "--namespace", value, "-o", str(registry)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as stopped:
        __main__.main()
    assert stopped.value.code == 2
    err = [line for line in capsys.readouterr().err.splitlines() if "ERROR" in line]
    assert err == [
        f"ERROR: loom id generate: argument --namespace: {text} [{_INVALID}]"
    ]
    assert trusted_message(err[0]) is not None
    assert not registry.exists()


@pytest.mark.parametrize(
    ("field", "value", "text"),
    [
        ("format", "x", "must be one of annotation, both, comment"),
        ("schema", "custom/1", "must be one of pitloom/1"),
        ("detail", "x", "must be one of full, minimal"),
        ("preserve_source_metadata", "x", "must be one of always, auto, never"),
        ("format", None, "must be one of annotation, both, comment"),
        ("format", [], "must be one of annotation, both, comment"),
        ("preserve_source_metadata", 1, "must be one of always, auto, never"),
    ],
    ids=[
        "format",
        "schema",
        "detail",
        "preserve",
        "format-none",
        "format-list",
        "preserve-int",
    ],
)
def test_provenance_settings_are_refused_when_built(
    field: str, value: object, text: str
) -> None:
    """The ``ProvenanceConfig`` (and ``PitloomConfig.provenance``) refuses
    a value when built or read, not when provenance is first written."""
    settings: dict[str, Any] = {field: value}
    with pytest.raises(ValueError) as caught:
        ProvenanceConfig(**settings)
    assert str(caught.value).startswith(f"ProvenanceConfig.{field}: {text}, got ")
    assert code_of(caught.value) == _INVALID
    assert trusted_message(_line(caught.value)) is not None

    config_settings: dict[str, Any] = {f"provenance_{field}": value}
    config = PitloomConfig(**config_settings)
    with pytest.raises(ValueError) as caught:
        _ = config.provenance
    assert str(caught.value).startswith(
        f"PitloomConfig.provenance_{field}: {text}, got "
    )
    assert code_of(caught.value) == _INVALID


def test_provenance_settings_are_checked_in_order() -> None:
    """Format, schema, detail, the preserve setting, then the budget."""
    bad: dict[str, Any] = {
        "preserve_source_metadata": "p",
        "max_source_metadata_bytes": 3,
    }
    with pytest.raises(ValueError, match=r"^ProvenanceConfig\.format: "):
        ProvenanceConfig(format="x", schema="y", detail="z", **bad)
    with pytest.raises(ValueError, match=r"^ProvenanceConfig\.schema: "):
        ProvenanceConfig(schema="y", detail="z", **bad)
    with pytest.raises(ValueError, match=r"^ProvenanceConfig\.detail: "):
        ProvenanceConfig(detail="z", **bad)
    with pytest.raises(
        ValueError, match=r"^ProvenanceConfig\.preserve_source_metadata: "
    ):
        ProvenanceConfig(**bad)
    with pytest.raises(ValueError, match=r"^ProvenanceConfig\.max_source"):
        ProvenanceConfig(max_source_metadata_bytes=3)


def test_an_unknown_schema_in_the_project_is_config_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``[tool.pitloom.provenance] schema`` names an encoder: one it does not
    know is refused when the configuration is read, with the file, not as a
    bare error halfway through the SBOM."""
    project = tmp_path / "demo"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "src" / "demo" / "__init__.py").write_bytes(b"")
    (project / "pyproject.toml").write_bytes(
        b'[project]\nname = "demo"\nversion = "1.0"\n'
        b'[tool.pitloom.provenance]\nschema = "bogus"\n'
    )
    out = tmp_path / "out.json"
    argv = ["loom", "generate", str(project), "-o", str(out), "--offline"]
    monkeypatch.setattr(sys, "argv", argv)
    assert __main__.main() == 1
    err = [line for line in capsys.readouterr().err.splitlines() if line]
    assert err == [
        f"ERROR: loom generate: FILE={project / 'pyproject.toml'}: "
        "[tool.pitloom.provenance] schema: must be one of pitloom/1, got a "
        "string 'bogus' [config-invalid]"
    ]
    assert trusted_message(err[0]) is not None
    assert not out.exists()


def test_project_metadata_without_its_config_has_no_effect(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "pyproject.toml").write_bytes(
        b'[project]\nname = "demo"\nversion = "1.0"\n'
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(
            tmp_path, offline=True, project_metadata=ProjectMetadata(name="other")
        )
    (record,) = caplog.records
    text = record.getMessage()
    assert text == (
        f"Options: {tmp_path}: project_metadata has no effect without "
        "pitloom_config (the project's metadata is read again from it)"
    )
    assert getattr(record, "pitloom_code", None) == "option-no-effect"
    assert trusted_message(f"WARNING: {text} [option-no-effect]") is not None
