---
Created: 2026-11-13
Last-Modified: 2026-11-13
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message frames: `loom <command>:` on every CLI `ERROR:` line

See also: [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(decision I) and [message-catalogue-migration-plan.md](../design/message-catalogue-migration-plan.md)
(catalogue PR 4).

## What was built

Every `ERROR:` line the command line prints starts with the frame of the
command that printed it: `ERROR: loom generate: <text> [code]`. Before a
command is known (a parse error of the top parser, Ctrl-C before the
arguments parse) the frame is `loom: `. The Hatchling hook's one failure line
starts `Pitloom build hook: `. The library prints no `ERROR:` line and puts no
frame on an exception's text. The old `<what> failed:` strings are gone.

## Mechanism

- `pitloom.messages._frames`: `COMMAND_FRAME` (`loom %(subcommand)s: `),
  `TOP_FRAME`, `HOOK_FRAME` and the relay frame; `FRAMES` is the table
  `trusted_message` reads, so a framed line is trusted and a forged one is
  not. `LOOM_COMMANDS` (in `_fields.py`) lists the 16 command paths, held to
  the parser's `prog` values by `tests/messages/test_frames.py`.
- `pitloom.logging_config`: `print_error` prepends the frame of the open
  `error_frame()` (a `ContextVar`); `__main__.main()` and `console_main()`
  open it with `loom: ` and `_run()` sets the command's once the arguments
  parsed, so Ctrl-C is framed by the command that was running. The parser's
  own errors pass their frame explicitly (`_LoomParser.error`), so one line
  never carries two.
- `cli_error_handler` is a bare decorator; it names no text.
- A test forbids `log.error` in the command line code, which would skip the
  frame; `print_error` is the one way.

## Decisions and paths rejected

- Every CLI `ERROR:` line, not only the handler wrapper's: one mechanism, and
  the argparse errors already read this way.
- The command path comes from the sub-parsers' `dest` fields
  (`command`, `fragment_command`, `id_command`), not per-sub-parser defaults,
  whose behaviour differs by Python version.
- `interrupted` stays an uncoded line (framed); a code for it needs an
  exit-130 rule the generated reference's ERROR text does not state.
- The `Build:` and `Git source:` WARNING sub-prefixes are not frames yet:
  they need a WARNING line on each family they relay (PRs 13 and 14).
- Ratchet: a `str(exc)` passthrough forwarding the exception's code is out of
  scope (`{e}`, `{message}` templates), so the handler and the parser add no
  uncoded site; the hook's failure line (`%s%s`) leaves one.
