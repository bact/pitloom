# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project's TOML file loaded for a use, every failure a coded
:class:`~pitloom.messages.CodedValueError` (or, for a file not there, a
:class:`~pitloom.messages.CodedFileNotFoundError`): one except chain for a
file on disk (:func:`load_project_toml`) and for an archive member's bytes
(:func:`load_project_toml_bytes`), and the UTF-8 decoding of a member read
as text (:func:`decode_member_text`).

:mod:`pitloom._toml_io` stays raw: it leaves the exception policy to its
callers, and this module is that policy for every caller that raises.

See also: :mod:`pitloom.core.config_cascade` (a ``--config`` file) and
:mod:`pitloom.extract.project` (the project readers).
"""

from __future__ import annotations

import os
from pathlib import Path

from pitloom._toml_io import TOMLDecodeError, load_toml_bytes, load_toml_file
from pitloom.messages import CodedValueError
from pitloom.messages.config import CONFIG_MALFORMED, TOML_LINE
from pitloom.messages.files import file_unreadable_error
from pitloom.messages.targets import input_not_found, is_input_file

__all__ = ["decode_member_text", "load_project_toml", "load_project_toml_bytes"]


def load_project_toml(
    path: str | os.PathLike[str], *, kind: str, use: str
) -> dict[str, object]:
    """*path* parsed as TOML, read for *use* (one of
    :data:`~pitloom.messages.READ_USES`); *kind* (one of
    :data:`~pitloom.messages.INPUT_KINDS`) names it when it is not there.
    Every line names *path* as given.

    Raises:
        FileNotFoundError: *path* is not a regular file (missing, a
            directory, or gone since the check): ``input-not-found``.
        ValueError: the file is not UTF-8 (``file-unreadable/not-utf8``),
            not valid TOML (``config-malformed``) or cannot be read
            (``file-unreadable``).
    """
    if not is_input_file(path):
        raise input_not_found(kind, path)
    # Order matters: a TOMLDecodeError and a UnicodeDecodeError are both
    # ValueErrors; a file gone since the check is not "unreadable".
    try:
        return load_toml_file(Path(path))
    except FileNotFoundError:
        raise input_not_found(kind, path) from None
    except TOMLDecodeError as exc:
        raise _malformed(path, exc) from None
    except (UnicodeDecodeError, OSError) as exc:
        raise file_unreadable_error(exc, file=path, use=use) from None
    except (ValueError, RecursionError) as exc:
        # Not a TOMLDecodeError: an integer over Python's digit limit, or
        # arrays nested past the parser's depth limit.
        raise _malformed(path, exc) from None


def load_project_toml_bytes(raw: bytes, *, file: str, use: str) -> dict[str, object]:
    """*raw*, an archive member's bytes, parsed as TOML, as
    :func:`load_project_toml` parses a file, read for *use*; *file* names
    it (``demo-1.0.tar.gz:pyproject.toml``).

    Raises:
        ValueError: the bytes are not UTF-8 (``file-unreadable/not-utf8``)
            or not valid TOML (``config-malformed``).
    """
    # Order as load_project_toml: both decode errors are ValueErrors.
    try:
        return load_toml_bytes(raw)
    except TOMLDecodeError as exc:
        raise _malformed(file, exc) from None
    except UnicodeDecodeError as exc:
        raise file_unreadable_error(exc, file=file, use=use) from None
    except (ValueError, RecursionError) as exc:
        raise _malformed(file, exc) from None


def decode_member_text(raw: bytes, *, file: str, use: str) -> str:
    """*raw*, an archive member's bytes, as strict UTF-8 text, read for
    *use*; *file* names it (``demo-1.0.tar.gz:setup.cfg``).

    Raises:
        ValueError: the bytes are not UTF-8 (``file-unreadable/not-utf8``).
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise file_unreadable_error(exc, file=file, use=use) from None


def _malformed(file: str | os.PathLike[str], exc: BaseException) -> CodedValueError:
    """The ``config-malformed`` error for *file*, whose TOML *exc* stopped."""
    return CodedValueError(CONFIG_MALFORMED, line=TOML_LINE, file=file, failure=exc)
