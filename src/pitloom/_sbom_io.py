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

import sys
from pathlib import Path
from typing import TextIO

#: The ``-o`` value that means "write to standard output".
STDOUT = "-"


def is_stdout(output_path: Path | str | None) -> bool:
    """Whether *output_path* is ``-``: the SBOM is then all of stdout, so no
    data line may follow it there."""
    return output_path is not None and str(output_path) == STDOUT


def open_text_lf(path: Path | str) -> TextIO:
    """Open *path* for writing UTF-8 text with ``\\n`` line endings."""
    return open(path, "w", encoding="utf-8", newline="\n")  # noqa: SIM115


def write_text_lf(path: Path | str, text: str) -> None:
    """Write *text* to *path* as UTF-8 with ``\\n`` line endings."""
    with open_text_lf(path) as f:
        f.write(text)


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
    "write_sbom_output",
    "write_stdout_lf",
    "write_text_lf",
]
