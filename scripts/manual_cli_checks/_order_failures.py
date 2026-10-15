# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Invariant H of the order-matrix checks: a step run against an injected
v2 or unparsable registry, or a read-only one.

- v2 or invalid JSON (design D10, section 6; rollout section 10): exit 1,
  no output, the broken bytes left as they were, and on a CLI surface
  exactly one ``ERROR:`` naming the registry file (``version 2, expected
  3`` for a v2 file); ``loom.Run`` raises ``ValueError`` instead.
- Read-only (build notes, order-matrix round): the registry is not
  overwritten; one ``ID registry: failed to save <path>: <reason>`` line,
  the only ``ERROR:`` and exit 1 for ``id generate``/``id import``, else a
  ``WARNING:``, no ``ERROR:`` and exit 0.

See also: ``_order_invariants.py`` (A-F, which skip these steps).
"""

from __future__ import annotations

from _order_capture import LOOM_SURFACES, Captured
from _order_ops import BAD_JSON, V2_REGISTRY

_ID_COMMANDS = frozenset({"gen", "gen-ds", "gen-min", "import", "import0"})
#: The one failed-save wording on every surface (``failed_to_save_message``).
_FAILED_SAVE = "ID registry: failed to save "


def injected(cap: Captured) -> list[tuple[str, str]]:
    """(code, message) for each way *cap*, run against a v2 or invalid
    registry, broke H."""
    found = []
    content = (V2_REGISTRY if cap.step.kind == "v2" else BAD_JSON).encode()
    if cap.reg_raw != content:
        found.append(("H/overwritten", "the broken registry was rewritten"))
    if cap.rc == 0:
        found.append(("H/exit", "exit 0 on a broken registry"))
    found += [
        ("H/output", f"{surface} output written")
        for surface, raw in cap.raw.items()
        if raw is not None
    ]
    v2 = cap.step.kind == "v2"
    if cap.step.op in LOOM_SURFACES:
        needle = "version 2, expected 3" if v2 else "ID registry"
        if needle not in cap.stderr:
            found.append(("H/message", f"no {needle!r}"))
        return found
    errors = [ln for ln in cap.stderr_lines if ln.startswith("ERROR: ")]
    wanted = "version 2, expected 3" if v2 else "ID registry file"
    if len(errors) != 1 or wanted not in errors[0]:
        found.append(
            ("H/message", f"not one ERROR with {wanted!r}: {cap.stderr_lines[:3]}")
        )
    return found


def read_only(cap: Captured, prev: Captured | None) -> list[tuple[str, str]]:
    """(code, message) for each way *cap*, run against a read-only
    registry, broke H."""
    found = []
    if prev is not None and cap.reg_raw != prev.reg_raw:
        found.append(("H/overwritten", "a read-only registry was rewritten"))
    id_command = cap.step.op in _ID_COMMANDS
    level = "ERROR: " if id_command else "WARNING: "
    saves = [ln for ln in cap.stderr_lines if "failed to save" in ln]
    if len(saves) != 1 or not saves[0].startswith(f"{level}{_FAILED_SAVE}"):
        found.append(("H/message", f"not one {level}{_FAILED_SAVE}: {saves}"))
    errors = [ln for ln in cap.stderr_lines if ln.startswith("ERROR: ")]
    if errors != (saves if id_command else []):
        found.append(("H/message", f"other ERROR lines: {errors[:2]}"))
    if cap.rc != (1 if id_command else 0):
        found.append(("H/exit", f"exit {cap.rc}"))
    return found
