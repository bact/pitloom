# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` shape for an explicit option that has no effect.

Every "has no effect" warning -- a build flag without ``--allow-build``, an
option the target cannot act on (``--use-lockfile`` for a non-project
target included) -- is logged here, so the wording cannot drift between subsystems:

``WARNING: Options: <subject>: <flag> has no effect <reason> [option-no-effect]``
(``Build: `` for a build flag)

The catalogue owns the text (:func:`pitloom.messages.options.warn_option_no_effect`).

No leading underscore: imported from ``pitloom.cli`` as well as from
within ``pitloom.core``.

See also: :mod:`pitloom.core.build_options` and
:mod:`pitloom.core.inert_options`, the two callers that decide *which*
flags to warn about.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from pitloom.core.url_masking import sanitize_url, sanitize_url_credentials
from pitloom.messages.options import OPTIONS_PREFIX, warn_option_no_effect

log = logging.getLogger(__name__)

INERT_LOG_PREFIX = OPTIONS_PREFIX
"""Sub-prefix for an option the target or command cannot act on -- sibling
of :data:`pitloom.core._models_wheel_types.BUILD_LOG_PREFIX`. It is the
catalogue's :data:`pitloom.messages.options.OPTIONS_PREFIX`, which the
``option-no-effect`` lines are built from; this name is for the other
``Options:`` lines and for readers matching them."""


def warn_no_effect(
    subject: object,
    flags: Iterable[str],
    reason: str,
    *,
    build: bool = False,
    level: int = logging.WARNING,
) -> None:
    """Log one ``WARNING:`` per flag in *flags*, in the given order; with
    *level* ``logging.INFO``, an ``INFO:`` (a config key the surface never
    acts on, as opposed to a flag the user gave on its command line).

    *reason* follows "has no effect" with no trailing punctuation, e.g.
    ``"without --allow-build"``.

    *subject* may be a user-given URL or path: credentials are masked here,
    and the line's ``name`` field escapes a control character. *build*: a
    build flag (``Build: ``), else an option the target or command cannot
    act on (``Options: ``).

    Raises:
        pitloom.core.internal_error.InternalError: *level* ``logging.INFO``
            with *build*, or neither ``WARNING`` nor ``INFO``
            (:func:`~pitloom.messages.options.warn_option_no_effect`).
    """
    text = str(subject)
    shown = sanitize_url(text) if "://" in text else sanitize_url_credentials(text)
    for flag in flags:
        warn_option_no_effect(
            log,
            build=build,
            subject=shown,
            option=flag,
            when=reason,
            level=level,
        )


__all__ = ["INERT_LOG_PREFIX", "warn_no_effect"]
