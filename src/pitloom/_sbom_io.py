# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Write SBOM text with ``\\n`` line endings and UTF-8, on every platform.

Text mode translates ``\\n`` to ``\\r\\n`` on Windows, so the same SBOM would
have different bytes there -- and a Windows console's code page may not
encode it at all. Every SBOM, fragment or registry file Pitloom writes goes
through here.

See also: :mod:`tests.test_sbom_io` (the guard that no other text write
appears in ``src/``).
"""

from __future__ import annotations

import contextlib
import errno
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import TextIO

#: The ``-o`` value that means "write to standard output".
STDOUT = "-"


def is_stdout(output_path: Path | str | None) -> bool:
    """Whether *output_path* is ``-``: the SBOM is then all of stdout, so no
    data line may follow it there."""
    return output_path is not None and str(output_path) == STDOUT


def open_text_lf(path: Path | str | int) -> TextIO:
    """Open *path* (or an open file descriptor, which the result then owns)
    for writing UTF-8 text with ``\\n`` line endings."""
    return open(path, "w", encoding="utf-8", newline="\n")  # noqa: SIM115


def write_text_lf(path: Path | str, text: str) -> None:
    """Write *text* to *path* as UTF-8 with ``\\n`` line endings."""
    with open_text_lf(path) as f:
        f.write(text)


def replace_text_lf(path: Path | str, text: str) -> None:
    """Write *text* to *path* as :func:`write_text_lf` does, atomically: into
    a new file beside it, then :func:`os.replace` over it, so a reader never
    sees part of either version.

    A symlink at *path* keeps pointing at the replaced file, which keeps its
    permission bits; a new file gets the umask's, as with ``open()``. A file
    this process may not write raises ``PermissionError``, as ``open()``
    would: replacing its directory entry would bypass its mode. The
    temporary name is random, created exclusively and written through that
    one descriptor, so two processes never write one file; on failure it is
    removed and *path* is left as it was.

    A directory that refuses the temporary file (read-only, while the file
    in it is writable) gets the file written in place instead, as
    :func:`write_text_lf` does; with no file there, the ``PermissionError``
    names *path*, never the temporary file.
    """
    target = os.path.realpath(path)
    if os.path.exists(target) and not os.access(target, os.W_OK):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(path))
    directory, name = os.path.split(target)
    temp = os.path.join(directory, f".{name}.{secrets.token_hex(8)}.tmp")
    # O_BINARY: a Windows descriptor is text mode by default, adding CRs.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(temp, flags, 0o666)
    except PermissionError as exc:
        if not os.path.isfile(target):
            raise PermissionError(exc.errno, exc.strerror, str(path)) from exc
        # Not atomic: a reader may see the file truncated or part-written.
        write_text_lf(target, text)
        return
    try:
        with open_text_lf(descriptor) as f:
            f.write(text)
        with contextlib.suppress(FileNotFoundError):
            os.chmod(temp, stat.S_IMODE(os.stat(target).st_mode))
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def write_stdout_lf(text: str) -> None:
    """Write *text* to standard output as UTF-8 bytes, ending in exactly one
    trailing ``\\n`` if it had none, whatever the console's encoding and
    newline translation."""
    data = text if text.endswith("\n") else f"{text}\n"
    sys.stdout.flush()
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:  # a text-only replacement stream, e.g. io.StringIO
        sys.stdout.write(data)
        return
    buffer.write(data.encode("utf-8"))
    buffer.flush()


def write_sbom_output(sbom_json: str, output_path: Path | str | None) -> None:
    """Write an SBOM to *output_path*, to standard output for ``-``, or
    nowhere for ``None``."""
    if output_path is None:
        return
    if is_stdout(output_path):
        write_stdout_lf(sbom_json)
    else:
        write_text_lf(output_path, sbom_json)


__all__ = [
    "STDOUT",
    "is_stdout",
    "open_text_lf",
    "replace_text_lf",
    "write_sbom_output",
    "write_stdout_lf",
    "write_text_lf",
]
