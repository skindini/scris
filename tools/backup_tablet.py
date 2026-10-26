#!/usr/bin/env python3
"""
backup_tablet.py — pull EVERY document off a reMarkable via the USB web interface.

Recursively walks /documents/ and downloads each doc as a PDF (pen strokes baked
in) into a dated backup dir, mirroring the on-device folder structure.

NOTE: this is a FLATTENED backup — the USB interface cannot emit editable .rm
strokes. If reMarkable cloud sync is on, that is the lossless backup; this is
the local belt-and-suspenders copy (and the only option for unsynced docs).

Usage:
    python3 backup_tablet.py [dest-dir]     # default: ./backup_<today>/
"""
from __future__ import annotations
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

TABLET = "http://10.11.99.1"


def _get(path: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(f"{TABLET}{path}", timeout=timeout) as r:
        return r.read()


def safe(name: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "_", name).strip() or "untitled"


def walk(folder_id: str, rel: Path, dest: Path, log: list[str]) -> None:
    path = f"/documents/{folder_id}" if folder_id else "/documents/"
    items = json.loads(_get(path).decode())
    for d in items:
        name = safe(d.get("VisibleName", d["ID"]))
        if d.get("Type") == "CollectionType":
            walk(d["ID"], rel / name, dest, log)
        else:
            if not name.lower().endswith(".pdf"):
                name += ".pdf"
            out = dest / rel / name
            if out.exists():  # name collision inside same folder
                out = dest / rel / f"{name}__{d['ID'][:8]}.pdf"
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = _get(f"/download/{d['ID']}/placeholder")
                out.write_bytes(data)
                print(f"  OK   {rel / name}  ({len(data):,} bytes)")
                log.append(f"OK   {d['ID']}  {rel / name}  {len(data)} bytes")
            except Exception as e:
                print(f"  FAIL {rel / name}  ({e})")
                log.append(f"FAIL {d['ID']}  {rel / name}  {e}")


def main() -> None:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path.cwd() / f"backup_{date.today().isoformat()}"
    dest.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    print(f"backing up tablet -> {dest}")
    walk("", Path(), dest, log)
    (dest / "MANIFEST.txt").write_text("\n".join(log) + "\n")
    fails = sum(1 for line in log if line.startswith("FAIL"))
    print(f"done: {len(log) - fails}/{len(log)} docs backed up -> {dest}")
    if fails:
        sys.exit(f"{fails} FAILED — see {dest / 'MANIFEST.txt'}; do NOT wipe yet.")


if __name__ == "__main__":
    main()
