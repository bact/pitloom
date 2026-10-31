# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The calls the usage scan recognises: which ones read a file, which write
it, which only mention it.

The table is data, so a library is added in one place. A call is known by the
last name of its callee (``load`` in ``joblib.load``, ``np.load`` and
``self.load``), never by its module: a receiver's type is not known from the
syntax, and a name such as ``save_model`` means the same on any object. A call
that is in none of the lists is not an error: the path it receives is then
recorded as an unknown access.

The path is not told by its argument position. ``torch.save(obj, path)`` and
``np.save(path, arr)`` differ, but the scan looks for a path-shaped value that
names a model, so the one argument that matches is the path.

See also: :mod:`pitloom.extract._usage_ast` (the scan that reads it) and
:mod:`pitloom.core.model_usage` (the accesses).
"""

from __future__ import annotations

from typing import Final

from pitloom.core.model_usage import UsageAccess

__all__ = [
    "MODE_CALLS",
    "access_of_mode",
    "access_of_name",
    "is_mention_call",
]

#: Callees that open a file in a mode: the last name, the position of the
#: ``mode`` argument, and the mode when it is left out. ``open`` covers
#: ``io.open``, ``gzip.open``, ``tarfile.open``, ``Path.open`` (whose path is
#: the receiver, so its mode is the first argument: see
#: :data:`RECEIVER_MODE_POSITION`) and a reader that is called ``open``.
MODE_CALLS: Final[dict[str, tuple[int, str]]] = {
    "open": (1, "r"),
    "File": (1, "r"),
    "ZipFile": (1, "r"),
    "TarFile": (1, "r"),
    "memmap": (2, "r+"),
}

#: ``Path(...).open(mode)``: the path is the receiver, the mode comes first.
RECEIVER_MODE_POSITION: Final = 0

#: Names that read a model when the path is given to them, though they do not
#: begin with a reading word.
_READ_NAMES: Final = frozenset({"booster", "inferencesession", "interpreter", "llama"})
#: A name starting with one of these reads or writes the file it is given
#: (``load_model``, ``read_text``, ``from_pretrained``; ``save_pretrained``,
#: ``dump``, ``to_onnx``). Compared in lower case.
_READ_PREFIXES: Final = ("load", "read", "from_", "restore")
_WRITE_PREFIXES: Final = ("save", "write", "dump", "export", "to_")

#: A call whose arguments say something about a file but do not touch it:
#: output and logging. The name alone decides, as for the table above.
_MENTION_NAMES: Final = frozenset(
    {
        "print",
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "exception",
        "critical",
        "fatal",
        "log",
        "echo",
        "exit",
    }
)
#: An exception built from the path is the message of the failure, not a use.
_MENTION_SUFFIXES: Final = ("Error", "Exception", "Warning", "Exit")


def access_of_mode(mode: str) -> UsageAccess:
    """The access a file mode (``"rb"``, ``"w+"``) opens: ``+`` is both, ``w``,
    ``a`` and ``x`` write, ``r`` reads, anything else is unknown."""
    if "+" in mode:
        return UsageAccess.READ_WRITE
    if any(flag in mode for flag in "wax"):
        return UsageAccess.WRITE
    if "r" in mode:
        return UsageAccess.READ
    return UsageAccess.UNKNOWN


def access_of_name(name: str) -> UsageAccess:
    """The access a callee named *name* means, by its first word; unknown for
    a name that is neither a reader's nor a writer's. A name in
    :data:`MODE_CALLS` is not decided here: its mode is."""
    lowered = name.lower()
    if lowered in _READ_NAMES or lowered.startswith(_READ_PREFIXES):
        return UsageAccess.READ
    if lowered.startswith(_WRITE_PREFIXES):
        return UsageAccess.WRITE
    return UsageAccess.UNKNOWN


def is_mention_call(name: str) -> bool:
    """Whether a callee named *name* only mentions its arguments (output,
    logging, an exception)."""
    return name in _MENTION_NAMES or name.endswith(_MENTION_SUFFIXES)
