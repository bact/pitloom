# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the AST model-usage visitor, call table and path matcher.

Pure functions only -- no file I/O.

See also: :mod:`tests.extract.scanner.test_scanner` (scanner integration and
parse-failure reporting) and :mod:`pitloom.extract._usage_ast`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import warnings

import pytest

from pitloom.core.model_usage import (
    ModelUsage,
    UsageAccess,
    combine_access,
    merge_usages,
)
from pitloom.extract._usage_ast import find_usages, parse_python, python_version
from pitloom.extract._usage_match import UsageModel, matches
from pitloom.extract._usage_table import (
    access_of_mode,
    access_of_name,
    is_mention_call,
)

_MODEL = UsageModel("model.ftz", ("pkg/data/model.ftz", "src/pkg/data/model.ftz"))


def _accesses(source: str, model: UsageModel = _MODEL) -> frozenset[UsageAccess]:
    (found,) = find_usages(parse_python(source), [model])
    return found


# --- combine_access and merge_usages ----------------------------------------


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        ([UsageAccess.READ], UsageAccess.READ),
        ([UsageAccess.WRITE], UsageAccess.WRITE),
        ([UsageAccess.UNKNOWN], UsageAccess.UNKNOWN),
        ([UsageAccess.READ_WRITE], UsageAccess.READ_WRITE),
        ([UsageAccess.READ, UsageAccess.WRITE], UsageAccess.READ_WRITE),
        ([UsageAccess.WRITE, UsageAccess.READ], UsageAccess.READ_WRITE),
        ([UsageAccess.READ, UsageAccess.UNKNOWN], UsageAccess.READ),
        ([UsageAccess.WRITE, UsageAccess.UNKNOWN], UsageAccess.WRITE),
        (
            [UsageAccess.READ, UsageAccess.WRITE, UsageAccess.UNKNOWN],
            UsageAccess.READ_WRITE,
        ),
        ([UsageAccess.READ_WRITE, UsageAccess.UNKNOWN], UsageAccess.READ_WRITE),
    ],
    ids=[
        "read",
        "write",
        "unknown",
        "rw",
        "r+w",
        "w+r",
        "r+u",
        "w+u",
        "r+w+u",
        "rw+u",
    ],
)
def test_combine_access(inputs: list[UsageAccess], expected: UsageAccess) -> None:
    assert combine_access(inputs) == expected


def test_combine_access_empty_raises() -> None:
    with pytest.raises(ValueError, match="no access"):
        combine_access([])


def test_merge_usages_sorts_and_combines_per_path() -> None:
    usages = [
        ModelUsage("pkg/b.py", UsageAccess.UNKNOWN),
        ModelUsage("pkg/a.py", UsageAccess.READ),
        ModelUsage("pkg/a.py", UsageAccess.WRITE),
        ModelUsage("pkg/b.py", UsageAccess.WRITE),
    ]
    assert merge_usages(usages) == [
        ModelUsage("pkg/a.py", UsageAccess.READ_WRITE),
        ModelUsage("pkg/b.py", UsageAccess.WRITE),
    ]


# --- _usage_table -----------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("r", UsageAccess.READ),
        ("rb", UsageAccess.READ),
        ("rt", UsageAccess.READ),
        ("w", UsageAccess.WRITE),
        ("wb", UsageAccess.WRITE),
        ("wt", UsageAccess.WRITE),
        ("a", UsageAccess.WRITE),
        ("ab", UsageAccess.WRITE),
        ("x", UsageAccess.WRITE),
        ("xb", UsageAccess.WRITE),
        ("r+", UsageAccess.READ_WRITE),
        ("rb+", UsageAccess.READ_WRITE),
        ("w+", UsageAccess.READ_WRITE),
        ("a+b", UsageAccess.READ_WRITE),
        ("", UsageAccess.UNKNOWN),
        ("b", UsageAccess.UNKNOWN),
    ],
)
def test_access_of_mode(mode: str, expected: UsageAccess) -> None:
    assert access_of_mode(mode) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("load", UsageAccess.READ),
        ("load_model", UsageAccess.READ),
        ("load_file", UsageAccess.READ),
        ("read_bytes", UsageAccess.READ),
        ("read_text", UsageAccess.READ),
        ("from_pretrained", UsageAccess.READ),
        ("restore", UsageAccess.READ),
        ("InferenceSession", UsageAccess.READ),
        ("Booster", UsageAccess.READ),
        ("Interpreter", UsageAccess.READ),
        ("Llama", UsageAccess.READ),
        ("save", UsageAccess.WRITE),
        ("save_model", UsageAccess.WRITE),
        ("save_file", UsageAccess.WRITE),
        ("save_pretrained", UsageAccess.WRITE),
        ("write_bytes", UsageAccess.WRITE),
        ("write_text", UsageAccess.WRITE),
        ("dump", UsageAccess.WRITE),
        ("export", UsageAccess.WRITE),
        ("to_onnx", UsageAccess.WRITE),
        ("exists", UsageAccess.UNKNOWN),
        ("stat", UsageAccess.UNKNOWN),
    ],
)
def test_access_of_name(name: str, expected: UsageAccess) -> None:
    assert access_of_name(name) == expected


@pytest.mark.parametrize(
    ("name", "mention"),
    [
        ("print", True),
        ("info", True),
        ("warning", True),
        ("warn", True),
        ("error", True),
        ("debug", True),
        ("FileNotFoundError", True),
        ("ValueError", True),
        ("RuntimeWarning", True),
        ("SystemExit", True),
        ("load", False),
        ("open", False),
    ],
)
def test_is_mention_call(name: str, mention: bool) -> None:
    assert is_mention_call(name) is mention


# --- _usage_match -----------------------------------------------------------


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("model.ftz", True),
        ("./model.ftz", True),
        ("data/model.ftz", True),
        ("pkg/data/model.ftz", True),
        ("src/pkg/data/model.ftz", True),
        ("data\\model.ftz", True),
        ("pkg\\data\\model.ftz", True),
        ("/abs/checkout/pkg/data/model.ftz", True),
        ("C:\\work\\src\\pkg\\data\\model.ftz", True),
        ("~/work/pkg/data/model.ftz", True),
        ("../data/model.ftz", True),
        ("data/sub/../model.ftz", True),
        ("%s/model.ftz", True),
        ("{}/data/model.ftz", True),
        ("other/model.ftz", False),
        ("pkg/other/model.ftz", False),
        ("/abs/other/model.ftz", False),
        ("{}/other/model.ftz", False),
        ("my_model.ftz", False),
        ("model.ftz.bak", False),
        ("saved model.ftz to disk", False),
        ("model.ftz/extra", False),
        ("", False),
        ("/", False),
    ],
)
def test_matches_path_shapes_and_directory_suffixes(
    literal: str, expected: bool
) -> None:
    assert matches(literal, _MODEL) is expected


# --- AST classification -----------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ('open("model.ftz")', {UsageAccess.READ}),
        ('open("model.ftz", "rb")', {UsageAccess.READ}),
        ('open("model.ftz", mode="rt")', {UsageAccess.READ}),
        ('open("model.ftz", "wb")', {UsageAccess.WRITE}),
        ('open("model.ftz", "a")', {UsageAccess.WRITE}),
        ('open("model.ftz", "x")', {UsageAccess.WRITE}),
        ('open("model.ftz", "r+b")', {UsageAccess.READ_WRITE}),
        ('open("model.ftz", mode)', {UsageAccess.UNKNOWN}),
        ('from pathlib import Path\nPath("model.ftz").open()', {UsageAccess.READ}),
        ('from pathlib import Path\nPath("model.ftz").open("wb")', {UsageAccess.WRITE}),
        (
            'from pathlib import Path\nPath("model.ftz").open(mode="w")',
            {UsageAccess.WRITE},
        ),
        (
            'from pathlib import Path\nPath("model.ftz").read_bytes()',
            {UsageAccess.READ},
        ),
        (
            'from pathlib import Path\nPath("model.ftz").write_bytes(b"")',
            {UsageAccess.WRITE},
        ),
        ('import h5py\nh5py.File("model.ftz")', {UsageAccess.READ}),
        ('import h5py\nh5py.File("model.ftz", "w")', {UsageAccess.WRITE}),
        ('import h5py\nh5py.File("model.ftz", "r+")', {UsageAccess.READ_WRITE}),
        ('import numpy as np\nnp.memmap("model.ftz")', {UsageAccess.READ_WRITE}),
        ('import numpy as np\nnp.memmap("model.ftz", str, "r")', {UsageAccess.READ}),
        ('import fasttext as ft\nft.load_model("model.ftz")', {UsageAccess.READ}),
        ('from joblib import load\nload("model.ftz")', {UsageAccess.READ}),
        ('from joblib import dump\ndump(obj, "model.ftz")', {UsageAccess.WRITE}),
        ('import torch\ntorch.save(state, "model.ftz")', {UsageAccess.WRITE}),
        ('import torch\ntorch.save(obj=state, f="model.ftz")', {UsageAccess.WRITE}),
        ('import torch\ntorch.load("model.ftz")', {UsageAccess.READ}),
        ('import onnx\nonnx.load("model.ftz")', {UsageAccess.READ}),
        ('import onnx\nonnx.save(m, "model.ftz")', {UsageAccess.WRITE}),
        (
            'import onnxruntime as ort\nort.InferenceSession("model.ftz")',
            {UsageAccess.READ},
        ),
        (
            'from safetensors.torch import load_file\nload_file("model.ftz")',
            {UsageAccess.READ},
        ),
        (
            'from safetensors.torch import save_file\nsave_file(t, "model.ftz")',
            {UsageAccess.WRITE},
        ),
        ('AutoModel.from_pretrained("model.ftz")', {UsageAccess.READ}),
        ('model.save_model("model.ftz")', {UsageAccess.WRITE}),
        ('tagger.open("model.ftz")', {UsageAccess.READ}),
        ('get_loader().load("model.ftz")', {UsageAccess.READ}),
        ('callbacks[0]("model.ftz")', {UsageAccess.UNKNOWN}),
        ('os.path.exists("model.ftz")', {UsageAccess.UNKNOWN}),
        ('Path("model.ftz").stat()', {UsageAccess.UNKNOWN}),
        ('Path("model.ftz").suffix', {UsageAccess.UNKNOWN}),
        ('FILES = ["model.ftz"]', {UsageAccess.UNKNOWN}),
    ],
    ids=lambda val: val if isinstance(val, str) and len(val) < 30 else "case",
)
def test_call_and_mode_classification(code: str, expected: set[UsageAccess]) -> None:
    assert _accesses(code) == expected


@pytest.mark.parametrize(
    "code",
    [
        "# model.ftz\nx = 1\n",
        '"""Module docstring mentioning model.ftz."""\n',
        'def f():\n    """Function docstring: model.ftz"""\n    return 1\n',
        'class C:\n    """Class docstring: model.ftz"""\n',
        '"bare string statement model.ftz"\n',
        'print("model.ftz")\n',
        'import logging\nlogging.info("loading %s", "model.ftz")\n',
        'logger.warning("missing %s", "model.ftz")\n',
        'import warnings\nwarnings.warn("model.ftz")\n',
        'raise FileNotFoundError("model.ftz")\n',
        'raise RuntimeError("model.ftz")\n',
        'raise "model.ftz"\n',
        'assert ok, "model.ftz"\n',
        'msg = "Failed to load model.ftz from disk"\n',
    ],
    ids=[
        "comment",
        "module-doc",
        "func-doc",
        "class-doc",
        "bare-expr",
        "print",
        "logging-info",
        "logger-warn",
        "warnings-warn",
        "raise-fnf",
        "raise-rt",
        "raise-bare",
        "assert-msg",
        "sentence",
    ],
)
def test_mention_only_and_non_path_strings_produce_no_edge(code: str) -> None:
    assert not _accesses(code)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ('M = "data/model.ftz"\nopen(M, "rb")\n', {UsageAccess.READ}),
        ('M: str = "data/model.ftz"\nopen(M, "wb")\n', {UsageAccess.WRITE}),
        ('A = "data"\nB = A + "/model.ftz"\nopen(B)\n', {UsageAccess.READ}),
        ('M = "data/model.ftz"\nprint(M)\n', set()),
        ('M = "data/model.ftz"\n', {UsageAccess.UNKNOWN}),
        ('M = "data/model.ftz"\nM = "other"\nopen(M)\n', {UsageAccess.UNKNOWN}),
        ('self.path = "data/model.ftz"\n', {UsageAccess.UNKNOWN}),
        (
            'from pathlib import Path\nopen(Path("pkg") / "data" / "model.ftz")\n',
            {UsageAccess.READ},
        ),
        (
            "from pathlib import Path\n"
            'Path(__file__).parent.joinpath("data", "model.ftz").read_bytes()\n',
            {UsageAccess.READ},
        ),
        (
            'from pathlib import Path\nopen(str(Path("data/model.ftz").resolve()))\n',
            {UsageAccess.READ},
        ),
        (
            'import os\nopen(os.path.join(base, "data", "model.ftz"), "wb")\n',
            {UsageAccess.WRITE},
        ),
        ('open(f"{base}/data/model.ftz")\n', {UsageAccess.READ}),
        ('D = "data"\nopen(f"{D}/model.ftz", "wb")\n', {UsageAccess.WRITE}),
        ('open(f"{base}/other/model.ftz")\n', set()),
        ('open("%s/data/model.ftz" % base)\n', {UsageAccess.READ}),
        ('open("{}/data/model.ftz".format(base))\n', {UsageAccess.READ}),
        ('open(prefix + "/data/model.ftz")\n', {UsageAccess.READ}),
        ('open(prefix + "model.ftz")\n', set()),
        ('open("data\\\\model.ftz")\n', {UsageAccess.READ}),
    ],
    ids=[
        "const-assign",
        "ann-assign",
        "chained-const",
        "const-printed",
        "const-unread",
        "reassigned",
        "attr-assign",
        "path-div",
        "joinpath",
        "str-resolve",
        "os-join",
        "fstring-unknown-head",
        "fstring-known",
        "fstring-wrong-dir",
        "percent-format",
        "str-format",
        "add-with-sep",
        "add-no-sep",
        "windows-backslash",
    ],
)
def test_intra_file_path_resolution(code: str, expected: set[UsageAccess]) -> None:
    assert _accesses(code) == expected


def test_read_and_write_in_one_file_both_recorded() -> None:
    code = 'M = "model.ftz"\nsave_model(M)\nload_model(M)\n'
    found = _accesses(code)
    assert found == {UsageAccess.READ, UsageAccess.WRITE}
    assert combine_access(found) == UsageAccess.READ_WRITE


def test_bare_filename_matches_each_same_named_model_while_dir_disambiguates() -> None:
    m1 = UsageModel("m.bin", ("pkg/a/m.bin",))
    m2 = UsageModel("m.bin", ("pkg/b/m.bin",))
    assert find_usages(parse_python('load("m.bin")'), [m1, m2]) == [
        {UsageAccess.READ},
        {UsageAccess.READ},
    ]
    assert find_usages(parse_python('load("a/m.bin")'), [m1, m2]) == [
        {UsageAccess.READ},
        set(),
    ]


def test_parse_python_silences_invalid_escape_warnings_under_error_filter() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tree = parse_python('open("data\\model.ftz")\n')
    assert find_usages(tree, [_MODEL]) == [{UsageAccess.READ}]


def test_python_version_is_major_dot_minor() -> None:
    ver = python_version()
    parts = ver.split(".")
    assert len(parts) == 2 and all(p.isdigit() for p in parts)
