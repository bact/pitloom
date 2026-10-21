# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for reading a fragment so that the merged document serialises:
a value RFC 8785 cannot write makes the fragment unreadable (one warning
naming it, an error when required), a lone surrogate is written as text.

See also: test_fragments_merge_required.py (``required``) and
tests/plugins/test_hatch_build.py (the same fragments through the hook).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests.extract.conftest import make_hook

_AGENT = "https://e.org/a#A"


def write_fragment(path: Path, *, size: str = "10", name: str = "d") -> Path:
    """A fragment holding a dataset of *size* (JSON text) named *name*
    (JSON string text, escapes included)."""
    path.write_text(
        '{"@context":"https://spdx.org/rdf/3.0.1/spdx-context.jsonld","@graph":['
        '{"type":"CreationInfo","@id":"_:c","specVersion":"3.0.1",'
        f'"created":"2024-01-01T00:00:00Z","createdBy":["{_AGENT}"]}},'
        f'{{"type":"SoftwareAgent","spdxId":"{_AGENT}","name":"x",'
        '"creationInfo":"_:c"},'
        '{"type":"dataset_DatasetPackage","spdxId":"https://e.org/a#D",'
        f'"name":"{name}","creationInfo":"_:c","dataset_datasetSize":{size},'
        '"dataset_datasetType":["text"],'
        '"software_downloadLocation":"https://e.org/x"}]}',
        encoding="ascii",
    )
    return path


_BAD_SIZES = ["100000000000000000000", "1e999"]


@pytest.mark.parametrize("size", _BAD_SIZES, ids=["integer", "float"])
@pytest.mark.parametrize("pretty", [False, True], ids=["compact", "pretty"])
def test_an_unserialisable_optional_fragment_is_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, size: str, pretty: bool
) -> None:
    frag = write_fragment(tmp_path / "f.spdx3.json", size=size)
    exporter = Spdx3JsonExporter()
    merged = merge_fragments(tmp_path, [FragmentConfig(path=frag.name)], exporter)
    assert merged == 0
    assert len(caplog.messages) == 1
    assert caplog.messages[0].startswith(f"Failed to read SBOM fragment {frag}: ")
    exporter.to_json(pretty=pretty)


@pytest.mark.parametrize("size", _BAD_SIZES, ids=["integer", "float"])
def test_an_unserialisable_required_fragment_is_an_error(
    tmp_path: Path, size: str
) -> None:
    frag = write_fragment(tmp_path / "f.spdx3.json", size=size)
    with pytest.raises(FragmentMergeError, match="f.spdx3.json"):
        merge_fragments(
            tmp_path,
            [FragmentConfig(path=frag.name, required=True)],
            Spdx3JsonExporter(),
        )


@pytest.mark.parametrize("pretty", [False, True], ids=["compact", "pretty"])
@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_a_lone_surrogate_is_written_as_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pretty: bool, required: bool
) -> None:
    frag = write_fragment(tmp_path / "f.spdx3.json", name="a\\ud800b")
    exporter = Spdx3JsonExporter()
    merged = merge_fragments(
        tmp_path, [FragmentConfig(path=frag.name, required=required)], exporter
    )
    assert merged == 1
    assert [m for m in caplog.messages if "lone surrogates" in m] == [
        f"FILE={frag}: lone surrogates written as \\uXXXX"
    ]
    out = json.loads(exporter.to_json(pretty=pretty))
    names = [n.get("name") for n in out["@graph"]]
    assert "a\\ud800b" in names


def test_merge_fragments_returns_the_merged_count(tmp_path: Path) -> None:
    good = write_fragment(tmp_path / "good.spdx3.json")
    configured = [
        FragmentConfig(path=good.name),
        FragmentConfig(path="missing.spdx3.json"),
    ]
    assert merge_fragments(tmp_path, configured, Spdx3JsonExporter()) == 1


_HUGE = "100000000000000000000"


def _project(root: Path, required: bool) -> Path:
    write_fragment(root / "bad.json", size=_HUGE)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n'
        "[tool.pitloom.fragment]\n"
        f'files = [{{path = "bad.json", required = {str(required).lower()}}}]\n',
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_the_cli_names_an_unserialisable_fragment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    required: bool,
) -> None:
    """``loom project``: a skipped fragment is a warning naming it; a
    required one fails the command with one ``ERROR:`` line."""
    project = _project(tmp_path, required)
    monkeypatch.setattr(
        "sys.argv", ["loom", "project", str(project), "-o", str(tmp_path / "o.json")]
    )
    code = __main__.main()
    err = capsys.readouterr().err.splitlines()
    assert (code == 1) is required
    assert len([ln for ln in err if "bad.json" in ln and "Failed to read" in ln]) == 1
    assert len([ln for ln in err if ln.startswith("ERROR: ")]) == int(required)
    if not required:
        assert "dataset_datasetSize" not in (tmp_path / "o.json").read_text("utf-8")


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_the_hook_names_an_unserialisable_fragment(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, required: bool
) -> None:
    project = _project(tmp_path, required)
    hook = make_hook(str(project), {})
    build_data: dict[str, object] = {}
    with caplog.at_level("WARNING"):
        if required:
            with pytest.raises(FragmentMergeError, match="bad.json"):
                hook.initialize("standard", build_data)
        else:
            hook.initialize("standard", build_data)
            hook.finalize("standard", build_data, "")
    assert len([m for m in caplog.messages if "Failed to read" in m]) == 1
