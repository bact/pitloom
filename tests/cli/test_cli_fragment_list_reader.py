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
from pitloom.cli.commands.fragment import _fragment_sha256_status
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
    "digest",
    ["00", "z" * 64, "ab" * 31, "a" * 65, "a" * 64 + "z"],
    ids=["short", "non-hex", "62", "65", "trailing"],
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


def test_the_list_compares_a_digest_in_lower_case() -> None:
    """The comparison lower-cases the digest itself, whoever built the
    entry (the configuration reader already keeps it lower case)."""
    digest = hashlib.sha256(b"x").hexdigest()
    assert _fragment_sha256_status(b"x", digest.upper(), "f.json") == "match"


def _list_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: bytes,
) -> tuple[int, str, str]:
    """``loom fragment list`` of a project with the one fragment *content*:
    the exit code, standard output and standard error."""
    (tmp_path / "f.json").write_bytes(content)
    code = _list(tmp_path, monkeypatch, '[{ path = "f.json" }]')
    out, err = capsys.readouterr()
    return code, out, err


def test_a_fragment_nested_past_the_parser_is_listed_without_a_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The depth is far past the recursion limit of every supported Python,
    so the reader refuses it, and the count (a second parse) must not crash."""
    deep = b"[" * 100_000 + b"]" * 100_000
    code, out, err = _list_one(tmp_path, monkeypatch, capsys, deep)
    assert code == 0
    assert "ELEMENTS=- " in out
    assert err.rstrip().endswith("[fragment-invalid]")


@pytest.mark.parametrize(
    "content", [b"[]", b"[" + _BIG.encode() + b"]"], ids=["read", "refused"]
)
def test_a_top_level_array_has_no_element_count(
    content: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only an object has an ``@graph``: an array, read or refused, is no
    zero-element fragment."""
    _, out, _ = _list_one(tmp_path, monkeypatch, capsys, content)
    assert "ELEMENTS=- " in out


def test_a_fragment_with_no_document_does_not_resolve_the_projects_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The id reads the project's metadata: only a fragment with an
    ``SpdxDocument`` needs it, and one without is ``SAME_DOCUMENT=false``."""

    def refuse(_project_dir: Path) -> str:
        raise AssertionError("the project's own id was resolved")

    monkeypatch.setattr("pitloom.cli.commands.fragment.project_document_id", refuse)
    code, out, _ = _list_one(tmp_path, monkeypatch, capsys, _GRAPH)
    assert code == 0
    assert "SAME_DOCUMENT=false" in out
