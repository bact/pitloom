# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounds on a pickle before fickling sees it.

fickling turns every opcode into Python AST nodes, at roughly two hundred
times the pickle's size in memory and time, so a few MiB of opcodes is
enough to exhaust a machine. :func:`first_pickle` walks the opcodes with
:func:`pickletools.genops` (which allocates nothing per opcode), refuses a
pickle past :data:`MAX_PICKLE_OPCODES`, and returns only the bytes of the
first pickle, so fickling's input is bounded by what was verified.

See also: :mod:`pitloom.extract.ai_model.pytorch`.
"""

from __future__ import annotations

# genops only reads opcodes; nothing is unpickled.
import pickletools  # nosec B403

from pitloom.extract.ai_model.limits import ModelLimitExceeded

#: Most opcodes of the pickle fickling is given. A model's ``data.pkl`` holds
#: thousands to a few hundred thousand.
MAX_PICKLE_OPCODES = 250_000


def first_pickle(data: bytes) -> bytes:
    """The bytes of the first pickle in *data*, through its ``STOP`` opcode.

    Raises:
        ModelLimitExceeded: The pickle has more than
            :data:`MAX_PICKLE_OPCODES` opcodes.
        ValueError: *data* is not a complete, well-formed pickle.
    """
    count = 0
    try:
        for opcode, _arg, pos in pickletools.genops(data):
            count += 1
            if count > MAX_PICKLE_OPCODES:
                raise ModelLimitExceeded(
                    f"pickle with more than {MAX_PICKLE_OPCODES} opcodes"
                )
            if opcode.name == "STOP" and pos is not None:
                return data[: pos + 1]
    except ModelLimitExceeded:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        # genops raises ValueError, but also KeyError/UnicodeDecodeError/...
        raise ValueError(f"not a well-formed pickle: {exc}") from exc
    # Unreachable with bytes input: genops returns at STOP or raises when the
    # data ends first. Kept as the return-type guarantee, and as the refusal
    # if a later genops stops early without raising.
    raise ValueError("not a well-formed pickle: no STOP opcode")
