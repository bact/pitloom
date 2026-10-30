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
source for calls of `log.<level>(...)`, `print(..., file=sys.stderr)`, `raise`
statements and `*_message` builders whose arguments (or f-string parts) name a
path-like variable bare.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from pitloom.core.quote_source import quote_source
from pitloom.extract.ai_model.reader import read_ai_model

_SRC = Path(__file__).parent.parent / "src" / "pitloom"

#: Variables and attributes that hold a user-given path or file name.
_PATHY = re.compile(
    r"(^|_)(path|paths|dir|directory|filename|root|folder|member)$"
    r"|^(archive|archive_name|wheel_name|sdist_name|marker_name|candidate_name"
    r"|lock_file|location|orig_filename|p|pattern|wheel_obj|sboms_prefix)$"
)
_PART_ATTRIBUTES = frozenset({"name", "parent", "stem", "suffix"})
_SAFE_CALLS = frozenset(
    {
        "quote_source",
        "loggable",
        "one_line",
        "type",
        "excerpt",
    }
)
_LEVELS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})
_LOGGERS = frozenset({"log", "logger", "logging", "_log", "_logger"})
#: Calls that log through a helper: the message is the first argument.
_LOG_HELPERS = frozenset({"warn_once", "print_error", "report_error_line"})

#: Calls that take a path and quote it inside, or only count paths. The
#: catalogue's CodedValueError and CodedImportError write each value through
#: its field (a ``path`` in quotes, a ``file`` through loggable);
#: ``refusal_error`` says the refusal through CodedValueError, else quoted.
_QUOTING_CALLS = frozenset(
    {
        "CodedImportError",
        "CodedValueError",
        "_interpolation_error",
        "_missing_fragment_message",
        "_fragment_read_failure_message",
        "_same_document_message",
        "failed_to_save_message",
        "refusal_error",
        "name_key_reason",
        "detail",
        "detect_ai_model_format_from_name",
        "_once_key",
        "len",
    }
)

#: (file relative to src/pitloom, variable) pairs that are not paths here.
_NOT_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        # A TOML key path and a de-duplication key, not file names.
        ("core/_config_keys.py", "path"),
        ("extract/_license_detect.py", "path"),
        ("extract/project/_pyproject_fields.py", "project_dir"),
        # A TOML table path and a regex, shown with repr().
        ("core/_config_read.py", "table_path"),
        ("core/model_extract_limit.py", "table_path"),
        ("core/_config_parse_scan.py", "pattern"),
        # A URL shown with repr().
        ("_loom_dataset_meta.py", "location"),
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


#: Calls that quote their leading path arguments (how many) and show the rest as given.
_QUOTING_FIRST = {"registry_file_error": 1, "refusal": 2, "unreadable_member_error": 2}
#: Constructors whose filename argument ``OSError`` shows with ``repr()``.
_OS_ERRORS = frozenset({"PermissionError", "FileNotFoundError", "OSError"})


def _arguments(call: ast.Call) -> list[ast.expr]:
    found: list[ast.expr] = []
    for argument in [*call.args, *(k.value for k in call.keywords)]:
        if isinstance(argument, ast.Starred):
            argument = argument.value
        if isinstance(argument, ast.JoinedStr):
            found += [
                v.value for v in argument.values if isinstance(v, ast.FormattedValue)
            ]
        else:
            found.append(argument)
    return found


def _called_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def _bare(node: ast.AST) -> list[ast.expr]:
    """The path-like parts of *node* shown as they are: not inside a call that
    quotes, not the test of a conditional expression."""
    if isinstance(node, ast.Call) and _called_name(node) in (
        _SAFE_CALLS | _QUOTING_CALLS
    ):
        return []
    if isinstance(node, ast.IfExp):
        return _bare(node.body) + _bare(node.orelse)
    if isinstance(node, ast.expr) and _is_pathy(node):
        return [node]
    if isinstance(node, ast.JoinedStr):
        return [
            bare
            for value in node.values
            if isinstance(value, ast.FormattedValue)
            for bare in _bare(value.value)
        ]
    return [bare for child in ast.iter_child_nodes(node) for bare in _bare(child)]


def _raise_messages(exc: ast.Call) -> list[ast.expr]:
    """The parts of ``raise <exc>`` that carry text: not what a quoting helper
    quotes itself, nor the filename argument ``OSError`` shows."""
    name = _called_name(exc)
    if name in _QUOTING_CALLS:
        return []
    messages = _arguments(exc)
    if name in _OS_ERRORS and len(exc.args) == 3:
        return messages[:2]
    return messages[_QUOTING_FIRST.get(name, 0) :]


def _offenders(relative: str, tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        messages: list[ast.expr] = []
        if isinstance(node, ast.Call) and _is_message_call(node):
            messages = _arguments(node)
        elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            # The text of an exception reaches stderr, a log line or a
            # notification somewhere else: it names a path as the log does.
            messages = _raise_messages(node.exc)
        elif isinstance(node, ast.FunctionDef) and node.name.endswith("_message"):
            # A builder returns the text another module logs or raises.
            messages = [
                n.value
                for n in ast.walk(node)
                if isinstance(n, ast.Return) and n.value is not None
            ]
        for message in messages:
            for bare in _bare(message):
                shown = ast.unparse(bare)
                if (relative, shown) not in _NOT_PATHS:
                    found.append(f"{relative}:{bare.lineno}: {shown}")
    return found


def _bare_paths() -> list[str]:
    offenders = []
    for path in sorted(_SRC.rglob("*.py")):
        relative = path.relative_to(_SRC).as_posix()
        offenders += _offenders(relative, ast.parse(path.read_text(encoding="utf-8")))
    return offenders


def test_no_message_names_a_path_bare() -> None:
    offenders = _bare_paths()
    assert not offenders, "wrap in quote_source()/loggable():\n" + "\n".join(offenders)


def test_the_guard_sees_a_bare_path() -> None:
    """The scan is not vacuous: it flags a bare path wherever it hides and not a
    quoted one."""
    source = (
        "log.warning('x %s', project_dir)\n"
        "log.warning('x %s', quote_source(project_dir))\n"
        "print(f'ERROR: {sbom_path}', file=sys.stderr)\n"
        "print(f'ERROR: {loggable(str(sbom_path))}', file=sys.stderr)\n"
        "print_error(f'bad {str(sbom_path)}')\n"
        "print_error('in ' + wheel_path.name)\n"
        "print_error(f'in {wheel_path.name} ' + ('x' if sbom_filename else ''))\n"
        "log.warning(*args, wheel_path)\n"
        "raise ValueError(f'x {path}')\n"
        "raise ValueError(f'x {quote_source(path)}')\n"
        "raise registry_file_error(path, f'x {root}')\n"
        "raise registry_file_error(path, f'x {quote_source(root)}')\n"
        "raise PermissionError(1, 'x', str(path))\n"
        "raise PermissionError(1, f'x {path}', str(path))\n"
        "raise RemoteError(code='c', message=f'x {path}')\n"
        "raise refusal(a, e, f'x {root}')\n"
        "raise refusal(a, e, f'x {quote_source(root)}')\n"
        "def failed_message(path):\n"
        "    return f'failed {path}'\n"
        "def other(path):\n"
        "    return f'failed {path}'\n"
    )
    found = {line.split(":")[1] for line in _offenders("x.py", ast.parse(source))}
    assert found == {"1", "3", "5", "6", "7", "8", "9", "11", "14", "15", "16", "19"}


@pytest.mark.parametrize("name", ["a\nERROR: forged", "it's", "a\\b"])
def test_a_raised_path_is_quoted(tmp_path: Path, name: str) -> None:
    """A path in an exception message is escaped and delimited."""
    missing = tmp_path / name
    with pytest.raises(FileNotFoundError) as info:
        read_ai_model(missing)
    message = str(info.value)
    assert "\n" not in message
    assert quote_source(missing) in message
