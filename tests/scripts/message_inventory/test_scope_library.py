# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``scripts/message_inventory/_scope.py``: a raise is a library caller's
misuse, out of scope, only through the helpers of ``LIBRARY_EXC`` (the loom
SDK outside a ``loom.run()``) or as a raise ``LIBRARY_SITES`` names by
file, function, class and text (a value of the wrong Python type); a library
text alone (``loom SDK: ...``, ``No model set``), a ``TypeError`` elsewhere,
or another raise in a named function stays counted.

Each case is a line of :data:`SOURCE` or :data:`SITE_SOURCE` ending in
``# in: <id>`` (the ratchet counts it) or ``# out: <id>`` (it does not).

See also: test_scope_os_error.py (rule R-a), test_inventory.py.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SOURCE = """\
def call(value):
    raise _no_active_run("set_model")  # out: no-active-run
    raise TypeError(f"loom SDK: declared_license is not a str: {value}")  # in: type
    raise TypeError("x")  # in: bare-type
    raise _no_model_set("x")  # in: other-helper
    raise RuntimeError("No active loom.run() found")  # in: library-text
    raise RuntimeError("No model set. Call set_model() first.")  # in: no-model-text
    raise ValueError("loom SDK: croissant= is a URL")  # in: sdk-prefix
    raise ValueError("loom: croissant= is a URL")  # in: old-prefix
    raise ValueError("x is a Hugging Face source; not enriched")  # in: hf
"""
#: Two raises ``LIBRARY_SITES`` names, the same text in another function,
#: and new raises beside a named one: none of those is exempt.
SITE_SOURCE = """\
def scalar_text(value):
    raise TypeError(f"not a scalar: {type(value).__name__}")  # out: site
    raise TypeError("not a scalar")  # in: new-text
    raise ValueError(f"not a scalar: {type(value).__name__}")  # in: new-class
def other(value):
    raise TypeError(f"not a scalar: {type(value).__name__}")  # in: other
"""
#: ``IdRegistry._mint_id``: its library raise, and a new uncoded one.
REGISTRY_SOURCE = """\
class IdRegistry:
    def _mint_id(self, prefix):
        raise ValueError("ID registry: no id prefix for an empty type name")  # out: reg
        raise ValueError("ID registry: id number past the ceiling")  # in: reg-new
"""
_FILES = {
    "caller.py": SOURCE,
    "core/scalar_text.py": SITE_SOURCE,
    "id_registry/_registry.py": REGISTRY_SOURCE,
}

_MARK = re.compile(r"# (in|out): (\S+)$")
CASES = [
    (name, n, mark[0] == "in", mark[1])
    for name, source in _FILES.items()
    for n, line in enumerate(source.splitlines(), start=1)
    for mark in _MARK.findall(line)
]


@pytest.fixture(name="records", scope="module")
def records_fixture(
    mi: ModuleType, tmp_path_factory: pytest.TempPathFactory
) -> list[dict[str, Any]]:
    """The sites of :data:`SOURCE` as ``src/pitloom/caller.py``."""
    root = tmp_path_factory.mktemp("library")
    package = root / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    for name, source in _FILES.items():
        (package / name).parent.mkdir(exist_ok=True)
        (package / name).write_bytes(source.encode("utf-8"))
    return mi.inventory(Path(root))  # type: ignore[no-any-return]


def test_every_case_is_found() -> None:
    assert len(CASES) == 15


@pytest.mark.parametrize(
    ("name", "line", "scoped"),
    [(name, n, scoped) for name, n, scoped, _ in CASES],
    ids=[case_id for _, _, _, case_id in CASES],
)
def test_only_the_helper_or_a_named_site_is_library_misuse(
    mi: ModuleType,
    records: list[dict[str, Any]],
    name: str,
    line: int,
    scoped: bool,
) -> None:
    (site,) = [
        r for r in records if r["file"] == f"src/pitloom/{name}" and r["line"] == line
    ]
    assert mi.in_scope(site) is scoped


#: The library exemptions as ruled, by file, function and class (the text
#: of each is checked against the tree by tests/test_message_ratchet.py): a
#: new helper name or a new raise is a decision, so it changes this test too.
_LIBRARY_EXC = frozenset({"_no_active_run"})
_REGISTRY = "src/pitloom/id_registry/_registry.py"
_LIBRARY_SITES = frozenset(
    {
        (
            "src/pitloom/core/_models_wheel_types.py",
            "validate_build_timeout",
            "TypeError",
        ),
        (
            "src/pitloom/core/build_options.py",
            "BuildOptions.__post_init__",
            "TypeError",
        ),
        ("src/pitloom/core/scalar_text.py", "scalar_text", "TypeError"),
        (_REGISTRY, "_require_bool", "TypeError"),
        (_REGISTRY, "IdRegistry.load", "TypeError"),
        (_REGISTRY, "IdRegistry._mint_id", "ValueError"),
        (_REGISTRY, "IdRegistry.save", "ValueError"),
        ("src/pitloom/id_registry/_types.py", "_require_names", "TypeError"),
    }
)


def test_the_library_exemptions_are_pinned(mi: ModuleType) -> None:
    scope = importlib.import_module(f"{mi.__name__}._scope")
    assert scope.LIBRARY_EXC == _LIBRARY_EXC
    assert len(scope.LIBRARY_SITES) == len(_LIBRARY_SITES)
    assert {site[:3] for site in scope.LIBRARY_SITES} == _LIBRARY_SITES


def test_a_new_helper_or_a_loom_prefix_fails_the_ratchet(
    mi_main: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A raise through a helper ``LIBRARY_EXC`` does not name, or a text
    starting ``loom: ``, is an uncoded site: the ratchet fails on it."""
    package = tmp_path / "src" / "pitloom"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    source = package / "caller.py"
    source.write_bytes(b'def call():\n    raise _no_active_run("set_model")\n')
    baseline = tmp_path / "uncoded.txt"
    args = ["--root", str(tmp_path), "--baseline", str(baseline)]
    assert mi_main.main([*args, "--write-baseline"]) == 0
    assert mi_main.main([*args, "--check"]) == 0
    for raise_line in ('raise _no_model_set("x")', 'raise ValueError("loom: x")'):
        source.write_bytes(
            b'def call():\n    raise _no_active_run("set_model")\n'
            + f"    {raise_line}\n".encode()
        )
        capsys.readouterr()
        assert mi_main.main([*args, "--check"]) == 1
        assert capsys.readouterr().err.startswith("ERROR: pitloom.caller: 1 uncoded")
