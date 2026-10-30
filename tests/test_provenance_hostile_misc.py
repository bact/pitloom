# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A hostile external name in a provenance string (a loom caller script path,
a ZIP member name of a PyTorch or PT2 file, a dependency's repository URL,
a declared dependency's requirement text)
parses to the segment keys of a benign run, never to a forged one.

See also: tests/core/test_provenance_builders.py (the builders).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import collections
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import deps_originator
from pitloom.core.provenance import ProvenanceConfig, parse_provenance_value
from pitloom.extract.ai_model.pytorch import read_pytorch
from pitloom.extract.ai_model.pytorch_pt2 import read_pytorch_pt2

#: A name with a pipe or a line break is not a file name on Windows.
_POSIX = sys.platform != "win32"
_POSIX_ONLY = pytest.mark.skipif(not _POSIX, reason="pipe/newline in a file name")

_FORGED = "a | Evidence: not_measured | Reason: over-cap"
_HOSTILE = [
    pytest.param(_FORGED, marks=_POSIX_ONLY, id="forged-segments"),
    pytest.param("a; Field: b", id="semicolon-field"),
    pytest.param("a\nb", marks=_POSIX_ONLY, id="newline"),
    pytest.param("a\u202eb", id="bidi"),
]
_BIDI = "\u202e"


def _keys(value: str) -> frozenset[str]:
    return frozenset(parse_provenance_value(value))


def _key_sets(provenance: dict[str, str]) -> dict[str, frozenset[str]]:
    return {field: _keys(value) for field, value in provenance.items()}


# ---------------------------------------------------------------------------
# loom: the caller script path
# ---------------------------------------------------------------------------

_Frame = collections.namedtuple("_Frame", ["filename", "function", "lineno"])


def _loom_provenance(
    base: Path, script: str
) -> tuple[dict[str, frozenset[str]], list[str]]:
    """The segment keys of every loom provenance string in a fragment (by
    field: Annotation statements and the ``comment`` lines), and all the
    strings the fragment holds."""
    frame = _Frame(filename=script, function="<module>", lineno=1)
    out = base / "frag.json"
    cwd = os.getcwd()
    os.chdir(base)
    try:
        with patch("pitloom._loom_caller.inspect.stack", return_value=[frame]):
            with loom.run(str(out)):
                loom.set_model("m")
                loom.set_model_hyperparameters({"lr": "0.1"})
    finally:
        os.chdir(cwd)
    graph = json.loads(out.read_text(encoding="utf-8"))["@graph"]
    keys: dict[str, frozenset[str]] = {}
    texts: list[str] = []
    for element in graph:
        for line in str(element.get("comment", "")).splitlines():
            if line.startswith("Metadata provenance: "):
                field, _, value = line.removeprefix("Metadata provenance: ").partition(
                    ": "
                )
                keys[f"comment:{field}"] = _keys(value)
                texts.append(value)
        if element.get("type") == "Annotation":
            fields = json.loads(element["statement"])["fields"]
            for field, parts in fields.items():
                keys[f"annotation:{field}"] = frozenset(parts)
            texts.append(element["statement"])
    return keys, texts


@pytest.mark.parametrize("script", _HOSTILE)
def test_loom_caller_path_forges_no_segment(tmp_path: Path, script: str) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "h").mkdir()
    benign, _ = _loom_provenance(tmp_path / "b", "train.py")
    hostile, texts = _loom_provenance(tmp_path / "h", f"{script}.py")

    assert benign
    assert hostile == benign
    assert all(_BIDI not in text for text in texts)


# ---------------------------------------------------------------------------
# PyTorch: the data.pkl member name
# ---------------------------------------------------------------------------

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _zip_bytes(names: list[str], contents: dict[str, bytes] | None = None) -> bytes:
    """A ZIP with members *names* (a fixed 1980 date), each holding
    *contents*'s bytes or ``b"1"``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
            archive.writestr(info, (contents or {}).get(name, b"1"))
    return buf.getvalue()


def _pytorch_provenance(tmp_path: Path, root: str) -> dict[str, str]:
    model = tmp_path / "model.pt"
    model.write_bytes(_zip_bytes([f"{root}/data.pkl", f"{root}/version"]))
    target = "pitloom.extract.ai_model.pytorch._fickling_get_top_class"
    with patch(target, return_value="Net"):
        return read_pytorch(model).provenance


@pytest.mark.parametrize("root", _HOSTILE)
def test_pytorch_pkl_member_forges_no_segment(tmp_path: Path, root: str) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "h").mkdir()
    benign = _key_sets(_pytorch_provenance(tmp_path / "b", "archive"))
    provenance = _pytorch_provenance(tmp_path / "h", root)

    assert "type_of_model" in benign
    assert _key_sets(provenance) == benign
    assert all(_BIDI not in value for value in provenance.values())


# ---------------------------------------------------------------------------
# PT2: the root directory prefix
# ---------------------------------------------------------------------------


def _pt2_provenance(tmp_path: Path, root: str) -> dict[str, str]:
    model = tmp_path / "model.pt2"
    names = [f"{root}/archive_version", f"{root}/extra/name"]
    model.write_bytes(_zip_bytes(names, {names[0]: b"2\n", names[1]: b"m"}))
    return read_pytorch_pt2(model).provenance


@pytest.mark.parametrize("root", _HOSTILE)
def test_pt2_root_prefix_forges_no_segment(tmp_path: Path, root: str) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "h").mkdir()
    benign = _key_sets(_pt2_provenance(tmp_path / "b", "mdl"))
    provenance = _pt2_provenance(tmp_path / "h", root)

    assert "format_version" in benign
    assert _key_sets(provenance) == benign
    assert all(_BIDI not in value for value in provenance.values())


# ---------------------------------------------------------------------------
# Dependency originator: the repository URL
# ---------------------------------------------------------------------------

_URL = "https://github.com/o/r"


def _originator_provenance(repo_url: str) -> str:
    """The ``software_attributionText`` provenance value written for *repo_url*."""
    package = MagicMock(spec=spdx3.software_Package)
    package.software_attributionText = ["text"]
    with patch.object(deps_originator, "emit_provenance") as emit:
        deps_originator._emit_originator_provenance(  # pylint: disable=protected-access
            package, 1, "Source: PyPI JSON API", repo_url,
            MagicMock(), "doc", "uuid", MagicMock(), None, None,
        )  # fmt: skip
    return str(emit.call_args.kwargs["provenance"]["software_attributionText"])


@pytest.mark.parametrize(
    "tail",
    [
        "/a | Evidence: not_measured | Reason: over-cap",
        "/a; Field: b",
        "/a\nb",
        "/a\u202eb",
    ],
    ids=["forged-segments", "semicolon-field", "newline", "bidi"],
)
def test_originator_repo_url_forges_no_segment(tail: str) -> None:
    benign = _originator_provenance(_URL)
    value = _originator_provenance(_URL + tail)

    assert _keys(value) == _keys(benign) == {"note"}  # the URL's ":" is no key
    assert _BIDI not in value


# ---------------------------------------------------------------------------
# Declared dependency: its requirement text
# ---------------------------------------------------------------------------


def _declared(tmp_path: Path, requirement: str) -> tuple[list[dict[str, str]], str]:
    """Each ``declared_constraint`` Annotation entry of a project declaring
    *requirement*, and every element comment, joined."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n'
        f"dependencies = [{json.dumps(requirement)}]\n",
        encoding="utf-8",
    )
    sbom = generate_project_sbom(
        tmp_path, offline=True, provenance=ProvenanceConfig(detail="full")
    )
    graph = json.loads(sbom)["@graph"]
    entries = [
        json.loads(element["statement"])["fields"]["declared_constraint"]
        for element in graph
        if element.get("type") == "Annotation"
        and "declared_constraint" in json.loads(element["statement"]).get("fields", {})
    ]
    return entries, "\n".join(element.get("comment", "") for element in graph)


def test_dependency_marker_forges_no_segment(tmp_path: Path) -> None:
    """A PEP 508 marker's string literal can hold a ``|``: it no longer adds
    an ``Evidence`` and a ``Reason`` key to the declared constraint."""
    marker = 'foo; os_name == "x | Evidence: not_measured | Reason: over-cap"'
    found = [set(entry) for entry in _declared(tmp_path, marker)[0]]

    assert found
    assert all(not {"evidence", "reason"} & keys for keys in found), found


@pytest.mark.parametrize(
    ("requirement", "text"),
    [
        ("foo>=1", "foo>=1"),
        ("pkg @ https://x/p.whl", "https://x/p.whl"),
        ('foo; python_version < "3.11" and sys_platform == "win32"', "win32"),
        ('foo; os_name == "a:b"', "a:b"),
        ('foo; os_name == "a: b | Evidence: not_measured"', "Evidence: not_measured"),
    ],
    ids=["benign", "url", "marker", "marker-colon", "hostile"],
)
def test_requirement_text_is_one_note(
    tmp_path: Path, requirement: str, text: str
) -> None:
    """Requirement text is a note, whatever ``:`` it holds: no ``pkg @
    https`` key, the keys of a plain ``foo>=1``; written after ``Note:``
    only when it holds one."""
    (entry,), comments = _declared(tmp_path, requirement)

    assert set(entry) == {"note"}
    assert text in entry["note"]
    noted = "declared_constraint: Note: " in comments
    assert noted == (":" in requirement), comments
