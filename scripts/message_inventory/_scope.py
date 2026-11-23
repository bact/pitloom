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

An internal invariant is marked by its class: ``raise InternalError(...)``
(:class:`pitloom.core.internal_error.InternalError`, a ``ValueError``), found
by the class name or the name it is imported under. :data:`INTERNAL_PAT`
is the older list of such texts; a raise moves from it to the class, never
back.

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
#: Exception classes whose text is the DETAIL of a wrapper's line. An
#: ``argparse`` type or action error is the detail of the parser's own line
#: (``argument --x: <detail>``), which ``_LoomParser.error`` codes.
DETAIL_EXC = frozenset(
    {
        "ArgumentError",
        "ArgumentTypeError",
        "argparse.ArgumentError",
        "argparse.ArgumentTypeError",
        "Malformed",
        "UnsupportedVersion",
        "LimitExceeded",
        "ModelOverCap",
        "ModelLimitExceeded",
        "ConfigShapeError",
        "MarkerShapeError",
        "_UnsupportedAttribute",
        "ParameterCountRejected",
        "HeaderBlockOverCap",
        "_OverCap",
        "_over_cap",
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
#: Message texts of invariants a user never meets.
INTERNAL_PAT = re.compile(
    r"already entered|outlived its with-block|outside its with-block|"
    r"re-entrantly|CREATOR_TYPES keys|merkle_root\(\)|Limits\.\{name\}|"
    r"does not accept .*INERT|not a scalar|names must be a sequence|"
    r"RegistryEntry\.sha256|file path must be a str|refuse_credentials must "
    r"be a bool|no ID registry loaded in "
    r"this session|No path given and registry|capture state lock|has no spdxId "
    r"assigned|Duplicate spdxId|Dependency\.base_pep_508_name|type parameters|"
    r"EmbedFileCache: every call|build option \{name\} must be bool|"
    r"build timeout must be an int|max_bytes must be a positive|"
    r"Failed to build relationship|^received \{|no id prefix for an empty|"
    r"GGUF array field without|duplicate key$|"
    r"^not JSON: |is not a JSON value|"
    r"content_type_method must be one of"
)
#: Message texts of errors raised to a Python caller of the library.
LIBRARY_PAT = re.compile(
    r"No active loom\.run|No model set|^loom: |generate_project_sbom\(\)|"
    r"local enrichment does not apply|caller (info|script path)"
)
#: A template that is only another message passed through.
PASSTHROUGH_PAT = re.compile(
    r"^(%s|"
    r"ERROR: \{escape_controls|%s; skipped|%s%s)?$"
)
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
    text = rec["template"] or ""
    if (
        exc in DETAIL_EXC
        or is_os_error_rebuilt(rec)
        or (rec["file"].startswith(READER_PACKAGE) and rec["file"] != READER_DISPATCH)
    ):
        return "detail"
    names = {exc.rpartition(".")[2], rec.get("exc_origin") or ""}
    if INTERNAL_PAT.search(text) or names & INTERNAL_EXC:
        return "internal"
    if LIBRARY_PAT.search(text) or exc == "_no_active_run":
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
    template = rec["template"]
    return any(
        (
            # the logging plumbing and the KEY=VALUE writer
            rec["file"].endswith(("logging_config.py", "cli/kv_output.py")),
            rec["file"].startswith(MECHANISM),  # the coding mechanism itself
            is_summary(rec),  # kind summary: no condition, so no code (R1)
            in_helper_body,
            template is not None and bool(PASSTHROUGH_PAT.match(template)),
            bool(rec.get("relays")),  # another's text said again (_relay.py)
        )
    )


def in_scope(rec: dict[str, Any]) -> bool:
    """Whether the ratchet counts *rec*."""
    return not _excluded(rec) and reach(rec) in _VISIBLE
