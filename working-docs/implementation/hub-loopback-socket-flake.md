---
Created: 2026-11-24
Last-Modified: 2026-11-24
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Hub loopback socket flake (PIT-20): cause, fix and lessons

See also:
[findings-to-fix-first.md](../design/provenance-taxonomy/findings-to-fix-first.md)
(row PIT-20),
[recurring-bug-patterns-test-harness.md](recurring-bug-patterns-test-harness.md)
(the short rule, with the other test harness patterns),
[testing-and-review-policy.md](testing-and-review-policy.md).

**Status:** fixed by pull request 528, merged 2026-11-24. One matter of
production behaviour is open (the last section but one).

Each fact says how it is known: *run here* (2026-11-24, Python 3.10.18),
*read here* (the library's source, `huggingface_hub` 2.2.0, in the
repository's environment), or *fix session* (measured on 2026-11-23 by
the session that made the fix, with `huggingface_hub` 2.4.0 on Python
3.13 and 2.2.0 on Python 3.10; not run again here).

## What was seen

- CI of pull request 519 (documents only), run 45168805298: four tests
  of `tests/extract/remote/test_hub_loopback.py` failed on "Test on
  Python 3.13 (macos-latest)" with `ResourceWarning: unclosed
  socket.socket`, reported at a line of
  `huggingface_hub/utils/_detect_agent.py` and made a failure by
  `filterwarnings = error` (*fix session*, from the log).
- The rerun did not pass: attempt 2 failed in the same way on "Test on
  Python 3.11 (windows-latest)", one test. `gh run view <id> --log`
  shows the last attempt; `--attempt 1 --log` shows the first (*fix
  session*).
- CI had `huggingface-hub` 2.4.0 on every leg (*fix session*).

## Cause

1. The library builds its user agent with `detect_agent()`. The first
   call in a process, with no cache file under `HF_HOME` younger than
   24 hours, runs `_fetch_registry()`: a `GET` of
   `{constants.ENDPOINT}/api/agent-harnesses` with a short timeout. Any
   exception is swallowed and logged at debug level. It is skipped when
   `constants.HF_HUB_OFFLINE` is set. The source calls it "best-effort
   telemetry" (*read here*).
2. `constants.ENDPOINT` is the real Hub. The loopback tests patch the
   endpoint of the API object only, so this request left for a host
   that is not this machine (*fix session*).
3. The loopback guard `_loopback_only` in `tests/conftest.py` refused
   that `connect` by raising `_NetworkBlockedError`, a `RuntimeError`.
4. `socket.create_connection` closes its socket on an `OSError` only.
   With another exception the socket stays open, held by the traceback,
   and Python reports it when the object is freed: here at the end of
   the library's `except` block, which is why the warning named a line
   of the library (*run here*, the probe below).
5. The registry is cached per process. Only the first detection of an
   xdist worker fetches, and only if that falls in a `loopback` test is
   there a socket to leak. Hence now and then (*fix session*).

The probe, standard library only, no packet leaves the machine:

```python
import socket, sys, warnings

warnings.simplefilter("always")
seen = []
warnings.showwarning = lambda m, *a, **k: seen.append(str(m))


def run(exc_type, close_first):
    real = socket.socket.connect

    def connect(self, address, *args):
        if close_first:
            self.close()
        raise exc_type("refused by the guard")

    socket.socket.connect = connect
    seen.clear()
    try:
        try:
            socket.create_connection(("192.0.2.1", 443), timeout=1)
        except Exception:
            pass
    finally:
        socket.socket.connect = real
    return [s for s in seen if "unclosed" in s]
```

| Exception raised by `connect` | Socket closed first | Unclosed socket reported |
| --- | --- | --- |
| `RuntimeError` | no | yes |
| `RuntimeError` | yes | no |
| `OSError` | no | no |

## Fix (tests only)

- `tests/conftest.py`, `_loopback_only`: `self.close()` before the
  raise.
- `tests/test_loopback_marker.py`: a refused connection leaves
  `sock.fileno() == -1`, through `connect`, `connect_ex` and
  `socket.create_connection`.
- No warning filter and no switch of the library: the leak was ours, so
  it was not an unavoidable third-party warning.

## Forced reproduction

A rerun cannot show a flake gone. The variance source is the per-process
cache, so a pytest plugin clears it before every test; every test then
meets the registry unresolved, as the first Hub test of a worker does
(*fix session*):

```python
import pytest


@pytest.fixture(autouse=True)
def _fresh_agent_registry():
    from huggingface_hub.utils import _detect_agent

    _detect_agent._registry = None
    yield
```

Run with an empty `HF_HOME`, the plugin's folder on `PYTHONPATH`,
`-p <plugin> -n0 -p no:cacheprovider`. It reaches into a private name of
the library, which is fine for a scratch probe and not for the suite.

| File | Without the guard fix | With it |
| --- | --- | --- |
| `tests/extract/remote/test_hub_loopback.py` | 17 failed | 17 passed |
| `tests/extract/remote/test_huggingface_api_timeout.py` | 2 failed, 2 passed | 4 passed |
| `tests/test_loopback_marker.py` | 7 failed, 10 passed | 17 passed |

(Python 3.13.12 with `huggingface_hub` 2.4.0, on `main` at ef5be3b2 with
the workaround of pull request 524 removed; *fix session*.)

## A second fix made at the same time

Pull request 524 (another line of work, merged 2026-11-23) met the same
failure and added a workaround to the `hub` fixture of
`test_hub_loopback.py`: it replaced the library's private
`_fetch_registry`, with a comment that named another cause. It covered
one test file of two: the two tests of `test_huggingface_api_timeout.py`
still failed on demand. Pull request 528 removed it.

## Production behaviour, open

Measured with a loopback server as `HF_ENDPOINT` and no test guard,
through `pitloom.extract.remote.huggingface_fetch._load_model_info`
(*fix session*, 2.4.0):

- No socket is left open.
- The first Hub read of a process sends one request that Pitloom did
  not ask for: `GET {HF_ENDPOINT}/api/agent-harnesses`, with no
  `Authorization` header and a 3 second timeout. On a 200 answer the
  library writes `.agent_harnesses.json` under `HF_HOME` and is silent
  for 24 hours; on a failure it asks again in every process.
- With `HF_HUB_DISABLE_TELEMETRY=1` (or `DISABLE_TELEMETRY`, or
  `DO_NOT_TRACK`) the request is not sent from the user-agent builder.
  Other callers of the detection in the library are not gated by it.
- Pitloom's own requests carry `unknown/None; hf_hub/<version>; ...` as
  user agent (no `library_name` is passed).

Not decided: whether Pitloom switches this off for its own Hub reads,
says so in the documentation, or leaves it. It is a case of the rule
that a check on the URL does not cover every client a fetch starts.
The tests still make the library try a DNS lookup of the real Hub from
loopback and unmarked tests; switching telemetry off for the whole
suite would stop that and was not done.

## Lessons

1. **A guard or a mock that raises inside a standard-library call must
   raise what that call cleans up on, or clean up itself.**
   `socket.create_connection` closes on `OSError` only.
2. **A third-party warning in a flaky test is first suspect for our own
   harness.** The place a `ResourceWarning` names is where the object
   was freed, not where it was leaked; `tracemalloc` gives the place of
   allocation.
3. **Find the variance source and force it.** Here a per-process cache
   decided which test met the leak. A rerun, or a second run that
   passes, says nothing.
4. **Read the result of every attempt of a CI run before saying a rerun
   passed.**
5. **A brief for a fix asks for the cause first.** The brief for this
   one offered two shapes (a switch of the library, a narrow `ignore`),
   and both were wrong.
6. **Before a fix starts, look for an open or just-merged pull request
   with the same symptom.** Two fixes of one flake ran at the same
   time; the workaround had to be taken out again.
7. **A library may open connections of its own beside the one asked
   for.** List them when a new version of a network library comes in
   (CI installs the newest release in the declared range).
