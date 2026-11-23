# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SBOM fragment families on every surface that merges or lists
fragments: ``loom project``, ``loom merge`` and ``loom fragment list`` (a
child process: the stderr line, its ``[code]``, the exit status, no output
file on a failure, standard output data only), the library
(``merge_fragments``, ``generate_project_sbom``, ``generate_merged_sbom``:
the ``pitloom_code`` of each record and of ``FragmentMergeError``) and the
Hatchling hook (the ``ERROR:`` with ``[fragment-missing]``). A fragment a
merge needs and one it does not are each one test.

See also: tests/messages/test_fragments.py (the entries and their lines),
tests/messages/test_fragments_hostile.py (an attacker's text in them) and
tests/assemble/test_fragments_surfaces.py (an earlier SBOM as a fragment).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    FragmentMergeError,
    generate_merged_sbom,
    generate_project_sbom,
)
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.quote_source import quote_source
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from tests._license_graph import fragment_graph
from tests._loom_child import coded_lines, run_loom
from tests.extract.conftest import make_hook, staged_sbom

pytestmark = pytest.mark.platform  # child processes, paths, stderr bytes

#: A mode of 0 holds the user only off Windows and not as root.
_CAN_CHMOD = sys.platform != "win32" and getattr(os, "geteuid", lambda: 1)() != 0
_AT = ["--creation-datetime", "2026-01-01T00:00:00Z"]
_NS = "https://spdx.org/spdxdocs/frag"
_NOT_MERGED = "; not merged"
_WILL_FAIL = "; required, so the merge will fail"
_MISSING = "fix each as its WARNING says"

#: What a fragment holds, by name: the line its failure says, the code, and
#: how it is written (a directory named ``x.json`` is unreadable everywhere).
_BAD: dict[str, tuple[str, str, bytes | None]] = {
    "json": ("is not valid JSON (", "fragment-invalid", b"{not json"),
    "spdx": ("is not SPDX 3 JSON-LD Pitloom can merge (", "fragment-invalid", b"3"),
    "read": ("could not be read (", "fragment-unreadable", None),
}


def _write(path: Path, content: bytes | None) -> None:
    """*content* as *path*; ``None``: a directory there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        path.mkdir()
    else:
        path.write_bytes(content)


def _package(name: str, description: str = "d", ns: str = _NS) -> dict[str, Any]:
    return {
        "type": "software_Package",
        "spdxId": f"{ns}#{name}",
        "name": name,
        "description": description,
    }


def _good(path: Path, *elements: dict[str, Any]) -> None:
    """A valid fragment (the package ``P``, else *elements*) at *path*."""
    document = fragment_graph(list(elements) or [_package("P")])
    _write(path, json.dumps(document).encode("utf-8"))


def _dangling() -> list[dict[str, Any]]:
    """A package and a relationship from it to an element no document holds."""
    relation = {
        "type": "Relationship",
        "spdxId": f"{_NS}#R",
        "from": f"{_NS}#P",
        "to": [f"{_NS}#gone"],
        "relationshipType": "other",
    }
    return [_package("P"), relation]


def _project(root: Path, files: str) -> Path:
    """A project whose ``[tool.pitloom.fragment] files`` is the TOML *files*."""
    project = root / "proj"
    (project / "demo").mkdir(parents=True)  # the package Hatchling discovers
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        f"[tool.pitloom.fragment]\nfiles = [{files}]\n",
        encoding="utf-8",
    )
    return project


def _entry(path: str, required: bool) -> str:
    return f'{{ path = "{path}", required = true }}' if required else f'"{path}"'


def _tagged(stderr: bytes) -> list[str]:
    """Each line of *stderr*, each starting with exactly one level tag."""
    lines = [ln for ln in stderr.decode("utf-8").splitlines() if ln.strip()]
    tags = ("ERROR: ", "WARNING: ", "INFO: ")
    assert all(ln.startswith(tags) for ln in lines), lines
    assert not any(ln.partition(": ")[2].startswith(tags) for ln in lines)
    return lines


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")


# -- loom project --------------------------------------------------------------


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("bad", sorted(_BAD))
def test_loom_project_says_a_fragment_it_cannot_merge(
    tmp_path: Path, bad: str, required: bool
) -> None:
    words, code, content = _BAD[bad]
    project = _project(tmp_path, _entry("frags/f.json", required))
    _write(project / "frags" / "f.json", content)
    out = tmp_path / "out.spdx3.json"
    done = run_loom(["project", str(project), "-o", str(out), *_AT], tmp_path)
    lines = _tagged(done.stderr)
    (said,) = [ln for ln in lines if ln.endswith(f"[{code}]")]
    assert said.startswith("WARNING: FILE=frags/f.json: SBOM fragment " + words)
    assert said.endswith(f"{_WILL_FAIL if required else _NOT_MERGED} [{code}]")
    codes = list(coded_lines(done.stderr).values())
    if not required:
        assert done.returncode == 0 and out.exists(), done.stderr
        assert codes == [code]
        return
    assert done.returncode == 1 and not out.exists()
    assert codes == [code, "fragment-missing"]
    assert lines[-1] == (
        "ERROR: loom project: 1 required SBOM fragment(s) not merged: "
        f"frags/f.json; {_MISSING} [fragment-missing]"
    )


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_loom_project_says_a_fragment_that_is_not_there(
    tmp_path: Path, required: bool
) -> None:
    project = _project(tmp_path, _entry("frags/gone.json", required))
    out = tmp_path / "out.spdx3.json"
    done = run_loom(["project", str(project), "-o", str(out), *_AT], tmp_path)
    code = "input-not-found/fragment"
    (said,) = [ln for ln, c in coded_lines(done.stderr).items() if c == code]
    assert said.startswith("WARNING: FILE=frags/gone.json: SBOM fragment not found")
    assert said.endswith(f"{_WILL_FAIL if required else _NOT_MERGED} [{code}]")
    assert (done.returncode, out.exists()) == ((1, False) if required else (0, True))
    assert ("fragment-missing" in coded_lines(done.stderr).values()) is required


def test_required_fragments_are_listed_in_configuration_order(tmp_path: Path) -> None:
    """Not sorted, not the order they failed in: the order configured."""
    project = _project(
        tmp_path,
        ", ".join(_entry(n, True) for n in ("z.json", "a.json", "m.json")),
    )
    _write(project / "m.json", b"{not json")
    done = run_loom(
        ["project", str(project), "-o", str(tmp_path / "o"), *_AT], tmp_path
    )
    assert done.returncode == 1
    assert _tagged(done.stderr)[-1].startswith(
        "ERROR: loom project: 3 required SBOM fragment(s) not merged: "
        f"z.json, a.json, m.json; {_MISSING}"
    )


def test_a_conflict_between_two_fragments_is_a_coded_warning(tmp_path: Path) -> None:
    project = _project(tmp_path, '"frags/a.json", "frags/b.json"')
    _good(project / "frags" / "a.json", _package("P", "first"))
    _good(project / "frags" / "b.json", _package("P", "second"))
    done = run_loom(
        ["project", str(project), "-o", str(tmp_path / "o"), *_AT], tmp_path
    )
    assert done.returncode == 0, done.stderr
    assert list(coded_lines(done.stderr).items()) == [
        (
            f"WARNING: Merge: ELEMENT={_NS}#P: description differs; kept 'first', "
            "dropped 'second' [fragment-conflict]",
            "fragment-conflict",
        )
    ]


def test_a_reference_to_nothing_stops_the_merge(tmp_path: Path) -> None:
    project = _project(tmp_path, '"frags/a.json"')
    _good(project / "frags" / "a.json", *_dangling())
    out = tmp_path / "o"
    done = run_loom(["project", str(project), "-o", str(out), *_AT], tmp_path)
    assert done.returncode == 1 and not out.exists()
    assert list(coded_lines(done.stderr).values()) == ["reference-not-found"] * 2
    lines = _tagged(done.stderr)
    assert lines[0].startswith(f"WARNING: Merge: ELEMENT={_NS}#R: to names ")
    assert lines[-1] == (
        "ERROR: loom project: 1 reference(s) to elements not in the merged "
        "document; regenerate the base SBOM, then run the enrichment again "
        "[reference-not-found]"
    )


# -- loom merge ----------------------------------------------------------------


def _shown(directory: str, name: str) -> str:
    """A fragment of *directory* as ``loom merge`` names it: the directory as
    typed joined with the name, as the OS writes it (a ``FILE=`` value is not
    quoted)."""
    return os.path.join(directory, name)


@pytest.mark.parametrize("bad", ["json", "spdx"])
def test_loom_merge_leaves_out_a_fragment_and_counts_the_rest(
    tmp_path: Path, bad: str
) -> None:
    words, code, content = _BAD[bad]
    _good(tmp_path / "fr" / "a.json")
    _good(tmp_path / "fr" / "b.json", _package("Q"))
    _write(tmp_path / "fr" / "c.json", content)
    done = run_loom(["merge", "fr", "-o", "m.json"], tmp_path)
    assert done.returncode == 0, done.stderr
    lines = _tagged(done.stderr)
    assert len(lines) == 2
    assert lines[0].startswith(
        f"WARNING: FILE={_shown('fr', 'c.json')}: SBOM fragment {words}"
    )
    assert lines[0].endswith(f"{_NOT_MERGED} [{code}]")
    assert lines[1] == "INFO: merge: merged 2 fragment(s)"  # not 3: one is left out
    assert (tmp_path / "m.json").exists()
    assert done.stdout.decode("utf-8").startswith("PITLOOM_SBOM_OUTPUT_PATH=")


@pytest.mark.skipif(not _CAN_CHMOD, reason="needs a mode the user is held to")
def test_loom_merge_leaves_out_a_file_it_may_not_read(tmp_path: Path) -> None:
    """Stage ``read``: a ``*.json`` file of the directory with no permission
    (a directory of that name is no fragment file, so no line)."""
    _good(tmp_path / "fr" / "a.json")
    locked = tmp_path / "fr" / "c.json"
    _good(locked)
    locked.chmod(0)
    try:
        done = run_loom(["merge", "fr", "-o", "m.json"], tmp_path)
    finally:
        locked.chmod(0o600)
    assert done.returncode == 0, done.stderr
    coded = list(coded_lines(done.stderr).items())
    assert len(coded) == 1
    said, code = coded[0]
    assert code == "fragment-unreadable"
    assert said.startswith(
        f"WARNING: FILE={_shown('fr', 'c.json')}: SBOM fragment could not be read ("
    )
    assert _tagged(done.stderr)[-1] == "INFO: merge: merged 1 fragment(s)"


@pytest.mark.parametrize("directory", ["fr", "./fr"], ids=["bare", "dot"])
def test_loom_merge_of_nothing_it_can_merge_exits_1_and_writes_nothing(
    tmp_path: Path, directory: str
) -> None:
    _write(tmp_path / "fr" / "a.json", b"{not json")
    _write(tmp_path / "fr" / "b.json", b"3")
    done = run_loom(["merge", directory, "-o", "m.json"], tmp_path)
    assert done.returncode == 1 and not (tmp_path / "m.json").exists()
    lines = _tagged(done.stderr)
    assert list(coded_lines(done.stderr).values()) == [
        "fragment-invalid",
        "fragment-invalid",
        "fragment-missing",
    ]
    assert f"FILE={_shown(directory, 'a.json')}" in lines[0]  # as typed
    assert lines[-1] == (
        f"ERROR: loom merge: no SBOM fragment in '{directory}' could be merged; "
        f"{_MISSING} [fragment-missing]"
    )
    assert not any("creation time" in ln for ln in lines)
    assert done.stdout == b""


def test_loom_merge_says_a_conflict_with_the_earlier_file_kept(tmp_path: Path) -> None:
    _good(tmp_path / "fr" / "a.json", _package("P", "first"))
    _good(tmp_path / "fr" / "b.json", _package("P", "second"))
    done = run_loom(["merge", "fr", "-o", "m.json"], tmp_path)
    assert done.returncode == 0, done.stderr
    assert list(coded_lines(done.stderr).items()) == [
        (
            f"WARNING: Merge: ELEMENT={_NS}#P: description differs; kept 'first', "
            "dropped 'second' [fragment-conflict]",
            "fragment-conflict",
        )
    ]


# -- loom fragment list --------------------------------------------------------


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("bad", sorted(_BAD))
def test_fragment_list_says_the_line_the_merge_would(
    tmp_path: Path, bad: str, required: bool
) -> None:
    words, code, content = _BAD[bad]
    project = _project(tmp_path, _entry("frags/f.json", required))
    _write(project / "frags" / "f.json", content)
    done = run_loom(["fragment", "list", "--project-dir", str(project)], tmp_path)
    assert done.returncode == int(required), done.stderr
    (said,) = [ln for ln, c in coded_lines(done.stderr).items() if c == code]
    assert said.startswith("WARNING: FILE=frags/f.json: SBOM fragment " + words)
    assert said.endswith(f"{_WILL_FAIL if required else _NOT_MERGED} [{code}]")
    (data,) = done.stdout.decode("utf-8").splitlines()  # stdout is data only
    assert data.startswith(f"PATH=frags/f.json ROLE=- REQUIRED={str(required).lower()}")
    assert data.endswith("SAME_DOCUMENT=-")


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_fragment_list_says_a_fragment_that_is_not_there(
    tmp_path: Path, required: bool
) -> None:
    project = _project(tmp_path, _entry("frags/gone.json", required))
    done = run_loom(["fragment", "list", "--project-dir", str(project)], tmp_path)
    assert done.returncode == int(required)
    code = "input-not-found/fragment"
    (said,) = [ln for ln, c in coded_lines(done.stderr).items() if c == code]
    assert said.startswith("WARNING: FILE=frags/gone.json: SBOM fragment not found")
    assert said.endswith(f"{_WILL_FAIL if required else _NOT_MERGED} [{code}]")


def test_fragment_list_says_a_digest_that_does_not_match(tmp_path: Path) -> None:
    project = _project(tmp_path, '{ path = "f.json", sha256 = "' + "0" * 64 + '" }')
    _good(project / "f.json")
    done = run_loom(["fragment", "list", "--project-dir", str(project)], tmp_path)
    assert done.returncode == 0, done.stderr
    coded = list(coded_lines(done.stderr).items())
    assert len(coded) == 1
    said, code = coded[0]
    assert code == "fragment-digest-invalid"
    assert said.startswith("WARNING: FILE=f.json: SHA-256 ")
    assert said.endswith(f" does not match the configured {'0' * 64} [{code}]")
    assert "SHA256=mismatch" in done.stdout.decode("utf-8")


# -- the library ---------------------------------------------------------------


def _printed(caplog: pytest.LogCaptureFixture) -> list[tuple[str, str | None]]:
    """Each record of *caplog*: its text and its code."""
    return [(r.getMessage(), getattr(r, CODE_ATTR, None)) for r in caplog.records]


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize("bad", sorted(_BAD))
def test_merge_fragments_carries_the_code_on_the_record_and_the_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bad: str, required: bool
) -> None:
    _, code, content = _BAD[bad]
    _write(tmp_path / "f.json", content)
    frags = [FragmentConfig(path="f.json", required=required)]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if required:
            with pytest.raises(FragmentMergeError) as raised:
                merge_fragments(tmp_path, frags, Spdx3JsonExporter())
            assert code_of(raised.value) == "fragment-missing"
            assert getattr(raised.value, CODE_ATTR) == "fragment-missing"
            assert isinstance(raised.value, ValueError)
            assert str(raised.value).endswith(_MISSING)
        else:
            assert merge_fragments(tmp_path, frags, Spdx3JsonExporter()) == 0
    ((text, said),) = _printed(caplog)
    assert said == code
    assert text.endswith(_WILL_FAIL if required else _NOT_MERGED)


def test_merge_fragments_returns_the_number_it_merged(tmp_path: Path) -> None:
    _good(tmp_path / "a.json")
    _good(tmp_path / "b.json", _package("Q"))
    _write(tmp_path / "c.json", b"{not json")
    frags = [FragmentConfig(path=f"{n}.json") for n in "abc"]
    assert merge_fragments(tmp_path, frags, Spdx3JsonExporter()) == 2


def test_a_dangling_reference_raises_with_its_code_and_a_coded_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _good(tmp_path / "f.json", *_dangling())
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FragmentMergeError) as raised:
            merge_fragments(
                tmp_path, [FragmentConfig(path="f.json")], Spdx3JsonExporter()
            )
    assert code_of(raised.value) == "reference-not-found"
    ((text, code),) = _printed(caplog)
    assert code == "reference-not-found" and text.startswith(f"Merge: ELEMENT={_NS}#R:")


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_generate_project_sbom_says_the_fragment_and_fails_when_required(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, required: bool
) -> None:
    project = _project(tmp_path, _entry("f.json", required))
    _write(project / "f.json", b"{not json")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if required:
            with pytest.raises(FragmentMergeError) as raised:
                generate_project_sbom(project, offline=True)
            assert code_of(raised.value) == "fragment-missing"
        else:
            assert generate_project_sbom(project, offline=True)
    assert [c for _, c in _printed(caplog)] == ["fragment-invalid"]


def test_generate_merged_sbom_counts_what_it_merged(tmp_path: Path) -> None:
    _good(tmp_path / "a.json")
    _good(tmp_path / "b.json", _package("Q"))
    _write(tmp_path / "c.json", b"{not json")
    counted: list[int] = []
    out = tmp_path / "out.json"
    sbom = generate_merged_sbom(tmp_path, output_path=out, on_merged=counted.append)
    assert counted == [2] and out.read_text(encoding="utf-8") == sbom


@pytest.mark.parametrize("given", ["path", "str"])
def test_generate_merged_sbom_of_nothing_mergeable_raises_before_writing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, given: str
) -> None:
    frags = tmp_path / "fr"
    _write(frags / "a.json", b"{not json")
    out = tmp_path / "out.json"
    counted: list[int] = []
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FragmentMergeError) as raised:
            generate_merged_sbom(
                frags if given == "path" else str(frags),
                output_path=out,
                on_merged=counted.append,
            )
    assert code_of(raised.value) == "fragment-missing"
    assert str(raised.value) == (
        f"no SBOM fragment in {quote_source(frags)} could be merged; {_MISSING}"
    )
    assert not out.exists() and not counted
    assert [c for _, c in _printed(caplog)] == ["fragment-invalid"]


# -- the Hatchling hook --------------------------------------------------------


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_the_hook_says_the_error_with_its_code_when_a_fragment_is_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], required: bool
) -> None:
    project = _project(tmp_path, _entry("f.json", required))
    _write(project / "f.json", b"{not json")
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    if required:
        with pytest.raises(FragmentMergeError):
            hook.initialize("standard", build_data)
        assert staged_sbom(build_data) is None
    else:
        hook.initialize("standard", build_data)
        staged = staged_sbom(build_data)
        assert staged is not None and staged.exists()
        hook.finalize("standard", build_data, "")
    lines = _tagged(capsys.readouterr().err.encode("utf-8"))
    codes = list(coded_lines("\n".join(lines).encode("utf-8")).values())
    if required:
        assert codes[-1] == "fragment-missing"
        assert lines[-1].startswith("ERROR: ")
        assert lines[-1].endswith(f"{_MISSING} [fragment-missing]")
        assert "1 required SBOM fragment(s) not merged: f.json" in lines[-1]
    else:
        assert codes == ["fragment-invalid"]
