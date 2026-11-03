# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the AST model-usage visitor (:mod:`pitloom.extract._usage_ast`).

Pure functions only -- no file I/O.

See also: :mod:`tests.extract.scanner.test_usage_match` (call table and path
matcher tests), :mod:`tests.extract.scanner.test_usage_unparseable`
(parse-failure reporting) and :mod:`tests.extract.scanner.test_scanner`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import warnings

import pytest

from pitloom.core.model_usage import UsageAccess, combine_access
from pitloom.extract._usage_ast import find_usages
from pitloom.extract._usage_match import UsageModel
from pitloom.extract._usage_parse import parse_python, python_version

_MODEL = UsageModel("model.ftz", ("pkg/data/model.ftz", "src/pkg/data/model.ftz"))


def _accesses(source: str, model: UsageModel = _MODEL) -> frozenset[UsageAccess]:
    (found,) = find_usages(parse_python(source), [model])
    return found


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
        (
            'from joblib import load as jl_load\njl_load("model.ftz")',
            {UsageAccess.READ},
        ),
        ('from .utils import load_model as lm\nlm("model.ftz")', {UsageAccess.READ}),
        ('from joblib import dump\ndump(obj, "model.ftz")', {UsageAccess.WRITE}),
        ('import torch\ntorch.save(state, "model.ftz")', {UsageAccess.WRITE}),
        ('import torch\ntorch.save(obj=state, f="model.ftz")', {UsageAccess.WRITE}),
        ('import torch\ntorch.load("model.ftz")', {UsageAccess.READ}),
        (
            'import torch\ntorch.load("model.ftz" if cond else "other.ftz")',
            {UsageAccess.READ},
        ),
        ('open(custom or "model.ftz", "wb")', {UsageAccess.WRITE}),
        ('import tarfile\ntarfile.open("model.ftz", "r:xz")', {UsageAccess.READ}),
        (
            'from safetensors import safe_open\nsafe_open("model.ftz", "pt")',
            {UsageAccess.READ},
        ),
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
        ("f\"{load_model('model.ftz')}\"", {UsageAccess.READ}),
        (
            'from pathlib import Path\nPath("model.ftz").read_text() + "\\n"',
            {UsageAccess.READ},
        ),
        ('"{}".format(load_model("model.ftz"))', {UsageAccess.READ}),
        ('"%s" % load_model("model.ftz")', {UsageAccess.READ}),
        ('callbacks[0]("model.ftz")', {UsageAccess.UNKNOWN}),
        (
            'from pathlib import Path\ncallback(Path("model.ftz").read_bytes)',
            {UsageAccess.UNKNOWN},
        ),
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
        'raise CustomProblem("model.ftz")\n',
        'raise "model.ftz"\n',
        'assert ok, "model.ftz"\n',
        'print("model.ftz" if cond else "other")\n',
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
        "raise-custom",
        "raise-bare",
        "assert-msg",
        "print-ifexp",
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
        ('M = "data/model.ftz"\nbak = f"{M}.bak"\n', {UsageAccess.UNKNOWN}),
        ('M = "data/model.ftz"\nM = "other"\nopen(M)\n', {UsageAccess.UNKNOWN}),
        ('M = "data/model.ftz"\ndel M\n', {UsageAccess.UNKNOWN}),
        ('M = "data/model.ftz"\ndef f(M): open(M, "wb")\n', {UsageAccess.UNKNOWN}),
        ('M = "data/model.ftz"\nimport os as M\n', {UsageAccess.UNKNOWN}),
        ('M = "data/model.ftz"\ndef M(): pass\n', {UsageAccess.UNKNOWN}),
        (
            'M = "data/model.ftz"\ntry:\n    pass\nexcept Exception as M:\n    pass\n',
            {UsageAccess.UNKNOWN},
        ),
        (
            'M = "data/model.ftz"\nmatch x:\n    case str() as M:\n'
            '        open(M, "wb")\n',
            {UsageAccess.UNKNOWN},
        ),
        ('M: str\nA = B = "data/model.ftz"\n', {UsageAccess.UNKNOWN}),
        (
            'def load(p: str = "data/model.ftz"):\n    return open(p, "rb")\n',
            {UsageAccess.READ},
        ),
        (
            'def load(*, p: str = "data/model.ftz"):\n    print(p)\n',
            set(),
        ),
        (
            'def load(p: str = "data/model.ftz"):\n    return 1\n',
            {UsageAccess.UNKNOWN},
        ),
        ('self.path = "data/model.ftz"\n', {UsageAccess.UNKNOWN}),
        ('open("{\u00b2}".format(1))\nW = "model.ftz"\n', {UsageAccess.UNKNOWN}),
        (
            'M = "data/model.ftz"\ndef f(p=M):\n    return open(p, "wb")\n',
            {UsageAccess.WRITE},
        ),
        (
            'B = "other"\ndef f(p=B + "/model.ftz"):\n    return open(p)\n',
            set(),
        ),
        ('A = "data/model.ftz"\nB = A\nprint(B)\n', set()),
        ('A = "data/model.ftz"\nB = A\nopen(B, "wb")\n', {UsageAccess.WRITE}),
        (
            'from pathlib import Path\nM = "data/model.ftz"\nP = Path(M)\n'
            "torch.load(P)\n",
            {UsageAccess.READ},
        ),
        ('open("{!s}/{}".format("model.ftz", "x"))\n', set()),
        ('open("{:s}/{}".format("data", "model.ftz"))\n', {UsageAccess.READ}),
        ('open("data/{n!s}".format(n="model.ftz"))\n', {UsageAccess.READ}),
        ('open("{.x}/{}".format(a, "model.ftz"))\n', {UsageAccess.READ}),
        ('open("{:{}}/{}".format("a", 4, "model.ftz"))\n', set()),
        ('open("{}/{}".format(*xs, "model.ftz"))\n', set()),
        ('open("%s/%s" % (*xs, "model.ftz"))\n', set()),
        ('open("{{}}/{}".format("model.ftz"))\n', {UsageAccess.READ}),
        ('open("{".format("model.ftz"))\n', set()),
        ('open("x%%s/%s" % "model.ftz")\n', {UsageAccess.READ}),
        ('open("%5s" % "model.ftz")\n', set()),
        ('open("%*d/%s" % (3, 4, "model.ftz"))\n', set()),
        ('open("data/%(n)s" % {"n": "model.ftz"})\n', {UsageAccess.READ}),
        ('open("other/%(n)s" % {"n": "model.ftz"})\n', set()),
        ('open("data/%(n)s" % ("model.ftz",))\n', set()),
        ('open("data/%(n)s" % {**d, "m": "model.ftz"})\n', set()),
        ("open(f\"{'data/model.ftz'!s}\")\n", {UsageAccess.READ}),
        ("open(f\"{'data/model.ftz'!r}\")\n", {UsageAccess.UNKNOWN}),
        ("def load(*, p):\n    return p\n", set()),
        ("def load(p=1):\n    return p\n", set()),
        ('open(base % "model.ftz")\n', set()),
        (
            'from pathlib import Path\nopen(Path("pkg") / "data" / "model.ftz")\n',
            {UsageAccess.READ},
        ),
        (
            "from pathlib import PureWindowsPath\n"
            'open(PureWindowsPath("pkg\\\\data") / "model.ftz")\n',
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
        (
            'from os.path import join\nopen(join(base, "data", "model.ftz"))\n',
            {UsageAccess.READ},
        ),
        (
            "import os.path as osp\n"
            'open(osp.join("other", "/abs/pkg/data/model.ftz"))\n',
            {UsageAccess.READ},
        ),
        (
            'import ntpath\nopen(ntpath.join(base, "data\\\\model.ftz"))\n',
            {UsageAccess.READ},
        ),
        (
            'from . import join\nopen(join("other", "model.ftz"))\n',
            {UsageAccess.UNKNOWN},
        ),
        ('open(f"{base}/data/model.ftz")\n', {UsageAccess.READ}),
        ('D = "data"\nopen(f"{D}/model.ftz", "wb")\n', {UsageAccess.WRITE}),
        ('EXT = ".ftz"\nopen(f"data/model{EXT}")\n', {UsageAccess.READ}),
        ('EXT = ".ftz"\nopen(f"data/model{EXT!r}")\n', set()),
        ('EXT = ".ftz"\nopen(f"data/model{EXT:>8}")\n', set()),
        ('open(f"{base}/other/model.ftz")\n', set()),
        ('open(f"{base}//other/model.ftz")\n', set()),
        ('open(f"{prefix}model.ftz")\n', set()),
        ('open("%s/data/model.ftz" % base)\n', {UsageAccess.READ}),
        ('open("data/%s" % "model.ftz")\n', {UsageAccess.READ}),
        ('open("%s/%s" % ("data", "model.ftz"))\n', {UsageAccess.READ}),
        ('open("%s/model.ftz" % "other")\n', set()),
        ('open("{}/data/model.ftz".format(base))\n', {UsageAccess.READ}),
        ('open("data/{}".format("model.ftz"))\n', {UsageAccess.READ}),
        ('open("{0}/{1}".format("data", "model.ftz"))\n', {UsageAccess.READ}),
        ('open("{d}/{f}".format(d="data", f="model.ftz"))\n', {UsageAccess.READ}),
        ('open("{}/model.ftz".format("other"))\n', set()),
        ('open(prefix + "/data/model.ftz")\n', {UsageAccess.READ}),
        ('open(prefix + "model.ftz")\n', set()),
        ('open("data/model.ftz" + ext)\n', set()),
        ('from pathlib import Path\nopen(Path("model.ftz") / sub)\n', set()),
        ('open(str("data/model.ftz", "utf-8"))\n', {UsageAccess.UNKNOWN}),
        ('open("data\\\\model.ftz")\n', {UsageAccess.READ}),
    ],
    ids=lambda val: val if isinstance(val, str) and len(val) < 24 else "case",
)
def test_intra_file_path_resolution(code: str, expected: set[UsageAccess]) -> None:
    assert _accesses(code) == expected


def test_deep_and_exponential_constants_stay_bounded() -> None:
    chain = ['A0 = "a/model.ftz"']
    for idx in range(1, 31):
        chain.append(f'A{idx} = A{idx - 1} + "/" + A{idx - 1}')
    chain.append("open(A30)")
    assert _accesses("\n".join(chain)) == set()

    deep = " + ".join(['"a"'] * 200)
    assert _accesses(f'x = {deep}\nopen("model.ftz")\n') == {UsageAccess.READ}


def test_expression_over_a_cap_is_not_followed() -> None:
    """Past the depth or length cap an expression gives no edge, not just
    the tail that is left of it."""
    nested = "Path(" * 70 + '"other"' + ")" * 70
    assert _accesses(f'open({nested} / "model.ftz")\n') == set()
    assert _accesses('open(Path(Path("other")) / "model.ftz")\n') == set()
    shallow = 'from pathlib import Path\nopen(Path(Path("data")) / "model.ftz")\n'
    assert _accesses(shallow) == {UsageAccess.READ}
    long = "x" * 4100
    assert _accesses(f'open(base + "{long}" + "/model.ftz")\n') == set()
    assert _accesses('open(base + "data" + "/model.ftz")\n') == {UsageAccess.READ}


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
