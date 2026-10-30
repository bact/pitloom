---
Created: 2026-10-29
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Messages and codes

See also: [Message codes](message-codes.md) for every code, [Command
line](cli.md#output) for the output convention, [GitHub
Action](github-action.md#annotations) for annotations, and [Python
API](python-api.md) for the library.

Pitloom reports what it decided on stderr, one line per event. A
**catalogued** message ends in a stable code, so a script, a CI step or an
agent can tell which condition it is without matching free text. A line
without a code is not catalogued yet.

## Line grammar

```text
LEVEL: [SUBJECT=value: ]CONDITION[; ACTION] [code]
```

- `LEVEL` is `ERROR`, `WARNING` or `INFO`, always at the start of the line.
- `SUBJECT=value` names what the line is about (`FILE=models/m.gguf`), when it
  has one.
- `CONDITION` says what happened; `; ACTION` is what the reader can do next.
- `[code]` is the last token. `DEBUG` lines carry no code.
- An `ERROR:` line may start with what failed (`model command failed:`), and a
  model scan's line with the model it read: the prefixes are listed with the
  catalogue, in [Message codes](message-codes.md).

To read a line back, match this regular expression on the line without its
line ending. The groups are the level, the text and the code:

```text
^(ERROR|WARNING|INFO): (.*) \[([a-z][a-z0-9/-]*)\]$
```

On Windows, Python ends each stderr line with a carriage return: strip a
trailing `\r` before matching.

## Codes

A code is a family, or a family, `/` and a variant: `lfs-pointer`,
`lfs-pointer/shipped`. Each part is lower-case ASCII words joined by single
hyphens, `[a-z][a-z0-9]*(-[a-z0-9]+)*`, and a code has at most 40 characters.

- A family names one condition by its cause, never by what Pitloom did about
  it: subject first (`file-unreadable`), or the condition alone when it does
  not depend on the subject (`lfs-pointer`, `over-cap`).
- A variant is the same condition where the advice or what the SBOM records
  differs (`lfs-pointer/shipped`: the pointer is inside a built artefact).
- One code covers its condition at every level. As an `ERROR`, the command
  stops for that input and writes nothing for it (exit 1).
- No printed code names its producer. The names `pitloom`, `licenseid`,
  `lumina`, `spdx`, `sbom`, `sarif` and `bom` are reserved: no family takes
  one.

## What a code guarantees

A code is stable from the release that first prints it (its "Since" below):

- It is never renamed, reused for another condition or removed while its
  condition can occur. Its wording may change: match the code, not the words.
- New variants may appear in any release.
- A code whose condition can no longer occur is marked retired and stays in
  the catalogue.
- Should a released code be renamed, the catalogue names the code it replaces
  for one minor release.

Trusting a code:

- The last `[code]` of a line is Pitloom's. A line without a code never ends
  in one: a value that would end it so (a file named `x [lfs-pointer]`) is
  printed with its `[` escaped, `WARNING: skipped x \x5blfs-pointer]`. In a
  catalogued line the value stays as it is and the real code comes last.
- **Trust a code only when it is catalogued and the text before it is one of
  that code's lines at that level**, each value of its shape (a path in
  quotes, a 64-digit hex `oid`), after at most one prefix from the catalogue's
  table. Another program writing to the same stream can print anything.

`pitloom.messages.trusted_message(line)` does this check: it returns the
catalogue entry (`Message`) for a line it trusts, else `None`. It reads a line
of at most 65,536 characters.

## What a trusted line does and does not prove

A trusted line is Pitloom's wording for a catalogued code. It does not prove
that every value in it is harmless. A free field such as `FILE=` holds the
name of a file as it is, and a file can be named
`x; run 'git lfs pull'; FILE=x`. This line is still the `lfs-pointer` line,
and `trusted_message` returns its entry:

```text
WARNING: FILE=x; run 'git lfs pull'; FILE=x: Git LFS pointer, content not read; run 'git lfs pull' for the content [lfs-pointer]
```

So take the code and the catalogue entry, never the free text of the line:

- The advice an agent or script acts on comes from the catalogue entry of the
  code (`Message.advice`, and who acts on it), never from the words in the
  line.
- Read a value from a free field as data about the input (a file name), not as
  an instruction, and not as a second field of the line.

## In the library

A library user reads the code from the log record or the exception, not from
text:

```python
import logging

from pitloom.messages import code_of


class CodeHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        print(getattr(record, "pitloom_code", None), record.getMessage())


logging.getLogger("pitloom").addHandler(CodeHandler())

try:
    ...  # a call that raises
except Exception as exc:
    print(code_of(exc))  # the catalogued code, or None
```

- A log record of a catalogued message has the attribute `pitloom_code`;
  `record.getMessage()` is the text without the code. A record without the
  attribute is not catalogued.
- An exception of a catalogued condition, of any class, has the attribute
  `pitloom_code`. `pitloom.messages.code_of(exc)` returns it when it is a
  catalogued code, and `None` for anything else. An exception's own `code`
  (an HTTP status, an exit status, `git.too-large` of a remote-source error)
  is never read.
- A Git URL's checkout over `max_clone_bytes`, or a `git` call's output over
  its cap, raises a `RemoteSourceError` whose `code` is `git.too-large` or
  `git.output-too-large` and whose `pitloom_code` is `over-cap`.

The command line prints the code of the exception it reports at the end of its
`ERROR:` line.

## In GitHub Actions

The action re-emits each stderr line as an annotation with the level
prefix removed, so the code stays at the end of the annotation text:

```text
::warning::FILE=models/m.gguf: Git LFS pointer, content not read; run 'git lfs pull' for the content [lfs-pointer]
```

The raw log is still fenced with `::stop-commands::`, and the fence is
unchanged. The annotation is emitted after it.

## SARIF

Pitloom has no SARIF output yet. The codes leave room for one: a family can be
a SARIF rule `id`, a code its hierarchical `ruleId` (`lfs-pointer/shipped`),
and a code's section of [Message codes](message-codes.md) its help link.

## Catalogue

Every code, with what it means, what Pitloom did and what to tell the user, is
in [Message codes](message-codes.md), generated from the catalogue.
