# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The boundaries of the lines a fragment merge says, one test per side of
each rule (for ``A and B``, one where only ``A`` fails and one where only
``B`` does): a property folded (empty takes the value silently, a respelling
and a path ending in the other are DEBUG, a real difference is one
``fragment-conflict`` naming the value kept), a dictionary entry of one key,
an id one element holds and another wants, a name two digests share, a
fragment that is the document being merged into, and the required fragments
a merge could not do without.

See also: tests/messages/test_fragments_surfaces.py (the same lines on every
surface), tests/messages/test_fragments_hostile.py and
tests/assemble/test_fragments_unify.py (the fold helpers).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import code_of
from pitloom.messages.fragments import SHOWN_FILES
from tests._license_graph import fragment_graph, write_fragment
from tests.core.test_fragments_merge_id_types import (
    _DATASET,
    _FILE,
    _MAIN,
    _SHARED,
    _base,
    _by_id,
)

pytestmark = pytest.mark.platform  # paths and files

_NS = "https://spdx.org/spdxdocs/frag"
_P = f"{_NS}#P"
_FOLD_LOGGER = "pitloom.assemble.spdx3._fragments_props"
_A, _B = "a" * 64, "b" * 64
_HASH = "verifiedUsing"


def _digest(algorithm: str, value: str) -> list[dict[str, str]]:
    return [{"type": "Hash", "algorithm": algorithm, "hashValue": value}]


def _fold(
    tmp: Path,
    base: list[dict[str, Any]],
    fragments: list[list[dict[str, Any]]],
    caplog: pytest.LogCaptureFixture,
) -> tuple[dict[str, dict[str, Any]], list[logging.LogRecord]]:
    """The merged elements by id and every record of the merge (``DEBUG`` up)
    of *fragments* folded into the base document holding *base*."""
    exporter = _base(base)
    names = []
    for n, elements in enumerate(fragments):
        names.append(FragmentConfig(path=f"f{n}.json"))
        write_fragment(tmp / f"f{n}.json", fragment_graph(elements))
    caplog.clear()
    # The fold's own logger: ``pitloom`` itself is set back to INFO on the way.
    with (
        caplog.at_level(logging.INFO, logger="pitloom"),
        caplog.at_level(logging.DEBUG, logger=_FOLD_LOGGER),
    ):
        merge_fragments(tmp, names, exporter)
    return _by_id(exporter.to_json(pretty=True)), list(caplog.records)


def _said(records: list[logging.LogRecord]) -> list[tuple[str, str]]:
    """The ``WARNING:`` and ``INFO:`` records: their code and their text."""
    return [
        (getattr(r, CODE_ATTR, ""), r.getMessage())
        for r in records
        if r.levelno >= logging.INFO
    ]


def _pkg(spdx_id: str = _P, **fields: Any) -> dict[str, Any]:
    return {"type": "software_Package", "spdxId": spdx_id, "name": "p", **fields}


# -- _merge_scalar ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kept", "dropped", "result", "said"),
    [
        ("", "Y", "Y", False),  # an empty value takes the fragment's, silently
        ("X", "", "X", False),  # an empty one drops nothing
        ("X", "X", "X", False),
        ("X", "Y", "X", True),  # only a real difference is a line
    ],
    ids=["fills", "dropped-empty", "equal", "differs"],
)
def test_a_property_folds_one_way_and_says_only_a_real_difference(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    kept: str,
    dropped: str,
    result: str,
    said: bool,
) -> None:
    base = [_pkg(description=kept)] if kept else [_pkg()]
    elements, records = _fold(tmp_path, base, [[_pkg(description=dropped)]], caplog)
    assert elements[_P].get("description", "") == result
    expected = (
        [
            (
                "fragment-conflict",
                f"Merge: ELEMENT={_P}: description differs; kept 'X', dropped 'Y'",
            )
        ]
        if said
        else []
    )
    assert _said(records) == expected


@pytest.mark.parametrize(
    ("first", "second", "field"),
    [
        ('{"a":1,"b":[2]}', '{ "b": [2],  "a": 1 }', "description"),
        ("src/a.py", "a.py", "name"),
        ("a.py", "src/a.py", "name"),
    ],
    ids=["same-json", "path-suffix", "path-suffix-reversed"],
)
def test_a_respelling_and_a_path_suffix_name_are_debug_not_a_conflict(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    first: str,
    second: str,
    field: str,
) -> None:
    base = [_pkg(**{field: first})]
    elements, records = _fold(tmp_path, base, [[_pkg(**{field: second})]], caplog)
    assert elements[_P][field] == first
    assert _said(records) == []
    debug = [r for r in records if r.levelno == logging.DEBUG and "Merge:" in r.msg]
    assert len(debug) == 1 and not hasattr(debug[0], CODE_ATTR)


def test_a_name_that_is_not_a_path_suffix_is_a_conflict(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The path rule needs the ``/``: ``xa.py`` does not end ``a.py`` as a
    file name does."""
    _, records = _fold(tmp_path, [_pkg(name="xa.py")], [[_pkg(name="a.py")]], caplog)
    ((code, text),) = _said(records)
    assert code == "fragment-conflict" and "name differs; kept 'xa.py'" in text


def test_the_value_kept_is_the_earlier_source_in_a_project_merge_and_in_loom_merge(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The base (the project's own element) beats a fragment; of two
    fragments the first configured beats the second."""
    _, records = _fold(
        tmp_path,
        [_pkg(description="project")],
        [[_pkg(description="one")], [_pkg(description="two")]],
        caplog,
    )
    assert [t.partition("; ")[2] for _, t in _said(records)] == [
        "kept 'project', dropped 'one'",
        "kept 'project', dropped 'two'",
    ]
    (tmp_path / "m").mkdir()
    _, records = _fold(
        tmp_path / "m",
        [],
        [[_pkg(description="one")], [_pkg(description="two")]],
        caplog,
    )
    assert [t.partition("; ")[2] for _, t in _said(records)] == [
        "kept 'one', dropped 'two'"
    ]


# -- _merge_colliding_entry --------------------------------------------------------


def _hyper(value: str) -> dict[str, Any]:
    entry = {"type": "DictionaryEntry", "key": "lr", "value": value}
    return {
        "type": "ai_AIPackage",
        "spdxId": f"{_NS}#M",
        "name": "m",
        "ai_hyperparameter": [entry],
    }


@pytest.mark.parametrize(
    ("kept", "dropped", "result", "said"),
    [
        ("", "2", "2", False),  # an empty value is filled in silently
        ("1", "", "1", False),
        ("1", "1", "1", False),
        ('{"a":1}', '{ "a": 1 }', '{"a":1}', False),  # the same JSON is quiet
        ("1", "2", "1", True),
    ],
    ids=["fills", "dropped-empty", "equal", "same-json", "differs"],
)
def test_a_dictionary_entry_of_one_key_folds_as_a_property_does(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    kept: str,
    dropped: str,
    result: str,
    said: bool,
) -> None:
    elements, records = _fold(tmp_path, [_hyper(kept)], [[_hyper(dropped)]], caplog)
    (entry,) = elements[f"{_NS}#M"]["ai_hyperparameter"]
    assert entry.get("value", "") == result
    expected = (
        [
            (
                "fragment-conflict",
                f"Merge: ELEMENT={_NS}#M: ai_hyperparameter key 'lr' differs; "
                "kept '1', dropped '2'",
            )
        ]
        if said
        else []
    )
    assert _said(records) == expected


# -- rename_id_clash and the digests -----------------------------------------------


def _file(
    spdx_id: str, digests: list[dict[str, str]] | None, name: str = "data"
) -> Any:
    element: dict[str, Any] = {"type": _FILE, "spdxId": spdx_id, "name": name}
    if digests:
        element[_HASH] = digests
    return element


def _dataset(spdx_id: str) -> dict[str, Any]:
    return {
        "type": _DATASET,
        "spdxId": spdx_id,
        "name": "data",
        "dataset_datasetType": ["text"],
    }


def test_an_id_another_type_holds_is_line_one_and_both_are_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    elements, records = _fold(
        tmp_path, [_file(_SHARED, None)], [[_dataset(_SHARED)]], caplog
    )
    new_id = f"{_MAIN}#DatasetPackage-1"
    assert _said(records) == [
        (
            "fragment-id-conflict",
            f"Merge: ELEMENT={_SHARED}: id held by a '{_FILE}', also wanted by a "
            f"'{_DATASET}'; both kept, the later is now {new_id}",
        )
    ]
    assert {elements[_SHARED]["type"], elements[new_id]["type"]} == {_FILE, _DATASET}


def test_an_id_two_artefacts_of_one_type_share_is_line_two(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _, records = _fold(
        tmp_path,
        [_file(_SHARED, _digest("sha256", _A))],
        [[_file(_SHARED, _digest("sha256", _B))]],
        caplog,
    )
    ((code, text),) = _said(records)
    assert code == "fragment-id-conflict"
    assert (
        f"id held by two '{_FILE}' elements of different sha256 digests; both" in text
    )


@pytest.mark.parametrize(
    ("kept", "dropped"),
    [
        (_digest("sha256", _A), _digest("sha256", _A.upper())),  # case only
        (_digest("sha256", _A), _digest("sha512", "c" * 128)),  # algorithm only
        (_digest("sha256", _A), None),
        (None, _digest("sha256", _A)),
    ],
    ids=["case", "algorithm", "dropped-none", "kept-none"],
)
def test_digests_that_do_not_conflict_say_no_line(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    kept: list[dict[str, str]] | None,
    dropped: list[dict[str, str]] | None,
) -> None:
    elements, records = _fold(
        tmp_path, [_file(_SHARED, kept)], [[_file(_SHARED, dropped)]], caplog
    )
    assert _said(records) == []
    assert [i for i, e in elements.items() if e["type"] == _FILE] == [_SHARED]


def test_a_name_two_digests_share_is_said_once_by_the_id_or_by_the_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The id conflict says it when the ids are the same (not a second line
    for the name); two ids with one name say the name."""
    by_id = [
        _file(_SHARED, _digest("sha256", _A)),
        _file(_SHARED, _digest("sha256", _B)),
    ]
    _, records = _fold(tmp_path, [by_id[0]], [[by_id[1]]], caplog)
    assert [c for c, _ in _said(records)] == ["fragment-id-conflict"]
    (tmp_path / "n").mkdir()
    _, records = _fold(
        tmp_path / "n",
        [_file(_SHARED + "-1", _digest("sha256", _A))],
        [[_file(_SHARED + "-2", _digest("sha256", _B))]],
        caplog,
    )
    ((code, text),) = _said(records)
    assert code == "fragment-hash-conflict"
    assert (
        f"a '{_FILE}' named data has SHA-256 '{_B}', another of that name '{_A}'"
        in text
    )


@pytest.mark.parametrize(
    ("kept", "dropped"),
    [
        (None, _digest("sha256", _A)),
        (_digest("sha256", _A), None),
        (_digest("sha512", "c" * 128), _digest("sha256", _A)),
        (_digest("sha256", _A), _digest("sha256", _A.upper())),
    ],
    ids=["kept-none", "dropped-none", "other-algorithm", "case"],
)
def test_a_name_with_no_two_sha256_values_to_compare_says_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    kept: list[dict[str, str]] | None,
    dropped: list[dict[str, str]] | None,
) -> None:
    _, records = _fold(
        tmp_path,
        [_file(_SHARED + "-1", kept)],
        [[_file(_SHARED + "-2", dropped)]],
        caplog,
    )
    assert _said(records) == []


# -- fragment-unusable and fragment-missing -----------------------------------------


def _document(spdx_id: str) -> dict[str, Any]:
    return {"type": "SpdxDocument", "spdxId": spdx_id, "name": "d"}


@pytest.mark.parametrize(
    ("elements", "merged", "said"),
    [
        ([_document(_MAIN), _pkg()], 0, True),  # the document being merged into
        ([_document(_MAIN + "-other"), _pkg()], 1, False),
        ([_pkg()], 1, False),  # no SpdxDocument never matches
    ],
    ids=["same", "other-document", "no-document"],
)
@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_only_a_fragment_with_the_documents_own_id_is_unusable(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    elements: list[dict[str, Any]],
    merged: int,
    said: bool,
    required: bool,
) -> None:
    write_fragment(tmp_path / "f.json", fragment_graph(list(elements)))
    frags = [FragmentConfig(path="f.json", required=required)]
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        if said and required:
            with pytest.raises(FragmentMergeError) as raised:
                merge_fragments(tmp_path, frags, _base([]))
            assert code_of(raised.value) == "fragment-missing"
        else:
            assert merge_fragments(tmp_path, frags, _base([])) == merged
    outcome = "required, so the merge will fail" if required else "not merged"
    assert _said(caplog.records) == (
        [
            (
                "fragment-unusable",
                "FILE=f.json: SBOM fragment is the document being merged into "
                f"({_MAIN}); {outcome}",
            )
        ]
        if said
        else []
    )


def test_no_required_fragment_unmet_is_no_error(tmp_path: Path) -> None:
    """The raise needs a required fragment not merged: optional ones that fail
    and required ones that merge never raise."""
    (tmp_path / "bad.json").write_bytes(b"{not json")
    write_fragment(tmp_path / "ok.json", fragment_graph([_pkg()]))
    frags = [
        FragmentConfig(path="bad.json"),
        FragmentConfig(path="ok.json", required=True),
    ]
    assert merge_fragments(tmp_path, frags, _base([])) == 1


def test_the_number_is_the_paths_named_and_the_list_is_capped(
    tmp_path: Path,
) -> None:
    total = SHOWN_FILES + 3
    frags = [FragmentConfig(path=f"m{i}.json", required=True) for i in range(total)]
    with pytest.raises(FragmentMergeError) as raised:
        merge_fragments(tmp_path, frags, Spdx3JsonExporter())
    text = str(raised.value)
    assert text.startswith(f"{total} required SBOM fragment(s) not merged: m0.json, ")
    assert f"m{SHOWN_FILES - 1}.json and 3 more; " in text
    assert f"m{SHOWN_FILES}.json" not in text
