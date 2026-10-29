# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which sites the ratchet counts: the lines a user can see on stderr as
``WARNING:``, ``INFO:`` or ``ERROR:``.

Out of scope are the sites that are not Pitloom's own message to a person:
``DEBUG`` lines, ``KEY=VALUE`` data on stdout, traceback lines, text that
passes another message through unchanged (``str(exc)``), the detail text of
a reader's exception (it is the DETAIL of a line a wrapper says), internal
invariants a caller never sees, library-only errors raised to a Python
caller, and a helper's call sites whose text lives in the helper body (the
body is counted once).

``reach`` is a static guess for ``raise`` sites (which of them reach the CLI
as an ``ERROR:`` line), by exception class and message text.

See also: ``_coded.py`` (coded or not) and ``_baseline.py`` (the counts).
"""

from __future__ import annotations

import re
from typing import Any

#: The catalogue package: its sites are the mechanism, not messages.
MECHANISM = "src/pitloom/messages/"
#: Exception classes whose text is the DETAIL of a wrapper's line.
DETAIL_EXC = frozenset(
    {
        "Malformed",
        "UnsupportedVersion",
        "LimitExceeded",
        "ModelOverCap",
        "ModelLimitExceeded",
        "_ConfigShapeError",
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
        "_shape_error",
    }
)
#: Exception classes that are programming errors or process control.
INTERNAL_EXC = frozenset(
    {"AttributeError", "SystemExit", "TerminationSignal", "LockNotReleased"}
)
#: Message texts of invariants a user never meets.
INTERNAL_PAT = re.compile(
    r"already entered|outlived its with-block|outside its with-block|"
    r"re-entrantly|CREATOR_TYPES keys|merkle_root\(\)|Limits\.\{name\}|"
    r"does not accept .*INERT|not a scalar|names must be a sequence|"
    r"RegistryEntry\.sha256|file path must be a str|no ID registry loaded in "
    r"this session|No path given and registry|capture state lock|has no spdxId "
    r"assigned|Duplicate spdxId|Dependency\.base_pep_508_name|type parameters|"
    r"EmbedFileCache: every call|build option \{name\} must be bool|"
    r"build timeout must be an int|max_bytes must be a positive|"
    r"Failed to build relationship|^received \{|no id prefix for an empty|"
    r"GGUF array field without|Unknown provenance schema|duplicate key$|"
    r"^not JSON: |is not a JSON value|^\{name\} must be a table|"
    r"content_type_method must be one of|Invalid creator type person"
)
#: Message texts of errors raised to a Python caller of the library.
LIBRARY_PAT = re.compile(
    r"No active loom\.run|No model set|^loom: |generate_project_sbom\(\)|"
    r"local enrichment does not apply|caller (info|script path)|"
    r"Invalid creator type|Creator name must|Tool name must"
)
#: A template that is only another message passed through.
PASSTHROUGH_PAT = re.compile(
    r"^(%s|\{error_msg\}: \{e\}|\{self\.prog\}: \{message\}|"
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


def _raise_reach(rec: dict[str, Any]) -> str:
    exc = rec.get("exc_class") or ""
    text = rec["template"] or ""
    if exc in DETAIL_EXC:
        return "detail"
    if INTERNAL_PAT.search(text) or exc in INTERNAL_EXC:
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


def in_scope(rec: dict[str, Any]) -> bool:
    """Whether the ratchet counts *rec*."""
    if rec["file"].endswith(("logging_config.py", "cli/kv_output.py")):
        return False  # the logging plumbing and the KEY=VALUE writer
    if rec["file"].startswith(MECHANISM):
        return False  # the coding mechanism itself
    if rec["site_kind"] == "helper_call" and rec.get("tmpl_source") == "helper":
        # Its text is in the helper body, counted there; but the body of a
        # catalogue helper (``emit``) is the mechanism, so its callers count.
        if not rec.get("helper_def", "").startswith(MECHANISM):
            return False
    if rec["template"] is not None and PASSTHROUGH_PAT.match(rec["template"]):
        return False
    return reach(rec) in _VISIBLE
