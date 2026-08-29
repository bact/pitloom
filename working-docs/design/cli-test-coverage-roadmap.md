---
Created: 2026-08-14
Last-Modified: 2026-08-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# CLI split, test-suite modularization, and coverage roadmap

**Status: CLOSED.** All three original goals shipped and were
verified exceeded as of 2026-08-21:

- `src/pitloom/__main__.py` (was 1,320 lines) split into
  `src/pitloom/cli/` (`parser.py`, `options.py`, `verbose.py`,
  `constants.py`, `ids.py`, `commands/` with one file per verb).
- Test suite modularized into `tests/cli/`/`tests/core/`/
  `tests/extract/`/`tests/assemble/`, mirroring the source layout
  (folder-per-area once an area reaches 3+ related files, per
  `AGENTS.md`'s Testing section).
- Coverage floor (`fail_under` in `pyproject.toml`) raised
  88 -> 90 -> 95 -> **97**; measured coverage reached 99.89%.

Current numbers for any of the above (line counts, file layout,
coverage %) should be read from the tree/CI directly rather than from
this doc -- they will have moved on.

## Next step

Nothing from this doc's original scope remains open. File-size drift
that has resumed since the test-suite split is tracked in the sibling
doc instead: [complexity-and-file-size-roadmap.md](complexity-and-file-size-roadmap.md).

### Pickup prompt for a new session

```text
This doc's scope (the __main__.py -> cli/ split, test-suite
modularization, and coverage floor raise) is CLOSED -- do not redo
any of it. For file-size or coverage follow-up, check
complexity-and-file-size-roadmap.md instead.
```
