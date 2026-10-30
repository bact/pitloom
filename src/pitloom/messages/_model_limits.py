# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a model's bound check stops its read when no cap is crossed: the file
declares more than it can hold, or the check cannot run on it. A reader
raises :class:`pitloom.extract.ai_model.limits.ModelLimitExceeded` with one
of these texts, each ``%d`` a whole number, and the ``model-unreadable``
line names it as its ``<reason>``: a closed field, trusted only in these
shapes. ``tests/messages/test_model_stub.py`` holds every raise to the
table.

See also: :mod:`pitloom.messages._model_stub` (the entry) and
:mod:`pitloom.messages._fields` (the field).
"""

from __future__ import annotations

from typing import Final

#: A GGUF header declaring more tensors than the file can hold.
LIMIT_GGUF_TENSORS: Final = "GGUF header declares %d tensors"
#: A GGUF header declaring more key/value pairs than the file can hold.
LIMIT_GGUF_PAIRS: Final = "GGUF header declares %d key/value pairs"
#: A GGUF array declaring more elements than the file can hold.
LIMIT_GGUF_ARRAY: Final = "GGUF array of %d elements, more than the file holds"
#: A GGUF version the ``gguf`` package reads but the bound check does not know.
LIMIT_GGUF_VERSION: Final = "GGUF version %d, not bounded"
#: A ZIP archive whose entries cannot be counted: Python's ``zipfile`` changed.
LIMIT_ZIP_UNCHECKABLE: Final = "ZIP archive not checkable: zipfile internals changed"
#: A ZIP central directory that is not one.
LIMIT_ZIP_MALFORMED: Final = "malformed ZIP central directory"

#: Every reason, as the field's pattern reads them.
MODEL_LIMIT_REASONS: Final = (
    LIMIT_GGUF_TENSORS,
    LIMIT_GGUF_PAIRS,
    LIMIT_GGUF_ARRAY,
    LIMIT_GGUF_VERSION,
    LIMIT_ZIP_UNCHECKABLE,
    LIMIT_ZIP_MALFORMED,
)
