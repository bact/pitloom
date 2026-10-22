# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: a path or file name in a log record or a stderr line goes
through `quote_source` (a path), `loggable` or `one_line` (other untrusted
text), as CLAUDE.md's "CLI output" section says, so Windows backslashes are not
doubled and a newline cannot start another line.

The formatter of `configure_logging` escapes control characters whatever a call
site did, so this guards the display, not the line structure. It reads the
source for calls of `log.<level>(...)` and `print(..., file=sys.stderr)`
whose arguments (or f-string parts) name a path-like variable bare.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src" / "pitloom"

#: Variables and attributes that hold a user-given path or file name.
_PATHY = re.compile(
    r"(^|_)(path|paths|dir|directory|filename|root|folder|member)$"
    r"|^(archive|archive_name|wheel_name|sdist_name|marker_name|candidate_name"
    r"|lock_file|location|orig_filename|p|pattern)$"
)
_PART_ATTRIBUTES = frozenset({"name", "parent", "stem", "suffix"})
_SAFE_CALLS = frozenset(
    {
        "quote_source",
        "loggable",
        "one_line",
        "escape_controls",
        "ascii",
        "excerpt",
        "hide_temp_dir",
        "sanitize_url_credentials",
    }
)
_LEVELS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})
_LOGGERS = frozenset({"log", "logger", "logging", "_log", "_logger"})
#: Calls that log through a helper: the message is the first argument.
_LOG_HELPERS = frozenset({"warn_once"})

#: (file relative to src/pitloom, variable) pairs that are not paths here.
_NOT_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        # A TOML key path and a de-duplication key, not file names.
        ("core/_config_keys.py", "path"),
        ("extract/_license_detect.py", "path"),
    }
)


def _is_pathy(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return _PATHY.search(node.id) is not None
    if isinstance(node, ast.Attribute):
        # ``wheel_path.name``/``.parent``/``.stem`` are as user-given as the path.
        if node.attr in _PART_ATTRIBUTES and _is_pathy(node.value):
            return True
        return _PATHY.search(node.attr) is not None
    return False


def _is_message_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _LEVELS:
        owner = func.value
        owner_name = (
            owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
        )
        return owner_name in _LOGGERS
    if isinstance(func, ast.Name) and func.id in _LOG_HELPERS:
        return True
    return (
        isinstance(func, ast.Name)
        and func.id == "print"
        and any(keyword.arg == "file" for keyword in node.keywords)
    )


def _arguments(call: ast.Call) -> list[ast.expr]:
    found: list[ast.expr] = []
    for argument in call.args:
        if isinstance(argument, ast.JoinedStr):
            found += [
                v.value for v in argument.values if isinstance(v, ast.FormattedValue)
            ]
        else:
            found.append(argument)
    return found


def _bare_paths() -> list[str]:
    offenders = []
    for path in sorted(_SRC.rglob("*.py")):
        relative = path.relative_to(_SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_message_call(node):
                for argument in _arguments(node):
                    shown = ast.unparse(argument)
                    if _is_pathy(argument) and (relative, shown) not in _NOT_PATHS:
                        offenders.append(f"{relative}:{node.lineno}: {shown}")
    return offenders


def test_no_message_names_a_path_bare() -> None:
    offenders = _bare_paths()
    assert not offenders, "wrap in quote_source()/loggable():\n" + "\n".join(offenders)


def test_the_guard_sees_a_bare_path(tmp_path: Path) -> None:
    """The scan is not vacuous: it flags a bare path and not a quoted one."""
    source = (
        "log.warning('x %s', project_dir)\n"
        "log.warning('x %s', quote_source(project_dir))\n"
        "print(f'ERROR: {sbom_path}', file=sys.stderr)\n"
        "print(f'ERROR: {loggable(str(sbom_path))}', file=sys.stderr)\n"
    )
    calls = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)]
    flagged = [
        c.lineno
        for c in calls
        if _is_message_call(c) and any(_is_pathy(a) for a in _arguments(c))
    ]
    assert flagged == [1, 3]
