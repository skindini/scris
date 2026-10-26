#!/usr/bin/env python3
"""
vector_pull.py — pull a document's handwriting off SCRIS as editable SVG vectors.

This is the round-trip the USB web interface can't do (it only emits flattened
PDFs). Transport is SSH (a key-authed root login on the tablet; host alias from
env SCRIS_SSH_HOST, default `scris`); conversion is `rmc` (v6 .rm parser) from the repo venv.

    python3 tools/vector_pull.py <name-or-uuid> [dest-dir]

Output: vectors/<name>/page-NN.svg (+ the raw .rm strokes staged in raw/<uuid>/,
gitignored). Pages follow the document's on-device order.

Requires: SSH to the tablet working (see README) and .venv/bin/rmc
(python3 -m venv .venv && .venv/bin/pip install rmc).
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
XOCHITL = "/home/root/.local/share/remarkable/xochitl"
RMC = HERE / ".venv" / "bin" / "rmc"
SSH_HOST = os.environ.get("SCRIS_SSH_HOST", "scris")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def ssh(cmd: str, binary: bool = False) -> bytes | str:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", SSH_HOST, cmd],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        sys.exit(f"ssh failed: {r.stderr.decode().strip() or cmd}")
    return r.stdout if binary else r.stdout.decode()


def resolve(ref: str) -> tuple[str, str]:
    """Return (uuid, visibleName) for a uuid or a (partial) name."""
    if UUID_RE.match(ref):
        meta = json.loads(ssh(f"cat {XOCHITL}/{ref}.metadata"))
        return ref, meta.get("visibleName", ref)
    out = ssh(f"grep -l -i {json.dumps(ref)} {XOCHITL}/*.metadata || true")
    hits = []
    for m in out.split():
        meta = json.loads(ssh(f"cat {m}"))
        if meta.get("type") == "DocumentType" and ref.lower() in meta.get("visibleName", "").lower():
            hits.append((Path(m).stem, meta["visibleName"]))
    if not hits:
        sys.exit(f"no document matching '{ref}' on the tablet.")
    if len(hits) > 1:
        listing = "\n".join(f"  {u}  {n}" for u, n in hits)
        sys.exit(f"'{ref}' is ambiguous:\n{listing}")
    return hits[0]


def page_order(content: dict) -> list[str]:
    if "cPages" in content:                       # v6 layout
        return [p["id"] for p in content["cPages"]["pages"]
                if "deleted" not in p]
    return content.get("pages", [])               # older layout


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    ref = sys.argv[1]
    uuid, name = resolve(ref)
    safe = re.sub(r'[/\\:*?"<>|]', "_", name).strip() or uuid

    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "vectors" / safe
    raw = HERE / "raw" / uuid
    raw.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)

    # stage .content + all .rm pages locally in one tar stream
    tar = ssh(f"cd {XOCHITL} && tar cf - {uuid}.content {uuid}/ 2>/dev/null", binary=True)
    subprocess.run(["tar", "xf", "-", "-C", str(raw)], input=tar, check=True)

    content = json.loads((raw / f"{uuid}.content").read_text())
    pages = page_order(content)
    if not pages:
        sys.exit(f"'{name}' has no pages.")

    made, blank = 0, 0
    for i, pid in enumerate(pages, 1):
        rm = raw / uuid / f"{pid}.rm"
        if not rm.exists():                       # page never written on
            blank += 1
            continue
        out = dest / f"page-{i:02d}.svg"
        r = subprocess.run([str(RMC), "-t", "svg", "-o", str(out), str(rm)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAIL page {i}: {r.stderr.strip()}")
        else:
            print(f"  OK   page {i} -> {out}")
            made += 1
    print(f"'{name}': {made} page(s) vectorized, {blank} blank -> {dest}")


if __name__ == "__main__":
    main()
