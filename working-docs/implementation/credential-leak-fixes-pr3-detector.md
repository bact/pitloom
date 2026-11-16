<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-16
Last-Modified: 2026-11-16
-->

# Credential detector and masker: PR 3 decisions

See also: [credential-leak-fixes.md](credential-leak-fixes.md) (what was
built, and the gaps still tracked) and
[credential-detect-and-refuse.md](../design/credential-detect-and-refuse.md)
(the plan).

The detector and masker extras, third-party log masking and wheel patterns
of PR 3, with the evidence for each decision.

- **Names** (checked 2026-11-16 against `is_secret_name`): `Signature`
  (CloudFront, any case, and `CloudFront-Signature`), `X-Amz-Signature`,
  `X-Amz-Credential`, `X-Amz-Security-Token` and `;jsessionid=` were
  refused already; nothing added. Not added, as no secret: `state`
  (RFC 6749 10.12: a value binding the redirect to the user agent's
  session against forgery, worthless once the flow ends; `?state=CA` is a
  common address or map parameter, so a weak name would warn on many
  ordinary URLs); CloudFront `Policy` (base64 JSON of the resource, expiry
  and IP condition, readable by anyone holding the URL; the signature
  beside it is what grants access) and `Key-Pair-Id` (the id of the
  public key). Masking `Signature` alone disables the signed URL. Pinned
  in `test_url_masking_nested_values.py`.
- **Decoded query values**: each query or fragment parameter value of a
  URL field, and its whole fragment, is read after each decode that
  changes it, at most `PURL_DECODE_ROUNDS` (5), as a whole URL, scp-style
  address or access token (`_hits._decoded_value_hits`); a decoded level
  is not decoded again (each depth of the outer value is a full decode),
  and an identifier's `embedded` reading skips it (it reads every depth of
  the whole text already). No false positive on ordinary encoded values
  (`?next=https%3A%2F%2Fexample.org%2Fa`, `a%40b.org`). Time at 1 MiB,
  before and after (macOS, Python 3.10, detector as a value): `query-many`
  0.41 to 0.75 s, `query-nested` 0.29 to 0.63 s, `query-deep` 0.38 to
  0.46 s; growth-ratio rows `query-deep`, `query-many`, `query-nested`,
  `fragment-deep`, `break-password` added.
  Review round: a decoded level that is no URL is also read for its
  parameters (`_hits._param_hits`, the URL scan's name rules on `"?" +
  value`), so a relative target (`?next=%2Fcb%3Ftoken%3DT`), a fragment
  query (`#access_token%3DT`) and `?q=a%26token%3DT` are found; ordinary
  `next=%2Fa%2Fb`, `q=a%26b%3Dc` are not. Rows `query-relative`,
  `query-marks`, `deep-segments` added. A credential encoded six times or
  more is still no hit, but the masker now prints any query or fragment
  value still encoded after five decodes as `***`
  (`_mask._masked_deep_values`).
  Second review: `_param_hits` read a decoded value as a query from its
  start (`"?" + value`), so `?next=access_token%3DT` was found but its
  `shown` printed the secret (the masker reads no parameter at a value's
  start). Ruling: a parameter value is no query; a name at its start is no
  parameter, decoded or plain (`?next=access_token=T` was never a hit).
  Evidence: search and filter values hold `name=value` pairs whose names
  are whole secret names (`?filter=auth%3Dbasic`, `?u=key%3Dvalue`,
  `?q=sig%3Dx`), which a start-of-value rule would refuse. A fragment is
  still read from its start (`#access_token%3DT`), as the plain
  `#access_token=T` is. A differential test over the decoded corpus asserts that no
  finding's `shown`, masked text or log line holds the secret, fully
  decoded. Decoys (a secret at each depth 1 to 5, then one at 6 to 11)
  spent the masker's five rounds, so a deeper value was printed one decode
  from readable; now, when every round showed a credential, each value
  still encoded is printed as `***` (`_mask._still_encoded`), else only one
  still encoded after five more decodes (`_deeper_than_read`). Growth row
  `decoys` added; its 1 MiB run takes about 5 s for the detector (the
  masker's own cost on a text that holds a hit), so it is not a 1 MiB row.
- **False positives kept** (no safe rule): `https://h:?mirror@cdn` and
  `https://u:?pw@h` have one shape, a name, `:`, a break and an `@`; a
  dotted name is no host proof (`first.last:?pw@h`), so both are found
  and a message hides `h`. `https://h:/path?x@y` is neither found nor
  masked (the `/` ends the authority). `?v=10%3A30%40ab%3Ac` decodes to
  `10:30@ab:c`, an scp-style password by shape, as the plain spelling is
  already. Both are listed in `docs/url-credentials.md`.
- **`?` or `#` password**: `urllib.parse.urlsplit("https://u:?pw@h/x")`
  gives netloc `u:` and query `pw@h/x` (no user name); WHATWG's authority
  state and git's `credential_from_url` (`strcspn(cp, "/?#")` before the
  `@`) end the authority at the `?` too, so no client sends it as a
  password. The detector reads it as one anyway (the value states it); the
  Git split keeps the clients' reading (see "Empty port").
- **Third-party logs**: `MaskingRecordFactory` masks a record of
  `urllib3`, `requests` or a child logger when its text holds a credential
  (`log_masking.mask_third_party_record`): URLs as a log line masks them,
  plus secret parameters without a URL (`mask_free_params`: urllib3 logs
  the request target, `"GET /x?token=T HTTP/1.1"`, and `Retry` lines name
  `url='/x?...'`). A clean record keeps its `msg` and `args`; a masked one
  gets new ones (copy-on-write). No new process-global state: the factory
  `configure_logging()` installs already, which `tests/conftest.py`
  resets. Every entry point calls `configure_logging()` first (checked:
  `__main__._run`, `plugins/hatch.py`, each public generator, `embed`).
  Review round: every log text (`log_masking.masked_text`: a message, a
  traceback, `stack_info`, of a `pitloom` or a third-party record, and
  `print_error`) is masked by one call, `masked_given_path(...,
  free_params=True)`, so secret parameters without a URL are masked at
  every decode depth (`"GET /x?next=/cb%3Ftoken%3DT"`, an exception's
  `url: /y?token=T`). Only a parameter named like a secret is touched:
  `?page=2&sort=asc` in a traceback's source line is kept. A third-party
  record whose arguments cannot be formatted gets the same fixed text as
  a `pitloom` one (`_set_unformatted`), so `Handler.handleError` never
  prints its raw arguments.
- **Wheel patterns** (`verify-wheel`, `validate-wheel`, `embed-wheel`):
  `glob.glob` raises `RecursionError` on a pattern with more wildcard
  directories than the recursion limit (`'*/' * 1200 + '*.whl'`, no
  directory need exist); a bracket in a name (`d[1]/x.whl`) is a pattern
  that matched nothing, so an existing file was refused; a long name and a
  path 1000 levels deep without wildcards expand fine. Now the first is
  `input-not-found` with its own line, the pattern quoted; the second
  falls back to the file named as typed when the pattern matches nothing
  (as a shell does).
