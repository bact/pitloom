# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build-type SBOM for a wheel embed: the project directory's rescan
layered onto the built wheel's own file records, and the file-discovery
cache a multi-wheel batch shares.

Split out of :mod:`pitloom.embed` to keep it under the file-size limit.

See also: :mod:`pitloom._embed_generate` (which calls
:func:`_build_sbom_from_project_and_wheel`), :mod:`pitloom.embed` (the
public embed API, which re-exports :class:`EmbedFileCache`) and
:mod:`pitloom.core.build_signals` (the termination guard keeping a
build-and-read result from leaking).
"""

from __future__ import annotations

import contextlib
import dataclasses
import threading
from collections.abc import Callable, Hashable
from pathlib import Path
from types import TracebackType
from typing import TypeVar, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build as assemble_spdx3
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.build_options import BuildOptions
from pitloom.core.build_signals import TerminationGuard
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import _build_merkle_tree, get_wheel_files
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.enrich import run_enrichers_for_models
from pitloom.extract.binary import find_phantom_dependencies
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import IdRegistry

_T = TypeVar("_T")


def _merge_file_extras(
    wheel_files: list[ProjectFile], project_files: list[ProjectFile]
) -> list[ProjectFile]:
    """Layer re-scanned content-type/header data onto the wheel's own files.

    ``wheel_files`` (from :func:`pitloom.extract.wheel.read_wheel`) is the
    source of truth for what the already-built wheel actually contains --
    including ``.dist-info/*`` entries and any build-hook-injected files
    that never existed in ``project_dir`` -- so it is kept intact,
    including its hashes computed from the wheel's own bytes.
    ``project_files`` (from :func:`~pitloom.core.models.get_wheel_files`)
    only supplies the content-type/file-header extras it computed by
    re-scanning the sources, adopted for files present in both lists.
    """
    extras_by_path = {f.distribution_path: f for f in project_files}
    merged: list[ProjectFile] = []
    for wheel_file in wheel_files:
        extra = extras_by_path.get(wheel_file.distribution_path)
        if extra is None:
            merged.append(wheel_file)
            continue
        merged.append(
            dataclasses.replace(
                wheel_file,
                copyright_text=extra.copyright_text,
                copyright_source=extra.copyright_source,
                file_contributors=extra.file_contributors,
                file_type=extra.file_type,
                spdx_license_identifier=extra.spdx_license_identifier,
                content_type=extra.content_type,
                content_type_method=extra.content_type_method,
            )
        )
    return merged


def _compute_wheel_merkle_root(files: list[ProjectFile]) -> str | None:
    """Merkle root over *files*' own digests -- the wheel's truth, not a rescan.

    Mirrors :func:`pitloom.core._models_wheel.get_wheel_files`'s ordering
    (sort by ``distribution_path``) and hashing convention so the result is
    reproducible the same way, but computed from files whose
    ``digest_sha256`` already reflects the wheel's own bytes (post-merge)
    instead of a fresh ``project_dir`` rescan that can diverge from them.
    """
    if not files:
        return None
    ordered = sorted(files, key=lambda f: f.distribution_path)
    # ProjectFile.digest_sha256 is Optional to accommodate
    # get_wheel_files(skip_merkle_root=True), but `files` here is always
    # _merge_file_extras()'s output, which inherits every entry's digest
    # from wheel_metadata.files (the wheel's own real hashes) -- never
    # from the skip-hashing rescan -- so it's always populated.
    leaf_hashes = [bytes.fromhex(cast(str, f.digest_sha256)) for f in ordered]
    return _build_merkle_tree(leaf_hashes)


class EmbedFileCache:
    """One file discovery, one build-flag settle and one cleanup for a
    batch of embeds from the same project directory -- e.g. several wheels
    in one ``loom embed-wheel`` run, or a library loop passing
    ``file_cache=`` to :func:`~pitloom.embed.embed_wheel_sbom`.

    Use it as a context manager around the whole batch. Inside the block,
    :meth:`resolve` runs discovery (and any ``--allow-build`` build) on its
    first call only, and :meth:`settle` warns about each ineffective build
    flag once (:meth:`once` does the same for any other per-batch warning,
    e.g. an option the embed cannot use) -- all hold a lock, so threads
    sharing one batch still get one discovery and one warning each.
    Leaving the block runs the discovery's cleanup once, after every wheel
    is done -- never per wheel, as an earlier wheel's cleanup would delete
    files a later one still reads. The block holds a
    :class:`~pitloom.core.build_signals.TerminationGuard`, so a signal
    during the batch still removes the build's temp directory -- but only
    for a discovery the block's own thread ran. Guard ownership is
    thread-local, so one a worker thread ran registers with that thread's
    own guard. It is removed when the block exits normally, and leaks if
    a signal ends the process first, or if the block's own exit is
    interrupted once that discovery is already cached.

    Every call in a batch must use the same project directory, file-scan
    settings and build options: :meth:`resolve` raises :class:`ValueError`
    otherwise. Using it outside the block, or entering it twice, raises
    :class:`RuntimeError`. After the block it can be entered again and
    resolves afresh.
    """

    def __init__(self) -> None:
        self._resolved: tuple[list[ProjectFile], Callable[[], None]] | None = None
        # What the cached file list was resolved from; see resolve().
        self._resolved_from: tuple[object, ...] | None = None
        # Batch memo, key -> result; see once() and settle().
        self._settled: dict[Hashable, object] = {}
        # The block's guard; None outside the block.
        self._guard: TerminationGuard | None = None
        # Threads sharing one batch get one discovery and one cleanup.
        self._lock = threading.Lock()

    def __enter__(self) -> EmbedFileCache:
        if self._guard is not None:
            raise RuntimeError("EmbedFileCache is already entered")
        # Start clean rather than trust the last block to have finished:
        # an interrupted exit leaves its batch behind on purpose, since
        # that state belongs to whichever thread holds the lock at the
        # time, not to the exit. Deliberately not locked: a thread of the
        # last block may hold the lock for a whole build, and the next
        # batch must not wait for it. A fresh dict rather than clear(),
        # so a settle() still running for the last block writes into the
        # dict it took, never into this block's.
        self._settled = {}
        self._resolved = None
        self._resolved_from = None
        guard = TerminationGuard()
        guard.__enter__()
        self._guard = guard
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            with self._lock:
                # Locked: a thread still inside resolve() finishes first, so
                # its cleanup is never dropped, and it then sees the closed
                # block instead of caching a result nothing will clean up.
                self._close(exc_type, exc, traceback)
        except BaseException as err:
            # Interrupted before the block was closed -- a Ctrl-C while
            # waiting for a thread still inside resolve(), which holds the
            # lock for a whole --allow-build build. Release the guard (its
            # handlers would otherwise outlive the block, and every later
            # block in this thread would nest under a dead owner) and
            # nothing else: the batch's state belongs to whichever thread
            # holds the lock. The guard's own cleanups remove what a
            # discovery on this thread left behind; one still running on a
            # worker thread removes its own when it finds the block gone
            # (see resolve()). The next __enter__ resets the rest.
            guard, self._guard = self._guard, None
            if guard is not None:
                guard.__exit__(type(err), err, err.__traceback__)
            raise

    def _close(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the block, under the lock: forget the batch, run the
        discovery's cleanup, release the guard."""
        try:
            self._settled.clear()
            self._resolved_from = None
            if self._resolved is not None:
                _, cleanup = self._resolved
                self._resolved = None
                cleanup()
        except BaseException as err:
            # Hand the guard the cleanup's own failure (e.g. Ctrl-C
            # during the rmtree), so it still runs its fallback removal.
            exc_type, exc, traceback = type(err), err, err.__traceback__
            raise
        finally:
            # Released from the attribute, never through a local taken
            # earlier: an interrupt before this point must leave it where
            # __exit__'s own handler can still find it.
            if self._guard is not None:
                try:
                    self._guard.__exit__(exc_type, exc, traceback)
                finally:
                    self._guard = None

    def resolve(
        self,
        project_dir: Path,
        pitloom_config: PitloomConfig,
        build_options: BuildOptions,
    ) -> list[ProjectFile]:
        """Return the cached file list, running discovery on first use.

        Raises :class:`RuntimeError` outside a ``with`` block, and
        :class:`ValueError` when a later call in the block asks for a
        different project directory, file-scan settings or build options
        than the first -- the cached list would silently not match it.
        """
        content_type = pitloom_config.content_type
        resolved_from = (
            project_dir,
            pitloom_config.extract_file_header,
            content_type.enabled,
            content_type.method,
            content_type.overrides,
            build_options,
        )
        with self._lock:
            # Inside the lock: the block may have closed while another
            # thread's discovery held it.
            self._require_block("resolve")
            if self._resolved is None:
                block = self._guard
                _, project_files, cleanup = get_wheel_files(
                    project_dir,
                    scan_file_headers=pitloom_config.extract_file_header,
                    detect_content_type=content_type.enabled,
                    content_type_method=content_type.method,
                    content_type_overrides=content_type.overrides,
                    skip_merkle_root=True,
                    build_options=build_options,
                )
                if self._guard is not block:
                    # The block this discovery was started for closed
                    # while it held the lock (an interrupt in __exit__),
                    # and another may already have taken its place --
                    # each block gets its own guard, so identity, not
                    # mere presence, is what says "still the same one".
                    # Nothing else would run this cleanup, and no block
                    # may be handed a result it never asked for.
                    cleanup()
                    self._require_block("resolve")
                    raise RuntimeError(
                        "EmbedFileCache.resolve() outlived its with-block: "
                        "the batch it was called for ended while it ran"
                    )
                self._resolved = (project_files, cleanup)
                self._resolved_from = resolved_from
            elif resolved_from != self._resolved_from:
                raise ValueError(
                    "EmbedFileCache: every call in one batch must use the same "
                    "project directory, file-scan settings and build options"
                )
            return self._resolved[0]

    def settle(
        self, build_options: BuildOptions, subject: object, reason: str | None = None
    ) -> BuildOptions:
        """Settle *build_options* -- with
        :meth:`~pitloom.core.build_options.BuildOptions.settle`, or with
        :meth:`~pitloom.core.build_options.BuildOptions.settle_not_applicable`
        and *reason* when given -- once per block for each distinct
        (*build_options*, *reason*) pair, reusing that result on later
        calls, so each ineffective flag warns once for the batch. A call
        with other options or another reason settles (and warns) itself.

        Raises :class:`RuntimeError` outside a ``with`` block.
        """
        return self.once(
            ("build_options", build_options, reason),
            lambda: (
                build_options.settle(subject)
                if reason is None
                else build_options.settle_not_applicable(subject, reason)
            ),
            "settle",
        )

    def once(
        self, key: Hashable, compute: Callable[[], _T], method: str = "once"
    ) -> _T:
        """*compute*'s result, computed on the first call with *key* in
        this block and reused after -- so a warning *compute* logs is
        logged once for the batch. The caller keys on everything the result
        depends on.

        Raises :class:`RuntimeError` outside a ``with`` block.
        """
        with self._lock:
            self._require_block(method)
            # This block's memo, taken once: __enter__ gives the next
            # block a new one, so a late call here cannot warn into it.
            settled = self._settled
            if key not in settled:
                # Under the lock: a warning is part of computing, so two
                # threads must not both emit it.
                settled[key] = compute()
            return cast(_T, settled[key])

    def _require_block(self, method: str) -> None:
        if self._guard is None:
            raise RuntimeError(
                f"EmbedFileCache.{method}() outside its with-block: "
                "use 'with EmbedFileCache() as cache:' around the batch"
            )


# pylint: disable-next=too-many-arguments
def _build_sbom_from_project_and_wheel(
    project_dir: Path,
    wheel_metadata: ProjectMetadata,
    pitloom_config: PitloomConfig,
    registry: IdRegistry | None,
    creation_metadata: CreationMetadata | None,
    *,
    build_options: BuildOptions = BuildOptions(),
    file_cache: EmbedFileCache | None = None,
) -> str:
    """Generate a canonical Build SBOM from project sources and wheel files.

    *build_options* is a separate parameter, not read off
    ``pitloom_config``: it deliberately has no ``[tool.pitloom]`` cascade
    (see ``ConfigOverrides.build_options``).

    *file_cache*, when given, resolves *project_dir*'s file list through
    it and leaves the cleanup to its owner (see :class:`EmbedFileCache`)
    -- the multi-wheel batch path. ``None`` resolves through a cache
    private to this call, cleaned up before it returns.
    """
    # merkle_root (the rescan's own, over project_dir's on-disk bytes) is
    # deliberately discarded here -- see _compute_wheel_merkle_root below,
    # which recomputes it from the wheel's own (post-merge) file hashes so
    # it can't diverge from what merged_files actually reports. Per-file
    # digest_sha256 is skipped for the same reason: _merge_file_extras
    # below only adopts project_files' content-type/header extras, never
    # its digest, so hashing every file here would be wasted I/O too.
    #
    # The cache's block owns SIGTERM/SIGHUP handling while a build-and-read
    # result is in use (see pitloom.core.build_signals), and its exit runs
    # the discovery cleanup -- after every step below that re-reads a
    # ProjectFile's bytes via physical_path (AI-model scanning, enrichment),
    # and even if one of them raises.
    with (
        contextlib.nullcontext(file_cache)
        if file_cache is not None
        else EmbedFileCache()
    ) as cache:
        project_files = cache.resolve(project_dir, pitloom_config, build_options)
        # Layer content-type/file-header extras onto the wheel's own
        # file records rather than replacing them outright: replacing
        # would drop .dist-info entries and any build-hook-injected
        # files (e.g. compiled extensions, auditwheel-repaired shared
        # libraries) that read_wheel() found in the actual wheel but
        # that a source-tree rescan can't see.
        merged_files = _merge_file_extras(wheel_metadata.files, project_files)
        # replace_with_fresh_containers(), not a bare
        # dataclasses.replace() or an in-place `.files =` assignment:
        # every dict/list field NOT given here (provenance,
        # field_conflicts, etc.) also gets its own fresh copy, so the
        # caller's wheel_metadata (e.g. embed_wheel_sbom's
        # read_wheel() result) can never be silently mutated as a
        # side effect of anything downstream mutating this SBOM's own
        # project_metadata.
        project_metadata = wheel_metadata.replace_with_fresh_containers(
            files=merged_files
        )
        merkle_root = _compute_wheel_merkle_root(merged_files)
        ai_models = scan_project_for_ai_models(project_dir, project_files)
        enrichment_results = run_enrichers_for_models(
            ai_models, pitloom_config.enrich, project_dir
        )
    phantom_deps = find_phantom_dependencies(merged_files)

    doc = DocumentModel(
        project=project_metadata,
        creation_metadata=creation_metadata or CreationMetadata(),
        ai_models=ai_models,
        phantom_dependencies=phantom_deps,
    )
    exporter = assemble_spdx3(
        doc,
        merkle_root=merkle_root,
        sbom_type=spdx3.software_SbomType.build,
        registry=registry,
        enrichment_results_by_model=enrichment_results,
        **pitloom_config.assemble_options,
    )
    # Fragments merge only into a project directory's SBOM, as for
    # `loom project` (assemble/_generators.py): not an sdist's, even from
    # an explicit --config.
    if Path(project_dir).is_dir():
        merge_fragments(project_dir, pitloom_config.fragments, exporter)
    return exporter.to_json(pretty=False)
