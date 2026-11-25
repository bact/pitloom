# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which sites the ratchet counts: the lines a user can see on stderr as
``WARNING:``, ``INFO:`` or ``ERROR:``.

Out of scope are the sites that are not Pitloom's own message to a person:
``DEBUG`` lines, ``KEY=VALUE`` data on stdout, traceback lines, text that
passes another message through unchanged (a frame before a relayed record;
the catch-all handler's line, which says the caught exception's own text
and code; ``argparse``'s own text in an ``ArgumentParser.error`` override:
see ``_relay.py``, keyed on the code's shape, never on a variable's name),
the detail text of a reader's exception (it is the DETAIL of a line a
wrapper says; an ``OSError`` rebuilt from the OS's own errno and
description too, :func:`is_os_error_rebuilt`), internal invariants a caller never sees,
library-only errors raised to a Python caller, and a helper's call sites
whose text lives in the helper body (the body is counted once).

An internal invariant is marked by its class only: ``raise
InternalError(...)`` (:class:`pitloom.core.internal_error.InternalError`, a
``ValueError``), found by the class name or the name it is imported under
(:data:`INTERNAL_EXC`). No message text marks one: a text pattern would
hide a new raise that happens to share its words.

``reach`` is a static guess for ``raise`` sites (which of them reach the CLI
as an ``ERROR:`` line), by exception class and message text. A raise in a
model reader's package (:data:`READER_PACKAGE`, its dispatch module
:data:`READER_DISPATCH` aside) is detail by where it is: only the dispatch
calls a reader, and only the scanner calls the dispatch, so its text is the
detail of the scanner's line (``tests/test_message_ratchet.py`` holds both
facts).

See also: ``_coded.py`` (coded or not), ``_relay.py`` (the relays) and
``_baseline.py`` (the counts).
"""

from __future__ import annotations

import ast
import re
from typing import Any

#: The catalogue package: its sites are the mechanism, not messages.
MECHANISM = "src/pitloom/messages/"
#: Exception classes whose text is the DETAIL of a wrapper's line, or that a
#: wrapper turns into a coded line of its own (a carrier of a cap) or into
#: control flow (a signal). An ``argparse`` type or action error is the
#: detail of the parser's own line (``argument --x: <detail>``), which
#: ``_LoomParser.error`` codes. Keyed on the bare name, so a name here has
#: one class in ``src/``. A model reader's own exceptions are left out: a
#: raise in :data:`READER_PACKAGE` is detail by where it is. Each name and
#: raise site is proved by ``tests/messages/test_detail_classes*.py``.
DETAIL_EXC = frozenset(
    {
        "argparse.ArgumentError",
        "argparse.ArgumentTypeError",
        "ModelOverCap",
        "MarkerShapeError",
        "ParameterCountRejected",
        "HeaderBlockOverCap",
        "_OverCap",
        "InvalidRequirement",
        "InvalidMarker",
        "InvalidSpecifier",
        "ReadBudgetExceeded",
        "_Unlistable",
        "_DuplicateKeyError",
        "LockFileRefusedError",
        "on_duplicate",
        "NotAModel",
        "MemberReadError",
        "FragmentReadError",
        "_MarkersTypeError",
        "_NonJsonConstant",
        "_NotComparableJson",
    }
)
#: Exception classes that are programming errors or process control.
INTERNAL_EXC = frozenset(
    {
        "AttributeError",
        "InternalError",
        "LockNotReleased",
        "SystemExit",
        "TerminationSignal",
    }
)
#: Helpers whose error is raised to a Python caller of the library: the
#: loom SDK called outside a ``loom.run()``.
LIBRARY_EXC = frozenset({"_no_active_run"})
#: Raises, by file, function, exception class and template, that only a
#: library caller's wrong argument reaches: a value of the wrong Python type
#: (a ``TypeError``), or a call that leaves out what the object lacks
#: (``IdRegistry.save()`` with no path, ``register()`` with an empty type
#: name). No command, hook, Action or file reaches them (the CLI passes only
#: its own types and a registry with a path). Named one raise at a time, not
#: one function: another raise in the same function (``--build-timeout 0``'s
#: ``_out_of_range``, a registry file past ``MAX_ID_NUMBER``), a new one, or
#: a listed one whose text changes stays counted.
LIBRARY_SITES = frozenset(
    {
        (
            "src/pitloom/_loom_dataset_meta.py",
            "_declared_licence",
            "TypeError",
            "loom SDK: declared_license must be a str, not %s",
        ),
        (
            "src/pitloom/core/_models_wheel_types.py",
            "validate_build_timeout",
            "TypeError",
            "build timeout must be an int number of seconds, "
            "got {type(value).__name__}",
        ),
        (
            "src/pitloom/core/build_options.py",
            "BuildOptions.__post_init__",
            "TypeError",
            "build option {name} must be bool, got {type(value).__name__}",
        ),
        (
            "src/pitloom/core/scalar_text.py",
            "scalar_text",
            "TypeError",
            "not a scalar: {type(value).__name__}",
        ),
        (
            "src/pitloom/id_registry/_registry.py",
            "_require_bool",
            "TypeError",
            "refuse_credentials must be a bool, not "
            "{type(refuse_credentials).__name__}",
        ),
        (
            "src/pitloom/id_registry/_registry.py",
            "IdRegistry.load",
            "TypeError",
            "ID registry file path must be a str or os.PathLike, not "
            "{type(path).__name__}",
        ),
        (
            "src/pitloom/id_registry/_registry.py",
            "IdRegistry._mint_id",
            "ValueError",
            "ID registry: no id prefix for an empty type name",
        ),
        (
            "src/pitloom/id_registry/_registry.py",
            "IdRegistry.save",
            "ValueError",
            "No path given and registry has no default path",
        ),
        (
            "src/pitloom/id_registry/_types.py",
            "_require_names",
            "TypeError",
            "names must be a sequence of names, not one str",
        ),
    }
)


def library_site_key(rec: dict[str, Any]) -> tuple[str, str, str, str]:
    """The :data:`LIBRARY_SITES` key of the raise *rec*: its file,
    function, exception class and template (``""`` for an absent one)."""
    return (
        rec["file"],
        rec.get("function") or "",
        rec.get("exc_class") or "",
        rec.get("template") or "",
    )


#: A template that is only another message passed through: left out only at
#: a site that forwards that message's code (``forwards_code``: the record's
#: or the exception's own, read at run time), so its line carries the code
#: of the text it says. A bare ``%s`` that forwards none is counted.
PASSTHROUGH_PAT = re.compile(r"^%s$")
#: Emitters of ``KEY=VALUE`` data, not of messages.
DATA_EMITTERS = frozenset(
    {"print_kv", "print_stdout", "sys.stdout.write", "log_verbose", "log_kv"}
)
_ERROR_EMITTERS = frozenset(
    {"print_error", "cli_error_handler", "argparse.error", "logging.error"}
)
_VISIBLE = frozenset(
    {
        "WARNING",
        "INFO",
        "ERROR",
        "CRITICAL",
        "ERROR(raise)",
        "ERROR(usage)",
        "WARNING|INFO",
        "UNTAGGED",
    }
)


#: The model readers' package: what a raise there says is the detail of the
#: scanner's line.
READER_PACKAGE = "src/pitloom/extract/ai_model/"
#: The dispatch to the readers, whose refusals a single-file surface prints.
READER_DISPATCH = "src/pitloom/extract/ai_model/reader.py"


#: The ``OSError`` family: a raise of one whose first argument is an errno
#: and whose second is the OS's own description is the OS's error.
OS_ERRORS = frozenset(
    {
        "BlockingIOError",
        "ChildProcessError",
        "ConnectionError",
        "EnvironmentError",
        "FileExistsError",
        "FileNotFoundError",
        "IOError",
        "InterruptedError",
        "IsADirectoryError",
        "NotADirectoryError",
        "OSError",
        "PermissionError",
        "ProcessLookupError",
        "TimeoutError",
    }
)


def _expr(text: str) -> ast.expr | None:
    """*text*, an argument as the walker unparsed it (cut to 80
    characters), as an expression; ``None`` when it does not parse."""
    try:
        return ast.parse(text, mode="eval").body
    except SyntaxError:
        return None


def _is_attribute_of_name(node: ast.expr | None, attr: str) -> bool:
    """*node* is ``<name>.<attr>``: ``exc.errno``, ``errno.EACCES``."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
    )


def _is_errno(node: ast.expr | None) -> bool:
    """An errno: ``errno.E<NAME>`` or another error's ``<name>.errno``."""
    if _is_attribute_of_name(node, "errno"):
        return True
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "errno"
        and re.fullmatch(r"E[A-Z0-9]+", node.attr) is not None
    )


def _is_call_of(node: ast.expr | None, module: str, name: str) -> bool:
    """*node* is ``<module>.<name>(<one argument>)``, no keyword."""
    return (
        isinstance(node, ast.Call)
        and _is_attribute_of_name(node.func, name)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == module
        and len(node.args) == 1
        and not node.keywords
    )


def _is_strerror(node: ast.expr | None) -> bool:
    """The OS's own description: exactly ``os.strerror(...)`` or another
    error's ``<name>.strerror``, nothing of Pitloom's added."""
    return _is_call_of(node, "os", "strerror") or _is_attribute_of_name(
        node, "strerror"
    )


def _is_bare_path(node: ast.expr | None) -> bool:
    """A path as given: a bare name or ``str(<name>)``."""
    if isinstance(node, ast.Name):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and not node.keywords
    )


def is_os_error_rebuilt(rec: dict[str, Any]) -> bool:
    """Whether *rec* raises an ``OSError`` built from the OS's own words
    (rule R-a): ``PermissionError(errno.EACCES, os.strerror(errno.EACCES),
    path)``, ``PermissionError(exc.errno, exc.strerror, str(path))``. Its
    text is the OS's, the detail of the caller's wrapping line
    (``file-unwritable``). An ``OSError`` given a text of Pitloom's in the
    description or the path (``os.strerror(...) + name``, ``f"{path}!"``),
    or more arguments, stays counted."""
    exc = (rec.get("exc_class") or "").rpartition(".")[2]
    args = rec.get("arg_exprs") or []
    return (
        rec["emitter"] == "raise"
        and exc in OS_ERRORS
        and _is_errno(_expr(rec.get("dynamic_expr") or ""))
        and 1 <= len(args) <= 2
        and _is_strerror(_expr(args[0]))
        and all(_is_bare_path(_expr(arg)) for arg in args[1:])
    )


def _raise_reach(rec: dict[str, Any]) -> str:
    exc = rec.get("exc_class") or ""
    if (
        exc in DETAIL_EXC
        or is_os_error_rebuilt(rec)
        or (rec["file"].startswith(READER_PACKAGE) and rec["file"] != READER_DISPATCH)
    ):
        return "detail"
    names = {exc.rpartition(".")[2], rec.get("exc_origin") or ""}
    if names & INTERNAL_EXC:
        return "internal"
    if exc in LIBRARY_EXC or library_site_key(rec) in LIBRARY_SITES:
        return "library"
    return "ERROR(usage)" if exc.startswith("argparse") else "ERROR(raise)"


def reach(rec: dict[str, Any]) -> str:
    """Where the site's text reaches: ``DEBUG``, ``STDOUT``, ``detail``,
    ``internal``, ``library``, ``ERROR(raise)``, ``ERROR(usage)``, ``ERROR``,
    ``WARNING|INFO`` (level chosen at run time), ``UNTAGGED``, or the
    site's own level."""
    emitter = rec["emitter"]
    if rec["level"] == "DEBUG":
        return "DEBUG"
    if rec["level"] == "STDOUT" or emitter in DATA_EMITTERS:
        return "STDOUT"
    if emitter == "raise":
        return _raise_reach(rec)
    if emitter in _ERROR_EMITTERS:
        return "ERROR"
    renamed = {"DYNAMIC": "WARNING|INFO", "STDERR_UNTAGGED": "UNTAGGED"}
    return renamed.get(str(rec["level"]), str(rec["level"]))


#: The catalogue's helper that says a summary (an ``INFO:`` line of no
#: condition), and the module that defines it.
SUMMARY_HELPER = "say_summary"
SUMMARY_MODULE = f"{MECHANISM}_summary.py:"


def is_summary(rec: dict[str, Any]) -> bool:
    """Whether *rec* says a summary: a call of the catalogue's own
    :data:`SUMMARY_HELPER`, known by the definition it reaches, never by
    the call's name or text alone (a module's own ``say_summary`` says
    anything)."""
    return (
        rec["site_kind"] == "helper_call"
        and rec.get("helper") == SUMMARY_HELPER
        and rec.get("helper_def", "").startswith(SUMMARY_MODULE)
    )


def is_passthrough(rec: dict[str, Any]) -> bool:
    """Whether *rec* only says another message again with its code: a
    :data:`PASSTHROUGH_PAT` template at a site that forwards a code."""
    template = rec["template"]
    return (
        bool(rec.get("forwards_code"))
        and template is not None
        and bool(PASSTHROUGH_PAT.match(template))
    )


def _excluded(rec: dict[str, Any]) -> bool:
    """Whether *rec* is left out whatever it reaches."""
    # A helper's call whose text is in the helper body is counted there; but
    # the body of a catalogue helper (``emit``) is the mechanism, so its
    # callers count.
    in_helper_body = (
        rec["site_kind"] == "helper_call"
        and rec.get("tmpl_source") == "helper"
        and not rec.get("helper_def", "").startswith(MECHANISM)
    )
    return any(
        (
            # the logging plumbing and the KEY=VALUE writer
            rec["file"].endswith(("logging_config.py", "cli/kv_output.py")),
            rec["file"].startswith(MECHANISM),  # the coding mechanism itself
            is_summary(rec),  # kind summary: no condition, so no code (R1)
            in_helper_body,
            is_passthrough(rec),  # a forwarded message said again
            bool(rec.get("relays")),  # another's text said again (_relay.py)
        )
    )


def in_scope(rec: dict[str, Any]) -> bool:
    """Whether the ratchet counts *rec*."""
    return not _excluded(rec) and reach(rec) in _VISIBLE
