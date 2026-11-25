---
Created: 2026-11-23
Last-Modified: 2026-11-25
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Adding or changing a message: steps and traps for agents

See also: [AGENTS.md](../../AGENTS.md) ("CLI output": the compact rule),
[message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(the contract), [agents-md-rationale.md](agents-md-rationale.md),
[message-catalogue-review-rounds.md](message-catalogue-review-rounds.md)
(what past reviews found).

A message a user, a script or a skill can read is an interface: its level,
condition, wording, code and advice are checked by tests, and skills quote it.
Say it through the catalogue, never as free text.

## Steps

1. **Look first.** Search `src/pitloom/messages/` (entries are in `_<family>.py`,
   their say-helpers in `_<family>_say.py`, fields in `_fields_*.py`) and the
   generated pages `docs/message-codes*.md` for the situation. A situation
   usually has a code already: add a line or a variant to it, not a new code.
   A new code is named by the cause (`family[/variant]`), carries `since` set
   to the next unreleased version, and passes `template_problem`.
2. **Say it through the catalogue**: `emit(...)`, a family's say-helper, or
   `CodedValueError(M, ...)` / `CodedOSError` / `CodedRuntimeError` for an
   exception that reaches the user. The code rides on the record and on the
   exception as `pitloom_code`. A programming error (a state no user input can
   reach) raises `InternalError`. A library caller's bad value is
   `option-invalid` through `invalid_value(Parameter(...), id)`.
3. **Text shape**: `LEVEL: [SUBJECT=value: ]CONDITION[; ACTION]`, one line,
   British English, plain ASCII, a literal subject key from the existing
   vocabulary (`FILE=`, `DIR=`, `URL=`, `FORMAT=`, `PACKAGE=`), a shared
   sub-prefix for a subsystem (`ID registry: `, `loom SDK: `). Match a
   sibling's wording before inventing one.
4. **Attacker text** (a file name, a URL, a metadata value, a tool's stderr, an
   exception message) goes through the field writers in
   `messages/_field_writers.py`, which mask credentials first, then cut, then
   escape control characters. Never `loggable()` or `quote_source()` first and
   mask after: an escape hides a token's shape. Write one hostile-input test per
   writer (a newline, ANSI, a URL credential, a forged `[code]`, a very long
   value).
5. **Regenerate and update together**: `python scripts/generate_message_reference.py
   --write`, then what a skill or doc quotes (`grep` the old text in `docs/`,
   `skills/`, `tests/`, `scripts/manual_cli_checks/`), and the `CHANGELOG.md`
   entry. A generated page stays under 30,000 bytes and 800 lines; split the
   topic in `messages/_topics.py` before it crosses.
6. **Test the surface**: a test that fails on the base tree, on each surface
   that can reach the message (CLI, library, hook, loom SDK).

## A line without a code: kinds

A tagged line (`ERROR:`, `WARNING:`, `INFO:`) with no code is one of three
kinds a record declares, or it fails the test run (`pitloom.messages.line_kind`
reads a printed line back; `tests/_strict_uncoded.py` is the check):

- **`summary`**: an `INFO:` line of a `SUMMARIES` template, said through
  `say_summary`. **`detail`**: a `-v` `INFO: KEY=VALUE` line from
  `pitloom.cli.kv_output.log_kv`. **`relay`**: another tool's words after a
  prefix of `pitloom.messages.RELAY_PREFIXES` (`licenseid: `,
  `setuptools stderr: `, `fickling: `, `spdx3-validate: `), after at most one
  frame of its level.
- A record's kind rides as `pitloom_kind` (`KIND_ATTR`); a record never
  carries both a code and a kind. A relay passes `extra=RELAY_EXTRA`, and the
  prefix is a module constant plus a `%s` argument (the inventory reads that
  shape as a `prefixed` relay); a new prefix joins `RELAY_PREFIXES` and the
  prose of `docs/messages.md` and both skills' `references/messages.md`
  (`tests/messages/test_relay_prefixes_docs.py`).
- A caller that re-says a captured record (`extract/_reader_relay.py`) copies
  `pitloom_kind` through, as it copies the code, or the re-said line is
  uncoded.
- Other lines have no kind and need none: `DEBUG:`, untagged text (argparse
  usage, a traceback) and `overlong` lines (over `LONGEST_LINE`, never read
  back; a finding in tests whatever its kind). An `ERROR:` line of an
  unexpected error (`InternalError` has no code) stays uncoded: a test that
  says one names it. A message that could not be shown (`UNSHOWN_MESSAGE`)
  prints that fixed text and keeps its error's code when it had one
  (`mask_record` replaces `msg` only; `print_error` masks the text, then
  appends the code), so it is uncoded only when its error had no code.
- A test that says an uncoded line on purpose carries
  `@pytest.mark.uncoded_output(*patterns)` on the test or its `pytest.param`
  (only the item's own markers count, never a module or class mark). Each
  pattern is a regular expression searched in the line; a line no pattern
  matches fails the test, and so does a pattern that matches no line (a stale
  allowance).
- A per-wheel `except (ValueError, OSError)` calls `report_wheel_failure`
  (`cli/commands/utils.py`) first: it re-raises `InternalError`, so a bug in
  Pitloom stops the run (`verify-wheel`, `validate-wheel`, `embed-wheel
  --verify/--validate`) instead of being said as that wheel's failure.
- Silent gaps of the check (its module docstring has the detail): an `INFO`
  record never reaches `Logger.handle` while the `pitloom` logger is
  unconfigured, so a test that wants it configures logging or lowers a level;
  `DEBUG`, the `pitloom.test_*` loggers and third-party ones are out of scope;
  a child process and the GitHub Action are seen only through
  `tests/_loom_child.run_loom` and the manual CLI checks; a record is rendered
  without the handler's masking.

## Checks that must pass before handoff

```shell
python -m scripts.message_inventory --check
python scripts/generate_message_reference.py --check
pytest tests/messages tests/test_message_ratchet.py
```

- `tests/test_message_ratchet.py`: the count of uncoded sites per module
  (`tests/fixtures/message-inventory/uncoded.txt`) may fall, never rise. After
  coding sites, `python -m scripts.message_inventory --write-baseline`.
- `tests/messages/test_drift_sources.py`: every entry is used; a module that
  says a family's text goes through the catalogue; each line reads back as its
  entry; the advice fits its actor.
- `tests/messages/test_drift_quotes.py`: skills and docs quote catalogued text.
- `tests/messages/test_generated_reference.py`: generated pages and skill
  copies are current and under the size caps.
- `tests/messages/test_messages_types.py`, `test_messages_trust.py`,
  `test_frames_codes.py`: code grammar, no uncatalogued line that ends in a
  code, frames allow exact codes.

## Traps

- **An exemption list can hide an uncoded line.** The inventory leaves out
  sites matched by `INTERNAL_PAT`, `LIBRARY_PAT`, `DETAIL_EXC` and
  `PASSTHROUGH_PAT` (`scripts/message_inventory/_scope.py`). 17a's review
  found two real uncoded lines (`loom env`'s pipdeptree output, an unknown
  provenance schema) hidden there. A raise a user can reach needs a code even
  if its text looks internal.
- **A relay can drop a code.** A caller that relays a lower layer's line must
  carry the code (`relay_coded_warning`, `code_extra_of`); check that the
  relayed record still has `pitloom_code`.
- **Level and effect go together.** `ERROR` only for a failed operation; a
  recovered problem is `WARNING`; a status or a hint is `INFO`. A message
  that says what Pitloom did instead ("; using X", "; left out") is a
  deviation and needs a `WARNING:`.
- **Do not widen a frame.** A frame (`Build: `, `Git source: `) trusts exact
  codes only; a new code a frame can print is added to that frame's list on
  purpose, with a test.
- **No hand-typed `[code]`** and no second tag in a line.
- **Absent source data is not an error.** A field the source never had stays
  empty, silently; only a read failure or a malformed source warns.
