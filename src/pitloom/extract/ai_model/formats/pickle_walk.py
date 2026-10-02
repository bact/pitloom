# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The opcodes of a pickle, without converting its decimal numbers.

:func:`pickletools.genops` converts the decimal text arguments of ``INT``,
``LONG``, ``GET`` and ``PUT`` with :func:`int` before it yields the opcode,
which is quadratic in the number of digits once
:func:`sys.set_int_max_str_digits` is off, and an error past the limit when
it is on. :func:`walk_opcodes` reads the same opcode table
(:data:`pickletools.opcodes`) but only locates a decimal argument, refusing
one over :attr:`Limits.max_pickle_decimal_digits`, so the cost and the
outcome do not depend on the interpreter's configuration. Every other
argument is read with the table's own reader, as ``genops`` does. Nothing
is unpickled.

A decimal argument is located, not checked: text that is not a number is
left to whoever converts it.

See also: :mod:`pitloom.extract.ai_model._pickle_bounds` (Pitloom's adapter).
"""

from __future__ import annotations

import io

# Only the opcode table and its argument readers; nothing is unpickled.
import pickletools  # nosec B403
from collections.abc import Iterator
from typing import IO, NamedTuple

from ._errors import LimitExceeded, Malformed
from ._limits import Limits

_CODE2OP = {op.code.encode("latin-1"): op for op in pickletools.opcodes}
_DECIMAL_ARGS = (pickletools.decimalnl_short, pickletools.decimalnl_long)
_DIGITS = b"0123456789"
_STOP = b"."


class Opcode(NamedTuple):
    """One opcode of a pickle.

    Attributes:
        name: The opcode's name in :data:`pickletools.opcodes` (``"STOP"``).
        pos: Its offset from where the walk started.
    """

    name: str
    pos: int


class PickleWalk(NamedTuple):
    """The first pickle of a stream.

    Attributes:
        end: Offset just past its ``STOP`` opcode, from where the walk
            started.
        opcodes: How many opcodes it holds, ``STOP`` included.
    """

    end: int
    opcodes: int


def walk_opcodes(source: bytes | IO[bytes], limits: Limits) -> Iterator[Opcode]:
    """Yield the opcodes of the first pickle in *source*, through ``STOP``.

    *source* is bytes or a binary file object read from its current
    position; positions are relative to it. A non-decimal argument is read
    with the opcode table's reader, which reads a declared length in one
    call: give a file object only where such a read is bounded (a
    :class:`io.BytesIO`, or a stream already capped in size).

    Raises:
        LimitExceeded: More than :attr:`Limits.max_pickle_opcodes` opcodes,
            or a decimal argument over :attr:`Limits.max_pickle_decimal_digits`
            digits or :attr:`Limits.max_pickle_decimal_bytes` bytes.
        Malformed: An unknown opcode, an argument that cannot be read, or
            the data ends before ``STOP``.
    """
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    start = stream.tell()
    count = 0
    while True:
        pos = stream.tell() - start
        code = stream.read(1)
        op = _CODE2OP.get(code)
        if op is None:
            if not code:
                raise Malformed("pickle exhausted before seeing STOP")
            raise Malformed(f"at position {pos}, opcode {code!r} unknown")
        if op.arg in _DECIMAL_ARGS:
            _skip_decimal(stream, limits)
        elif op.arg is not None:
            _read_arg(op.arg, stream)
        count += 1
        if count > limits.max_pickle_opcodes:
            raise LimitExceeded(
                f"pickle with more than {limits.max_pickle_opcodes} opcodes"
            )
        yield Opcode(op.name, pos)
        if code == _STOP:
            return


def first_pickle(source: bytes | IO[bytes], limits: Limits) -> PickleWalk:
    """Where the first pickle in *source* ends, and how many opcodes it holds.

    Raises:
        LimitExceeded: See :func:`walk_opcodes`.
        Malformed: See :func:`walk_opcodes`.
    """
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    start = stream.tell()
    count = sum(1 for _opcode in walk_opcodes(stream, limits))
    return PickleWalk(stream.tell() - start, count)


def _skip_decimal(stream: IO[bytes], limits: Limits) -> None:
    """Move past one newline-terminated decimal argument without converting
    it; :meth:`readline` with a size reads no further than the bound."""
    window = limits.max_pickle_decimal_bytes
    text = stream.readline(window + 1)
    if len(text) - len(text.translate(None, _DIGITS)) > (
        limits.max_pickle_decimal_digits
    ):
        raise LimitExceeded(
            "pickle with a decimal number over "
            f"{limits.max_pickle_decimal_digits} digits"
        )
    if not text.endswith(b"\n"):
        if len(text) <= window:
            raise Malformed("no newline found when trying to read stringnl")
        raise LimitExceeded(f"pickle with a decimal argument over {window} bytes")


def _read_arg(arg: pickletools.ArgumentDescriptor, stream: IO[bytes]) -> None:
    """Read one non-decimal argument with the opcode table's reader."""
    try:
        arg.reader(stream)
    except MemoryError:
        raise
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        # The readers raise ValueError, but also UnicodeDecodeError and,
        # for a few malformed escapes, others.
        raise Malformed(str(exc)) from exc
