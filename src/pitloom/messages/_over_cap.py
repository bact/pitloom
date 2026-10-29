# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``over-cap`` family (an input over one of Pitloom's caps) and
:class:`Cap`, the limit its lines name.

The code equals the evidence reason ``over-cap``
(:data:`pitloom.core.evidence.REASON_CODES`), which stays a literal there: a
reason is SBOM data and a code a stderr token, which may gain variants a
reason must not. ``tests/messages/test_drift_sources.py`` holds the two
equal.

See also: :mod:`pitloom.messages._over_cap_warning` (the one helper every
cap warns through).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pitloom.core.internal_error import InternalError
from pitloom.messages._fields import render
from pitloom.messages._types import Line, Message

#: What an input over a cap is, in every line and in an error's text.
REASON: Final = "larger than the %(limit)s-%(unit)s %(purpose)s cap"


@dataclass(frozen=True)
class Cap:
    """A limit Pitloom puts on an input, as the ``over-cap`` lines name it:
    ``<subject>=<where>: larger than the <limit>-<unit> <purpose> cap``, or
    ``FORMAT=<model_format> FILE=<where>: ...`` for a model.

    Raises:
        pitloom.core.internal_error.InternalError: A field does not have the
            shape its value has in a line, or a model's cap names no file.
    """

    #: The most the input may hold, in *unit*.
    limit: int
    #: What *limit* counts, singular (``"byte"``, ``"entry"``).
    unit: str
    #: What the cap is for (``"license-detection"``); the setting's name when
    #: a setting sets the limit (``"max-model-extract-bytes"``).
    purpose: str
    #: The key naming the input: ``"FILE"``, ``"DIR"``, ``"FIELD"``,
    #: ``"DATASET"``, ``"MARKER"`` or ``"REQUIREMENT"``.
    subject: str = "FILE"
    #: The format of the model whose file is the input (``"gguf"``), named
    #: first (:func:`pitloom.core.ai_metadata.model_cap`); ``None`` otherwise.
    model_format: str | None = None

    def __post_init__(self) -> None:
        """Check each field against the shape of its value in a line."""
        try:
            render(REASON, self.reason_values())
            render("%(key)s", {"key": self.subject})
            if self.model_format is not None:
                render("%(format)s", {"format": self.model_format})
        except ValueError as exc:
            raise InternalError(f"not a cap: {exc}") from None
        if self.model_format is not None and self.subject != "FILE":
            raise InternalError(f"a model's cap names its FILE, not {self.subject}")

    def reason_values(self) -> dict[str, object]:
        """The values :data:`REASON` names."""
        return {"limit": self.limit, "unit": self.unit, "purpose": self.purpose}

    @property
    def reason(self) -> str:
        """What an input over this cap is, the same in a ``WARNING:`` and
        in an error's text."""
        return render(REASON, self.reason_values())


#: A cap's warning, the input named by its key (``FILE=``, ``FIELD=``...).
KEY_LINE: Final = Line(
    level="WARNING", template=f"%(key)s=%(name)s: {REASON}; %(outcome)s"
)
#: A cap's warning naming a model: its format, then its file.
MODEL_LINE: Final = Line(
    level="WARNING",
    template=f"FORMAT=%(format)s FILE=%(file)s: {REASON}; %(outcome)s",
)
#: An sdist's own configuration file over the member cap: the sdist is
#: not read.
CONFIG_MEMBER_LINE: Final = Line(
    level="ERROR", template=f"config file %(path)s: {REASON}; not read"
)
#: A Git URL's checkout over the library caller's ``max_clone_bytes``.
CLONE_LINE: Final = Line(
    level="ERROR",
    template="the repository is larger than %(amount)s; git %(command)s was stopped",
)
#: A ``git`` call's output over its cap.
GIT_OUTPUT_LINE: Final = Line(
    level="ERROR", template="git %(command)s produced more than %(size)s"
)

#: An input over a cap.
OVER_CAP: Final = Message(
    code="over-cap",
    condition="over-cap",
    lines=(KEY_LINE, MODEL_LINE, CONFIG_MEMBER_LINE, CLONE_LINE, GIT_OUTPUT_LINE),
    summary="An input is larger than a cap Pitloom puts on what it reads or "
    "records, so that a crafted or unusually large input cannot exhaust time, "
    "memory or disk.",
    did="Kept what fits the cap and left the rest out, or did not read the "
    "input; the text after the semicolon says which.",
    effect="thinner",
    actor="user",
    advice="Tell the user which input was over which cap and what the SBOM "
    "lacks for it. Three caps are settings, which they can raise for an input "
    "they trust and then generate again: max-model-extract-bytes (and with it "
    "the per-wheel model-scan budget, four times it) by "
    "--max-model-extract-bytes or its [tool.pitloom] key; "
    "max-dataset-hash-bytes by its key, by --max-dataset-hash-bytes of loom id "
    "generate or by the max_dataset_hash_bytes argument of loom.Run; a Git "
    "URL's checkout by the max_clone_bytes argument of the library call. "
    "Every other cap is fixed. Do not raise a cap or generate again for them; "
    "ask first, and with nobody to ask, report it only.",
)

ENTRIES: Final = (OVER_CAP,)
