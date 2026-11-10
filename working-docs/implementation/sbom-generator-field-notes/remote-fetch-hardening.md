---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: one fetch policy for every remote source

See also: [README.md](README.md) (index of these notes),
[../remote-fetch-policy.md](../remote-fetch-policy.md) (what was built, with
the measured Hub answers), [pypi-url-sources.md](pypi-url-sources.md) and
[remote-git-sources.md](remote-git-sources.md) (the routes this policy
spans), [evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)
(caps bound reading, never reporting),
[agent-work-lessons-nov10.md](agent-work-lessons-nov10.md) (how the review
that found several of these items was run).

An SBOM generator that accepts a URL fetches from three kinds of source here:
a Git forge (through `git`), PyPI (through its own HTTP client) and the
Hugging Face Hub (partly through `huggingface_hub`). Facts checked on
2026-11-10 against the code of PR #468, its tests, and the Hub probes recorded
in the linked implementation note. Each item has a "Do:" rule. The items
state principles and the shape of each fix, not a way to reproduce a fault.

## 1. Three routes drift unless one object carries the policy

- **Each route had its own cap, its own offline test and its own URL check.**
  Before PR #468 the Git route had a clone size watch, the new PyPI route a
  download cap, and the Hub route no cap on its metadata files at all. One
  library entry point also read `offline` from its argument only, while the
  command line honoured the configuration file's `offline` too: the same
  setting meant different things on two surfaces. Do: put the cap, the
  offline switch and the caller's URL check in one immutable object
  (`RemoteFetchPolicy`), resolved in one function (flag, then explicit
  configuration, then default), and pass that object to every route; test
  every command and library call of every route against the resolver's
  result for the same inputs.
- **Only the last step differs, and that is fine.** `git` writes a checkout,
  so its cap watches the disk; the HTTP client counts bytes received. The
  number, its name in messages and its default (512 MiB, the model-file
  default) are shared. Do: share the policy and the words; let each route
  measure in the unit it can measure.
- **Shared conditions get shared codes.** Over the cap, a network failure, a
  timeout and offline mode are one catalogue family each across the three
  routes; each route keeps its own line where its subject differs (a clone,
  a download, a file read while the model is still described). A consumer
  that keys on the code (an AI skill explaining the output) then needs one
  rule per condition, not one per route. Do: name a family by its cause
  and reuse it before inventing a route-specific one.
- **Check the URL before the offline switch.** An invalid URL refused under
  offline mode as "offline" hides the first problem the user must fix. Do:
  read and validate the input, then apply the offline refusal, the same order
  on every route.

## 2. A library that fetches for you is outside your policy

- **A convenience download has no cap.** The Hub route fetched `config.json`,
  tokenizer and generation configs, licence files and the cards with the
  library's own download function: no size cap, the weights' deadline, then a
  whole-file parse. A JSON parse can take several times the file's size in
  memory. Do: fetch small metadata files through your own capped client,
  with a cap per kind of file that matches the cap of the reader that will
  parse it, and a deadline sized for metadata, not for weights.
- **A library may send a token where you would not.** The Hub library takes
  the endpoint from an environment variable and, measured on its 2.4.0
  release, sends the token to whatever scheme that endpoint has. Refusing the
  endpoint for your own file fetches is not enough while other calls of the
  same library still go there with the token: the fix asks the Hub nothing
  at all when the endpoint is refused, and a test asserts that no request
  arrives. Do: list every request a third-party client makes on your behalf
  and decide each one; a check on your own requests does not cover the
  library's.
- **What stays outside is written down.** The Hub's API calls (model info,
  file listing) remain library requests: they download no file, and the cap
  and URL check do not reach them. That is stated in the user page and the
  notes. Do: state the boundary of a policy where a user reads it.

## 3. Hosts are a family, matched as DNS names

- **A CDN host is regional.** The Hub's large files redirect to a host under
  `cdn.hf.co` whose first label names a region. An exact host list breaks for
  a user served by another region. The match is a DNS suffix: lower case,
  one trailing dot dropped, every label a valid letter-digit-hyphen label,
  the domain itself or `.` plus the domain at the end, default port only.
  A substring test would accept a name that merely contains the domain. Do:
  match a host family as labels, never as a substring, and test both near
  misses (a longer label ending in the name, the name followed by another
  domain).
- **A host has more than one spelling.** Full-width and ideographic dots, a
  percent-encoded label and an internationalised name all map to an ASCII
  host somewhere in the stack (IDNA in Python, the URL parser in curl). The
  PyPI recogniser normalises them before deciding "is this PyPI"; the Git
  route, which hands the URL to another program, refuses a host not typed in
  ASCII before any process starts, and accepts the `xn--` form. Do: decide,
  per route, whether a non-ASCII spelling is normalised or refused, and do
  it before the first network-facing program sees the URL.
- **A token follows the origin, not the host name.** Scheme, host and port
  must all match the configured origin for an `Authorization` header to be
  added; a CDN, another port or plain http get none. Do: implement the
  same-origin rule once and use it for every credential (URL user
  information on the Git route, the Hub token).

## 4. Server text and subprocess text are input

- **Classify a failure from the tool's own lines, not the server's.** `git`
  forwards the server's messages as `remote:` lines. Matching "connection
  timed out" anywhere in the error text let a server choose the error class
  the user saw. The classifier now reads only git's own `fatal:`/`error:`
  lines, with quoted spans and URLs removed (they can hold server-chosen
  text), and runs git under `LC_ALL=C` so the phrases are the English ones
  it matches. Do: when a subprocess relays remote text, decide from the
  lines the subprocess wrote about itself, in a fixed locale.
- **Every value in a message is escaped, once, by one helper.** File names
  from a JSON API, a redirect target, a server's error body: each passes
  through the same quoting helper that escapes control characters, so no
  remote text can start a new log line. Do: test each emitter with a
  newline in the value.
- **Temporary paths are masked in output.** Each route's download directory
  has a known prefix that the output masks as `<download>`, so two runs of
  one URL give the same messages and the SBOM holds no local path. Do: give
  every temporary directory a recognisable prefix and mask it in one place.

## 5. Cleanup is part of the fetch

- **Clean up when the normal exit never runs.** A build-tool hook staged its
  SBOM in a temporary directory removed in its `finalize()` step, which the
  build tool skips in some modes and on failure; the directory was left
  behind. A finaliser bound to the object's lifetime now removes it too. Do:
  tie a temporary resource to a context manager or a finaliser, not to a
  callback that a caller may skip.
- **One helper creates and removes every temporary directory.** The Git,
  PyPI and Hub routes and the hook share it: a failed removal is one
  `WARNING:` naming the directory, never a failure of an SBOM that
  was already written, and the retry that makes files writable does not
  follow links or Windows junctions out of the directory. Do: share the
  helper; review its retry for what it may touch outside the tree.

## 6. Measured cost of the review that found these

- After the feature's CI was green, four fresh-context reviewers, one per area
  (Hub route, Git route, PyPI route plus HTTP client, hook plus shared
  helpers), each found at least one real fault that the author's tests had
  not exercised: the token sent to the endpoint by the library's own calls,
  metadata parsed whole without a cap, the classifier reading server text,
  the staging leak, host spellings outside the recogniser, a policy object
  that accepted invalid values. Every fault was fixed in the same PR, each
  with a regression test that fails without the fix. Do: run area-split
  reviews after the suite is green, not instead of it; brief each reviewer
  with the threat list of its area.
