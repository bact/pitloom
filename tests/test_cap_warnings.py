# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for an input over a cap
(:func:`pitloom.logging_config.warn_over_cap`), and a drift guard: every cap
Pitloom defines as a module constant is wrapped in a ``Cap`` that its own
module passes to it, or is listed with why not.

See also: tests/test_logging_config.py (the shared log formatting).
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

import pytest

from pitloom import logging_config
from pitloom.extract._license_detect import LICENSE_FILE_MAX_BYTES, read_license_members
from pitloom.logging_config import Cap, over_cap_of, warn_over_cap

_LOG = logging.getLogger("pitloom.test_cap_warnings")


@pytest.mark.parametrize(
    ("cap", "where", "once", "expected"),
    [
        (
            Cap(10, "byte", "usage-scan"),
            "a.py",
            False,
            "FILE=a.py: larger than the 10-byte usage-scan cap; skipped",
        ),
        (
            Cap(3, "entry", "self-reference expansion", "FIELD"),
            "x\n::error::\x1b",
            True,
            "FIELD='x\\n::error::\\x1b': larger than the 3-entry self-reference"
            " expansion cap; skipped",
        ),
        (
            Cap(4, "level", "GGUF-array-nesting").after("FORMAT=gguf"),
            "m.gguf",
            True,
            "FORMAT=gguf FILE=m.gguf: larger than the 4-level GGUF-array-nesting"
            " cap; skipped",
        ),
    ],
    ids=["file", "field-escaped-once", "keys-after"],
)
def test_warn_over_cap(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    cap: Cap,
    where: str,
    once: bool,
    expected: str,
) -> None:
    """*where* is escaped (no forged second line); *once* logs a repeat
    at DEBUG; each record carries its cap for a relay."""
    monkeypatch.setattr(logging_config, "_WARNED_ONCE", set())
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        warn_over_cap(_LOG, cap, where, once=once)
        warn_over_cap(_LOG, cap, where, once=once)
    levels = [logging.WARNING, logging.DEBUG if once else logging.WARNING]
    assert [r.levelno for r in caplog.records] == levels
    assert caplog.messages == [expected, expected]
    assert [over_cap_of(r) for r in caplog.records] == [(cap, "skipped")] * 2
    assert over_cap_of(logging.makeLogRecord({})) is None


def test_a_licence_file_over_its_cap_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The licence-detection cap, through the shared wording: a project
    read twice in one run (a lock-file re-read) warns once."""
    licence = tmp_path / "LICENSE"
    licence.write_bytes(b"x" * (LICENSE_FILE_MAX_BYTES + 1))
    with caplog.at_level(logging.WARNING):
        assert not read_license_members(tmp_path)
        assert not read_license_members(tmp_path)
    assert caplog.messages == [
        f"FILE={licence}: larger than the 262144-byte license-detection cap; skipped"
    ]


_DISPLAY = "cuts only what a message or an element name shows"
_SHOWN = "representation: the output text says what was left out"
_NOT_INPUT = "not a cap on input"
_HEURISTIC = "classification: a longer value is not that kind of value"

#: ``module:constant`` -> why it does not warn through warn_over_cap.
_ALLOWED = {
    "assemble/spdx3/_license_elements.py:_MAX_NAME_LENGTH": _DISPLAY,
    "assemble/spdx3/deps_pypi.py:_PYPI_LICENSE_FIELD_MAX_LEN": _HEURISTIC,
    "assemble/spdx3/deps_pypi.py:_PYPI_MAX_CONCURRENT_FETCHES": _NOT_INPUT,
    # scanner_wheel.py warns with the configured value's Cap.
    "core/_config_types.py:DEFAULT_MAX_MODEL_EXTRACT_BYTES": "a setting's default",
    "core/_models_wheel_build_kill.py:_GROUP_POLL_MAX_SECONDS": _NOT_INPUT,
    "core/_models_wheel_build_subprocess.py:_MESSAGE_MAX_CHARS": _DISPLAY,
    "core/_models_wheel_types.py:MAX_BUILD_TIMEOUT_SECONDS": "over it: ERROR",
    "core/_models_wheel_types.py:_ECHO_LIMIT": _DISPLAY,
    "core/_models_wheel_types.py:_MAX_SIGNIFICANT_DIGITS": "over it: ERROR",
    "core/ai_metadata.py:SOURCE_METADATA_MAX_DEPTH": _SHOWN,
    "core/canonical_json.py:MAX_SAFE_INTEGER": _NOT_INPUT,
    "core/scalar_text.py:MAX_INTEGER_DIGITS": _SHOWN,
    "core/wheel_dist_info.py:MAX_NAME_CHARS": _HEURISTIC,
    "extract/_file_headers.py:_HEADER_SCAN_MAX_BYTES": "headers lead a file",
    "extract/_file_headers.py:_HEADER_SCAN_MAX_LINES": "headers lead a file",
    "extract/_interrupt_hold.py:HOLD_LIMIT": _NOT_INPUT,
    "extract/_license.py:_MAX_LICENSE_ID_CHARS": _HEURISTIC,
    "extract/_license.py:_SCORE_CAP": _NOT_INPUT,
    "extract/_license_classify.py:_MAX_EXPRESSION_LENGTH": _HEURISTIC,
    "extract/ai_model/safetensors.py:SAFETENSORS_FORMAT_MAX_HEADER_BYTES": _HEURISTIC,
    "extract/remote/huggingface_field.py:_TOKENIZER_MAX_LEN_UNLIMITED": _NOT_INPUT,
}

_CAP_NAME = re.compile(r"^_?(?:[A-Z0-9]+_)*(?:MAX|CAP|LIMIT|BUDGET)(?:_[A-Z0-9]+)*$")
_SRC = Path(__file__).resolve().parents[1] / "src" / "pitloom"


def _caps(tree: ast.Module) -> list[str]:
    """The module constants of *tree* named as a cap, string ones (message
    templates) and ``Cap(...)`` ones (the cap, wrapped) left out."""
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        template = isinstance(value, ast.Constant) and isinstance(value.value, str)
        if not (template or _calls(value, {"Cap"})):
            names += [t.id for t in targets if isinstance(t, ast.Name)]
    return [name for name in names if _CAP_NAME.match(name)]


def _calls(node: ast.AST, names: set[str]) -> bool:
    """Whether *node* is a call of one of the plain *names*."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in names
    )


def _names(node: ast.AST) -> set[str]:
    """The names and attribute names in *node*."""
    return {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(node)
        if isinstance(n, (ast.Name, ast.Attribute))
    }


def _target(node: ast.AST) -> str | None:
    """The name, or attribute name, an assignment target binds."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def _assigned(node: ast.AST) -> tuple[list[str | None], ast.AST | None]:
    """What an assignment statement *node* binds, and its value."""
    if isinstance(node, ast.Assign):
        return [_target(t) for t in node.targets], node.value
    if isinstance(node, ast.AnnAssign):
        return [_target(node.target)], node.value
    return [], None


def _flow(trees: list[ast.Module]) -> tuple[set[str], set[str]]:
    """The carriers and holders of *trees*, to a fixed point. A carrier is
    a name or attribute in the arguments of ``warn_over_cap`` or of a
    holder, or one in a value assigned to a carrier; a holder, a class
    keeping a carrier attribute (``self.cap = cap``)."""
    carriers: set[str] = set()
    holders: set[str] = set()
    size = -1
    while size != len(carriers) + len(holders):
        size = len(carriers) + len(holders)
        for node in (n for tree in trees for n in ast.walk(tree)):
            targets, value = _assigned(node)
            if isinstance(node, ast.Call) and _calls(node, {"warn_over_cap", *holders}):
                for arg in [*node.args, *(k.value for k in node.keywords)]:
                    carriers |= _names(arg)
            elif value is not None and carriers.intersection(targets):
                carriers |= _names(value)
            elif isinstance(node, ast.ClassDef) and any(
                isinstance(t, ast.Attribute) and t.attr in carriers
                for n in ast.walk(node)
                for t in getattr(n, "targets", [])
            ):
                holders.add(node.name)
    return carriers, holders


def _warned(
    call: ast.Call,
    parents: dict[ast.AST, ast.AST],
    carriers: set[str],
    holders: set[str],
) -> bool:
    """Whether the ``Cap(...)`` *call* reaches ``warn_over_cap``: as an
    argument of it or of a holder, assigned to a carrier, or returned by a
    function that is one."""
    node: ast.AST = call
    while node in parents and not isinstance(node, ast.stmt):
        node = parents[node]
        if _calls(node, {"warn_over_cap", *holders}):
            return True
    if carriers.intersection(_assigned(node)[0]):
        return True
    if not isinstance(node, ast.Return):
        return False
    while not isinstance(node, ast.FunctionDef):
        node = parents[node]
    return node.name in carriers


def _routed(tree: ast.Module, carriers: set[str], holders: set[str]) -> set[str]:
    """The names in the limit of each ``Cap(...)`` of *tree*, imported from
    :mod:`pitloom.logging_config`, whose value reaches ``warn_over_cap``
    (:func:`_warned`), given the *carriers* and *holders* of every module
    (:func:`_flow`)."""
    if not any(
        isinstance(node, ast.ImportFrom)
        and node.module == "pitloom.logging_config"
        and any(alias.name == "Cap" for alias in node.names)
        for node in ast.walk(tree)
    ):
        return set()
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _calls(node, {"Cap"})
        and node.args
        and _warned(node, parents, carriers, holders)
        for name in _names(node.args[0])
    }


_IMPORT = "from pitloom.logging_config import Cap, over_cap_of, warn_over_cap\n"


@pytest.mark.parametrize(
    ("source", "routed"),
    [
        ("warn_over_cap(log, Cap(A, 'b', 'c'), w)", {"A"}),
        ("C = Cap(A, 'b', 'c')\ndef f():\n    warn_over_cap(log, C, w)", {"A"}),
        ("c = Cap(A, 'b', 'c') if x else Cap(B, 'b', 'c')\nwarn_over_cap(log, c, w)",
         {"A", "B"}),
        ("class O(Exception):\n    def __init__(self, cap):\n        self.cap = cap\n"
         "try:\n    raise O(Cap(A, 'b', 'c'))\nexcept O as o:\n"
         "    warn_over_cap(log, o.cap, w)", {"A"}),
        ("C = Cap(A * n, 'b', 'c')\nc = C if x else D\nwarn_over_cap(log, c, w)",
         {"A", "n"}),
        ("def f():\n    if x:\n        return Cap(A, 'b', 'c')\n"
         "warn_over_cap(log, f(), w)", {"A"}),
        ("self.c = Cap(A, 'b', 'c')\nwarn_over_cap(log, self.c, w)", {"A"}),
        ("C = Cap(A, 'b', 'c')\nwarn_over_cap(log, D, w)", set()),
        ("f(Cap(A, 'b', 'c'))\nwarn_over_cap(log, D, w)", set()),
        ("def f():\n    return Cap(A, 'b', 'c')\nwarn_over_cap(log, g(), w)", set()),
    ],
    ids=["argument", "named", "either", "held", "assigned-into", "returned",
         "attribute", "never-passed", "passed-elsewhere", "returned-elsewhere"],
)  # fmt: skip
def test_routed_needs_the_cap_passed_to_the_helper(
    source: str, routed: set[str]
) -> None:
    """The guard's own rows: a ``Cap`` counts only when its value reaches
    ``warn_over_cap``, not when one is merely built."""
    tree = ast.parse(_IMPORT + source)
    assert _routed(tree, *_flow([tree])) == routed
    bare = ast.parse(source)
    assert _routed(bare, *_flow([bare])) == set()  # not the shared Cap


def test_every_cap_warns_through_the_shared_helper() -> None:
    """Each cap constant is wrapped in a ``Cap`` whose value reaches
    :func:`~pitloom.logging_config.warn_over_cap`, in any module
    (:func:`_routed`), or is listed with a reason; no listed entry is
    stale. Static: it proves the call is written, not that it is reached
    (each cap's own tests drive the warning)."""
    modules = {
        path.relative_to(_SRC).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(_SRC.rglob("*.py"))
    }
    carriers, holders = _flow(list(modules.values()))
    unrouted: set[str] = set()
    routed: set[str] = set()
    for module, tree in modules.items():
        passed = _routed(tree, carriers, holders)
        for name in _caps(tree):
            (routed if name in passed else unrouted).add(f"{module}:{name}")
    assert len(routed) >= 20
    assert len(routed | unrouted) > 40  # the scan does find the caps
    assert sorted(unrouted - set(_ALLOWED)) == []  # route it, or list why not
    assert sorted(set(_ALLOWED) - unrouted) == []  # stale entries
