# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Where a ``setup.cfg`` key lives, and what a bad ``%`` in its value is.

setuptools (``Distribution.parse_config_files``, 84.0.0) and pbr read
``setup.cfg`` with :class:`configparser.ConfigParser`, whose
``BasicInterpolation`` makes ``%`` syntax: ``50% faster`` fails their own
build, so Pitloom reads it the same way and fails too, naming the section,
the key and the ``%%`` escape. ``$`` is not special.

See also: :mod:`pitloom.extract.project.setuptools_cfg`.
"""

from __future__ import annotations

import configparser

from pitloom.logging_config import loggable, one_line

#: What every interpolation error says, and the fix for a stray '%' only: a
#: missing key or a reference cycle is not mended by '%%'.
_FAILS_TOO = "setuptools fails on it too"
_PERCENT_FIX = "; write a literal '%' as '%%'"


def section_declares_key(
    cfg: configparser.ConfigParser, section: str, key: str
) -> bool:
    """Return whether *section* itself declares *key*, ignoring any value
    only inherited from ``[DEFAULT]``.

    ``cfg.items(section)`` merges in ``[DEFAULT]``, so a shared value would
    make every section look as if it declared the key. ``cfg._sections``
    holds each section's own keys; the public API has no such accessor.
    """
    # pylint: disable-next=protected-access
    sections: dict[str, dict[str, str]] = cfg._sections  # type: ignore[attr-defined]
    return key in sections.get(section, {})


def interpolation_problem(
    cfg: configparser.ConfigParser, exc: configparser.InterpolationError
) -> str:
    """One line for *exc*, raised reading a value of *cfg*: ``[section]
    key: <what is wrong>; <the fix>``. A value inherited from ``[DEFAULT]``
    names ``[DEFAULT]``, where it is written."""
    section = exc.section
    # *exc* may come from a case-keeping copy of *cfg* (extras' markers).
    if not section_declares_key(cfg, section, cfg.optionxform(exc.option)):
        section = configparser.DEFAULTSECT
    fix = ""
    if isinstance(exc, configparser.InterpolationMissingOptionError):
        reason = f"%({exc.reference})s names no key of [{exc.section}] or [DEFAULT]"
    elif isinstance(exc, configparser.InterpolationDepthError):
        reason = (
            f"%(...)s references nest deeper than "
            f"{configparser.MAX_INTERPOLATION_DEPTH} levels"
        )
    else:
        reason = exc.message
        fix = _PERCENT_FIX
    where = loggable(f"[{section}] {exc.option}")
    return f"{where}: {one_line(reason)}; {_FAILS_TOO}{fix}"
