# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Atheris fuzz harness for GGUF model header parsing.

Target: ``pitloom.extract.ai_model.gguf.read_gguf``, an untrusted-input
boundary -- it parses an AI model file that could come from anywhere a user
points ``loom model`` or ``loom generate`` at, through Pitloom's own header
reader (``pitloom.extract.ai_model.formats.gguf_header``). ``read_gguf``
raises ``ValueError`` for a file that is no well-formed GGUF and
``ModelLimitExceeded`` for a count beyond the file: Pitloom's intentional
refusals, not bugs, so this harness swallows them. A header over a bound is
read in part, with a warning, and returns. Anything else escaping
``_run_one`` (a ``struct.error``, a ``UnicodeDecodeError``, a
``KeyError``/``IndexError`` from the field conversion) is a genuine bug.

Requires the ``gguf`` package (``pip install pitloom[gguf]``; Pitloom still
takes quantisation names and tensor type sizes from it) and ``atheris``.
Seeds: ``fuzz/gguf_seeds.py`` writes hostile headers next to the fixtures.

See ``fuzz/README.md`` for how to run this.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# pylint: disable=wrong-import-position
from pitloom.extract.ai_model.gguf import read_gguf  # noqa: E402
from pitloom.extract.ai_model.limits import ModelLimitExceeded  # noqa: E402

_FUZZ_INPUT_PATH = Path(tempfile.gettempdir()) / "pitloom-fuzz-gguf-input.gguf"


def _run_one(data: bytes) -> None:
    """Write fuzzer bytes to a scratch file and feed it to the target.

    ``read_gguf`` takes a filesystem path (it memory-maps the file), so a
    real (reused, not per-call-unique) temp file is the harness's input.
    """
    _FUZZ_INPUT_PATH.write_bytes(data)
    try:
        read_gguf(_FUZZ_INPUT_PATH)
    except (ValueError, ModelLimitExceeded):
        pass  # Expected: read_gguf's own refusals.


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
