# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's parameter count: derived from tensor shapes or stated by a source.

Both routes are bounded: no value above :data:`MAX_PARAMETER_COUNT` is ever
multiplied out in full or recorded, and a rejection anywhere means no count
at all, never a partial one. The functions are pure; a caller turns a
:class:`ParameterCountRejected` into its ``WARNING:``
(:func:`pitloom.extract.ai_model.parameter_count.warn_parameter_count`).

See also: :mod:`pitloom.extract.ai_model.parameter_count` (the reader side).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pitloom.messages import DIMENSION_REASON, STATED_COUNT_REASON, Cap

#: The largest count recorded: 16 digits, so ``str()`` is safe on every Python.
MAX_PARAMETER_COUNT = 10**15

#: :data:`MAX_PARAMETER_COUNT` as a model warning names it.
PARAMETER_COUNT_CAP = Cap(MAX_PARAMETER_COUNT, "element", "parameter-count")

#: The ``ai_hyperparameter`` key holding the count.
PARAMETER_COUNT_KEY = "parameters"

#: The provenance key of the count: the
#: :class:`~pitloom.core.ai_metadata.AiModelMetadata` field name.
PARAMETER_COUNT_PROVENANCE_KEY = "parameter_count"

#: The provenance suffix of a count summed from tensor shapes.
TENSOR_ELEMENT_SUM_METHOD = " | Method: tensor_element_sum"

#: The package comment line saying what the ``parameters`` entry is. No
#: ``;``: a merge joins comments with ``"; "``, and
#: :func:`with_parameter_count_note` finds the note as a whole segment.
PARAMETER_COUNT_NOTE = (
    'Parameter count: ai_hyperparameter "parameters" holds the number of '
    "elements in the model's stored tensors, as its parameter count, because "
    "SPDX 3.0.1 has no model-size property (it is not a hyperparameter)."
)

_REPR_CHARS = 40


class ParameterCountRejected(ValueError):
    """A shape or a stated count that yields no parameter count.

    Attributes:
        reason: Why, in the catalogue's words (no unbounded text).
        over_cap: Whether the count exceeds :data:`MAX_PARAMETER_COUNT`.
        value: The rejected tensor dimension as shown (its ``repr``, cut to
            40 characters); ``None`` for a stated count or a count over
            the cap.
    """

    def __init__(
        self, reason: str, *, over_cap: bool, value: str | None = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.over_cap = over_cap
        self.value = value


def _over_cap() -> ParameterCountRejected:
    return ParameterCountRejected(f"count is over {MAX_PARAMETER_COUNT}", over_cap=True)


def _bounded_repr(value: object) -> str:
    """A short ``repr`` of *value*, whatever the object is."""
    try:
        text = repr(value)
    # pylint: disable-next=broad-exception-caught
    except Exception:
        return f"<{type(value).__name__}>"
    return text if len(text) <= _REPR_CHARS else text[:_REPR_CHARS] + "..."


def tensor_elements(shape: Sequence[object]) -> int:
    """The number of elements of a tensor of *shape* (``()``: a scalar, 1).

    Every dimension is checked, a zero one included.

    Raises:
        ParameterCountRejected: A dimension is not a non-negative ``int``
            (``over_cap`` false), or the count is over
            :data:`MAX_PARAMETER_COUNT` (``over_cap`` true; raised as soon
            as it is known, so a huge dimension is never multiplied out).
    """
    total = 1
    zero = over = False
    for dim in shape:
        if not isinstance(dim, int) or isinstance(dim, bool) or dim < 0:
            shown = _bounded_repr(dim)
            raise ParameterCountRejected(
                DIMENSION_REASON % {"value": shown}, over_cap=False, value=shown
            )
        if dim == 0:
            zero = True
        elif over or dim > MAX_PARAMETER_COUNT or total * dim > MAX_PARAMETER_COUNT:
            over = True  # a later zero dimension still makes the count 0
        else:
            total *= dim
    if zero:
        return 0
    if over:
        raise _over_cap()
    return total


def tensor_element_sum(shapes: Iterable[Sequence[object]]) -> int | None:
    """The sum of :func:`tensor_elements` over *shapes*; ``None`` when there
    is no element (no tensor, or only empty ones).

    Raises:
        ParameterCountRejected: A shape is rejected or the sum is over
            :data:`MAX_PARAMETER_COUNT`: no partial sum is ever returned.
    """
    total = 0
    for shape in shapes:
        total += tensor_elements(shape)
        if total > MAX_PARAMETER_COUNT:
            raise _over_cap()
    return total or None


def stated_parameter_count(value: object) -> int | None:
    """The parameter count a source states: *value* when a positive ``int``
    within the cap; ``None`` for ``None`` or ``0`` (no count stated).

    Raises:
        ParameterCountRejected: *value* is not a non-negative ``int``, or is
            over :data:`MAX_PARAMETER_COUNT`.
    """
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ParameterCountRejected(STATED_COUNT_REASON, over_cap=False)
    if value > MAX_PARAMETER_COUNT:
        raise _over_cap()
    return value or None


def is_parameter_count_text(value: object) -> bool:
    """Whether *value* reads as a parameter count: a ``str`` of ASCII digits
    that is positive and within :data:`MAX_PARAMETER_COUNT` (``"7B"`` is not)."""
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and len(value) <= len(str(MAX_PARAMETER_COUNT))
        and 0 < int(value) <= MAX_PARAMETER_COUNT
    )


def with_parameter_count_note(comment: str | None, has_count: bool) -> str | None:
    """*comment* with :data:`PARAMETER_COUNT_NOTE` as its first line iff
    *has_count*, and nowhere else.

    Every copy of the note is removed first, as a whole line or as a
    ``"; "``-joined segment (a merge joins comments so), with the separator
    and any line it leaves empty; the rest keeps its order. Idempotent.

    Returns:
        The comment, or ``None`` when nothing is left.
    """
    lines: list[str] = []
    for line in (comment or "").split("\n"):
        parts = line.split("; ")
        kept = [part for part in parts if part.strip() != PARAMETER_COUNT_NOTE]
        if kept:  # a line of notes only goes
            lines.append("; ".join(kept))
    rest = "\n".join(lines).strip("\n")
    if has_count:
        return f"{PARAMETER_COUNT_NOTE}\n{rest}" if rest else PARAMETER_COUNT_NOTE
    return rest or None
