# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Refresh ``tests/fixtures/spdx-model/v<version>/`` from spdx.org.

Downloads the SPDX JSON-LD context, SHACL model and JSON Schema byte for byte
and rewrites ``SHA256SUMS``. Needs the network. ``--check`` changes nothing
and exits 1 when upstream differs from the snapshot.

Usage: ``python scripts/refresh_spdx_model_snapshot.py [--check] [--version V]``
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

DEFAULT_VERSION = "3.0.1"
SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/spdx-model"

Fetch = Callable[[str], bytes]


def sources(version: str) -> dict[str, str]:
    """Return the upstream URL of each snapshot file for *version*."""
    rdf = f"https://spdx.org/rdf/{version}"
    return {
        "spdx-context.jsonld": f"{rdf}/spdx-context.jsonld",
        "spdx-json-schema.json": (
            f"https://spdx.org/schema/{version}/spdx-json-schema.json"
        ),
        "spdx-model.ttl": f"{rdf}/spdx-model.ttl",
    }


def fetch_url(url: str) -> bytes:
    """Download *url* (https only) and return its bytes."""
    if not url.startswith("https://"):
        raise ValueError(f"not an https URL: {url}")
    with urllib.request.urlopen(url, timeout=60) as response:  # nosec B310
        return bytes(response.read())


def drifted(version: str, root: Path, fetch: Fetch) -> list[str]:
    """Return the names whose upstream bytes differ from the files in *root*."""
    out = []
    for name, url in sources(version).items():
        local = root / f"v{version}" / name
        upstream = hashlib.sha256(fetch(url)).hexdigest()
        if (
            not local.is_file()
            or hashlib.sha256(local.read_bytes()).hexdigest() != upstream
        ):
            out.append(name)
    return out


def refresh(version: str, root: Path, fetch: Fetch) -> None:
    """Rewrite the snapshot files and ``SHA256SUMS`` of *version* under *root*."""
    target = root / f"v{version}"
    target.mkdir(parents=True, exist_ok=True)
    sums = []
    for name, url in sorted(sources(version).items()):
        data = fetch(url)
        (target / name).write_bytes(data)
        sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    (target / "SHA256SUMS").write_text("".join(sums), encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None, fetch: Fetch = fetch_url) -> int:
    """Run the command line; return the exit status."""
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n", maxsplit=1)[0]
    )
    parser.add_argument("--check", action="store_true", help="report drift only")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args(argv)
    if args.check:
        names = drifted(args.version, SNAPSHOT_ROOT, fetch)
        for name in names:
            print(f"ERROR: upstream differs from snapshot: {name}", file=sys.stderr)
        return 1 if names else 0
    refresh(args.version, SNAPSHOT_ROOT, fetch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
