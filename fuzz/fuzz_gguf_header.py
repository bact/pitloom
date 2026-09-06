# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Atheris fuzz harness for GGUF model header parsing.

Target: ``pitloom.extract._gguf.read_gguf``, an untrusted-input boundary --
it parses an AI model file (via the third-party ``gguf`` package's
``GGUFReader``) that could come from anywhere a user points ``loom model``
or ``loom generate`` at. ``read_gguf`` deliberately catches ``GGUFReader``
constructor failures and re-raises them as ``ValueError`` -- that is
Pitloom's own intentional "not a GGUF file" signal, not a bug, so this
harness swallows it. Everything else escaping ``_run_one`` (a
``UnicodeDecodeError`` from a malformed STRING field's bytes, a
``struct.error``, an unexpected ``KeyError``/``AttributeError`` from a
field ``GGUFReader`` parsed successfully but with an unexpected shape,
etc.) is a genuine bug: ``read_gguf``'s own field-extraction code has no
such catch-all once ``GGUFReader`` itself accepts the file.

Requires the ``gguf`` package (``pip install pitloom[gguf]`` or
``pip install gguf``) in addition to ``atheris``.

See ``fuzz/README.md`` for how to run this.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# pylint: disable=wrong-import-position
from pitloom.extract._gguf import read_gguf  # noqa: E402

_FUZZ_INPUT_PATH = Path(tempfile.gettempdir()) / "pitloom-fuzz-gguf-input.gguf"


def _run_one(data: bytes) -> None:
    """Write fuzzer bytes to a scratch file and feed it to the target.

    ``GGUFReader`` (and, transitively, ``read_gguf``) only accepts a
    filesystem path, not an in-memory buffer, so a real (reused, not
    per-call-unique) temp file is the harness's only option here.
    """
    _FUZZ_INPUT_PATH.write_bytes(data)
    try:
        read_gguf(_FUZZ_INPUT_PATH)
    except ValueError:
        pass  # Expected: read_gguf's own "not a valid GGUF file" signal.


# atheris/libFuzzer entrypoint name:
def TestOneInput(data: bytes) -> None:  # noqa: N802
    _run_one(data)


def main() -> None:
    # pylint: disable=import-outside-toplevel
    import atheris

    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
