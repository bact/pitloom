# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A relay: another tool's own words, said after its name and with no code
(Pitloom names no condition of its own).

Each relay module keeps its prefix as a module constant, the shape the
message inventory reads as a ``prefixed`` relay
(``scripts/message_inventory/_relay.py``); a drift test holds each of them in
:data:`RELAY_PREFIXES`. A relay record carries :data:`RELAY_EXTRA`.

See also: :mod:`pitloom.messages._line_kind` (reading a relay line back).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.logging_config import KIND_ATTR, RELAY_KIND
from pitloom.messages._sbom_input import VALIDATOR_PREFIX

#: What a relay line's text starts with, after at most one frame: whose
#: words follow. LicenseID's warnings
#: (:mod:`pitloom.extract._licenseid_relay`), setuptools' stderr
#: (:mod:`pitloom.core._models_wheel_setuptools_relay`), fickling's stderr
#: (:mod:`pitloom.extract.ai_model.pytorch`) and the SPDX 3 validator's
#: findings (:data:`~pitloom.messages._sbom_input.VALIDATOR_PREFIX`).
RELAY_PREFIXES: Final = (
    "licenseid: ",
    "setuptools stderr: ",
    "fickling: ",
    VALIDATOR_PREFIX,
)

#: The ``extra`` of a relay record: its kind
#: (:data:`~pitloom.logging_config.KIND_ATTR`) a relay. Read-only, so no
#: caller can change what every relay passes.
RELAY_EXTRA: Final[Mapping[str, object]] = MappingProxyType({KIND_ATTR: RELAY_KIND})
