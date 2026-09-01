# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``INFO:``/``WARNING:``/``ERROR:`` log-message formatting.

See also: :mod:`pitloom.__main__` (the ``loom`` CLI entry point),
:mod:`pitloom.plugins.hatch` (the Hatchling build-hook entry point), and
every public generator/enrich function in :mod:`pitloom.assemble` (the
library API) -- all call :func:`configure_logging` so ``log.info(...)``/
``log.warning(...)`` output looks the same regardless of which entry
point invoked Pitloom.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

# Guards the handlers.clear()/addHandler() swap below (see
# configure_logging()'s docstring) and the _WARNED_ONCE read-then-write in
# warn_once() -- one lock for all shared mutable state in this module.
_CONFIG_LOCK = threading.Lock()

# The environment variable a bare configure_logging() (debug=None)
# falls back to -- see apply_debug_override()'s docstring for why every
# no-argument call site needs to agree on the same source of truth.
PITLOOM_DEBUG_ENV_VAR = "PITLOOM_DEBUG"

# Truthy values for the PITLOOM_DEBUG opt-in below; anything else
# (including unset) leaves DEBUG suppressed.
_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: Keys already surfaced once via :func:`warn_once` in this process.
#: Keyed by ``(logger.name, key)`` so two independent call sites can't
#: collide by picking the same short key string.
_WARNED_ONCE: set[tuple[str, str]] = set()


def _debug_requested(debug: bool | None) -> bool:
    """Resolve the effective debug flag: an explicit ``debug`` argument
    wins; ``None`` falls back to the ``PITLOOM_DEBUG`` environment
    variable, so entry points that don't parse CLI flags themselves
    (the Hatchling hook, every public library-API generator) still get
    the opt-in for free."""
    if debug is not None:
        return debug
    return os.environ.get(PITLOOM_DEBUG_ENV_VAR, "").strip().lower() in _TRUTHY


def apply_debug_override(debug: bool | None) -> None:
    """Normalize an explicit debug choice (the CLI's ``--debug``/
    ``--no-debug``) into the ``PITLOOM_DEBUG`` environment variable, so
    it stays the effective choice for the rest of the process.

    Every public generator (``generate_project_sbom()`` and friends, the
    Hatchling build hook, ``merge_fragments()``) calls bare
    ``configure_logging()`` internally -- ``debug=None`` -- to (re)apply
    the shared ``INFO:``/``WARNING:``/``ERROR:`` formatting before doing
    its own work. Each of those calls independently falls back to
    ``PITLOOM_DEBUG`` (see :func:`_debug_requested`); without this
    function, a CLI-only ``debug=True`` passed to the *first*
    ``configure_logging()`` call (in ``__main__.main()``) would be
    silently discarded by the *next* one, reverting to ``INFO`` unless
    ``PITLOOM_DEBUG`` also happened to be set -- ``loom --debug
    project .`` would look like it worked (the top-level logger briefly
    goes to ``DEBUG``) but produce no ``DEBUG:`` output once
    ``generate_project_sbom()`` reconfigures it. Routing the CLI's
    choice through the same environment variable every call site already
    consults makes every subsequent bare ``configure_logging()`` agree,
    with no signature changes needed at any of those call sites.
    ``debug=None`` (``--debug`` omitted) leaves ``PITLOOM_DEBUG`` as the
    caller found it -- an ambient environment setting is respected, not
    overwritten with an implicit "off". ``debug=False`` (``--no-debug``)
    sets the variable to ``"0"`` rather than unsetting it, so it stays
    distinguishable from "never configured" for anything downstream (a
    subprocess pitloom shells out to, another `PITLOOM_DEBUG` reader) that
    treats the two states differently.

    This mutates ``os.environ`` for the remaining lifetime of the current
    process -- correct for the CLI, which runs once per process and exits.
    A caller that invokes :func:`pitloom.__main__.main` or a public
    generator more than once in one long-lived process (a wrapper script,
    a test harness) and wants one invocation's ``--debug``/``--no-debug``
    choice to not leak into the next must save
    ``os.environ.get(PITLOOM_DEBUG_ENV_VAR)`` before calling this and
    restore it (or delete the key if it was absent) afterward.
    ``apply_debug_override(False)`` does **not** do this for you -- it
    sets an explicit, equally permanent ``"0"``, it does not restore
    whatever ambient value was there before."""
    if debug is None:
        return
    os.environ[PITLOOM_DEBUG_ENV_VAR] = "1" if debug else "0"


def configure_logging(*, debug: bool | None = None) -> None:
    """Prefix internal ``log.info(...)``/``log.warning(...)`` output with
    ``INFO: ``/``WARNING: ``.

    Without this, Python's last-resort handler either drops ``INFO``
    records entirely (the root logger's default effective level is
    ``WARNING``) or, for ``WARNING``, prints them to stderr with no
    prefix at all -- both break the shared grep-able ``LEVEL:
    <description>`` convention (see ``ERROR:``, used by the CLI's own
    ``print()`` calls) documented in ``CLAUDE.md``'s "CLI output"
    section. ``DEBUG`` stays suppressed unless opted into: pass
    ``debug=True``/``debug=False`` for an explicit choice made by the
    caller itself, or leave ``debug`` at its default ``None`` to fall
    back to the ``PITLOOM_DEBUG`` environment variable
    (``1``/``true``/``yes``/``on``, case-insensitive). The CLI itself
    always calls this with no arguments; see :func:`apply_debug_override`'s
    docstring for how ``--debug``/``--no-debug`` reach it (and every other
    bare ``configure_logging()`` call downstream) via ``PITLOOM_DEBUG``
    instead of a direct ``debug=`` argument. When enabled,
    ``log.debug(...)`` records get the same ``%(levelname)s: `` prefix as
    ``INFO``/``WARNING``, i.e. ``DEBUG: <message>`` -- still a developer
    diagnostic, not one of ``CLAUDE.md``'s three normal-invocation
    levels, but consistently formatted when a caller asks to see it.
    Reconfigures on every call rather than guarding with a "configured
    once" flag, so repeated calls in the same process (e.g. across
    tests, or a build tool invoking the Hatchling hook more than once)
    don't stack duplicate handlers. The new handler is built first and
    ``logger.handlers`` is replaced with a whole new list in one
    assignment (never cleared-then-appended in place), so a concurrent
    ``log.warning(...)``/``log.info(...)`` call on another thread always
    sees either the fully-old or fully-new handler list -- never an
    empty one mid-swap -- without needing to lock log emission itself.
    A module-level lock still serializes the reconfiguration itself, so
    two threads each calling this at once can't race on ``setLevel()``
    or leave the logger in a state neither call intended. Propagation to
    the root logger is left untouched, so ``pytest``'s ``caplog``
    fixture still captures these records; a host application that
    already configures its own root logging may then see pitloom's
    ``INFO:``/``WARNING:`` lines twice (once via this handler, once via
    its own root handler) -- disabling propagation would fix that but
    silently break every test in this suite that captures pitloom's log
    output via bare ``caplog.at_level(...)`` (implicitly root-scoped),
    so it stays as a documented tradeoff rather than a silent one.
    """
    level = logging.DEBUG if _debug_requested(debug) else logging.INFO
    logger = logging.getLogger("pitloom")
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    with _CONFIG_LOCK:
        logger.setLevel(level)
        logger.handlers = [handler]


def warn_once(log: logging.Logger, key: str, msg: str, *args: object) -> None:
    """Log *msg* at WARNING the first time *key* fires on *log* in this
    process, DEBUG on every later occurrence.

    Protects a caller that runs the same fallible check on every
    iteration of a loop (e.g. once per :mod:`pitloom.loom` call in a
    training run) from flooding stderr when the underlying condition is
    persistent rather than one-off. Every occurrence after the first is
    a real, separate instance of the same problem -- demoting it to
    ``DEBUG`` (silent in a normal invocation, per ``CLAUDE.md``'s "CLI
    output" section) trades "no silent deviations" for "no unbounded
    spam" on purpose: a user who wants to know it is *still* failing on
    call #10,000 can rerun with ``--debug``, but a default run isn't
    flooded by a condition that, once known, adds nothing by repeating.
    A documented tradeoff, not a silent one.

    *key* is scoped by ``log.name`` internally, so two unrelated call
    sites picking the same short key string (e.g. ``"version"``) can't
    silently suppress each other's first occurrence.
    """
    dedup_key = (log.name, key)
    with _CONFIG_LOCK:
        first_occurrence = dedup_key not in _WARNED_ONCE
        _WARNED_ONCE.add(dedup_key)
    log.log(logging.WARNING if first_occurrence else logging.DEBUG, msg, *args)
