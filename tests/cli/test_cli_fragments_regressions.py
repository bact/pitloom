# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regressions of the fragment commands found while cataloguing their lines,
each a test that failed before the fix: ``loom merge`` counted the files and
not the fragments it merged (S1), wrote an empty SBOM when none merged (S2),
``loom fragment list`` read a fragment with a reader of its own and
disagreed with the merge (S4), dangling references were said in set order
(S5), and a malformed ``sha256`` was accepted and a lower-case match was
case-sensitive (S9).

See also: tests/messages/test_fragments_surfaces.py (every line on every
surface) and tests/assemble/test_fragments_read_stages.py (the reader).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import FragmentMergeError, generate_merged_sbom
from pitloom.core.config import read_pitloom_config
from pitloom.messages import code_of
from tests._license_graph import fragment_graph
from tests._loom_child import coded_lines, run_loom

pytestmark = pytest.mark.platform  # child processes, files, stdout bytes

_NS = "https://spdx.org/spdxdocs/frag"
_AT = ["--creation-datetime", "2026-01-01T00:00:00Z"]


def _write(path: Path, *elements: dict[str, Any]) -> bytes:
    """A fragment of *elements* at *path*; its bytes."""
    raw = json.dumps(fragment_graph(list(elements))).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _package(name: str = "P") -> dict[str, Any]:
    return {"type": "software_Package", "spdxId": f"{_NS}#{name}", "name": name}


def _dataset(size: int) -> dict[str, Any]:
    return {
        "type": "dataset_DatasetPackage",
        "spdxId": f"{_NS}#D",
        "name": "d",
        "dataset_datasetType": ["text"],
        "dataset_datasetSize": size,
    }


def _project(root: Path, files: str) -> Path:
    project = root / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        f"[tool.pitloom.fragment]\nfiles = [{files}]\n",
        encoding="utf-8",
    )
    return project


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")


# -- S1 and S2: ``loom merge`` ---------------------------------------------------


def test_s1_loom_merge_counts_the_fragments_it_merged_not_the_files(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "fr" / "a.json", _package("A"))
    _write(tmp_path / "fr" / "b.json", _package("B"))
    (tmp_path / "fr" / "c.json").write_bytes(b"{not json")  # one of three
    done = run_loom(["merge", "fr", "-o", "m.json"], tmp_path)
    assert done.returncode == 0, done.stderr
    stderr = done.stderr.decode("utf-8")
    assert "INFO: merge: merged 2 fragment(s)" in stderr
    assert "merged 3" not in stderr


def test_s2_loom_merge_of_nothing_mergeable_exits_1_and_writes_nothing(
    tmp_path: Path,
) -> None:
    (tmp_path / "fr").mkdir()
    (tmp_path / "fr" / "a.json").write_bytes(b"{not json")
    (tmp_path / "fr" / "b.json").write_bytes(b'{"a": 1}')
    done = run_loom(["merge", "fr", "-o", "m.json"], tmp_path)
    assert done.returncode == 1
    assert not (tmp_path / "m.json").exists()
    assert list(coded_lines(done.stderr).values())[-1] == "fragment-missing"
    stderr = done.stderr.decode("utf-8")
    assert "creation time" not in stderr and "1970" not in stderr
    assert "merge: merged" not in stderr  # no summary of a merge not done
    assert done.stdout == b""


def test_s2_the_library_raises_before_it_writes(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_bytes(b"{not json")
    out = tmp_path / "out.json"
    with pytest.raises(FragmentMergeError) as raised:
        generate_merged_sbom(tmp_path, output_path=out)
    assert code_of(raised.value) == "fragment-missing" and not out.exists()


# -- S4: ``fragment list`` reads as the merge does ----------------------------------


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_s4_a_number_with_no_rfc_8785_spelling_fails_the_list_as_the_merge(
    tmp_path: Path, required: bool
) -> None:
    entry = '{ path = "big.json", required = true }' if required else '"big.json"'
    project = _project(tmp_path, entry)
    _write(project / "big.json", _dataset(2**60))
    listed = run_loom(["fragment", "list", "--project-dir", str(project)], tmp_path)
    built = run_loom(
        ["project", str(project), "-o", str(tmp_path / "o"), *_AT], tmp_path
    )
    assert listed.returncode == built.returncode == int(required)
    for done in (listed, built):
        assert "fragment-invalid" in coded_lines(done.stderr).values()
        assert "exceeds safe integer domain" in done.stderr.decode("utf-8")
    assert f"REQUIRED={str(required).lower()}" in listed.stdout.decode("utf-8")


# -- S5: dangling references in id order --------------------------------------------


def _dangling(count: int, *, reverse: bool) -> list[dict[str, Any]]:
    ids = range(count)
    relations = [
        {
            "type": "Relationship",
            "spdxId": f"{_NS}#r{i}",
            "from": f"{_NS}#P",
            "to": [f"{_NS}#gone{i}"],
            "relationshipType": "other",
        }
        for i in (reversed(ids) if reverse else ids)
    ]
    return [_package(), *relations]


def test_s5_dangling_references_are_said_sorted_whatever_the_input_order(
    tmp_path: Path,
) -> None:
    seen = []
    for n, reverse in enumerate((False, True)):
        directory = tmp_path / str(n)
        _write(directory / "d.json", *_dangling(6, reverse=reverse))
        done = run_loom(["merge", str(directory), "-o", str(directory / "o")], tmp_path)
        assert done.returncode == 1
        lines = [
            ln
            for ln in done.stderr.decode("utf-8").splitlines()
            if "reference-not-found" in ln and ln.startswith("WARNING")
        ]
        # The id holds ``:``: take it up to the ``: `` that ends the subject.
        found = [re.search(r"ELEMENT=(\S+): ", ln) for ln in lines]
        seen.append([m.group(1) for m in found if m is not None])
    assert seen[0] == seen[1] == sorted(seen[0])
    assert len(seen[0]) == 6 and len(set(seen[0])) == 6  # six ids, not one


# -- S9: a configured digest ----------------------------------------------------------


@pytest.mark.parametrize("command", ["list", "project"])
@pytest.mark.parametrize(
    "digest", ["00", "z" * 64, "a" * 63], ids=["short", "no-hex", "63"]
)
def test_s9_a_malformed_sha256_is_a_configuration_error(
    tmp_path: Path, command: str, digest: str
) -> None:
    project = _project(tmp_path, f'{{ path = "f.json", sha256 = "{digest}" }}')
    _write(project / "f.json", _package())
    args = (
        ["fragment", "list", "--project-dir", str(project)]
        if command == "list"
        else ["project", str(project), "-o", str(tmp_path / "o"), *_AT]
    )
    done = run_loom(args, tmp_path)
    assert done.returncode == 1
    assert list(coded_lines(done.stderr).values()) == ["config-invalid"]
    assert "sha256" in done.stderr.decode("utf-8") and not (tmp_path / "o").exists()


@pytest.mark.parametrize("case", [str.lower, str.upper], ids=["lower", "upper"])
def test_s9_a_digest_in_either_case_matches(
    tmp_path: Path, case: Callable[[str], str]
) -> None:
    project = _project(tmp_path, "")
    raw = _write(project / "f.json", _package())
    digest = case(hashlib.sha256(raw).hexdigest())
    pyproject = project / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(
        text.replace(
            "files = []", f'files = [{{ path = "f.json", sha256 = "{digest}" }}]'
        ),
        encoding="utf-8",
    )
    done = run_loom(["fragment", "list", "--project-dir", str(project)], tmp_path)
    assert done.returncode == 0, done.stderr
    assert "SHA256=match" in done.stdout.decode("utf-8")
    assert "fragment-digest-invalid" not in coded_lines(done.stderr).values()


# -- the summaries ---------------------------------------------------------------------

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "fragments"


@pytest.mark.usefixtures("offline_spdx3_validate")
@pytest.mark.parametrize(
    "names",
    [
        ["dataset-fragment.spdx3.json"],
        ["dataset-fragment.spdx3.json", "ai-model-fragment.spdx3.json"],
    ],
    ids=["one", "two"],
)
def test_fragment_validate_counts_the_documents_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    names: list[str],
) -> None:
    # The fixtures state different ``created`` for one CreationInfo, so as a
    # merged set they are not one document: each is checked alone.
    paths = [str(_FIXTURES / n) for n in names]
    monkeypatch.setattr(
        "sys.argv", ["loom", "fragment", "validate", "--no-merge", *paths]
    )
    assert __main__.main() == 0
    err = capsys.readouterr().err.splitlines()
    assert err[-1] == f"INFO: fragment validate: {len(names)} document(s) valid"


@pytest.mark.parametrize(
    "files", ["", "files = []"], ids=["no-table-key", "empty-list"]
)
def test_fragment_list_with_nothing_configured_says_so_and_prints_nothing(
    tmp_path: Path, files: str
) -> None:
    """Present but empty is still "no fragments configured": exit 0."""
    project = tmp_path / "proj"
    project.mkdir()
    table = f"\n[tool.pitloom.fragment]\n{files}\n" if files else ""
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n' + table, encoding="utf-8"
    )
    done = run_loom(["fragment", "list", "--project-dir", str(project)], tmp_path)
    assert done.returncode == 0
    # splitlines: a Windows child ends its lines with CRLF.
    assert done.stderr.splitlines() == [b"INFO: fragment list: no fragments configured"]
    assert done.stdout == b""


def test_s9_a_configured_digest_is_kept_in_lower_case(tmp_path: Path) -> None:
    """Read once, compared and shown in one spelling: the list's own
    ``.lower()`` would hide a config that kept the upper case."""
    digest = "AB" * 32
    project = _project(tmp_path, f'{{ path = "f.json", sha256 = "{digest}" }}')
    (entry,) = read_pitloom_config(project / "pyproject.toml").fragments
    assert entry.sha256 == digest.lower() != digest
