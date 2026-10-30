# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a template looks like (subject prefix, trailing period, "please"),
its placeholder-free form, and the emitter family a site belongs to.

See also: ``_scope.py`` (which sites count) and ``_walker_calls.py`` (which
stores these fields on each record).
"""

from __future__ import annotations

import ast
import re
from typing import Any

TAG_RE = re.compile(r"(?:^|\n)\s*(WARNING|ERROR|INFO|DEBUG):")
SUBJECT_RE = re.compile(
    r"^(?:%s|\{[^{}]*\})?"
    r"((?:[A-Z][A-Z0-9_]*=(?:%s|%\(\w+\)s|\{[^{}]*\}|[^\s:]*)\s?)+):"
)
LABEL_RE = re.compile(r"^([A-Za-z][\w ./-]{0,40}):(?:\s|$)")
#: A format placeholder: ``%s``, ``%(name)s``, ``%5.2f`` or ``{expr}``.
PH_RE = re.compile(r"%s|%\(\w+\)\w|%[-#0 +]*\d*(?:\.\d+)?[rsdifxXgG]|\{[^{}]*\}")

_PRINT_EMITTERS = (
    "print_stderr",
    "print_stdout",
    "print_file",
    "sys.stdout.write",
    "argparse.error",
    "sys.exit",
    "warnings.warn",
)
_HELPER_FAMILIES = {
    "print_error": "print_error / cli_error_handler",
    "cli_error_handler": "print_error / cli_error_handler",
    "print_kv": "KV (print_kv, log_kv, log_verbose)",
    "log_kv": "KV (print_kv, log_kv, log_verbose)",
    "log_verbose": "KV (print_kv, log_kv, log_verbose)",
    "kv_line": "KV (print_kv, log_kv, log_verbose)",
    "warn_over_cap": "over-cap",
    "warn_field_cap": "over-cap",
    "warn_archive_member_over_cap": "over-cap",
    "warn_once": "warn_once / log_once",
    "log_once": "warn_once / log_once",
}


def normalise(template: str | None) -> str | None:
    """*template* with every placeholder replaced by ``{}``."""
    if template is None:
        return None
    return PH_RE.sub("{}", template)


def emitter_family(emitter: str) -> str:
    """The emitter family of a site: ``raise``, ``logging.* (direct)``, a
    print or exit form, or ``helper call: <kind>``."""
    if emitter == "raise":
        return "raise"
    if emitter.startswith("logging."):
        return "logging.* (direct)"
    if emitter in _PRINT_EMITTERS:
        return emitter
    return "helper call: " + _HELPER_FAMILIES.get(emitter, "other named helper")


def count_args(call: ast.Call | None, tidx: int, tmpl: ast.expr | None) -> int:
    """How many values the template takes: extra positional arguments plus
    the f-string pieces."""
    if call is None:
        return 0
    count = max(0, len(call.args) - tidx - 1)
    if isinstance(tmpl, ast.JoinedStr):
        count += sum(isinstance(v, ast.FormattedValue) for v in tmpl.values)
    return count


def analyse(template: str | None) -> dict[str, Any]:
    """The shape of *template*: its KEY=VALUE or label prefix, whether it
    ends in a period or says "please", how the text after the prefix
    begins."""
    out: dict[str, Any] = {
        "subject_key": None,
        "has_subject_prefix": False,
        "prefix_label": None,
        "head": None,
        "has_semicolon": None,
        "prefix_tag_in_text": None,
        "multiline": None,
        "trailing_period": None,
        "has_please": None,
        "body_start": None,
        "body_start_char": None,
    }
    if template is None:
        return out
    body = template
    match = SUBJECT_RE.match(template)
    if match:
        out["subject_key"] = " ".join(re.findall(r"([A-Z][A-Z0-9_]*)=", match.group(1)))
        out["has_subject_prefix"] = True
        body = template[match.end() :].lstrip()
    else:
        label = LABEL_RE.match(template)
        if label:
            out["prefix_label"] = label.group(1)
            out["has_subject_prefix"] = True
            body = template[label.end() :].lstrip()
    out["head"] = template.split(":", 1)[0] if ":" in template else None
    out["has_semicolon"] = "; " in template
    tag = TAG_RE.search(template)
    out["prefix_tag_in_text"] = tag.group(1) if tag else None
    out["multiline"] = "\n" in template
    stripped = template.rstrip()
    out["trailing_period"] = stripped.endswith(".") and not stripped.endswith("..")
    out["has_please"] = bool(re.search(r"\bplease\b", template, re.I))
    if body.startswith(("%s", "{")) or re.match(r"%[-#0 +]*\d*[rsd]", body):
        out["body_start"] = "placeholder"
    elif body[:1].isalpha():
        out["body_start"] = "upper" if body[0].isupper() else "lower"
    elif body:
        out["body_start"] = "other"
    out["body_start_char"] = body[:1] or None
    return out
