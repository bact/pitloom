---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# AI model formats, Hugging Face Hub

See also: [AI model formats](ai-model-formats.md) for local model files, and
[AI model formats, fields read](ai-model-formats-fields.md#where-each-field-goes)
for where each value lands.

How Pitloom reads a model from the Hugging Face Hub by its URL or model ID.

## Hugging Face Hub models

Pass a Hugging Face Hub URL or a bare model ID instead of a local file --
no download required for the SBOM itself (needs
`pip install pitloom[huggingface_hub]`):

```bash
loom model https://huggingface.co/mistralai/Mistral-7B-v0.1
loom model Qwen/Qwen3-235B-A22B
```

The `www.huggingface.co` and `hf.co` forms, `http://` and any case of the host
are read as `https://huggingface.co/...`, with one `INFO:` line saying so
([`target-ambiguous/hf-url`](message-codes-targets.md#target-ambiguoushf-url)):
`INFO: URL=<url>: read as Hugging Face model <target> [target-ambiguous/hf-url]`.

This reads the model card, `config.json`, `tokenizer_config.json`,
`generation_config.json` and the Hub's model information, and produces an
`ai_AIPackage` as in the tables in
[What each format holds](ai-model-formats-fields.md#what-each-format-holds).

Those files (and a licence file, and each listed dataset's card) are
downloaded at the revision the Hub's model information names, from the Hub
(`huggingface.co`) and its CDN (`cdn.hf.co` or a host under it, https on the
default port) only, into a temporary directory removed afterwards; none goes
to the `huggingface_hub` cache. Each is capped at the smaller of
`--max-download-bytes` (`max-download-bytes`, 512 MiB by default) and its own
cap (`config.json`, `tokenizer_config.json` and `generation_config.json`
16 MiB; a model or dataset card 1 MiB; a licence file 256 KiB), counted on
the bytes received, and read within 120 s per file; a file over the cap or
the time is left out with a `WARNING:` naming the cap
([`over-cap`](message-codes-files.md#over-cap)) and the rest is read. A local card
over 1 MiB still has its frontmatter read when that closes within the first
MiB; a Hub card over 1 MiB is not downloaded. A Hugging
Face token (`HF_TOKEN`, or the stored `hf auth login`) is sent to the Hub
only, never to the CDN a file is redirected to. With `huggingface_hub`'s
`HF_ENDPOINT` set to another Hub (a mirror), the files are asked of that Hub
instead of `huggingface.co`, the token sent to it only, with an `INFO:`
([`url-moved/hf-endpoint`](message-codes-network.md#url-movedhf-endpoint)); an
`HF_ENDPOINT` that is not https (or holds credentials, a query or a fragment)
is refused, so the token never goes over plain http: nothing is asked of the
Hub (no file, no model or dataset information), the SBOM
holds the model's id and URL only, with one `WARNING:`
([`url-unsafe/hf-endpoint`](message-codes-network.md#url-unsafehf-endpoint)).
`https://HuggingFace.co/` and the port 443 count as the default Hub. A file the
repository does not hold is skipped silently; any other failed download (a
gated or private repository read without access, a network failure, a
timeout, a redirect elsewhere) leaves that file out with a `WARNING:`
carrying the code a Git or PyPI URL fails with
([`download-network-failed`](message-codes-network.md#download-network-failed),
[`download-timeout`](message-codes-network.md#download-timeout),
[`url-unsafe`](message-codes-network.md#url-unsafe)). `--offline` refuses the model
([`offline-unusable`](message-codes-network.md#offline-unusable)), and with
`huggingface_hub`'s `HF_HUB_OFFLINE` set no file is downloaded (one
`WARNING:` each). The Hub's model and dataset information (the model
information also lists the repository's files) are `huggingface_hub`
requests, each with a 30-second socket timeout (per connect or read, no total
deadline), and pass through neither the cap nor the library's `check_url=`,
which every file download does.

`huggingface_hub` also makes one request of its own, which Pitloom does not
ask for and does not read: on the first Hub request of a process it asks the
Hub (`HF_ENDPOINT`, if set) for `/api/agent-harnesses`, a list it uses to tell
whether an AI coding agent runs it, for its own user agent. It sends no token
with it, waits 3 seconds at most, and keeps the answer in
`.agent_harnesses.json` under `HF_HOME` for 24 hours. It is not made with
`HF_HUB_OFFLINE` set, and `HF_HUB_DISABLE_TELEMETRY=1` stops it for Pitloom's
requests (seen with `huggingface_hub` 2.2.0 and 2.4.0).

A failed model or dataset information request is one `WARNING:` that says
what is lost, with the same codes: a request that failed or timed out
(`download-network-failed`, `download-timeout`), `HF_HUB_OFFLINE`
(`offline-unusable`), or an answer that could not be read
([`hub-response-invalid`](message-codes-network.md#hub-response-invalid)):
`WARNING: URL=<url>: the Hub's answer could not be read (<failure>); <outcome>
[hub-response-invalid]`. A model whose information failed keeps its id and
URL and has no author, version, dates, tags or parameter count from the Hub,
and no licence file is looked for, since only the information lists them.

A model read with no revision (the information failed, or the Hub, a mirror
say, stated none) has its files read at the default branch as it is at the
time of the run, which can change between runs. One `WARNING:` says so, once
per read of a model, however many files are read
([`hub-revision-unpinned`](message-codes-network.md#hub-revision-unpinned)):
`WARNING: URL=<url>: the Hub stated no revision; files are read at the default
branch as it is now [hub-revision-unpinned]`. No file is read, and this line is
not said, with the Hub refused (`--offline`, a refused `HF_ENDPOINT`) or
`HF_HUB_OFFLINE` set. There is no option to pin the revision: for a repeatable
result, download the repository at a commit and run `loom model` on the local
copy.

It never opens a model file of the repository, so it reads no per-file
metadata and no hash: a repository whose weights are a `.keras` file gets an
SBOM from its card and configuration files, with no Keras-derived field, no
format and no file entry. Reading the archive's members over HTTP range
requests would be a partial download of the file from the Hub's storage hosts,
which Pitloom does not do. To get a model file's fields, download it and run
`loom model <file>`; for a model file in a Git repository, give its Git URL
(see [SBOM from a Git URL](git-urls.md#model-files)).

For each dataset the model card lists (`datasets:`, else the Hub's
`dataset:*` tags) that is a Hub repository id, Pitloom also reads that
dataset's own card and repository information, the first 20 datasets only. A dataset listed twice (a Hub id is
case-insensitive, so `O/D` is `o/d`) is one dataset, and a card lists at most
1000, with one `WARNING:` when it lists more:

| Dataset field | From | Provenance `Field:` |
| :------------ | :--- | :------------------ |
| licence | the card's `license`; for `other`, its `license_name` and `license_link` (name first, as `name (link)`; a name that reads as an SPDX licence is used alone unless the link reads as a different one, so `apache-2.0` with the Apache link gives `Apache-2.0`; with no name, the link; a name that does not read, such as `Modified MIT License`, keeps its link); `unknown`, `N/A`, `NOASSERTION` or an `other` with no real name or link give none; a list of several gives one `hasDeclaredLicense` each, in order, and a package comment that the card does not say whether they combine as AND or OR | `dataset card license` |
| description | the card's first prose paragraph; a table of contents, key lines (`**Paper:** [...]`), badges, HTML, tables and code blocks are passed over | `dataset card` |
| keywords (not written: SPDX 3.0.1 has no dataset keyword property) | the card's `tags` | `dataset card tags` |
| version | the repository's commit hash | `dataset_info sha` |
| creator (`publishedBy`) | the repository owner | `dataset_info author`, `Method: repository_owner` |

A field the dataset does not state is left out. A failed request (a network
error, a gated, private or deleted dataset) is one `WARNING:` naming the
dataset's page and what is not recorded, as for a model
(`WARNING: URL=<url>: <failure>; <outcome> [download-network-failed]`; never a
path in the local cache); the dataset keeps its name and download URL. A card
that cannot be read or parsed is one `WARNING:` of its own, as a local card is.
These requests run only when the model itself is looked up, so `--offline`
stops them too.
