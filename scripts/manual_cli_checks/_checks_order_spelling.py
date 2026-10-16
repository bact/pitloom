# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The path-spelling order checks (``O6``): a module named in NFD and a
model path typed in upper case, read back through every surface under the
invariants of ``_order_invariants.py`` (``N/*``: a key is NFC and spelt as
on disk).

- ``O6/<fixture>/nfd``: needs a file system that keeps an NFD name; skipped
  with the reason on one that normalises it to NFC.
- ``O6/<fixture>/upper``: needs a case-insensitive file system, where
  ``DEMO/TINY.safetensors`` is the model file; skipped on a case-sensitive
  one (the path would not exist).

See also: ``_checks_order.py`` (the runner of a sequence),
``_order_ops.py`` (``add-nfd``, ``model-upper``, ``train-upper``).
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from _checks_order import _finish, _run_all  # pylint: disable=protected-access
from _harness import CheckSkipped, Context, check
from _order_fixtures import Profile
from _order_gen import all_profiles, spellings
from _order_ops import NFD_STEM, applies


def keeps_nfd(directory: Path) -> bool:
    """Whether *directory*'s file system lists a file name in NFD as
    created (APFS and ext4 do; HFS+ lists NFC or NFD by its own rule)."""
    probe = directory / f"{NFD_STEM}-probe"
    probe.write_bytes(b"")
    try:
        return probe.name in os.listdir(directory)
    finally:
        probe.unlink()


def folds_case(directory: Path) -> bool:
    """Whether *directory*'s file system treats ``a`` and ``A`` as one."""
    probe = directory / "case-probe"
    probe.write_bytes(b"")
    try:
        return (directory / "CASE-PROBE").exists()
    finally:
        probe.unlink()


def _spelling_check(ctx: Context, profile: Profile, kind: str) -> None:
    if kind == "nfd" and not keeps_nfd(ctx.work):
        raise CheckSkipped("the file system does not keep a file name in NFD")
    if kind == "upper" and not folds_case(ctx.work):
        raise CheckSkipped("the file system is case-sensitive: no upper-case path")
    check_id = f"O6/{profile.name}/{kind}"
    _finish(ctx, check_id, _run_all(ctx, check_id, [spellings(profile, kind)]))


def _register() -> None:
    for profile in all_profiles():
        for kind, op in (("nfd", "add-nfd"), ("upper", "model-upper")):
            if applies(op, profile):
                check(
                    f"O6/{profile.name}/{kind}",
                    f"order: {kind} spelling, {profile.name}",
                )(functools.partial(_spelling_check, profile=profile, kind=kind))


_register()
