# Credentials in URLs

An SBOM can be published, so a credential in one is exposed to everyone who
reads it. Pitloom reads every URL field of the SBOM it writes and has two modes
for a value that holds a credential:

- **`warn`** (the default): the SBOM is written as it is, and each such value is
  one loud `WARNING:` naming it (masked), where it is and its fingerprint. The
  command exits 0 and a build goes on: Pitloom runs in CI and build hooks and
  does not fail them unless asked to.
- **`refuse`** (opt in): each such value is one `ERROR:`, no SBOM is written and
  the command exits 1 (the build hook fails the build), unless the run accepts
  that value by its fingerprint.

Pitloom never rewrites a value, so what an SBOM states is what the source said.
For CI, turn the `refuse` mode on:

```toml
[tool.pitloom]
url-credentials = "refuse"
```

or pass `--refuse-url-credentials` (in the GitHub Action: `url-credentials:
refuse`). The library takes
`credentials=CredentialPolicy(refuse=True)` or
`PitloomConfig(url_credentials="refuse")`. Any other value of the setting is an
error (`ERROR: loom <command>: FILE=<file>: [tool.pitloom] url-credentials:
must be "warn" or "refuse", got ... [config-invalid]`). `setup.cfg` takes
`[tool:pitloom] url-credentials`. There is no flag to turn the project's `refuse` off from the command line.

This page covers what is found, how to fix it, how to accept a value you know
is no secret, and what is not detected. See also [Dependency
sources](dependency-sources.md#credentials-in-a-url) (where project and
dependency URLs come from), [Loom ID registry keys](id-registry-keys.md#credentials-in-a-key)
(the same rule for a registry) and [Git URLs](git-urls.md) (the credential in
a URL you give to fetch).

## What is found

A value of a [field read](#fields-read) holds a credential when it holds:

- user information in a URL (`https://user:password@host/x`, `https://token@host/x`),
  after any scheme (`s3:/user:pw@host/x`, `ftp://...`), also a password that
  starts with `?` or `#` (`https://user:?pw@host/x`, which a client reads as
  host `user` and a query);
- a query or fragment parameter named like a secret (`token`, `access_token`,
  `api_key`, `client_key`, `password`, `secret`, `signature`, `key`,
  `session_id`, a `;jsessionid=` path parameter), also percent-encoded in a
  PURL qualifier;
- any of these in a URL's query value or fragment once percent-decoded, up to
  five times (`?next=https%3A%2F%2Fuser%3Apw%40host`), as in a PURL qualifier;
- an access token's shape anywhere in it (GitHub, GitLab, Slack, Hugging Face,
  AWS key id, PyPI, npm, OpenAI, Anthropic and Google API key prefixes);
- an scp-style address with a password (`alice:password@host:o/r`; a dotless
  host such as `build:42@ci:linux` counts);
- a query nested too deeply to read (more than 16 `?`), or a PURL qualifier
  still encoded after five decodes.

A value is read past an invisible format character (a zero-width space, a byte
order mark) and inside one pair of `<>` or quotes, as a client reads it.

A parameter named `code`, `session`, `ticket`, `sid` or `otp`, another that
ends in `_key` and is no kind of secret key (`sort_key`), and a user name alone
on an `ssh` or `git` URL (`ssh://git@github.com/o/r`) may hold a credential
only. These are **only warned of, in either mode**: the SBOM states them as
written, and the warning shows the value masked, once.

## Fields read

Only the fields below are read, each as one whole value, wherever the element
that holds them stands in the document (a nested `ExternalRef` or
`NamespaceMap` too). A field of this list is read for every SBOM Pitloom writes:
project, wheel, environment, model, Git and PyPI targets, a fragment, a merge
and an SBOM embedded in a wheel. A file given to `embed-wheel --sbom` is read
wider: see [By surface](#by-surface).

| Field | Read as |
| :--- | :--- |
| `software_downloadLocation`, `software_homePage`, `software_packageUrl`, `software_contentIdentifierValue`, `locator`, `identifierLocator`, `expandedlicensing_seeAlso`, `build_configSourceUri`, `build_buildType`, `security_locator` | A URL, a PURL or an scp-style address |
| `identifier`, whatever its `externalIdentifierType` | The same |
| `locationHint` | The same, but a value that is only scp-shaped is a file path (`meet-10:30@ab:c.json`), not a credential |
| `spdxId`, `@id`, `externalSpdxId`, `namespace`, and each field that refers to an element, an agent or other object by id (`createdBy`, `suppliedBy`, `creationInfo`, `from`, `to`, `subject`, `rootElement`, `element`, ...) when it holds an id and not the object | An identifier Pitloom or a merged document stores: a URL or an access token anywhere in it counts; an `ssh` or `git` user name alone is warned of, as in a URL field (a model named `ssh://git@github.com/o/m`). An id is also read percent-decoded, each depth as a client reads it (a dataset or model name that is a URL is part of its id, encoded) |
| Every string of a JSON statement Pitloom writes (an annotation whose `schema` starts `https://pitloom.dev/`: field provenance, metadata copied from a model, a conflict's candidates), and each segment (`Note:` and `Value:`) of a `Metadata provenance:` comment line | A URL, a PURL or an scp-style address (a dependency's direct reference, `foo @ https://host/x.whl`, is stated there whole) |

## What is not read

Prose. A README, a description, a licence text, a comment line that is not
Pitloom's provenance line, a name or a summary is never read, even when it
shows a URL with a password or a token. (A file given to `embed-wheel --sbom`
is not Pitloom's own: a string of it that is a whole URL with a credential, a
`name` too, is found; a sentence holding one is not.) A README example must
not block a build, and finding secrets in prose is a secret scanner's job.
Pitloom's log lines and `-v` details do mask a credential they print
(`https://***:***@host`, `ghp_***`); that is display only. They also mask the
credential after an HTTP `Bearer` or `Basic` scheme, keeping the scheme
(`Authorization: Bearer ***`), and a token, an scp-style password or a PURL
qualifier right after an escape sequence Pitloom writes for a control
character (`\t`, `\n`, `\r`, `\x1b`, `\u202e`, `\U000e0001`), as after white
space. A token glued to plain letters (`abghp_...`) is not masked, and a
backslash typed before a letter (a Windows folder `C:\tghp_...`) reads as such
an escape, so the name after it may be masked.

## What you see

In the `warn` mode, one `WARNING:` per value: the value (masked), the element
and the field (an RFC 6901 pointer into it) that hold it, a fingerprint and how
this surface turns the `refuse` mode on (see [By surface](#by-surface)). The
SBOM is written and the exit status is 0; the ID registry is saved as usual.

```text
WARNING: URL=https://example.org/?token=***: holds a credential (https://spdx.org/spdxdocs/demo-48d6...#Package-1 /software_downloadLocation, sha256:34973142468d1a90); the SBOM states it as written; remove it from the source, or refuse such values with --refuse-url-credentials [credentials-unsafe/written]
```

In the `refuse` mode, one `ERROR:` line per value, ending with how this surface
accepts it, then one count, and exit status 1. No SBOM is written, and the ID
registry file, if any, is left as it was.

```text
ERROR: loom project: URL=https://example.org/?token=***: holds a credential (https://spdx.org/spdxdocs/demo-48d6...#Package-1 /software_downloadLocation, sha256:34973142468d1a90); remove it from the source, or accept this value with --accept-url-credential sha256:34973142468d1a90 [credentials-unsafe/refused]
ERROR: loom project: 1 URL value(s) in the SBOM hold credentials; the SBOM is refused [credentials-unsafe/refused]
```

A value stated in two places is one line, at the first place it stands. A
`WARNING:` is said once per value in a process. The Hatchling build hook
starts each `ERROR:` line with `Pitloom build hook: `. The message codes are in [URL
credentials](message-codes-url-credentials.md#credentials-unsafewritten).

## Fixing it

Remove the credential from the source (the `pyproject.toml` URL, the
dependency's direct reference, the model card) and generate again. Use `.netrc`,
a credential helper or an environment variable instead. A credential that was in
a project's files is also in its history, and in the `warn` mode in every SBOM
written since: treat it as exposed and rotate it.

## Accepting one value

When a value is no secret (an example URL, a public demo token), accept that
value alone, by the fingerprint its `WARNING:` or `ERROR:` line prints: `sha256:` and 16
lowercase hex digits of the SHA-256 of the whole field value as it stands in
the SBOM. The fingerprint never shows the credential. A longer prefix (up to 64
digits) is accepted too; uppercase is not.

```bash
loom project . --accept-url-credential sha256:34973142468d1a90
```

```toml
[tool.pitloom]
accept-url-credentials = ["sha256:34973142468d1a90"]
```

The flag is repeatable and adds to the `pyproject.toml` list, never replaces
it. In the `refuse` mode an accepted value no longer refuses the SBOM; in
either mode it is stated as written, with one quieter `WARNING:` per value in
place of the `written` one (`WARNING: URL=<url>: holds a credential that
<fingerprint> accepts; the SBOM states it as written
[credentials-unsafe/accepted]`), so anyone who reads the SBOM reads it too. An accepted fingerprint that matches no
value of the SBOM is warned of too, once per fingerprint and SBOM, naming the
SBOM by its `SpdxDocument` id (`WARNING: Options: FINGERPRINT=<fingerprint>:
matches no URL of the SBOM <id> [option-no-effect]`). A fingerprint that a model fragment
inherits from the project's list is never reported for the fragment. A
fingerprint that is not `sha256:` and 16 to 64 lowercase hex digits is an error
that does not quote it, as a credential may have been pasted by mistake
(`PitloomConfig` raises it when built).

In `setup.cfg` the list is `[tool:pitloom] accept-url-credentials`, one
fingerprint per line or separated by commas or spaces. A bad entry is named by
its position from 0 (`[tool:pitloom] accept-url-credentials entry 2: not a
fingerprint`), without quoting it.

## By surface

Each `WARNING:` line ends with the way the surface that ran turns the `refuse`
mode on, and each `ERROR:` line with the way it accepts the value; the count
line is the same on every surface.

| Surface | `warn` (default) | `refuse` | Turn `refuse` on | Accept one value |
| :--- | :--- | :--- | :--- | :--- |
| CLI (`loom project`, `generate`, `wheel`, `model`, `env`, `enrich`, `embed-wheel`, `merge`) | SBOM written (to stdout too with `-o -`), `WARNING:` lines, exit 0 | `ERROR:` lines, exit 1, no SBOM (not to stdout with `-o -` either) | `--refuse-url-credentials`, or `url-credentials = "refuse"` in a config file (flags only for `merge` and `embed-wheel --sbom`) | `--accept-url-credential <fingerprint>`; or `accept-url-credentials` in a config file |
| Hatchling build hook | The build goes on, with the `WARNING:` lines | The build fails; each `ERROR:` line starts `Pitloom build hook: ` | `url-credentials = "refuse"` in `[tool.pitloom]` | `accept-url-credentials` in `[tool.pitloom]` |
| Python API | Returns; the `WARNING:` lines are logged | `ValueError` carrying the code `credentials-unsafe/refused` (the `ERROR:` lines are logged) | `credentials=CredentialPolicy(refuse=True)`, or `PitloomConfig(url_credentials="refuse")` | `credentials=CredentialPolicy(accepted=["<fingerprint>"])`, or `PitloomConfig(accept_url_credentials=...)` |
| `loom.Run` | The fragment is written when the run ends | Refused when the run ends: no fragment is written | `credentials=` as above, or the config's `url-credentials` | `credentials=` as above |
| GitHub Action | The step passes | The step fails | the `url-credentials: refuse` input (`warn` is the default), or `url-credentials` in the project's or the `config` file's `[tool.pitloom]` | the `accept-url-credentials` input (fingerprints separated by commas or line breaks, each passed as `--accept-url-credential`), or `accept-url-credentials` in `[tool.pitloom]` |

- `loom project`, `generate`, `wheel`, `model`, `env` and `enrich` read
  `url-credentials` and the `accept-url-credentials` list through `--config`
  or the project's own config; the flags add to them (`--refuse-url-credentials`
  turns `refuse` on, never off).
- `loom merge` has no `[tool.pitloom]` table: it reads only the flags, and so
  does `generate_merged_sbom()`, whose `credentials=` is keyword only and the
  one input. It checks the merged SBOM.
- `embed-wheel --sbom FILE` checks the file it is given: it is embedded
  unchanged (with warnings in the `warn` mode), or, in the `refuse` mode,
  refused and the wheel left as it was. Every string of the
  file is read, each as a whole value as a URL field is, not only the fields
  above: its `@context`, a property beside `@graph`, a key written expanded
  (`https://spdx.org/rdf/3.0.1/terms/...`) or prefixed, and an `@value`.
  Keys are not read. Only the flags (or
  `credentials=` through `ConfigOverrides`) apply to it; a `pyproject.toml`
  setting does not, since the SBOM is not Pitloom's own. A JSON SBOM given to it
  (or to `loom id import`) with an object that holds a key twice is refused
  with `[sbom-invalid]`, as JSON readers disagree on which value counts.
- The GitHub Action in model mode reads no project file: only the `config`
  input's file, if any, and `args:`.

```python
from pitloom import generate_project_sbom
from pitloom.core.credential_policy import CredentialPolicy

sbom = generate_project_sbom(
    ".", credentials=CredentialPolicy(accepted=["sha256:34973142468d1a90"])
)
```

## ID registry

A registry stores a key, an id and its namespace as written, so the same modes
hold there. A key given to `IdRegistry.register()` or to the `-e` option of
`loom id generate` that holds a credential is stored with a `WARNING:` in the
`warn` mode and refused in the `refuse` mode. A registry file that already
holds a credentialed key or `spdxId` is loaded as it is with a `WARNING:` per
entry in the `warn` mode; in the `refuse` mode it is not loaded at all and is
left as it is: `IdRegistry.load()` and `IdRegistry.rebase()` raise, naming the
file and the value (masked). Either way you remove the entry yourself. A
credentialed namespace (`--namespace`, `IdRegistry(namespace=...)`, a file's
namespace) is refused in either mode. `loom id import` and a run's harvest
skip an SBOM element whose key or id holds one, with a warning, in either mode
(it gets a new id next run).

`loom id generate` and `loom id import` take `--refuse-url-credentials`; they
read the project's `url-credentials` when no `-o` is given, as they read the
registry's location, or when `--project-dir` names the project (with `-o` and
no `--project-dir`, the current directory's config is not read; with `-o`, a
project config that cannot be read does not fail the run: a `WARNING:` says the
`warn` mode applies, `option-no-effect`). The library takes `refuse_credentials=True` on
`IdRegistry.load()`, `IdRegistry.new()` and the constructor; a registry passed
in to a run that refuses is turned to the `refuse` mode, its entries checked.
See [Credentials in a key](id-registry-keys.md#credentials-in-a-key).

## Not detected

Pitloom reads the shapes above; these are not detected, so keep such
credentials out of URLs:

- A `/` in a password (`https://u:p/w@host/x`). A `|` in a requirement's
  password is one too: Pitloom writes it as `/` in the SBOM.
- A password that starts with `?` or `#` right after `user:` and holds `=` or
  `&` (`https://u:?a=b@host/x`): it reads as a host, an empty port and a query.
  Conversely, `https://host:?mirror@cdn/x` is found as a credential, and a
  message masks `host`: nothing in the text tells a host and an empty port
  from a user name and an empty password. Accept its fingerprint.
- The no-slash form `https:u:p@host` (a client may read it as a URL).
- An scp-style address whose user is a bare token (`TOKEN@host:o/r`).
- A credential in a query value or fragment percent-encoded more than five
  times (a redirect chain may encode an ordinary URL that often, so it is not
  flagged); a message prints such a value as `***`.
- A query value that decodes to a time and a host-like word
  (`?v=10%3A30%40ab%3Ac`, which reads `10:30@ab:c`) is found as an scp-style
  password: accept its fingerprint.
- A secret-named pair at the start of a query value, plain or encoded
  (`?next=access_token=T`, `?next=access_token%3DT`): a value is no query, and
  search and filter values hold such pairs (`?filter=auth%3Dbasic`,
  `?u=key%3Dvalue`). After a `?`, `&` or `;` inside the value it is found
  (`?next=%2Fcb%3Ftoken%3DT`), and so is `key`, `auth` or `sig` there even when
  it holds no secret (`?return_to=%2Fsettings%3Fkey%3Dtheme`): accept its
  fingerprint.
- `state=` (OAuth's anti-forgery value) and CloudFront's `Policy=` and
  `Key-Pair-Id=` are no secret by decision: the `Signature=` beside them is
  found.
- A value wrapped in `<>` twice (`<<https://u:pw@host/x>>`), or a direct
  reference's URL wrapped in `<>` (`foo @ <https://u:pw@host/x>`).
- An access token followed by `;` or `#` in a PURL qualifier, and a token with
  a variation selector (U+FE0F) inside it.
- An old Slack workspace or bot token without the digit groups (`xoxa-`,
  `xoxr-`): a documentation word fits its shape.
- A GitLab (`glpat-`) or Google (`AIza`) key that lacks a digit, an upper-case
  or a lower-case letter: a documentation word fits the shape otherwise. A
  legacy OpenAI key (`sk-` without `proj-`, `svcacct-` or `admin-`).
- A token inside prose, a README or a description: see [What is not
  read](#what-is-not-read). That includes a dataset or model `name` that is a
  URL (a decision: a name is prose), and the free strings that are not typed as
  a URL (`hashValue`, `software_attributionText`, `standardName`,
  `software_packageVersion`), and a `DictionaryEntry` value, except in a file
  given to `embed-wheel --sbom`, where every string is read.
- A JSON statement's or a model's metadata *key* that is a credentialed URL
  (its values are read), and a JSON statement nested too deeply for
  `json.loads` (a merged fragment can hold one).
- An `ssh` user name that looks like a value (`ssh://abcdeftokenvalue@host`) is
  only warned of, as a weak value.
- A file name in a URL field that is scp-shaped (`meet-10:30@ab:c.txt`) is
  found as a credential: accept its fingerprint.
- In a log line, a `Bearer` or `Basic` credential shorter than 8 characters, or
  of 8 to 19 letters (and `-`, `_`) all of one case or a capital and then
  lower case: prose follows these words too (`Bearer token required`,
  `Basic Authentication`). A `Basic` value that is not base64, and other
  schemes (`Digest`, GitHub's `token`), are not masked either; a known token
  shape after them is.
- Logs that are not Pitloom's own: a third-party library's warning or log line
  and a Hatchling traceback are not masked (`urllib3` and `requests` log lines
  are, once Pitloom has set up its logging), and a line break in a password can
  split a traceback line so that its parts are not recognised.
- The GitHub Action prints `::add-mask::` for the credential-shaped parts of a
  URL in its `project-path`, `model`, `args` and `accept-url-credentials`
  inputs (user information, password, query and fragment; a piece under 6
  characters is not masked) before anything else, but GitHub prints a step's
  inputs before the step runs: a credential typed as text in a workflow is in
  that echo and in the workflow file. Only a `${{ secrets.NAME }}` value is
  hidden from the start. The decoded form of a percent-encoded password is not
  masked either.
- A Git URL's query and fragment are dropped before the clone URL is built, so
  a `?token=` value never reaches `git`'s command line or the clone's
  `.git/config`; the URL as given is still checked in the SBOM. User
  information (`https://user:token@host`) is kept off them too.

Pitloom is not a secret scanner. A credential that no rule here matches, or
that stands in prose, is written to the SBOM as it is in the source.
