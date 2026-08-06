"""Fetch a fixed, enumerated list of help.ubuntu.com community wiki pages.

The ONLY script in this repo allowed to touch the network (per tasks.md
Phase 1) — invoke manually, never import this module at test or request
time. Writes raw HTML to ``data/kb/raw/`` (gitignored) and records
provenance ({slug, url, fetched_at, sha256}) in ``data/kb/MANIFEST.json``
(committed) for `triage/ingest.py` to normalize and chunk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE_URL = "https://help.ubuntu.com/community/"

# category -> wiki page slug. Chosen so every triage.schemas.PRODUCT_AREAS
# value (excluding "other") is genuinely covered, ~8 pages each, ~40 total.
PAGES: list[tuple[str, str]] = [
    ("install", "Installation"),
    ("install", "Installation/FromUSBStick"),
    ("install", "UEFI"),
    ("install", "Grub2"),
    ("install", "Installation/CDIntegrityCheck"),
    ("install", "Installation/FromAnotherDistro"),
    ("install", "Installation/AMD64"),
    ("install", "LiveCD"),
    ("networking", "Firewall"),
    ("networking", "Gufw"),
    ("networking", "DoINeedAFirewall"),
    ("networking", "NetworkManager"),
    ("networking", "NetworkManagerOptions"),
    ("networking", "DnsAndDhcp"),
    ("networking", "BridgingNetworkInterfaces"),
    ("networking", "WifiDocs"),
    ("packaging", "AptGet/Howto"),
    ("packaging", "Repositories"),
    ("packaging", "Repositories/CommandLine"),
    ("packaging", "SynapticHowto"),
    ("packaging", "PPA"),
    ("packaging", "AptCdrom"),
    ("packaging", "PackageManagerTroubleshootingProcedure"),
    ("packaging", "AptitudeSurvivalGuide"),
    ("users_permissions", "RootSudo"),
    ("users_permissions", "Sudoers"),
    ("users_permissions", "AddUsersHowto"),
    ("users_permissions", "FilePermissions"),
    ("users_permissions", "FilePermissionsACLs"),
    ("users_permissions", "StrongPasswords"),
    ("users_permissions", "LostPassword"),
    ("users_permissions", "AutoAdminGroup"),
    ("hardware", "HardwareSupportComponentsWireless"),
    ("hardware", "BluetoothDevices"),
    ("hardware", "BinaryDriverHowto"),
    ("hardware", "BinaryDriverHowto/Nvidia"),
    ("hardware", "Printers"),
    ("hardware", "Scanners"),
    ("hardware", "SynapticsTouchpad"),
    ("hardware", "Webcam"),
]

RAW_DIR = Path("data/kb/raw")
MANIFEST_PATH = Path("data/kb/MANIFEST.json")


def _filename(slug: str) -> str:
    return slug.replace("/", "__") + ".html"


def fetch(limit: int | None = None) -> list[dict]:
    """Fetch ``limit`` pages (or all of them) and write raw HTML + manifest."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pages = PAGES if limit is None else PAGES[:limit]
    manifest: list[dict] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for category, slug in pages:
            url = BASE_URL + slug
            response = client.get(url)
            response.raise_for_status()
            content = response.content
            (RAW_DIR / _filename(slug)).write_bytes(content)
            manifest.append(
                {
                    "slug": slug,
                    "category": category,
                    "url": url,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="fetch only the first N pages")
    args = parser.parse_args()
    manifest = fetch(limit=args.limit)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    sys.stdout.write(f"Fetched {len(manifest)} pages -> {RAW_DIR}/, manifest -> {MANIFEST_PATH}\n")


if __name__ == "__main__":
    main()
