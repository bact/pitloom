# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom fragment list`` reads a fragment as the merge does, checks its
configured digest and says its summary.

See also: test_cli_fragment_list.py (the rest of ``fragment list``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.core.config import read_pitloom_config

pytestmark = pytest.mark.platform

_PROJECT = '[project]\nname = "smoke"\nversion = "0.1.0"\n'
_GRAPH = b'{"@graph": []}'
#: An integer no RFC 8785 spelling holds: the merge refuses the fragment.
_BIG = "1152921504606846976"


def _list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: str) -> int:
    """``loom fragment list`` of a project whose ``files`` setting is
    *files* (TOML text): the exit code."""
    (tmp_path / "pyproject.toml").write_text(
        f"{_PROJECT}\n[tool.pitloom.fragment]\nfiles = {files}\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "list", "--project-dir", str(tmp_path)]
    )
    return __main__.main()


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_a_number_the_merge_refuses_is_refused_by_the_list(
    required: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One reader: a fragment holding ``2**60`` is ``fragment-invalid`` in
    the list as in ``loom project``, and exits 1 when required."""
    (tmp_path / "big.json").write_text(
        '{"@context":"https://spdx.org/rdf/3.0.1/spdx-context.jsonld","@graph":['
        '{"type":"Agent","spdxId":"urn:a","name":"x",'
        f'"dataset_datasetSize":{_BIG}}}]}}',
        encoding="utf-8",
    )
    files = f'[{{ path = "big.json", required = {str(required).lower()} }}]'
    code = _list(tmp_path, monkeypatch, files)
    out, err = capsys.readouterr()
    assert code == int(required)
    assert "ELEMENTS=1 " in out
    (line,) = [x for x in err.splitlines() if x.startswith("WARNING: ")]
    assert line.startswith("WARNING: FILE=big.json: SBOM fragment is not SPDX 3 ")
    assert line.endswith(
        "; required, so the merge will fail [fragment-invalid]"
        if required
        else "; not merged [fragment-invalid]"
    )


@pytest.mark.parametrize(
    "digest", ["00", "z" * 64, "ab" * 31], ids=["short", "non-hex", "62"]
)
def test_a_malformed_configured_digest_is_a_config_error(
    digest: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "m.json").write_bytes(_GRAPH)
    files = f'[{{ path = "m.json", sha256 = "{digest}" }}]'
    code = _list(tmp_path, monkeypatch, files)
    out, err = capsys.readouterr()
    assert code == 1
    assert out == ""
    assert err.rstrip().endswith("[config-invalid]")
    assert "sha256" in err


def test_an_upper_case_configured_digest_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "m.json").write_bytes(_GRAPH)
    digest = hashlib.sha256(_GRAPH).hexdigest().upper()
    assert digest != digest.lower()
    code = _list(tmp_path, monkeypatch, f'[{{ path = "m.json", sha256 = "{digest}" }}]')
    out, err = capsys.readouterr()
    assert code == 0
    assert "SHA256=match" in out
    assert "does not match" not in err


def test_an_empty_files_setting_is_no_fragments_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Present but empty is still "none configured": one ``INFO:``."""
    code = _list(tmp_path, monkeypatch, "[]")
    assert (code, capsys.readouterr()) == (
        0,
        ("", "INFO: fragment list: no fragments configured\n"),
    )


def test_the_configured_digest_is_kept_in_lower_case(tmp_path: Path) -> None:
    digest = "AB" * 32
    (tmp_path / "pyproject.toml").write_text(
        f'{_PROJECT}\n[tool.pitloom.fragment]\nfiles = [{{ path = "m.json", '
        f'sha256 = "{digest}" }}]\n',
        encoding="utf-8",
    )
    (fragment,) = read_pitloom_config(tmp_path / "pyproject.toml").fragments
    assert fragment.sha256 == digest.lower() != digest
