---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# One fetch policy and shared codes for the Git, PyPI and Hugging Face routes

See also: [pypi-url-targets.md](pypi-url-targets.md) (the PyPI route and
the download cap, items 20-21), [remote-git-ingestion.md](remote-git-ingestion.md)
(the Git route) and
[message-catalogue-families.md](message-catalogue-families.md) (the
catalogue's families).

Built in PR #468 (user decision, 2026-11-10), in three parts.

## 1. Hugging Face metadata files under the download cap

The Hugging Face route downloaded `config.json`, `tokenizer_config.json`,
`generation_config.json`, licence files and the model and dataset cards with
`huggingface_hub.hf_hub_download` (and `ModelCard.load`) into the library's
cache, with no size cap. They are now fetched by
`extract/remote/_hub_files.HubFiles` through the hardened client
(`_http_fetch.fetch_to_file`): the `max-download-bytes` cap counted on the
bytes received, a host allowlist checked on every hop, the deadline, chunked
reads. Each file lands in its own folder of one temporary directory
(`pitloom-hf-`, masked as `<download>` in messages) removed when the read
ends. The per-file read caps (the dataset card's 1 MiB) stay on top.
`model_info()`, `dataset_info()` and `list_repo_files()` remain
`huggingface_hub` API requests: they download no file, and neither the cap
nor `check_url` reaches them (documented).

### Measured (2026-11-10, huggingface_hub 2.4.0)

The library builds `{ENDPOINT}/{repo}/resolve/{quote(revision, safe="")}/{quote(filename)}`
(`/datasets/{repo}/...` for a dataset), with `ENDPOINT` from `HF_ENDPOINT`,
default `https://huggingface.co`. Its `_httpx2_follow_hub_redirects_with_backoff`
follows a redirect that stays on a Hub origin (`huggingface.co`, `hf.co`,
the staging host, the configured endpoint) with the token, and stops at any
other host: there it downloads without the `authorization` header. It names
no CDN host. Probed with `curl`:

| Request | Answer |
| :------ | :----- |
| `huggingface.co/openai-community/gpt2/resolve/main/config.json` | `307`, relative `Location: /api/resolve-cache/models/openai-community/gpt2/<sha>/config.json?...`, `X-Repo-Commit`, `X-Linked-Size: 665`; then `200`, `Content-Length: 665` |
| same at the pinned commit | the same chain |
| `hf.co/...` | `307` to `https://huggingface.co/...` |
| `README.md`, `generation_config.json`, `tokenizer_config.json`, `LICENSE` of six popular repositories | each a relative `307` to `/api/resolve-cache/...` on `huggingface.co` (or `404`) |
| `model.safetensors` (HEAD only, Xet storage) | `302` to `https://us.aws.cdn.hf.co/xet-bridge-us/...?<signature>`, `X-Xet-Hash`, a `Link` to `cas-server.xethub.hf.co` |
| a gated repository's `config.json` (no token) | `401`, `X-Error-Code: GatedRepo`; its `README.md` `200` |
| a missing repository | `401` (`Invalid username or password`) |
| a missing file, or a missing revision | `404`, `X-Error-Code: EntryNotFound` |

So `FILE_HOSTS` is `huggingface.co` and the one CDN host seen,
`us.aws.cdn.hf.co`. A plain GET of the signed CDN URL serves a Xet file (the
library falls back to it without `hf_xet`), so no Xet client is needed. The
CDN host is regional: from another region the Hub may name another one, and
such a file is refused (`url-unsafe` `WARNING:`, the file left out). No
measured metadata file of the surveyed repositories left `huggingface.co`.
`HF_ENDPOINT` is not followed for these files (the base is fixed); the API
requests still follow it.

### Token

The token `huggingface_hub` would send (`HF_TOKEN`, else the stored login,
none under `HF_HUB_DISABLE_IMPLICIT_TOKEN`; `huggingface_hub.get_token()`) is
an `Authorization: Bearer` header sent only to a URL on the origin
`https://huggingface.co:443`
(`_http_credential.Credential.header_for`), the Git route's same-origin rule
for user information: never to the CDN (another host), another port, or
http. The `resolve-cache` hop is on the origin and keeps it, as a private or
gated repository needs. A test asserts the fake CDN saw no `Authorization`.

### Behaviour kept and changed

- `--offline` (and the config's `offline`) still refuses the model before any
  request, now `huggingface.offline` with `network-unusable`, raised by
  `read_huggingface(policy=...)` itself (it was a `ValueError` in
  `generate_model_sbom()`).
- `HF_HUB_OFFLINE` was honoured by `hf_hub_download` (cache only); now no
  file is downloaded and each is one `network-unusable` `WARNING:`. Nothing
  is read from the `huggingface_hub` cache any more.
- A file the repository does not hold (`404`) is absent, silently; it was a
  `DEBUG` line for the JSON files and a `WARNING:` for a missing model card.
  Any other failure (a gated repository's `401`, a network failure, a
  timeout, the cap, a refused redirect) is now one catalogued `WARNING:` per
  file, with the shared code; the JSON files were `DEBUG` before because
  `hf_hub_download` raised alike for a missing file and a failure. A gated
  repository read without access thus warns once per file it lists.
- The model card is read at the revision `model_info()` states (it was read
  unpinned).
- `generate(check_url=)` reached no Hugging Face request before; it now sees
  every file URL and redirect target, and its exception stops the read.

## 2. One policy resolved in one place

`core/fetch_policy.RemoteFetchPolicy(max_bytes, offline, check_url)`
(frozen) is made only by `core.config_cascade.resolve_fetch_policy`
(argument > explicit config > default; it replaced `resolve_download_cap`).
`generate_git_sbom()`, `generate_pypi_sbom_with_download()`,
`generate_model_sbom()` and the CLI's `run_remote` call it;
`fetch_git_project(policy=)`, `fetch_pypi_file(policy=)` and
`read_huggingface(policy=)` take it. The public generators keep their
`offline=`, `max_download_bytes=` and `check_url=` keywords. Only the last
step differs: `GitRunner(max_bytes)` watches the checkout's disk; the HTTP
client counts bytes received.

Drift found while wiring it: `generate_git_sbom()` passed its `offline`
argument alone and ignored `pitloom_config`'s `offline`, which the CLI
honoured. `tests/test_fetch_policy_surfaces.py` holds every library call and
command of the three routes to the policy the resolver makes for the same
flag, config and argument.

## 3. Shared codes

One family per shared condition, each route keeping its own line where its
subject or action differs (`messages/_remote_fetch.py`, moved out of
`_pypi.py`):

| Condition | Family | Git | PyPI | Hugging Face |
| :-------- | :----- | :-- | :--- | :----------- |
| over the cap | `over-cap` | `CLONE_LINE` (`git.too-large`) | `DOWNLOAD_LINE` (`pypi.too-large`) | `KEY_LINE` `WARNING:` |
| request failed | `download-network-failed` | `git <command> failed: <error>; nothing fetched` | `URL=<url>: <failure>; not read` | the same, `WARNING:`, `; <outcome>` |
| timeout | `download-timeout` | `git <command> did not finish within <seconds> seconds; stopped` | `URL=...: no complete answer within ...; not read` | the same, `WARNING:` |
| offline | `network-unusable` (new) | `URL=<url>: network access is forbidden (offline mode); nothing fetched` | the same | the same (`ERROR`); `WARNING:` under `HF_HUB_OFFLINE` |

`network-unusable`: the closed vocabulary has no "offline" or "forbidden";
`unusable` (the subject cannot be used here) fits the network with offline
mode on, as `temp-dir-unusable` fits a directory that cannot take a file.
`RemoteSourceError.code` keeps its route prefix (`git.*`, `pypi.*`,
`huggingface.*`); `pitloom_code` is the shared code. A git failure is
`download-network-failed` only when one of git's `fatal:`/`error:`/`remote:`
lines matches a transport failure (`_git_run._NETWORK_FAILURE`: a name that
does not resolve, a refused, reset or timed-out connection, TLS, an empty
reply, `RPC failed; curl N`, an HTTP 5xx); a repository, ref or sign-in the
server refused, or an HTTP 4xx, keeps no code (tested both ways). The
`warn_instead` helper says a catalogued fetch error again as its family's
`WARNING:` line for a caller that reads on (the Hugging Face route).

Left as is: the Git route's redirect probe refusal and `git.too-many-redirects`
are not catalogued (`url-unsafe` would fit; not asked).
