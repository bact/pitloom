# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Build-type SBOM for a wheel embed: the project directory's rescan
layered onto the built wheel's own file records, and the file-discovery
cache a multi-wheel batch shares.

Split out of :mod:`pitloom.embed` to keep it under the file-size limit.

See also: :mod:`pitloom.embed` (the public embed API, which calls
:func:`_build_sbom_from_project_and_wheel` and re-exports
:class:`EmbedFileCache`) and :mod:`pitloom.core.build_signals` (the
termination guard keeping a build-and-read result from leaking).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import cast

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
from pitloom.extract.scanner import scan_project_for_ai_models
from pitloom.ids import IdRegistry


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
    """Memoizes one project directory's file-discovery result (and its
    cleanup callback) across a batch of :func:`_build_sbom_from_project_and_wheel`
    calls that share the same *project_dir*/*pitloom_config*/*build_options*
    -- e.g. embedding into several wheels from one ``loom embed-wheel``
    invocation.

    Without this, each wheel in a multi-wheel batch independently called
    ``get_wheel_files()``: a ``--allow-build`` real PEP 517 build ran once
    per wheel instead of once for the whole batch. The build options are
    settled once per block too (:meth:`settle`), so an ineffective flag
    warns once for the batch, not once per wheel.

    Every call in a batch must use the same project directory, file-scan
    settings and build options: :meth:`resolve` raises
    :class:`ValueError` otherwise, rather than silently hand one call the
    file list resolved for another.

    A context manager, and must be used as one around the whole batch:
    :meth:`resolve` runs discovery at most once -- the first call in the
    block; every later call reuses that result. Leaving the block runs the
    cleanup callback once, on every exit path, after every wheel has
    finished consuming the files (a build-and-read result's files
    physically live in a temp directory it removes -- see
    :func:`~pitloom.core.models.get_wheel_files`'s own cleanup contract).
    Never per-wheel: an earlier wheel's cleanup would delete the files a
    later wheel in the same batch still needs to read. :meth:`resolve`
    outside the block raises :class:`RuntimeError`, as nothing would run
    that cleanup; entering the block while it is entered does too. The
    same instance can be entered again after the block, and then resolves
    afresh.

    The block also holds a
    :class:`~pitloom.core.build_signals.TerminationGuard`, so a
    SIGTERM/SIGHUP between or during wheels removes that directory before
    the process ends.

    Not used unless explicitly passed to
    :func:`_build_sbom_from_project_and_wheel` -- every other caller (a
    single ``embed_wheel_sbom()`` call, the public library API) keeps
    per-call resolve-then-cleanup behaviour.
    """

    def __init__(self) -> None:
        self._resolved: tuple[list[ProjectFile], Callable[[], None]] | None = None
        # What the cached file list was resolved from; see resolve().
        self._resolved_from: tuple[object, ...] | None = None
        # (given options, reason) -> settled options; see settle().
        self._settled: dict[tuple[BuildOptions, str | None], BuildOptions] = {}
        # The block's guard; None outside the block.
        self._guard: TerminationGuard | None = None

    def __enter__(self) -> EmbedFileCache:
        if self._guard is not None:
            raise RuntimeError("EmbedFileCache is already entered")
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
        guard, self._guard = self._guard, None
        self._settled.clear()
        self._resolved_from = None
        try:
            if self._resolved is not None:
                _, cleanup = self._resolved
                self._resolved = None
                cleanup()
        finally:
            if guard is not None:
                guard.__exit__(exc_type, exc, traceback)

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
        self._require_block("resolve")
        content_type = pitloom_config.content_type
        resolved_from = (
            project_dir,
            pitloom_config.extract_file_header,
            content_type.enabled,
            content_type.method,
            content_type.overrides,
            build_options,
        )
        if self._resolved is None:
            _, project_files, cleanup = get_wheel_files(
                project_dir,
                scan_file_headers=pitloom_config.extract_file_header,
                detect_content_type=content_type.enabled,
                content_type_method=content_type.method,
                content_type_overrides=content_type.overrides,
                skip_merkle_root=True,
                build_options=build_options,
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
        self._require_block("settle")
        key = (build_options, reason)
        if key not in self._settled:
            self._settled[key] = (
                build_options.settle(subject)
                if reason is None
                else build_options.settle_not_applicable(subject, reason)
            )
        return self._settled[key]

    def _require_block(self, method: str) -> None:
        if self._guard is None:
            raise RuntimeError(
                f"EmbedFileCache.{method}() outside its with-block: "
                "use 'with EmbedFileCache() as cache:' around the batch"
            )


def _batch_owned_cleanup() -> None:
    """Placeholder ``cleanup_discovery`` for the ``file_cache`` path below
    -- the batch owner (``file_cache``) runs the real cleanup once, so
    this call's own try/finally must not clean up early."""


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
    it instead of calling ``get_wheel_files()`` directly, and leaves its
    cleanup to the cache's owner (see :class:`EmbedFileCache`) rather
    than running it at the end of this call -- the multi-wheel batch
    path. ``None`` (every other caller) keeps the original per-call
    resolve-then-cleanup behaviour.
    """
    # merkle_root (the rescan's own, over project_dir's on-disk bytes) is
    # deliberately discarded here -- see _compute_wheel_merkle_root below,
    # which recomputes it from the wheel's own (post-merge) file hashes so
    # it can't diverge from what merged_files actually reports. Per-file
    # digest_sha256 is skipped for the same reason: _merge_file_extras
    # below only adopts project_files' content-type/header extras, never
    # its digest, so hashing every file here would be wasted I/O too.
    #
    # Owns SIGTERM/SIGHUP handling while a build-and-read result is in use
    # (see pitloom.core.build_signals); nested, and so inert, inside
    # file_cache's own guard.
    with TerminationGuard():
        cleanup_discovery: Callable[[], None]
        if file_cache is not None:
            project_files = file_cache.resolve(
                project_dir, pitloom_config, build_options
            )
            cleanup_discovery = _batch_owned_cleanup
        else:
            _, project_files, cleanup_discovery = get_wheel_files(
                project_dir,
                scan_file_headers=pitloom_config.extract_file_header,
                detect_content_type=pitloom_config.content_type.enabled,
                content_type_method=pitloom_config.content_type.method,
                content_type_overrides=pitloom_config.content_type.overrides,
                skip_merkle_root=True,
                build_options=build_options,
            )
        # cleanup_discovery (a no-op unless --allow-build's build-and-read
        # sourced project_files, or file_cache is given -- see above) must
        # stay alive -- and this whole block must run inside its try --
        # through every step below that either re-reads a ProjectFile's
        # bytes from disk via physical_path (AI-model scanning, enrichment)
        # or could itself raise before reaching them (the file-extras merge,
        # the fresh-containers copy): any of these raising before
        # cleanup_discovery() runs would leak the build-and-read temp
        # directory.
        try:
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
        finally:
            cleanup_discovery()
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
        provenance=pitloom_config.provenance,
        enrichment_results_by_model=enrichment_results,
        offline=pitloom_config.offline,
    )
    merge_fragments(project_dir, pitloom_config.fragments, exporter)
    return exporter.to_json(pretty=False)
