# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edge cases of the AST model-usage visitor found by mutation testing:
the caps' boundaries, the call sets, name binding and the expression shapes
that are (and are not) one path.

See also: :mod:`tests.extract.scanner.test_usage_ast` (the main cases) and
:mod:`tests.extract.scanner.test_usage_templates` (``.format``, ``%``, the
call table and the path matcher).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
import time

import pytest

from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_ast import find_usages
from pitloom.extract._usage_match import UsageModel
from pitloom.extract._usage_parse import parse_python

from ._usage_helpers import accesses

_R = UsageAccess.READ
_U = UsageAccess.UNKNOWN
_W = UsageAccess.WRITE
_ROOT = ("model.pkl",)
_DATA = ("data/model.pkl",)
_D = ("d/model.pkl",)


def _nest(depth: int) -> str:
    code = '"model.pkl"'
    for _ in range(depth):
        code = f'("d/" + {code})'
    return f"x = {code}\n"


@pytest.mark.parametrize(
    ("depth", "expected"), [(64, {_U}), (65, set())], ids=["at-cap", "over-cap"]
)
def test_depth_cap_boundary(depth: int, expected: set[UsageAccess]) -> None:
    assert (
        accesses(_nest(depth), "model.pkl", (f"{'d/' * depth}model.pkl",)) == expected
    )


@pytest.mark.parametrize(
    ("size", "expected"), [(4096, {_U}), (4097, set())], ids=["at-cap", "over-cap"]
)
def test_path_length_cap_boundary(size: int, expected: set[UsageAccess]) -> None:
    name = "m" * size
    assert accesses(f"x = {name!r}\n", name, (name,)) == expected


def test_nested_format_is_memoised() -> None:
    code = '"model.pkl"'
    for _ in range(22):
        code = f'"{{}}".format({code})'
    start = time.monotonic()
    assert accesses(f"open({code})\n") == {_R}
    assert time.monotonic() - start < 5


@pytest.mark.parametrize(
    "code",
    [
        "open(PureWindowsPath('model.pkl'))",
        "open(PurePath('model.pkl'))",
        "import os\nopen(os.path.expandvars('model.pkl'))",
        "import os\nopen(os.fspath('model.pkl'))",
        "open(Path('model.pkl').absolute())",
        "import zipfile\nzipfile.ZipFile('model.pkl')",
        "import tarfile\ntarfile.TarFile('model.pkl')",
        "open(Path('model.pkl').joinpath())",
    ],
    ids=lambda code: code.splitlines()[-1][:30],
)
def test_call_sets(code: str) -> None:
    assert accesses(code) == {_R}


@pytest.mark.parametrize(
    ("code", "paths", "expected"),
    [
        ("import os\nopen(os.path.join('d', 'model.pkl'))", _D, {_R}),
        ("import os.path\nopen(os.path.join('d', 'model.pkl'))", _D, {_R}),
        ("from .posixpath import join\nopen(join('d', 'model.pkl'))", _DATA, {_U}),
        (
            "from x import os\nimport os.path\nopen(os.path.join('d', 'model.pkl'))",
            _D,
            {_R},
        ),
        ("import os\nopen(os.path.join('', 'model.pkl'))", _DATA, {_R}),
        ("import os\nopen(os.path.join(f'', 'model.pkl'))", _DATA, {_R}),
        ("open(Path('other').joinpath('model.pkl'))", _DATA, set()),
        ("open(Path('data').joinpath('model.pkl'))", _DATA, {_R}),
        ("import os\nopen(os.path.join('other', x, 'model.pkl'))", _DATA, {_R}),
        ("import os\nopen(os.path.join('data/model.pkl', x))", _DATA, set()),
        ("import os\nopen(os.path.join(f'{x}/', 'model.pkl'))", _DATA, {_R}),
        ("open(f'{x}\\\\model.pkl')", _ROOT, {_R}),
    ],
    ids=str,
)
def test_imports_and_joins(
    code: str, paths: tuple[str, ...], expected: set[UsageAccess]
) -> None:
    assert accesses(code, "model.pkl", paths) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("MODEL='model.pkl'\ndel MODEL\nopen(MODEL)", {_U}),
        ("import os.path\nos='model.pkl'\nopen(os)", {_U}),
        (
            "MODEL='model.pkl'\ntry:\n pass\nexcept Exception as MODEL:\n pass\n"
            "open(MODEL)",
            {_U},
        ),
        ("MODEL='model.pkl'\nmatch x:\n case [*MODEL]:\n  pass\nopen(MODEL)", {_U}),
        ("MODEL='model.pkl'\nclass MODEL:\n pass\nopen(MODEL)", {_U}),
        ("B = A\nA = 'model.pkl'\nopen(A)", {_R, _U}),
        ("A = B = 'model.pkl'\nopen(A)", {_U}),
        ("async def f(p='model.pkl'):\n open(p)", {_R}),
        ("def f(a, p='model.pkl'):\n open(p)", {_R}),
        ("def f(p='model.pkl'):\n open(p)\n p = 1", {_U}),
        ("A='model.pkl'\nB=A\nC=B\nopen(C)", {_R}),
        ("X='model.pkl'\nX=g()\nopen(f'{X}/model.pkl')", {_R, _U}),
        ("MODEL: 'model.pkl' = 'model.pkl'\nopen(MODEL)", {_R, _U}),
        ("MODEL='model.pkl'\nopen(*MODEL)", {_R}),
        ("open('x' if ('model.pkl' if a else 'b') else 'z')", {_U}),
        ("load='model.pkl'\nload()", {_U}),
        ("str='model.pkl'\nopen(str)\nstr('x')", {_R, _U}),
    ],
    ids=lambda val: val.replace("\n", ";")[:40] if isinstance(val, str) else "x",
)
def test_name_binding(code: str, expected: set[UsageAccess]) -> None:
    assert accesses(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("open('%s' % (*x, 'model.pkl'))", set()),
        ("x.format('model.pkl')", set()),
        ("x = Path(foo='model.pkl')", {_U}),
        ("open(f'{\"model.pkl\":>20}')", {_U}),
        ("x = ('model.pkl',) + other", {_U}),
        ("import os\nos.fspath('model.pkl'.foo)", {_U}),
        ("open(f'{x}/model.pkl')", {_R}),
    ],
    ids=str,
)
def test_expression_shapes(code: str, expected: set[UsageAccess]) -> None:
    assert accesses(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("import zipfile\nzipfile.ZipFile('model.pkl')", {_R}),
        ("open('model.pkl', 'U')", {_U}),
        ("open('model.pkl', 'rU')", {_R}),
        ("log.exception('model.pkl')", set()),
        ("log.critical('model.pkl')", set()),
        ("log.fatal('model.pkl')", set()),
        ("log('model.pkl')", set()),
        ("click.echo('model.pkl')", set()),
        ("sys.exit('model.pkl')", set()),
        ("e = Exception('model.pkl')", set()),
        ("open('model.pkl', 'w')", {_W}),
    ],
    ids=str,
)
def test_calls_and_modes(code: str, expected: set[UsageAccess]) -> None:
    assert accesses(code) == expected


def test_parse_and_find_agree_on_an_empty_file() -> None:
    assert find_usages(parse_python(""), []) == []


def test_a_long_alias_chain_is_followed_in_linear_time() -> None:
    n = 3000
    lines = ['A0 = "data/model.pkl"']
    lines += [f"A{i} = A{i - 1}" for i in range(1, n)]
    lines.append(f"open(A{n - 1})")
    start = time.monotonic()
    assert accesses("\n".join(lines) + "\n", "model.pkl", _DATA) == {_R}
    assert time.monotonic() - start < 2


@pytest.mark.parametrize(
    "code",
    [
        "print(f\"loading {'data/model.pkl'!r}\")",
        "print(f\"{'data/model.pkl':>30}\")",
        "raise ValueError(f\"missing {Path('data/model.pkl')!r}\")",
        "p = 'data/model.pkl'\nprint(f'{p!r}')",
    ],
    ids=["repr", "spec", "path-repr", "constant-repr"],
)
def test_a_path_only_printed_with_a_conversion_or_spec_is_no_use(code: str) -> None:
    assert accesses(code, "model.pkl", _DATA) == set()


@pytest.mark.parametrize(
    "operand",
    ["{'a': 'other', **d}", "{'a': 'other', k: 1}"],
    ids=["unpacking", "computed-key"],
)
def test_an_earlier_dict_key_may_be_replaced_by_a_later_unknown_entry(
    operand: str,
) -> None:
    assert accesses(f"open('%(a)s/model.pkl' % {operand})", "model.pkl", _DATA) == {_R}


@pytest.mark.parametrize(
    "operand",
    ["{**d, 'a': 'other'}", "{1: 'x', 'a': 'other'}"],
    ids=["unpacking-first", "int-key"],
)
def test_a_dict_key_nothing_can_replace_is_known(operand: str) -> None:
    assert accesses(f"open('%(a)s/model.pkl' % {operand})", "model.pkl", _DATA) == set()


@pytest.mark.parametrize(
    "code",
    [
        "open('x\\x00/model.pkl' % ())",
        "open('\\x00/model.pkl'.format())",
        "open(f'\\x00/model.pkl'.format())",
    ],
    ids=["percent", "format", "fstring-template"],
)
def test_a_literal_with_a_nul_is_no_path(code: str) -> None:
    assert accesses(code, "model.pkl", _DATA) == set()


@pytest.mark.parametrize(
    "code",
    [
        "p = 'data/model.pkl'\nmatch cfg:\n    case {**p}:\n        torch.save(x, p)",
        *(
            pytest.param(
                f"def f[{params}](x): pass\nT = 'data/model.pkl'\nopen(T)",
                marks=pytest.mark.skipif(
                    sys.version_info < (3, 12), reason="type parameters need 3.12"
                ),
            )
            for params in ("T", "**T", "*T")
        ),
    ],
    ids=["match-mapping-rest", "type-var", "param-spec", "type-var-tuple"],
)
def test_a_name_bound_by_a_pattern_or_type_parameter_is_not_a_constant(
    code: str,
) -> None:
    assert accesses(code, "model.pkl", _DATA) == {_U}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("MODEL = 'model.pkl'\nf.write(MODEL)", {_U}),
        ("sys.stdout.write('model.pkl')", {_U}),
        ("Path('manifest.txt').write_text('model.pkl')", {_U}),
        ("f.writelines('model.pkl')", {_U}),
        ("Path('manifest.txt').write_bytes('model.pkl')", {_U}),
        ("json.dump('model.pkl', f)", {_U}),
        ("zf.write('model.pkl')", {_U}),
        ("joblib.dump(obj, 'model.pkl')", {_W}),
        ("joblib.dump(obj, filename='model.pkl')", {_W}),
        ("Path('model.pkl').write_text('x')", {_W}),
        ("f.Write('model.pkl')", {_U}),
        ("json.Dump('model.pkl', f)", {_U}),
        ("json.loads('model.pkl')", set()),
        ("pickle.dumps('model.pkl')", set()),
    ],
    ids=str,
)
def test_a_path_in_a_data_position_is_not_a_file_access(
    code: str, expected: set[UsageAccess]
) -> None:
    assert accesses(code) == expected


def test_reach_of_one_model_does_not_leak_to_another() -> None:
    models = [
        UsageModel("x.pkl", ("y.pkl/x.pkl",)),
        UsageModel("y.pkl", ("y.pkl/x.pkl/y.pkl",)),
    ]
    source = "R = 'y.pkl'\nP = R + '/x.pkl'\nopen(P + '/y.pkl')\n"
    assert find_usages(parse_python(source), models) == [{_U}, {_R, _U}]


def test_an_f_string_restarts_after_a_nul_piece() -> None:
    assert accesses("x = 'dir/model.pkl'\nopen(f'\\x00{x}')", "model.pkl", _DATA) == {
        _R
    }
