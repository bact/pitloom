# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``credentials-unsafe`` messages: the refusal of an SBOM whose URL
values hold a credential (:func:`say_refused`, :func:`refused_error`), a
value accepted (:func:`say_accepted`) or that may be one only
(:func:`say_weak`); the errors for a registry key or namespace that holds
one, the warning for an element the registry skips for one, and a registry
file refused (:func:`registry_file_refused_error`); a fingerprint that
accepts nothing (:func:`say_stale_fingerprint`) and a setting a file cannot
set (:func:`say_config_cli_only`).

See also: :mod:`pitloom.messages._url_credentials` (the entries) and
:mod:`pitloom.messages.url_credentials_git` (the Git variants).
"""

from __future__ import annotations

import logging
import os

from pitloom.core.internal_error import InternalError
from pitloom.core.url_masking import masked_given_path
from pitloom.messages._config_unsafe import CONFIG_UNSAFE_CLI_ONLY
from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._options import OPTION_NO_EFFECT, STALE_FINGERPRINT_LINE
from pitloom.messages._url_credentials import (
    ACCEPT_OPTION,
    ACCEPTED_LINE,
    ALLOW_OPTION,
    ALLOWED_LINE,
    CREDENTIALS_UNSAFE,
    CREDENTIALS_UNSAFE_ACCEPTED,
    CREDENTIALS_UNSAFE_REFUSED,
    CREDENTIALS_UNSAFE_REGISTRY,
    KEY_LINE,
    KEY_SKIPPED_LINE,
    NAMESPACE_CREDENTIALS_LINE,
    REFUSED_COUNT_LINE,
    REFUSED_LINE,
    REGISTRY_FILE_REFUSED_LINE,
    WEAK_LINE,
)

__all__ = [
    "CREDENTIALS_UNSAFE",
    "CREDENTIALS_UNSAFE_ACCEPTED",
    "CREDENTIALS_UNSAFE_REFUSED",
    "CREDENTIALS_UNSAFE_REGISTRY",
    "refused_error",
    "registry_file_refused_error",
    "registry_key_credentials_error",
    "registry_namespace_credentials_error",
    "say_accepted",
    "say_config_cli_only",
    "say_refused",
    "say_stale_fingerprint",
    "say_weak",
    "warn_registry_key_credentials_skipped",
]

#: Where the helpers that take no logger say their lines.
_log = logging.getLogger(__name__)


def _once(url: str) -> str:
    return f"{CREDENTIALS_UNSAFE.code}:{url}"


def warn_registry_key_credentials_skipped(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log* that an SBOM element with the registry
    key or id *url* (masked here) is left out of the ID registry."""
    shown = masked_given_path(url)
    emit(
        log,
        CREDENTIALS_UNSAFE_REGISTRY,
        logging.WARNING,
        line=KEY_SKIPPED_LINE,
        once=f"{CREDENTIALS_UNSAFE_REGISTRY.code}:{shown}",
        url=shown,
    )


def registry_key_credentials_error(url: str) -> CodedValueError:
    """The error for a registry key *url* that holds credentials, shown
    masked."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_REGISTRY, line=KEY_LINE, url=masked_given_path(url)
    )


def registry_namespace_credentials_error(namespace: str) -> CodedValueError:
    """The error for a registry *namespace* that holds credentials, shown
    masked."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_REGISTRY,
        line=NAMESPACE_CREDENTIALS_LINE,
        url=masked_given_path(namespace),
    )


def say_refused(url: str, element: str, pointer: str, fingerprint: str) -> None:
    """The ``ERROR:`` line, ``credentials-unsafe/refused``, for one URL-typed
    value *url* (shown masked) of the SBOM that holds a credential: the
    element *element* (its spdxId, masked) and its field *pointer* that hold
    the value, and the *fingerprint* that would accept it. Said every time,
    never once per process: each refused run names each value. The caller
    raises :func:`refused_error` after the last one.

    Raises:
        ValueError: *fingerprint* is not ``sha256:`` and 16 to 64 lower-case
            hex digits.
    """
    emit(
        _log,
        CREDENTIALS_UNSAFE_REFUSED,
        logging.ERROR,
        line=REFUSED_LINE,
        url=masked_given_path(url),
        element=element,
        pointer=masked_given_path(pointer),
        fingerprint=fingerprint,
        option=ACCEPT_OPTION,
    )


def refused_error(count: int) -> CodedValueError:
    """The closing error of an SBOM refused for *count* URL values that hold
    credentials (each said by :func:`say_refused`); its text names no URL.
    The caller raises it ``from None``.

    Raises:
        pitloom.core.internal_error.InternalError: *count* is not a whole
            number of 1 or more.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise InternalError(f"credentials-unsafe/refused for {count!r} values")
    return CodedValueError(
        CREDENTIALS_UNSAFE_REFUSED, line=REFUSED_COUNT_LINE, number=count
    )


def say_accepted(url: str, fingerprint: str | None) -> None:
    """The one ``WARNING:``, once per *url*, *fingerprint* and process, that
    the SBOM states *url* (shown masked), which holds a credential, as
    written: accepted by *fingerprint*, or, ``None``, by
    ``--allow-url-credentials``."""
    shown = masked_given_path(url)
    once = f"{CREDENTIALS_UNSAFE_ACCEPTED.code}:{fingerprint}:{url}"
    if fingerprint is None:
        emit(
            _log,
            CREDENTIALS_UNSAFE_ACCEPTED,
            logging.WARNING,
            line=ALLOWED_LINE,
            once=once,
            url=shown,
            option=ALLOW_OPTION,
        )
    else:
        emit(
            _log,
            CREDENTIALS_UNSAFE_ACCEPTED,
            logging.WARNING,
            line=ACCEPTED_LINE,
            once=once,
            url=shown,
            fingerprint=fingerprint,
        )


def say_weak(url: str) -> None:
    """The one ``WARNING:``, once per *url* and process, that the SBOM states
    *url* (shown masked) as written though it holds what may be a credential
    only (a weak :class:`~pitloom.core.url_masking.Finding`: a parameter of
    a weak name, an accepted ssh or git account name)."""
    emit(
        _log,
        CREDENTIALS_UNSAFE,
        logging.WARNING,
        line=WEAK_LINE,
        once=f"{_once(url)}:weak",
        url=masked_given_path(url),
    )


def registry_file_refused_error(
    file: str | os.PathLike[str], key: str
) -> CodedValueError:
    """The error for the ID registry *file* not loaded because the key or
    id *key* (shown masked) of an entry holds a credential. The caller
    raises it ``from None``."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_REGISTRY,
        line=REGISTRY_FILE_REFUSED_LINE,
        url=masked_given_path(key),
        file=file,
    )


def say_stale_fingerprint(fingerprint: str) -> None:
    """The one ``WARNING:``, ``option-no-effect``, once per *fingerprint* and
    process, that the accepted *fingerprint* matches no URL value of this
    SBOM."""
    emit(
        _log,
        OPTION_NO_EFFECT,
        logging.WARNING,
        line=STALE_FINGERPRINT_LINE,
        once=f"{OPTION_NO_EFFECT.code}:{fingerprint}",
        fingerprint=fingerprint,
    )


def say_config_cli_only(key: str, *, table: str = "[tool.pitloom]") -> None:
    """The one ``WARNING:``, ``config-unsafe/cli-only``, once per *key*,
    *table* and process, that the setting *key* of *table*
    (``[tool:pitloom]`` for ``setup.cfg``) is ignored: only the command line
    takes it."""
    emit(
        _log,
        CONFIG_UNSAFE_CLI_ONLY,
        logging.WARNING,
        once=f"{CONFIG_UNSAFE_CLI_ONLY.code}:{table}:{key}",
        setting=key,
        table=table,
    )
