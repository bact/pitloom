# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``fragment`` subcommand group: ``validate`` and ``list``."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pitloom.assemble import project_document_id
from pitloom.assemble.spdx3._fragments_read import (
    parse_fragment,
    read_fragment_bytes,
)
from pitloom.assemble.spdx3.fragments import _find_fragment_document_id
from pitloom.cli.commands.utils import (
    _import_spdx3_validate,
    _validate_spdx3_documents,
    cli_error_handler,
    input_file_or_say,
)
from pitloom.cli.kv_output import print_kv
from pitloom.core.config import FragmentConfig, read_pitloom_config
from pitloom.core.given_path import TypedPath
from pitloom.core.internal_error import InternalError
from pitloom.core.path_probe import is_missing_errno
from pitloom.messages import emit, say_summary
from pitloom.messages.fragments import (
    FRAGMENT_DIGEST_INVALID,
    FRAGMENT_LIST_NONE,
    FRAGMENT_VALIDATE_VALID,
    FragmentReadError,
    warn_fragment_unread,
    warn_same_document,
)
from pitloom.messages.metadata import relay_coded_warning
from pitloom.messages.targets import (
    is_input_dir,
    say_input_not_found,
    warn_fragment_not_found,
)

log = logging.getLogger(__name__)


@cli_error_handler
def _run_fragment_validate(args: argparse.Namespace) -> int:
    """Run `loom fragment validate`."""
    # Both checks run and report independently -- a user missing the
    # optional dependency AND passing a bad path should see both ERROR:
    # lines in one run, not just the first one, for one round trip.
    dependency_ok = _import_spdx3_validate() is not None

    paths: list[Path] = args.paths
    files_ok = True
    for p in paths:
        # Every path is reported, an unreadable one included.
        files_ok = input_file_or_say(p, "SBOM file") and files_ok

    if not dependency_ok or not files_ok:
        return 1

    exit_code = _validate_spdx3_documents(
        [str(p) for p in paths], check_merged=not args.no_merge
    )
    if exit_code == 0:
        for p in paths:
            print_kv(FILE=p, STATUS="valid")
        say_summary(log, FRAGMENT_VALIDATE_VALID, number=len(paths))
    return exit_code


def _graph_length(raw: bytes) -> int | None:
    """The length of the ``@graph`` array of the JSON *raw*, or ``None``
    when it is not an object with one (or not JSON): a fragment the SPDX 3
    reader refused still has its element count listed."""
    try:
        data = json.loads(raw)
    except Exception:  # pylint: disable=broad-exception-caught
        # The reader already said why this fragment failed.
        return None
    graph = data.get("@graph", []) if isinstance(data, dict) else None
    return len(graph) if isinstance(graph, list) else None


def _fragment_read_status(
    fragment_path: Path, shown: str, *, required: bool
) -> tuple[bytes | None, bool, int | None, str | None]:
    """Read *fragment_path* (named *shown*, as configured) once with the
    reader the merge uses
    (:func:`~pitloom.assemble.spdx3._fragments_read.parse_fragment`), for
    the element count, the SPDX 3 validity check and the SHA-256 check in
    :func:`_fragment_sha256_status`. Returns
    ``(raw_bytes, read_ok, element_count, document_id)``:

    - ``raw_bytes`` is the file's contents, or ``None`` only if the file
      itself couldn't be read (not on a JSON-parse failure) -- so a
      fragment with broken JSON can still have its hash verified by
      :func:`_fragment_sha256_status`.
    - ``read_ok`` is False on a read failure, or when the bytes are not an
      SPDX 3 JSON-LD document the merge reads -- exactly the conditions
      that make ``merge_fragments()`` treat a ``required=True`` fragment as
      unmet (a number no RFC 8785 spelling holds, for one, fails here as it
      does there), so callers key exit-code decisions on this, not on
      ``element_count``.
    - ``element_count`` is the fragment's ``@graph`` length, or ``None``
      if the parsed JSON isn't an object (not itself a read failure).
    - ``document_id`` is the fragment's own ``SpdxDocument`` id, or
      ``None`` without one or when ``read_ok`` is False.

    Logs one WARNING (``fragment-unreadable`` or ``fragment-invalid``, the
    merge's own line) on any failure.
    """
    try:
        raw = read_fragment_bytes(fragment_path)
    except FragmentReadError as exc:
        warn_fragment_unread(log, shown, exc, required=required)
        return None, False, None, None
    try:
        parsed = parse_fragment(raw, file=shown)
    except FragmentReadError as exc:
        warn_fragment_unread(log, shown, exc, required=required)
        return raw, False, _graph_length(raw), None
    graph = parsed.data.get("@graph", []) if isinstance(parsed.data, dict) else None
    elements = len(graph) if isinstance(graph, list) else None
    return raw, True, elements, _find_fragment_document_id(parsed.objects)


def _fragment_sha256_status(
    raw: bytes | None, expected_sha256: str | None, shown: str
) -> str:
    """Three-state SHA-256 display: ``-`` (not configured), ``unknown``
    (configured but the file couldn't be read), or ``match``/``mismatch``.
    Logs a WARNING on mismatch (*shown*: the fragment as configured). *raw*
    is checked independently of JSON
    validity: a fragment with broken JSON can still have its hash
    verified."""
    if expected_sha256 is None:
        return "-"
    if raw is None:
        return "unknown"
    actual = hashlib.sha256(raw).hexdigest()
    declared = expected_sha256.lower()
    if actual == declared:
        return "match"
    emit(
        log,
        FRAGMENT_DIGEST_INVALID,
        logging.WARNING,
        file=shown,
        measured=actual,
        declared=declared,
    )
    return "mismatch"


def _fragment_modified(mtime: float) -> str:
    """ISO 8601 UTC last-modified timestamp for a ``stat()`` result's
    ``st_mtime``."""
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _print_fragment_list_line(
    frag: FragmentConfig,
    *,
    exists: bool,
    elements: int | None,
    sha_status: str,
    modified: str | None,
    same_document: bool | None,
) -> None:
    """Print one `loom fragment list` output line for *frag*: every
    KEY=VALUE pair describes the same one data point (this fragment), so
    they belong on the same line per AGENTS.md's CLI-output convention
    ("Default: line-delimited, one data point per line") -- one line per
    fragment, not one line per field."""
    # frag.role is None (not configured) vs "" (explicitly set empty) are
    # distinct states -- only None prints as "-", matching this project's
    # own None-vs-empty convention (see AGENTS.md "Recurring bug patterns").
    role = frag.role if frag.role is not None else "-"
    print_kv(
        PATH=frag.path,
        ROLE=role,
        REQUIRED="true" if frag.required else "false",
        EXISTS="true" if exists else "false",
        ELEMENTS=elements if elements is not None else "-",
        SHA256=sha_status,
        MODIFIED=modified if modified is not None else "-",
        SAME_DOCUMENT="-" if same_document is None else str(same_document).lower(),
    )


def _report_fragment(
    project_dir: Path, frag: FragmentConfig, own_document_id: Callable[[], str | None]
) -> bool:
    """Log/print one configured fragment's status; return True if it's a
    ``required=True`` fragment that's missing, unreadable, not a valid
    SPDX3 JSON-LD document on its own, or the project's own document (an
    earlier SBOM of it, compared with *own_document_id*, called only for a
    fragment that has an ``SpdxDocument``) -- the same per-fragment
    conditions that make ``merge_fragments()`` raise ``FragmentMergeError``
    in a ``loom project`` build. This predicts a real build's per-fragment
    outcome, not the later cross-fragment merge itself (e.g. a
    dangling-reference failure that only surfaces once fragments are
    merged together isn't caught here -- see
    ``_raise_on_dangling_references`` in ``assemble.spdx3.fragments``)."""
    fragment_path = project_dir / frag.path
    # One stat() serves both `exists` and `modified`, avoiding a TOCTOU gap.
    # `exists` matches merge_fragments()'s missing-fragment check: both use
    # is_missing_errno(), so only a missing-path errno means "missing". Any
    # other failure (e.g. a permission error) is a present but inaccessible
    # path, which the read below reports.
    try:
        stat_result = fragment_path.stat()
    except OSError as exc:
        exists = not is_missing_errno(exc)
        mtime = None
    else:
        exists = True
        mtime = stat_result.st_mtime
    if not exists:
        warn_fragment_not_found(log, frag.path, required=frag.required)
        raw, read_ok, elements, doc_id = None, False, None, None
    else:
        raw, read_ok, elements, doc_id = _fragment_read_status(
            fragment_path, frag.path, required=frag.required
        )
    # None (unknown) unless the fragment parsed, as for ELEMENTS, or when
    # the project's own id cannot be resolved.
    same_document: bool | None = None
    if read_ok:
        own_id = own_document_id() if doc_id else ""
        same_document = None if own_id is None else bool(doc_id) and doc_id == own_id
    if same_document:
        warn_same_document(log, frag.path, str(doc_id), required=frag.required)

    sha_status = _fragment_sha256_status(raw, frag.sha256, frag.path)
    modified = _fragment_modified(mtime) if mtime is not None else None

    _print_fragment_list_line(
        frag,
        exists=exists,
        elements=elements,
        sha_status=sha_status,
        modified=modified,
        same_document=same_document,
    )
    return frag.required and (not exists or not read_ok or bool(same_document))


def _own_document_id(project_dir: Path) -> str | None:
    """The id a ``loom project`` build of *project_dir* gives, or ``None``
    with one ``WARNING:`` when its metadata cannot be read: the listing
    goes on, with ``SAME_DOCUMENT=-``."""
    try:
        return project_document_id(project_dir)
    except (InternalError, MemoryError):
        raise
    # Any metadata-read failure only leaves this one key unknown.
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        relay_coded_warning(log, exc, quiet=False)  # InternalError when uncoded
        return None


@cli_error_handler
def _run_fragment_list(args: argparse.Namespace) -> int:
    """Run `loom fragment list`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    if not is_input_dir(project_dir, shown=args.project_dir or project_dir):
        say_input_not_found("project directory", args.project_dir or project_dir)
        return 1
    pitloom_config = read_pitloom_config(project_dir / "pyproject.toml")

    if not pitloom_config.fragments:
        say_summary(log, FRAGMENT_LIST_NONE)
        return 0

    # Resolved once, and only for a fragment with an SpdxDocument: it reads
    # the project's metadata and walks its files.
    own_document_id = functools.cache(lambda: _own_document_id(project_dir))
    unmet_required = [
        _report_fragment(project_dir, frag, own_document_id)
        for frag in pitloom_config.fragments
    ]
    return 1 if any(unmet_required) else 0


def _run_fragment_command(args: argparse.Namespace) -> int:
    """Dispatch `loom fragment <command> ...` arguments."""
    if args.fragment_command == "validate":
        return _run_fragment_validate(args)
    if args.fragment_command == "list":
        return _run_fragment_list(args)
    return 1


def add_parser(subparsers: Any, _parent_parser: argparse.ArgumentParser) -> None:
    """Add the ``fragment`` subcommand to the main parser."""
    fragment_parser = subparsers.add_parser(
        "fragment",
        help="Work with dynamic execution SBOM fragments.",
        description=(
            "Work with dynamic execution SBOM fragments -- see also "
            "'pitloom merge' to combine fragments into one SBOM."
        ),
    )
    fragment_subparsers = fragment_parser.add_subparsers(
        dest="fragment_command", required=True
    )

    validate_parser = fragment_subparsers.add_parser(
        "validate",
        help="Validate SPDX 3 JSON document(s) against schema and SHACL rules.",
    )
    validate_parser.add_argument(
        "paths",
        nargs="+",
        type=TypedPath,
        metavar="PATH",
        help="SPDX 3 JSON document(s) to validate.",
    )
    validate_parser.add_argument(
        "--no-merge",
        action="store_true",
        help=(
            "Skip the merged-graph check across multiple PATHs (which "
            "catches type errors across ExternalMap references); validate "
            "each document only in isolation."
        ),
    )

    list_parser = fragment_subparsers.add_parser(
        "list",
        help="List configured SBOM fragments and their status.",
    )
    list_parser.add_argument(
        "--project-dir",
        type=TypedPath,
        default=None,
        help="Project directory containing pyproject.toml (default: cwd).",
    )

    fragment_parser.set_defaults(func=_run_fragment_command)
