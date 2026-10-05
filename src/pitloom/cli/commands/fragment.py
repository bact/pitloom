# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for Pitloom's SBOM generator."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import logging
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import project_document_id
from pitloom.assemble.spdx3.fragments import (
    _find_fragment_document_id,
    _fragment_read_failure_message,
    _missing_fragment_message,
    _same_document_message,
)
from pitloom.cli.commands.utils import (
    _import_spdx3_validate,
    _validate_spdx3_documents,
    cli_error_handler,
)
from pitloom.cli.kv_output import print_kv
from pitloom.core.config import FragmentConfig, read_pitloom_config
from pitloom.core.path_probe import is_missing_errno
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)


@cli_error_handler("fragment validate failed")
def _run_fragment_validate(args: argparse.Namespace) -> int:
    """Run `pitloom fragment validate`."""
    # Both checks run and report independently -- a user missing the
    # optional dependency AND passing a bad path should see both ERROR:
    # lines in one run, not just the first one, for one round trip.
    dependency_ok = _import_spdx3_validate() is not None

    paths: list[Path] = args.paths
    not_files = [p for p in paths if not p.is_file()]
    for p in not_files:
        kind = "directory" if p.is_dir() else "file not found"
        print(f"ERROR: {kind}: {p}", file=sys.stderr)

    if not dependency_ok or not_files:
        return 1

    exit_code = _validate_spdx3_documents(
        [str(p) for p in paths], check_merged=not args.no_merge
    )
    if exit_code == 0:
        for p in paths:
            print_kv(FILE=p, STATUS="valid")
        log.info("fragment validate: %d document(s) valid", len(paths))
    return exit_code


def _fragment_read_status(
    fragment_path: Path, *, required: bool
) -> tuple[bytes | None, bool, int | None, str | None]:
    """Read *fragment_path* once, for the element count, the SPDX3-
    validity check below, and the SHA-256 check in
    :func:`_fragment_sha256_status` -- avoids reading the same fragment
    file more than once. Returns
    ``(raw_bytes, read_ok, element_count, document_id)``:

    - ``raw_bytes`` is the file's contents, or ``None`` only if the file
      itself couldn't be read (not on a JSON-parse failure) -- so a
      fragment with broken JSON can still have its hash verified by
      :func:`_fragment_sha256_status`, matching pre-existing behavior.
    - ``read_ok`` is False on a read/JSON-parse failure, or when the JSON
      doesn't parse as a valid SPDX3 JSON-LD document -- the same two
      conditions that make ``merge_fragments()`` treat a ``required=True``
      fragment as unmet, so callers should key exit-code decisions on
      this, not on ``element_count``. (Syntactically valid JSON that
      isn't valid SPDX3 -- e.g. missing ``@context``, unrecognised
      ``type`` values -- fails here too, not just outright unparseable
      JSON.)
    - ``element_count`` is the fragment's ``@graph`` length, or ``None``
      if the parsed JSON isn't an object (not itself a read failure).
    - ``document_id`` is the fragment's own ``SpdxDocument`` id, or
      ``None`` without one or when ``read_ok`` is False.

    Logs a WARNING (shared wording with ``merge_fragments()``) on any
    read, JSON-parse, or SPDX3-parse failure.
    """
    try:
        raw = fragment_path.read_bytes()
    except OSError as exc:
        log.warning(
            _fragment_read_failure_message(fragment_path, exc, required=required)
        )
        return None, False, None, None
    try:
        # json.loads(bytes) -- not raw.decode("utf-8") + json.loads(str) --
        # to match the real merge path (json.load() on a binary handle):
        # both auto-detect and strip a leading UTF-8 BOM, while
        # json.loads(str) raises on one. Decoding first would make this
        # command reject a fragment a real build would merge successfully.
        data = json.loads(raw)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Broad on purpose, matching the SPDX3-deserialize catch below --
        # a narrower catch (e.g. just JSONDecodeError) still lets an
        # unusual failure (e.g. RecursionError on deeply nested JSON)
        # abort this entire command instead of degrading just this one
        # fragment, the same hazard the broad catch below already guards.
        log.warning(
            _fragment_read_failure_message(fragment_path, exc, required=required)
        )
        return raw, False, None, None
    graph = data.get("@graph", []) if isinstance(data, dict) else None
    elements = len(graph) if isinstance(graph, list) else None
    try:
        # deserialize_data(), not read() -- data is already parsed above,
        # no need to hand the deserializer raw bytes to re-parse as JSON.
        object_set = spdx3.SHACLObjectSet()
        spdx3.JSONLDDeserializer().deserialize_data(data, object_set)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Matches merge_fragments()'s own broad catch (fragments.py) --
        # the JSON-LD deserializer can raise a wide variety of exception
        # types for a malformed/non-SPDX3 document, none of them a stable
        # public contract worth narrowing to.
        log.warning(
            _fragment_read_failure_message(fragment_path, exc, required=required)
        )
        return raw, False, elements, None
    return raw, True, elements, _find_fragment_document_id(object_set)


def _fragment_sha256_status(
    raw: bytes | None, expected_sha256: str | None, fragment_path: Path
) -> str:
    """Three-state SHA-256 display: ``-`` (not configured), ``unknown``
    (configured but the file couldn't be read), or ``match``/``mismatch``.
    Logs a WARNING on mismatch. *raw* is checked independently of JSON
    validity -- a fragment with broken JSON can still have its hash
    verified, matching pre-existing behavior."""
    if expected_sha256 is None:
        return "-"
    if raw is None:
        return "unknown"
    actual = hashlib.sha256(raw).hexdigest()
    if actual.lower() == expected_sha256.lower():
        return "match"
    log.warning(
        "SBOM fragment %s SHA-256 mismatch: configured %s, actual %s",
        fragment_path,
        expected_sha256,
        actual,
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
    """Print one `pitloom fragment list` output line for *frag*: every
    KEY=VALUE pair describes the same one data point (this fragment), so
    they belong on the same line per CLAUDE.md's CLI-output convention
    ("Default: line-delimited, one data point per line") -- one line per
    fragment, not one line per field."""
    # frag.role is None (not configured) vs "" (explicitly set empty) are
    # distinct states -- only None prints as "-", matching this project's
    # own None-vs-empty convention (see CLAUDE.md "Recurring bug patterns").
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
    # A single stat() up front, reused for both `exists` and `modified` --
    # avoids both a second syscall and a TOCTOU gap where a later
    # separate stat() could raise on a file removed in between (the read
    # below has its own OSError handling, but stat() previously didn't).
    # `exists` matches merge_fragments()'s own missing-fragment check
    # (both now classify a stat()/exists() failure via the shared
    # is_missing_errno()) -- True for any path present, regardless of
    # type; a stat() failure only means "missing" for the same errno/
    # winerror set Path.exists()/is_file() treat that way; anything else
    # (e.g. a permission error) is a real, present-but-inaccessible path,
    # and the read attempt below reports that accurately instead of this
    # function mislabeling it "not found".
    try:
        stat_result = fragment_path.stat()
    except OSError as exc:
        exists = not is_missing_errno(exc)
        mtime = None
    else:
        exists = True
        mtime = stat_result.st_mtime
    if not exists:
        log.warning(_missing_fragment_message(fragment_path, required=frag.required))
        raw, read_ok, elements, doc_id = None, False, None, None
    else:
        raw, read_ok, elements, doc_id = _fragment_read_status(
            fragment_path, required=frag.required
        )
    # None (unknown) unless the fragment parsed, as for ELEMENTS, or when
    # the project's own id cannot be resolved.
    same_document: bool | None = None
    if read_ok:
        own_id = own_document_id() if doc_id else ""
        same_document = None if own_id is None else bool(doc_id) and doc_id == own_id
    if same_document:
        log.warning(
            _same_document_message(fragment_path, str(doc_id), required=frag.required)
        )

    sha_status = _fragment_sha256_status(raw, frag.sha256, fragment_path)
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
    # Any metadata-read failure (ValueError, OSError, a malformed field's
    # TypeError/AttributeError) only leaves this one key unknown.
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        log.warning(
            "fragment list: project metadata unreadable, SAME_DOCUMENT unknown: %s",
            loggable(str(exc)),
        )
        return None


@cli_error_handler("fragment list failed")
def _run_fragment_list(args: argparse.Namespace) -> int:
    """Run `pitloom fragment list`."""
    project_dir: Path = (args.project_dir or Path.cwd()).resolve()
    pitloom_config = read_pitloom_config(project_dir / "pyproject.toml")

    if not pitloom_config.fragments:
        log.info("fragment list: no fragments configured")
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
    """Dispatch `pitloom fragment <command> ...` arguments."""
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
        type=Path,
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
        type=Path,
        default=None,
        help="Project directory containing pyproject.toml (default: cwd).",
    )

    fragment_parser.set_defaults(func=_run_fragment_command)
