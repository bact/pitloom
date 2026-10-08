# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Atheris fuzz harness for CRFsuite model header and label parsing.

Target: ``pitloom.extract.ai_model.formats.crfsuite.read_crfsuite``, an
untrusted-input boundary: it parses the header, chunk headers and labels
string database of a CRFsuite model file a user points ``loom model`` or
``loom generate`` at. Its documented error contract is
``pitloom.extract.ai_model.formats.FormatError`` (``Malformed``,
``UnsupportedVersion``, ``LimitExceeded``), which this harness swallows.
Anything else escaping ``_run_one`` (``struct.error``, ``IndexError``,
``UnicodeDecodeError``, ``MemoryError``, ...) is a bug, as is a read past
``max_crfsuite_labels_chunk_bytes + 108`` bytes.

Pure Python and in memory: no third-party package and no temp file.
Seed it with ``tests/fixtures/aimodels/crfsuite/`` as the corpus directory.

See ``fuzz/README.md`` for how to run this.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# pylint: disable=wrong-import-position
from pitloom.extract.ai_model.formats import (  # noqa: E402
    FormatError,
    Limits,
)
from pitloom.extract.ai_model.formats.crfsuite import read_crfsuite  # noqa: E402

_LIMITS = Limits()
_BUDGET = _LIMITS.max_crfsuite_labels_chunk_bytes + 108


class _Counting(io.BytesIO):
    """Counts every byte read."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.total = 0

    def read(self, size: int | None = -1, /) -> bytes:
        data = super().read(size)
        self.total += len(data)
        return data


def _run_one(data: bytes) -> None:
    """Feed fuzzer bytes to the reader and check its read budget."""
    source = _Counting(data)
    try:
        read_crfsuite(source, _LIMITS)
    except FormatError:
        pass  # Expected: the reader's documented error contract.
    if source.total > _BUDGET:
        raise RuntimeError(f"read {source.total} bytes, budget {_BUDGET}")


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
