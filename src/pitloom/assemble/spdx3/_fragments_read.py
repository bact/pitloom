# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading one SPDX 3 JSON-LD fragment file into an object set.

See also: :mod:`pitloom.assemble.spdx3.fragments` (the merge).
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import rfc8785
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.logging_config import loggable, warn_lone_surrogates

log = logging.getLogger(__name__)


def read_fragment_set(fragment_path: Path) -> spdx3.SHACLObjectSet:
    """The objects of the fragment at *fragment_path*.

    A lone surrogate in a string (``"\\ud800"``, which no UTF-8 output can
    hold) is written as text, with one ``WARNING:``. The fragment's JSON
    must also be RFC 8785 serialisable, as the merged document is: an
    integer beyond +-(2**53 - 1) (``dataset_datasetSize``) or a number past
    a double has no JCS spelling, and one such value would otherwise fail
    the whole document's serialisation.

    Raises:
        Exception: Whatever reading, parsing or canonicalising the file
            raised; the caller reports the fragment as unreadable.
    """
    raw = fragment_path.read_bytes()
    data, lone = escape_lone_surrogates_in(json.loads(raw))
    rfc8785.dumps(data)
    if lone:
        warn_lone_surrogates(log, loggable(str(fragment_path)))
        raw = json.dumps(data).encode("ascii")
    fragment_set = spdx3.SHACLObjectSet()
    spdx3.JSONLDDeserializer().read(io.BytesIO(raw), fragment_set)
    return fragment_set
