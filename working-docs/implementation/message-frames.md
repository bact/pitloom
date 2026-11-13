---
Created: 2026-11-13
Last-Modified: 2026-11-14
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message frames: `loom <command>:` on every CLI `ERROR:` line

See also: [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(decision I) and [message-catalogue-migration-plan.md](../design/message-catalogue-migration-plan.md)
(catalogue PR 4); frames for PRs 5 to 18:
[message-frames-forward.md](../design/message-frames-forward.md).

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
- An `ERROR` record logged with `log.error` is framed by the formatter of
  `configure_logging` from the same `ContextVar`, so it reads as
  `print_error`'s line (`tests/messages/test_frames.py`); no test forbids
  `log.error` in the command line code (`cli/commands/verify_wheel.py:103`
  uses it). `print_error` stays the preferred way.

## Decisions and paths rejected

- Every CLI `ERROR:` line, not only the handler wrapper's: one mechanism, and
  the argparse errors already read this way.
- The command path comes from the sub-parsers' `dest` fields
  (`command`, `fragment_command`, `id_command`), not per-sub-parser defaults,
  whose behaviour differs by Python version.
- `interrupted` stays an uncoded line (framed); a code for it needs an
  exit-130 rule the generated reference's ERROR text does not state.
- The `Build:` and `Git source:` WARNING sub-prefixes are not frames yet:
  they need a WARNING line on each family they relay (PRs 13 and 14), and a
  frame restricted to the families it may precede
  ([message-frames-forward.md](../design/message-frames-forward.md)).
- `option-no-effect` keeps the literal prefix in its two templates
  (`Options: `, `Build: `); its helpers take `build: bool`, not a prefix
  string. PR 14 turns `Build: ` into a frame and collapses the two templates
  into one, same code and same text.
- Ratchet: the two relays are out of scope by the shape of their code, not by
  a variable's name (`scripts/message_inventory/_relay.py`): the handler's
  `print_error(str(e) or type(e).__name__, code=code_of(e))` in an
  `except Exception as e` (text and code both the caught exception's, its
  raise the counted site), and `argparse`'s own text in the `error(self,
  message)` override of an `ArgumentParser` subclass, said by `print_error`.
  Both need the call in the binder's own body (no nested function, lambda or
  comprehension) and no rebinding of the name there. A line forwarding a
  code but adding its own text, or under a narrower `except`
  (`loom id generate`'s), still counts. The handler and the parser so add no
  uncoded site; the hook's failure line (`%s%s`) leaves one. Rejected: a
  `{e}`/`{message}` template exemption, which would have exempted any new
  `log.warning(f"{message}")` in the tree.
- An exception with empty text is said by its class name
  (`ERROR: loom model: RuntimeError`), so the line never stops at the frame.
