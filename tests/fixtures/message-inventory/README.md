---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message inventory baseline

See also: [`../../test_message_ratchet.py`](../../test_message_ratchet.py)
(the ratchet); `scripts/message_inventory/` (the tool and what it counts).

`uncoded.txt` holds one `module count` line per `src/pitloom` module: the
number of message emission sites in scope (a `WARNING:`, `INFO:` or `ERROR:`
line a person can see) that say no catalogued message, so their line has no
trailing `[code]`. A module with none is absent. Sorted, LF line ends, no
timestamp.

The ratchet fails when a count rises, per module or in total (a new uncoded
message: give it a code in `pitloom.messages`), and when a count falls (the
baseline is stale: lower it). Regenerate from the repository root and
commit:

```shell
python -m scripts.message_inventory --write-baseline
```

It writes falls only: while a module or the total is above the baseline it
prints the rises and writes nothing. A site that moves to another module (a
module split) is moved in this file by hand; the total still holds.

To move a module's uncoded sites to another module:

1. Move the code and run `python -m scripts.message_inventory`: the old module
   falls and the new one rises, so `--write-baseline` refuses.
2. Edit this file by hand: lower the old module's line (delete it at 0) and add
   the new module's line with the count the old one lost.
3. State the move and why in "Changes" below, and run `--check`: the total
   must be the one before the move.

Code that has no uncoded site (a masking helper, say) needs no line. A
programming error is not a message: raise it as
`pitloom.core.internal_error.InternalError` and it is left out by its class,
never by raising a count.

`python -m scripts.message_inventory` prints the totals,
`--check` runs the ratchet, `--jsonl -` lists every site.

## Changes

- 2026-10-29 (#390): `pitloom.core.evidence` 4 to 0 and
  `pitloom.core.provenance` 3 to 2. Those raises (an unknown evidence level
  or reason, a fact whose fields do not fit, an unknown provenance segment
  key) are programming errors, now `InternalError`, out of scope. The 3 had
  been raised by hand for the segment-key raise; no count rose.
