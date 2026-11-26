# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``credentials-unsafe`` messages (the reference page "URL
credentials", ``url-credentials`` in
:data:`~pitloom.messages.TOPIC_TITLES`, the Git variants included): a URL
value of the SBOM that holds
a credential, written in the ``warn`` mode (:func:`say_written`) or refused
in the ``refuse`` mode (:func:`say_refused`, :func:`refused_error`), a value
accepted (:func:`say_accepted`) or that may be one only (:func:`say_weak`);
the errors for a registry key or namespace that holds one, the warnings for
a key stored and an element skipped for one, and a registry file refused or
loaded as it is (:func:`registry_file_refused_error`,
:func:`warn_registry_file_entry_kept`); a fingerprint that accepts nothing
(:func:`say_stale_fingerprint`).

See also: :mod:`pitloom.messages._url_credentials` (the entries) and
:mod:`pitloom.messages.url_credentials_git` (the Git variants).
"""

from __future__ import annotations

import functools
import logging
import os

from pitloom.core.internal_error import InternalError
from pitloom.core.url_masking import masked_given_path
from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._options import (
    MODE_UNREAD_LINE,
    OPTION_NO_EFFECT,
    STALE_FINGERPRINT_LINE,
)
from pitloom.messages._surface import SURFACE_CLI, SURFACE_HOOK, current_surface
from pitloom.messages._url_credentials import (
    ACCEPT_OPTION,
    ACCEPT_SETTING,
    ACCEPTED_LINE,
    CREDENTIALS_UNSAFE,
    CREDENTIALS_UNSAFE_ACCEPTED,
    CREDENTIALS_UNSAFE_REFUSED,
    CREDENTIALS_UNSAFE_REGISTRY,
    CREDENTIALS_UNSAFE_WRITTEN,
    KEY_KEPT_LINE,
    KEY_LINE,
    KEY_SKIPPED_LINE,
    MODE_SETTING,
    NAMESPACE_CREDENTIALS_LINE,
    REFUSE_OPTION,
    REFUSED_CONFIG_LINE,
    REFUSED_COUNT_LINE,
    REFUSED_LIBRARY_LINE,
    REFUSED_LINE,
    REGISTRY_FILE_KEPT_LINE,
    REGISTRY_FILE_REFUSED_LINE,
    WEAK_LINE,
    WRITTEN_CONFIG_LINE,
    WRITTEN_LIBRARY_LINE,
    WRITTEN_LINE,
)
from pitloom.messages._url_credentials_git import (
    CREDENTIALS_UNSAFE_GIT_LINE_BREAK,
    CREDENTIALS_UNSAFE_GIT_USERINFO,
    CREDENTIALS_UNSAFE_HTTP_CLEAR,
    GIT_LINE_BREAK_LINE,
    GIT_USERINFO_LINE,
    HTTP_CLEAR_LINE,
)

__all__ = [
    "CREDENTIALS_UNSAFE",
    "CREDENTIALS_UNSAFE_ACCEPTED",
    "CREDENTIALS_UNSAFE_GIT_LINE_BREAK",
    "CREDENTIALS_UNSAFE_GIT_USERINFO",
    "CREDENTIALS_UNSAFE_HTTP_CLEAR",
    "CREDENTIALS_UNSAFE_REFUSED",
    "CREDENTIALS_UNSAFE_REGISTRY",
    "CREDENTIALS_UNSAFE_WRITTEN",
    "GIT_LINE_BREAK_LINE",
    "GIT_USERINFO_LINE",
    "HTTP_CLEAR_LINE",
    "refused_error",
    "registry_file_refused_error",
    "registry_key_credentials_error",
    "registry_namespace_credentials_error",
    "say_accepted",
    "say_refused",
    "say_stale_fingerprint",
    "say_weak",
    "say_written",
    "warn_registry_file_entry_kept",
    "warn_registry_key_credentials_skipped",
    "warn_registry_key_kept",
]

#: Where the helpers that take no logger say their lines.
_log = logging.getLogger(__name__)


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


def warn_registry_key_kept(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log*, once per *url* (masked here) and
    process, that the registry key *url* is stored as written (the ``warn``
    mode)."""
    shown = masked_given_path(url)
    emit(
        log,
        CREDENTIALS_UNSAFE_REGISTRY,
        logging.WARNING,
        line=KEY_KEPT_LINE,
        once=f"{CREDENTIALS_UNSAFE_REGISTRY.code}:kept:{url}",
        url=shown,
    )


def warn_registry_file_entry_kept(
    log: logging.Logger, file: str | os.PathLike[str], key: str
) -> None:
    """The one ``WARNING:`` on *log*, once per *file*, *key* (masked here)
    and process, that the ID registry *file* is loaded with the entry whose
    key or id *key* holds a credential (the ``warn`` mode)."""
    emit(
        log,
        CREDENTIALS_UNSAFE_REGISTRY,
        logging.WARNING,
        line=REGISTRY_FILE_KEPT_LINE,
        once=f"{CREDENTIALS_UNSAFE_REGISTRY.code}:file:{os.fspath(file)}:{key}",
        url=masked_given_path(key),
        path=file,
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
    the value, and the *fingerprint* that would accept it, the way the
    surface that runs accepts it
    (:func:`~pitloom.messages.advice_surface`). Said every
    time, never once per process: each refused run names each value. The
    caller raises :func:`refused_error` after the last one.

    Raises:
        ValueError: *fingerprint* is not ``sha256:`` and 16 to 64 lower-case
            hex digits.
    """
    shown = masked_given_path(url)
    at = masked_given_path(pointer)
    surface = current_surface()
    if surface == SURFACE_CLI:
        emit(
            _log,
            CREDENTIALS_UNSAFE_REFUSED,
            logging.ERROR,
            line=REFUSED_LINE,
            url=shown,
            element=element,
            pointer=at,
            fingerprint=fingerprint,
            option=ACCEPT_OPTION,
        )
    elif surface == SURFACE_HOOK:
        emit(
            _log,
            CREDENTIALS_UNSAFE_REFUSED,
            logging.ERROR,
            line=REFUSED_CONFIG_LINE,
            url=shown,
            element=element,
            pointer=at,
            fingerprint=fingerprint,
            setting=ACCEPT_SETTING,
        )
    else:
        emit(
            _log,
            CREDENTIALS_UNSAFE_REFUSED,
            logging.ERROR,
            line=REFUSED_LIBRARY_LINE,
            url=shown,
            element=element,
            pointer=at,
            fingerprint=fingerprint,
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


def say_written(url: str, element: str, pointer: str, fingerprint: str) -> None:
    """The ``WARNING:``, ``credentials-unsafe/written``, that the SBOM
    states the URL-typed value
    *url* (shown masked), which holds a credential, as written (the ``warn``
    mode): the element *element* (its spdxId, masked) and its field
    *pointer* that hold it, its *fingerprint*, and how the surface that runs
    turns the ``refuse`` mode on
    (:func:`~pitloom.messages.advice_surface`). Said every
    time, never once per process: each SBOM that holds the value names it
    (the check says each distinct value of one SBOM once).

    Raises:
        ValueError: *fingerprint* is not ``sha256:`` and 16 to 64 lower-case
            hex digits.
    """
    say = functools.partial(
        emit,
        _log,
        CREDENTIALS_UNSAFE_WRITTEN,
        logging.WARNING,
        url=masked_given_path(url),
        element=element,
        pointer=masked_given_path(pointer),
        fingerprint=fingerprint,
    )
    surface = current_surface()
    if surface == SURFACE_CLI:
        say(line=WRITTEN_LINE, option=REFUSE_OPTION)
    elif surface == SURFACE_HOOK:
        say(line=WRITTEN_CONFIG_LINE, setting=MODE_SETTING)
    else:
        say(line=WRITTEN_LIBRARY_LINE)


def say_accepted(url: str, fingerprint: str) -> None:
    """The ``WARNING:`` that the SBOM states *url* (shown masked), which
    holds a credential, as written: accepted by *fingerprint*, in either
    mode. Said every time, as :func:`say_written` is."""
    emit(
        _log,
        CREDENTIALS_UNSAFE_ACCEPTED,
        logging.WARNING,
        line=ACCEPTED_LINE,
        url=masked_given_path(url),
        fingerprint=fingerprint,
    )


def say_weak(url: str) -> None:
    """The ``WARNING:`` that the SBOM states *url* (shown masked) as written
    though it holds what may be a credential only (a weak
    :class:`~pitloom.core.url_masking.Finding`: a parameter of a weak name,
    an accepted ssh or git account name). Said every time, as
    :func:`say_written` is."""
    emit(
        _log,
        CREDENTIALS_UNSAFE,
        logging.WARNING,
        line=WEAK_LINE,
        url=masked_given_path(url),
    )


def registry_file_refused_error(
    file: str | os.PathLike[str], key: str
) -> CodedValueError:
    """The error for the ID registry *file* (quoted) not loaded because the
    key or id *key* (shown masked) of an entry holds a credential. The
    caller raises it ``from None``."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_REGISTRY,
        line=REGISTRY_FILE_REFUSED_LINE,
        url=masked_given_path(key),
        path=file,
    )


def say_mode_unread(project: os.PathLike[str], failure: Exception) -> None:
    """The one ``WARNING:``, ``option-no-effect``, that the config of the
    project directory *project* could not be read, for *failure* (the
    exception: its text, credentials masked, on one line), so its
    ``url-credentials`` is not applied and the ``warn`` mode is used (``loom
    id`` with ``-o`` and ``--project-dir``). Said once per run: the run
    resolves its mode once."""
    emit(
        _log,
        OPTION_NO_EFFECT,
        logging.WARNING,
        line=MODE_UNREAD_LINE,
        dir=project,
        failure=failure,
        option=REFUSE_OPTION,
    )


def say_stale_fingerprint(fingerprint: str, document: str) -> None:
    """The one ``WARNING:``, ``option-no-effect``, once per *fingerprint*,
    *document* and process, that the accepted *fingerprint* matches no URL
    value of the SBOM *document* (its ``SpdxDocument``'s id, masked): a
    batch names each SBOM it holds for."""
    emit(
        _log,
        OPTION_NO_EFFECT,
        logging.WARNING,
        line=STALE_FINGERPRINT_LINE,
        once=f"{OPTION_NO_EFFECT.code}:{fingerprint}:{document}",
        fingerprint=fingerprint,
        element=document,
    )
