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
trailing ` [code]`. A module with none is absent. Sorted, LF line ends, no
timestamp.

The ratchet fails when a count rises (a new uncoded message: give it a code
in `pitloom.messages`) and when a count falls (the baseline is stale: lower
it). Regenerate from the repository root, check `git diff` shows only lower
numbers, and commit:

```shell
python -m scripts.message_inventory --write-baseline
```

`python -m scripts.message_inventory` prints the totals,
`--check` runs the ratchet, `--jsonl -` lists every site.
