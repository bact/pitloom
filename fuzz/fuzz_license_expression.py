# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Atheris fuzz harness for SPDX license expression classification.

Target: ``pitloom.extract._license.classify_license``. By its own
contract, this function degrades gracefully for any string input -- it
catches the third-party expression parser's own failures and classifies
the value as text, so it should never raise. Any exception escaping
``_run_one`` below is therefore, by definition, a bug: either in
Pitloom's own classification code or in the ``py-spdx-license`` library
it wraps.

See ``fuzz/README.md`` for how to run this.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# pylint: disable=wrong-import-position
from pitloom.extract._license import classify_license  # noqa: E402


def _run_one(data: bytes) -> None:
    """Decode fuzzer bytes to text and feed them straight to the target.

    ``errors="ignore"`` on decode is deliberate: malformed UTF-8 is not
    what this harness is testing (that's a separate, uninteresting
    failure mode); the interesting surface is the license-expression
    grammar itself, so any valid-enough text should reach it.
    """
    text = data.decode("utf-8", errors="ignore")
    classify_license(text)


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
