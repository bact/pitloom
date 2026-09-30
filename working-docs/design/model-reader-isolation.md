---
Created: 2026-09-30
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Model reader isolation (subprocess, pre-1.0)

Status: sketch, not built. Summarised in [roadmap.md](roadmap.md) as one
bullet linking here.

See also: [ai-model-scanning.md](../implementation/ai-model-scanning.md)
(what shipped: the native-reader gate and `--trust-wheel-model`).

## Problem

Some model readers call a native library in Pitloom's own process (today:
fastText's `load_model`; HDF5 and ONNX are candidates). A hostile file can
make the library loop or allocate without bound, and a Python signal handler
does not run while native code holds the interpreter, so Ctrl-C cannot
interrupt it. The size ceilings (`max-model-extract-bytes`, the per-wheel
budget, the 8 MiB inner-member cap) bound bytes read, not what a parser does
with them.

Shipped mitigation: in a wheel, such a format is listed without metadata
unless the caller passes `--trust-wheel-model`. A *project* scan still loads
every model in the directory, because the project is the user's own tree.
That is not safe for an untrusted checkout (`loom project` on a cloned
repository, or CI scanning a pull request from a fork).

## Sketch

Run the gated readers in a child process instead of refusing them:

- One worker per model (or one reused worker with a restart on failure)
  receiving a path, returning the `AiModelMetadata` as JSON on a pipe.
- Limits set by the parent: a wall-clock timeout, and an address-space or
  resident-memory limit (`resource.setrlimit` on POSIX; a Job Object with a
  process memory limit on Windows; macOS ignores `RLIMIT_AS` for some
  allocators, so measure before relying on it).
- On timeout or limit hit: kill the child, keep the format-only entry (the
  same stub as the gate), one `WARNING:` naming format and file.
- Parent never unpickles child output: JSON only, validated against the
  `AiModelMetadata` field set.
- The gate then needs no flag for a wheel; `--trust-wheel-model` would
  become "run in-process" (faster, no isolation) or be retired.

## Open questions

- Worker start cost against the fastText/ONNX import time; a pooled worker
  risks state leaking between models.
- Determinism: the child must not change output bytes (same reader, same
  logs relayed through the scanner's record capture).
- Windows Job Object through `ctypes` or a dependency (`pywin32`), and
  whether `TerminationGuard` should own the child.
- Whether the same worker can also cover the pickle path of `.pt` files
  (fickling already avoids executing it).
- Interaction with `--allow-build`, which already runs a child for a
  different reason.
