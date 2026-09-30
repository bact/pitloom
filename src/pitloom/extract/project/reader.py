# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Entry points for resolving a project's metadata and Pitloom config.

:func:`read_project` tries ``pyproject.toml`` first, then
``setup.cfg``/``setup.py``, or reads an sdist archive (.tar.gz, .zip), so
both the CLI (:mod:`pitloom.__main__`) and the library entry point
(:func:`pitloom.assemble.generate_project_sbom`) resolve project metadata
the same way. :func:`resolve_project_with_lockfile` additionally decides
the lock/pin cascade from a tri-state (CLI-flag-shaped) setting -- see its
own docstring.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom._toml_io import load_toml_file
from pitloom.core.config import (
    PYPROJECT_SOURCE,
    PitloomConfig,
    pyproject_config_applies,
    select_project_config,
)
from pitloom.core.project import (
    ProjectMetadata,
    is_sdist_archive,
    merge_project_metadata,
)
from pitloom.extract.lock import apply_locked_dependencies
from pitloom.extract.project._installed_reconcile import reconcile_installed_metadata
from pitloom.extract.project.installed import (
    _discover_candidate,
    _parse_installed_metadata,
)
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.project.setuptools import read_setuptools

log = logging.getLogger(__name__)


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _fallback_to_setuptools(
    project_path: Path,
    metadata: ProjectMetadata,
    pitloom_config: PitloomConfig,
    setup_cfg: Path,
    setup_py: Path,
    pyproject_path: Path,
    *,
    quiet: bool,
    read_config: bool,
) -> tuple[ProjectMetadata, PitloomConfig, Path]:
    """``pyproject.toml`` exists but resolved no usable metadata -- no
    ``[project]`` table (e.g. a custom/legacy build backend declaring only
    ``[build-system]``) and no ``[tool.poetry]`` fallback either -- while
    ``setup.cfg``/``setup.py`` hold the project's real metadata. Prefer
    that over the otherwise nameless/versionless stub ``read_pyproject()``
    returns; the same shape ``_models_wheel.py``'s file-discovery dispatch
    already treats as "no static pyproject.toml config" (see
    ``has_resolvable_pyproject_config()``).

    Split out of :func:`read_project` purely to keep that function's own
    cognitive-complexity ratchet -- no behavior split, just a named step.
    """
    if not quiet:
        log.warning(
            "%s has no usable [project] table and no [tool.poetry] "
            "fallback -- falling back to setup.cfg/setup.py metadata "
            "instead of an empty pyproject.toml-only result",
            pyproject_path,
        )
    # read_pyproject() may have already resolved locked_dependencies from
    # poetry.lock -- via _try_read_poetry()'s own "[tool.poetry] couldn't
    # be parsed, but still apply poetry.lock's resolved dependencies"
    # path, the exact case that leads here (an empty name with real
    # poetry.lock data already attached). Never silently drop a real
    # result just because metadata itself had to come from
    # setup.cfg/setup.py instead: without this, a lower-priority lock/pin
    # format could also silently win the cascade below in poetry.lock's
    # place, since apply_locked_dependencies() would see no prior result
    # at all on the replaced metadata.
    #
    # merge_project_metadata() (not a hand-rolled per-field carry-over)
    # does this generically for every ProjectMetadata field, `name`
    # always primary's (read_setuptools()'s -- the real resolved name)
    # and `locked_dependencies`/`provenance` falling back to secondary's
    # (the pre-swap `metadata`) when primary's own is empty -- the same
    # mechanism already used for the analogous [tool.pitloom]-config
    # carry-over just below, generalized so a future field needing the
    # same treatment doesn't need a third hand-copied carry-over here.
    pre_setuptools_metadata = metadata
    # Decide first: setup.cfg's [tool:pitloom] is parsed only when it is the
    # one that applies, as for an sdist -- an unused one cannot fail the run.
    pyproject_applies = read_config and pyproject_config_applies(
        load_toml_file(pyproject_path)
    )
    metadata, setuptools_pitloom_config = read_setuptools(
        project_path, quiet=quiet, read_config=read_config and not pyproject_applies
    )
    metadata = merge_project_metadata(
        primary=metadata, secondary=pre_setuptools_metadata
    )
    # pyproject.toml's [tool.pitloom] still applies when declared, though
    # metadata came from setup.cfg/setup.py; else setup.cfg's [tool:pitloom].
    # The rule an sdist archive shares. Without read_config both are
    # placeholders for a config the caller replaces.
    pitloom_config, source = select_project_config(
        pitloom_config, pyproject_applies, lambda: setuptools_pitloom_config
    )
    if source == PYPROJECT_SOURCE:
        return metadata, pitloom_config, pyproject_path
    return metadata, pitloom_config, setup_cfg if setup_cfg.exists() else setup_py


def read_project(
    project_path: Path,
    *,
    include_locked_dependencies: bool = True,
    include_installed_metadata: bool = True,
    quiet: bool = False,
    read_config: bool = True,
) -> tuple[ProjectMetadata, PitloomConfig, Path | None]:
    """Resolve project metadata and Pitloom config from *project_path*.

    If *project_path* is a source distribution archive (.tar.gz, .zip),
    extracts metadata from its internal PKG-INFO or pyproject.toml, and the
    config from its root ``pyproject.toml``/``setup.cfg``, as for the
    unpacked directory (see :func:`pitloom.extract.project.sdist.read_sdist`).
    Otherwise, treats *project_path* as a directory and tries
    ``pyproject.toml`` first, then ``setup.cfg``/``setup.py``.

    For every directory-based resolution (not the sdist-archive case),
    also overlays a sibling lock/pin file's resolved dependencies onto
    the result via a single, shared call to
    :func:`pitloom.extract.lock.cascade.apply_locked_dependencies`
    -- applied uniformly regardless of which metadata source won, since
    some lock formats (``Pipfile.lock``, pinned ``requirements.txt``)
    pair with a bare ``setup.py`` in real projects, never ``pyproject.toml``.

    ``include_locked_dependencies`` lets a build-stage or config-only
    caller (e.g. ``embed-wheel``, or a shared CLI helper that only wants
    ``[tool.pitloom]`` settings and discards the metadata) explicitly opt
    out of *every* lock/pin source -- source-stage lock/pin data must
    never leak into a build-stage SBOM, and skipping this also skips its
    file I/O for a caller that would discard the result anyway. It's
    forwarded to :func:`pitloom.extract.project.pyproject.read_pyproject` (which
    forwards it again to
    :func:`pitloom.extract.project.pyproject._try_read_poetry` for
    ``poetry.lock``, gated by that function's own identically-named
    parameter) *and* used directly here to gate
    :func:`pitloom.extract.lock.cascade.apply_locked_dependencies`
    for every other format -- one flag controls both, not two
    independently-set ones that happen to share a name.

    Args:
        project_path: Project root directory or sdist archive path.
        include_locked_dependencies: Whether to read any lock/pin file's
            resolved dependencies at all -- ``poetry.lock`` included
            (default ``True``). Pass ``False`` from any build-stage or
            metadata-discarding caller.
        include_installed_metadata: Whether to search *project_path* for an
            in-tree ``.egg-info``/``.dist-info`` (a build backend's
            editable-install byproduct -- see
            :mod:`pitloom.extract.project.installed`) and reconcile it into
            the result (default ``True``). Pass ``False`` from any
            build-stage or metadata-discarding caller, purely to skip the
            new filesystem globbing -- same rationale as
            ``include_locked_dependencies``, but a separate flag: the two
            gate genuinely different sources (a lock/pin file vs. an
            in-tree installed-metadata directory) that happen to share the
            same "skip for a caller that discards the result" rationale,
            not one another's setting.
        quiet: Suppress this read's own ``WARNING:`` lines (default
            ``False``). For a caller re-reading the same, already-read
            *project_path* a second time and only interested in a setting
            unrelated to the warning's cause -- never for a caller doing
            the only read that will happen.
        read_config: Whether to parse the project's own ``[tool.pitloom]``
            (default ``True``). Pass ``False`` when an explicit config
            replaces it: the defaults are returned instead, so a fault in
            the replaced config cannot fail the read.

    Returns:
        A 3-tuple of:

        * :class:`~pitloom.core.project.ProjectMetadata` -- resolved project
          metadata.
        * :class:`~pitloom.core.config.PitloomConfig` -- resolved
          ``[tool.pitloom]`` settings.
        * The config file path used; for an sdist, ``<archive>/<member>``
          (e.g. ``x.tar.gz/pyproject.toml``), or ``None`` when the archive
          has no config member (or *read_config* is off).

    Raises:
        FileNotFoundError: If *project_path* does not exist or no valid project
            config is found.
        ValueError: If config is malformed.
    """
    if not project_path.exists():
        raise FileNotFoundError(f"Project path not found: {project_path}")

    if is_sdist_archive(project_path):
        contents = read_sdist(project_path, read_config=read_config)
        contents.metadata.files = contents.files
        member = contents.config_member
        return (
            contents.metadata,
            contents.config,
            None if member is None else project_path / member,
        )

    setup_cfg = project_path / "setup.cfg"
    setup_py = project_path / "setup.py"

    config_path: Path | None
    pyproject_path = project_path / "pyproject.toml"
    if pyproject_path.exists():
        metadata, pitloom_config = read_pyproject(
            pyproject_path,
            include_locked_dependencies=include_locked_dependencies,
            quiet=quiet,
            read_config=read_config,
        )
        if not metadata.name and (setup_cfg.exists() or setup_py.exists()):
            metadata, pitloom_config, config_path = _fallback_to_setuptools(
                project_path,
                metadata,
                pitloom_config,
                setup_cfg,
                setup_py,
                pyproject_path,
                quiet=quiet,
                read_config=read_config,
            )
        else:
            config_path = pyproject_path
    elif setup_cfg.exists() or setup_py.exists():
        metadata, pitloom_config = read_setuptools(
            project_path, quiet=quiet, read_config=read_config
        )
        config_path = setup_cfg if setup_cfg.exists() else setup_py
    else:
        raise FileNotFoundError(
            f"No pyproject.toml, setup.cfg, or setup.py found in {project_path}"
        )

    if include_locked_dependencies:
        apply_locked_dependencies(metadata, project_path)

    if include_installed_metadata and metadata.name:
        metadata = _apply_installed_metadata(metadata, project_path, quiet=quiet)

    return metadata, pitloom_config, config_path


def _apply_installed_metadata(
    metadata: ProjectMetadata, project_path: Path, *, quiet: bool
) -> ProjectMetadata:
    """Search *project_path* for an in-tree installed-metadata candidate
    (see :mod:`pitloom.extract.project.installed`) and reconcile it into
    *metadata*, if found. Returns *metadata* unchanged when nothing is
    found.

    Split out of :func:`read_project` purely to keep that function's own
    branch/local count under this repo's complexity ratchet -- no
    behavior split, just a named step.

    Uses :func:`~pitloom.extract.project.installed._discover_candidate`
    directly (not the public, tuple-returning
    :func:`~pitloom.extract.project.installed.find_installed_metadata_candidate`)
    so the winning candidate's already-parsed
    :class:`email.message.Message` is reused for parsing here, instead of
    re-reading and re-parsing the exact same marker file a second time.
    """
    candidate = _discover_candidate(project_path, metadata.name, quiet=quiet)
    if candidate is None:
        return metadata
    source_label = f"Source: {candidate.label} | File: {candidate.marker_path.name}"
    installed = _parse_installed_metadata(candidate.message, source_label)
    return reconcile_installed_metadata(
        metadata, installed, candidate.label, project_path, quiet=quiet
    )


def resolve_project_with_lockfile(
    project_path: Path,
    use_lockfile: bool | None,
    explicit_config: PitloomConfig | None = None,
) -> tuple[ProjectMetadata, PitloomConfig, Path | None]:
    """Resolve project metadata, deciding the lock/pin cascade from
    *use_lockfile* itself when given, else from *explicit_config*'s
    ``use-lockfile``, else from the project's own ``[tool.pitloom]
    use-lockfile``.

    *explicit_config* (``--config``, ``pitloom_config=``) replaces the
    project's own ``[tool.pitloom]``, which is then not parsed at all, and
    is returned as the config; the returned path is still the project's
    own. This function never warns:
    a given *use_lockfile* that has no effect (an sdist) is settled by the
    caller's inert-option check.

    The cascade decision has to be known before the real metadata read
    runs, but ``[tool.pitloom] use-lockfile`` only becomes known *from* a
    :func:`read_project` call -- so when *use_lockfile* is ``None``, this
    "peeks" the config first via a
    ``include_locked_dependencies=False`` read (skips lock-file I/O only
    -- ``include_installed_metadata`` deliberately stays at its default,
    see the comment below), then only re-reads for real when that config
    says the cascade should run. That re-read is passed ``quiet=True``: it
    parses the same file the peek just did, so any ``WARNING:`` its
    content triggers was already emitted once by the peek -- re-emitting
    it would violate this repo's "one grep-able line per event"
    CLI-output contract. An sdist archive target skips the peek/reread
    dance entirely: :func:`read_project` ignores
    *include_locked_dependencies* for sdist targets (no lock/pin cascade
    support for archives yet), so peeking would always see the cascade as
    "on" and re-read (and re-extract the archive) for an identical result.
    Shared by :func:`pitloom.assemble.generate_project_sbom`,
    :func:`pitloom.assemble.enrich_model` and
    ``pitloom.cli.options_resolve._resolve_project_generation_settings`` so
    the resolution
    logic (and its remaining double-parse tradeoff for the on-cascade,
    non-sdist case -- an accepted cost, see
    ``working-docs/implementation/lock-file-cascade.md``) exists in one
    place, not duplicated per caller. That tradeoff now also covers a
    second cost: the peek's ``include_installed_metadata`` staying on
    means a project with an in-tree ``.egg-info``/``.dist-info`` pays for
    :mod:`pitloom.extract.project.installed`'s bounded glob and marker-file
    read twice (once per ``read_project`` call below), not once -- the
    same accepted-cost umbrella as the static-metadata double-parse, not a
    separate tradeoff of its own.
    """
    # An explicit config replaces the project's own, which is then not
    # parsed: a fault in it cannot fail a run that does not use it.
    read_config = explicit_config is None
    if is_sdist_archive(project_path):
        return _with_config(
            read_project(project_path, read_config=read_config), explicit_config
        )

    if use_lockfile is None and explicit_config is not None:
        use_lockfile = explicit_config.use_lockfile
    if use_lockfile is not None:
        return _with_config(
            read_project(
                project_path,
                include_locked_dependencies=use_lockfile,
                read_config=read_config,
            ),
            explicit_config,
        )

    # Deliberately leaves include_installed_metadata at its default (True)
    # on both calls below -- do NOT copy include_locked_dependencies=False
    # onto this peek. use_lockfile only decides the lock/pin cascade; when
    # peeked_config.use_lockfile is False, `peeked_metadata` below becomes
    # the actual returned metadata (no re-read happens), so disabling
    # installed-metadata resolution on the peek would make an unrelated
    # `[tool.pitloom] use-lockfile` setting silently also suppress
    # installed-metadata reconciliation -- a "no silent deviations"
    # violation (see working-docs/design/installed-dist-info-source.md).
    peeked_metadata, peeked_config, peeked_path = read_project(
        project_path, include_locked_dependencies=False
    )
    if peeked_config.use_lockfile:
        return read_project(project_path, quiet=True)
    return peeked_metadata, peeked_config, peeked_path


def _with_config(
    resolved: tuple[ProjectMetadata, PitloomConfig, Path | None],
    explicit_config: PitloomConfig | None,
) -> tuple[ProjectMetadata, PitloomConfig, Path | None]:
    """*resolved* with its config replaced by *explicit_config*, if given."""
    if explicit_config is None:
        return resolved
    metadata, _, path = resolved
    return metadata, explicit_config, path


__all__ = [
    "read_project",
    "resolve_project_with_lockfile",
]
