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
(`_http_fetch.fetch_capped`): a cap counted on the bytes received, a host
allowlist checked on every hop, a deadline, chunked reads. Each file lands
in its own folder of one temporary directory (`pitloom-hf-`, masked as
`<download>` in messages) removed when the read ends. `model_info()`,
`dataset_info()` and `list_repo_files()` remain `huggingface_hub` API
requests: they download no file, and neither the cap nor `check_url`
reaches them (documented).

### Per-kind caps and the metadata deadline (review round A)

A review found each metadata file downloaded under the 512 MiB weights cap
and then loaded whole (`json.load` of a text file takes about ten times its
size; `ModelCard.load` read the whole card), each with the 30-minute
weights deadline. Now each file is downloaded under the smaller of
`max-download-bytes` and the cap of its kind (`_hub_files.file_cap`), the
same cap its reader then reads within, and named as the one that bound
(the setting's name when it is the smaller or equal, since raising it is
what would help):

| File | Kind cap | Why this one |
| :--- | :------- | :----------- |
| `config.json`, `tokenizer_config.json`, `generation_config.json` | 16 MiB `Hub-JSON` (`_hub_files.HUB_JSON_CAP`) | parsed whole (bytes, so a BOM is accepted); real ones are KiB, a `tokenizer_config.json` with thousands of added tokens about 1 MiB (not measured here); the PyPI JSON cap (64 MiB) would let one file take ~700 MB parsed |
| model card `README.md` | 1 MiB `model-card` (`enrich.readme.MODEL_CARD_CAP`) | the local model card's cap; read by `enrich.readme.read_card` with a Hub `CardKind`, as the dataset card already was |
| licence files | 256 KiB `license-detection` (`_license_detect.LICENSE_FILE_CAP`) | every other licence reader's cap (project, wheel, sdist), read by `read_license_file`: one cap per kind of input, not the card's 1 MiB the review suggested |
| dataset card `README.md` | 1 MiB `dataset-card` | its reader's cap, unchanged |

A file over its kind cap is left out with one `over-cap` `WARNING:`
(`FILE=<repo>/<file>: larger than the <n>-byte <cap> cap; <what> not read`).
Unlike a local card, which keeps a frontmatter closed within its first MiB,
a Hub card over 1 MiB is not downloaded at all: the download keeps no
partial file it could tell from a whole one. The deadline is
`_hub_files.METADATA_DEADLINE_SECONDS`, a JSON API request's 120 s.

The model card is no longer parsed by `huggingface_hub.ModelCard`: the
frontmatter is the file's own YAML mapping (`tags` still made a list
without repeats, as the binding gave it). So a `model-index` is kept as the
card states it (the binding rebuilt it, and refused the whole card for one
it could not parse), a card whose frontmatter is not a mapping keeps its
text, and malformed YAML is one `card-malformed` `WARNING:` with the text
(and description) kept.

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

The one CDN host seen was `us.aws.cdn.hf.co`. A plain GET of the signed CDN
URL serves a Xet file (the library falls back to it without `hf_xet`), so no
Xet client is needed. The CDN host is regional (the `xet-bridge-us` path
names the region), so a file may be sent to another region's host: the
allowlist (`_hub_files.file_policy`) is the Hub's own host plus any host
under `cdn.hf.co` (`_hub_files.CDN_DOMAINS`), matched by
`_http_fetch.under_domain` as a DNS suffix: lower case, one trailing dot
dropped, every label a letter-digit-hyphen label, `cdn.hf.co` itself or
`.cdn.hf.co` at the end, on the default https port only. Not `hf.co` broadly
(`cdn-lfs.hf.co` and the rest stay refused), and no substring match
(`evilcdn.hf.co`, `cdn.hf.co.evil.example` are refused; tested). No measured
metadata file of the surveyed repositories left `huggingface.co`.

A review asked whether an LFS-tracked file not migrated to Xet would go to
another CDN (`cdn-lfs*.hf.co`, `cas-bridge.xethub.hf.co`). Probed on
2026-11-10 (`paths-info` API, then one ranged GET without a token):

| Request | Answer |
| :------ | :----- |
| `paths-info` of LFS files in `google-bert/bert-base-uncased`, `hf-internal-testing/tiny-random-bert`, `julien-c/dummy-unknown` (old, small repositories) | every LFS file carries a `xetHash`: none found that is LFS-only |
| `huggingface.co/julien-c/dummy-unknown/resolve/main/flax_model.msgpack` (58 KB, LFS pointer, Xet-backed) | `302` to `https://us.aws.cdn.hf.co/xet-bridge-us/<repo-id>/<xet-hash>?...&Expires=&Policy=&Signature=&Key-Pair-Id=`, `X-Linked-Size: 58499`, `X-Xet-Hash`; then `206` (range) |

An LFS file now goes to the same `cdn.hf.co` host as a Xet one; no
`cdn-lfs` or `cas-bridge` host appeared, so `CDN_DOMAINS` is unchanged. If
one ever does, the read warns `url-unsafe` for that file and goes on.

### `HF_ENDPOINT`

The Hub is `huggingface_hub.constants.ENDPOINT` (`_hub_files.hub_endpoint`),
the value the library itself resolved from `HF_ENDPOINT` at import (or the
staging Hub under `HUGGINGFACE_CO_STAGING`), so the files and the
`model_info()` API calls go to one Hub; re-reading the variable could
disagree with the library once it is imported. Its host (with its port when
not 443) replaces `huggingface.co` in the allowlist, the resolve URL is
built on it (a path prefix kept, as the library concatenates), the token
goes to its origin only, and `cdn.hf.co` stays allowed. A Hub other than the
default is one `INFO:` per read (`url-moved/hf-endpoint`).

`huggingface_hub` 2.4.0 takes an `http://` endpoint as given and sends the
token to it. Pitloom does not: an endpoint whose scheme is not in
`_http_fetch.ALLOWED_SCHEMES` (https), or holding user information, a query
or a fragment, is refused with one `WARNING:` per read
(`url-unsafe/hf-endpoint`, the credentials masked) and nothing is asked of
the Hub (`HubFiles.asks_hub`): no file, and no `model_info()`,
`list_repo_files()` or `dataset_info()`, which `huggingface_hub` would send
to the same endpoint with the token (review round A reproduced that with a
loopback http endpoint; a test now asserts it sees no request). The model
keeps its id and URL only, and no other line is said (the "without a
pinned revision" warnings were said for downloads that never happened).
Falling back to `huggingface.co` would contradict the user's choice of Hub.
A plain-http mirror is a loopback or test setup, where losing the metadata
is cheap; a token over http is not. The default Hub however spelt
(`https://HuggingFace.co/`, port 443) is the default, said nothing of; a
look-alike (`huggingface.co.evil.example`, `huggingface.co:8443`) is another
Hub, one `INFO:`; `https://huggingface.co@evil.example` is refused (user
information).

### Token

The token `huggingface_hub` would send (`HF_TOKEN`, else the stored login,
none under `HF_HUB_DISABLE_IMPLICIT_TOKEN`; `huggingface_hub.get_token()`) is
an `Authorization: Bearer` header sent only to a URL on the Hub's origin,
`https://huggingface.co:443` or the `HF_ENDPOINT` one
(`_hub_files.hub_credential`, `_http_credential.Credential.header_for`), the
Git route's same-origin rule
for user information: never to the CDN (another host), another port, or
http. The `resolve-cache` hop is on the origin and keeps it, as a private or
gated repository needs. A test asserts the fake CDN saw no `Authorization`.

### Behaviour kept and changed

- `--offline` (and the config's `offline`) still refuses the model before any
  request, now `huggingface.offline` with `offline-unusable`, raised by
  `read_huggingface(policy=...)` itself (it was a `ValueError` in
  `generate_model_sbom()`).
- `HF_HUB_OFFLINE` was honoured by `hf_hub_download` (cache only); now no
  file is downloaded and each is one `offline-unusable` `WARNING:`. Nothing
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
| offline | `offline-unusable` (new) | `URL=<url>: network access is forbidden (offline mode); nothing fetched` | the same | the same (`ERROR`); `WARNING:` under `HF_HUB_OFFLINE` |

`offline-unusable`: named by its cause, offline mode (the subject), with
`unusable` from the closed condition vocabulary (it has no "forbidden"): the
target cannot be used with offline mode on, as `temp-dir-unusable` names a
directory that cannot take a file.
`RemoteSourceError.code` keeps its route prefix (`git.*`, `pypi.*`,
`huggingface.*`); `pitloom_code` is the shared code. A git failure is
`download-network-failed` only when one of git's own `fatal:`/`error:`
lines (never a `remote:` line, which is the server's text; quoted spans and
URLs removed first; under `LC_ALL=C`) matches a transport failure
(`_git_run._NETWORK_FAILURE`: a name that does not resolve, a refused,
reset or timed-out connection, TLS, an empty reply, `RPC failed; curl N`,
an HTTP 5xx); a repository, ref or sign-in the server refused, or an HTTP
4xx, keeps no code (tested both ways). The
`warn_instead` helper says a catalogued fetch error again as its family's
`WARNING:` line for a caller that reads on (the Hugging Face route).

Left as is: the Git route's redirect probe refusal and `git.too-many-redirects`
are not catalogued (`url-unsafe` would fit; not asked).
