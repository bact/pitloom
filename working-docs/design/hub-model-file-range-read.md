---
Created: 2026-11-09
Last-Modified: 2026-11-09
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# A Hub model file read by HTTP range requests (evaluated, not built)

See also: [roadmap.md](roadmap.md),
[model-sbom-from-git.md](../implementation/model-sbom-from-git.md) (decision
D10 and the Git route),
[hugging-face-spaces-support.md](hugging-face-spaces-support.md),
[remote-source-ingestion.md](remote-source-ingestion.md),
[known-bugs/ai-models-readers-and-metadata.md](known-bugs/ai-models-readers-and-metadata.md)
(the open entry),
[archive-member-followups.md](archive-member-followups.md).

> **Status (2026-11-09):** evaluated and not built. The user docs say what
> the Hub route does not read; this note holds the design that would make it
> safe, if the gap is worth the cost.

## The gap

The Hugging Face route (`loom model huggingface.co/<org>/<name>`) reads the
repository's metadata: the model card, `model_info`, the config JSON files
(`config.json`, `tokenizer_config.json`, `generation_config.json`) and the
licence files. It never opens a model file and reads no per-file metadata or
hash. A repository whose weights are one `.keras` file therefore gets an SBOM
with no Keras-derived field: the format is unknown, there is no file entry and
no hash. The same holds for any format; Keras is the case where the missing
fields live in two small ZIP members.

## What a range read would do

A `.keras` file is a ZIP archive. Its central directory is at the end, and
`metadata.json` and `config.json` are small. A reader could fetch the last
bytes, find the two members' offsets and fetch only those, without the
weights (`model.weights.h5`, usually most of the bytes), then run the existing
Keras reader on them.

## Why it was not built

The cost is in what it is, not in the parsing:

- **A partial content fetch from a second host.** A Hub file URL answers with a
  redirect to the storage host (the LFS/CDN host, `cas-bridge` or `cdn-lfs`
  hostnames). Reading through `huggingface_hub` follows those redirects
  internally.
- **No Pitloom HTTP client.** The Git route has `check_url` per redirect hop and
  a size budget; the Hub route uses `huggingface_hub`, which gives Pitloom no
  hop to check, no byte budget and no control of which credentials go to which
  host.
- **It contradicts the documented rule** that Pitloom does not download model
  files (a Hub SBOM needs no weights). A range read is a download of part of a
  model file, from a host the user did not name.

Workaround, documented in `docs/ai-model-formats.md`: download the file, then
`loom model <file>`; for a model file in a Git host's repository, give its Git
URL.

## The design that would make it acceptable (gated follow-up)

Build it only with all of the following:

1. **An explicit opt-in flag** (CLI, library and Action alike; no
   `[tool.pitloom]` key, as for `--trust-wheel-model`): a config file in a
   repository must not be able to switch it on.
2. **Pitloom's own client** (`urllib` through the existing URL helpers), not
   `huggingface_hub`'s file download.
3. **Manual redirect hops, at most 5**, each target passed to `check_url`
   (library) and to the scheme/host rules before it is requested: a redirect to
   another scheme, a private address or a page that is not a file is refused,
   logged and raised.
4. **No `Authorization` header to the CDN host.** A token goes to the Hub host
   only; the signed storage URL carries its own authorisation.
5. **A request and byte budget** for the whole run (for example 8 requests and
   a few MiB), checked before each request; exceeding it is a stub with a
   `WARNING:`, not a silent truncation.
6. **End-of-central-directory search over the last 64 KiB plus 22 bytes** of
   the file, then only the central directory and the two members: `metadata.json`
   and `config.json`, each within the existing 8 MiB member cap, the whole
   archive within the existing ZIP entry and central-directory caps (read the
   caps the full reader applies, from the same constants).
7. **Abort if the server ignores `Range`.** A `200` answer without a
   `Content-Range` header means the server is sending the whole body: stop
   reading at once and close the connection; never stream the weights.
8. **Declared sizes never gate a cap or a read.** The `Content-Length` of the
   file, the sizes in the ZIP's central directory and the Hub's `size` are
   declared values: record them as declared with their source, if at all, and
   bound the reading by the budget, not by them (the evidence-level rule in
   [evidence-levels.md](evidence-levels.md)).
9. **A loopback test server** with `Range` support and a `302` to a second
   loopback port (`tests/_git_http_server.py` is the model), covering: the
   happy path, a server that ignores `Range`, a redirect loop, a redirect to a
   refused address, a budget overrun, a truncated central directory and a
   member over the cap.
10. **Docs wording to change** with it: `docs/ai-model-formats.md` (the Hub
    paragraph says no model file is opened), `docs/ai-model-scan-limits.md`
    (the target table: Hub models are not scanned) and the `sbom-generate` skill
    (`known-limitations.md`, the Hub line), plus a new catalogue message for a
    range read that was refused or fell back.

## Result of the evaluation

Not built for 0.23.4. The Git route was fixed instead (a `.keras` file in a Git
repository is read in full), and the Hub gap is documented with the
workaround.
