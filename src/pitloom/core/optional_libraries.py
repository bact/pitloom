# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The optional libraries Pitloom imports for a step, each with the extra of
Pitloom that installs it, and the one error a step raises when its library
is missing (``library-missing``, :func:`missing`).

See also: :mod:`pitloom.extract.ai_model.reader_requirements` (the model
readers' libraries) and :mod:`pitloom.messages._model_stub` (the entry).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pitloom.messages import LIBRARY_MISSING, CodedImportError


@dataclass(frozen=True)
class Requirement:
    """An optional library.

    Attributes:
        module: The top-level module imported.
        extra: The extra of Pitloom that installs it.
    """

    module: str
    extra: str

    @property
    def spec(self) -> str:
        """What to install: Pitloom with :attr:`extra` (``pitloom[gguf]``)."""
        return f"pitloom[{self.extra}]"


def missing(requirement: Requirement) -> CodedImportError:
    """The error a step raises when *requirement* cannot be imported: its
    module and the extra to install, coded ``library-missing``."""
    return CodedImportError(
        LIBRARY_MISSING, module=requirement.module, requirement=requirement.spec
    )


#: The Hugging Face Hub client, for a model on the Hub.
HUB: Final = Requirement("huggingface_hub", "huggingface_hub")
#: SPDX 3 schema and SHACL validation (``loom fragment validate``,
#: ``loom validate-wheel``).
VALIDATE: Final = Requirement("spdx3_validate", "validate")
#: PyPA build, for ``--allow-build``.
BUILD: Final = Requirement("build", "build")
#: magika, for ``content-type-method = "magika"``.
MAGIKA: Final = Requirement("magika", "content-type")
