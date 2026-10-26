#!/usr/bin/env python3
"""
scris.py — minimal read/write to SCRIS (reMarkable) over the USB web interface.

General-purpose file transport, decoupled from any one project: any PDF or EPUB
goes onto the tablet, and anything on it comes back as a PDF.

Transport is plain curl + urllib (stdlib only, no deps, no MCP). The USB web
interface is the reliable path, so that's what this uses.

Verified API surface (read from the tablet's own web-app JS, 2026-06-16) — the USB
web interface exposes ONLY:
    GET  /documents/            → JSON list of root items
    GET  /documents/{folder-id} → JSON list of a folder's items (also sets the
                                  server-side "last-browsed dir" that /upload targets)
    GET  /download/{doc-id}/placeholder → the document as a PDF (pen strokes baked in)
    POST /upload                → multipart file upload into the last-browsed dir
There is NO create-folder, move, or delete API. Consequences:
  • Upload accepts PDF / EPUB only, and lands in an ALREADY-EXISTING folder
    (GET that folder immediately before POST /upload — this tool does that for you).
  • Make/rename/trash folders on-device; this tool can't.

Tablet must be plugged in over USB, awake, with Settings → Storage → "USB web
interface" enabled. Base host is http://10.11.99.1.

SSH verbs (need a key-authed SSH host, default alias `scris`, see README — the things the web
API can't do; each batches its .metadata edits and restarts xochitl ONCE):
    python3 scris.py mkdir <name> [--in <folder>] [--register <key>]
    python3 scris.py mv <doc...> <folder>          # folder: FOLDERS name, uuid, or on-device name
    python3 scris.py trash <doc...>                # move to the tablet's trash

Guards on the SSH verbs: clean refusal when `ssh scris` is unreachable (the USB
web-API loop keeps working standalone), and no xochitl restart while a `.rm`
stroke file was written in the last 60 s (someone may be mid-stroke).

Usage:
    python3 scris.py ping                      # is the tablet reachable?
    python3 scris.py ls [folder]               # list root, a FOLDERS name, or a folder id
    python3 scris.py find <name>               # search the whole tree by VisibleName
    python3 scris.py pull <doc> [dest]         # download by doc-id OR name (default: pulled/)
    python3 scris.py push <file...> [--to <folder>]   # upload PDF/EPUB (default: root)

Everywhere a folder/doc is expected you may pass a raw UUID, a FOLDERS name, or
(for pull) a document's VisibleName — names are resolved by walking the tree.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TABLET = "http://10.11.99.1"
HERE = Path(__file__).resolve().parent
PULL_DIR = HERE / "pulled"
UPLOADABLE = {".pdf": "application/pdf", ".epub": "application/epub+zip"}

# Folder IDs live in folders.json next to this file (copy folders.example.json and
# fill in your own UUIDs — `scris.py ls` prints them). Other scripts may import
# scris.FOLDERS to share the one registry.
FOLDERS_FILE = Path(os.environ.get("SCRIS_FOLDERS_FILE", HERE / "folders.json"))


def _load_folders() -> dict[str, str]:
    if not FOLDERS_FILE.is_file():
        return {}
    data = json.loads(FOLDERS_FILE.read_text())
    folders: dict[str, str] = dict(data.get("folders", {}))
    for alias, name in data.get("aliases", {}).items():
        if name in folders:
            folders[alias] = folders[name]
    return folders


FOLDERS: dict[str, str] = _load_folders()


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def http_get(path: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(f"{TABLET}{path}", timeout=timeout) as r:
        return r.read()


def reachable() -> bool:
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "8",
         f"{TABLET}/documents/"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() == "200"


def require_tablet(retries: int = 3) -> None:
    # a plugged-in but sleeping tablet often answers on the 2nd/3rd try
    for i in range(retries):
        if reachable():
            return
        if i < retries - 1:
            time.sleep(2)
    sys.exit("SCRIS not reachable at 10.11.99.1 — plug in over USB, tap the screen "
             "to wake it, and enable Settings → Storage → USB web interface.")


def ls_items(folder_id: str | None) -> list[dict]:
    path = f"/documents/{folder_id}" if folder_id else "/documents/"
    return json.loads(http_get(path).decode())


def resolve_folder(ref: str | None) -> str | None:
    """A folder arg may be None (root), a FOLDERS name, or a raw UUID."""
    if ref is None:
        return None
    if ref in FOLDERS:
        return FOLDERS[ref]
    if UUID_RE.match(ref):
        return ref
    sys.exit(f"'{ref}' is not a FOLDERS name ({', '.join(FOLDERS) or 'none defined'}) "
             "or a folder id — run `scris.py ls` to look it up.")


def walk_tree(folder_id: str | None = None, rel: str = ""):
    """Yield (item, path-string) for every item on the tablet, depth-first."""
    for d in ls_items(folder_id):
        p = f"{rel}/{d.get('VisibleName', '')}".lstrip("/")
        yield d, p
        if d.get("Type") == "CollectionType":
            yield from walk_tree(d["ID"], p)


def resolve_doc(ref: str) -> str:
    """A doc arg may be a raw UUID or a (case-insensitive) VisibleName."""
    if UUID_RE.match(ref):
        return ref
    want = ref.lower()
    hits = [(d, p) for d, p in walk_tree()
            if d.get("Type") == "DocumentType"
            and want in d.get("VisibleName", "").lower()]
    exact = [(d, p) for d, p in hits if d.get("VisibleName", "").lower() == want]
    if exact:
        hits = exact
    if not hits:
        sys.exit(f"no document matching '{ref}' on the tablet — try `scris.py find`.")
    if len(hits) > 1:
        listing = "\n".join(f"  {d['ID']}  {p}" for d, p in hits)
        sys.exit(f"'{ref}' is ambiguous:\n{listing}\npull by id instead.")
    return hits[0][0]["ID"]


def cmd_ping(_args) -> None:
    print("reachable" if reachable() else "NOT reachable (plug in + enable USB web interface)")


def cmd_ls(args) -> None:
    folder_id = resolve_folder(args.folder)
    require_tablet()
    items = ls_items(folder_id)
    # collections first, then documents, each alphabetical
    items.sort(key=lambda d: (d.get("Type") != "CollectionType", d.get("VisibleName", "").lower()))
    if not items:
        print("(empty)")
        return
    for d in items:
        kind = "DIR " if d.get("Type") == "CollectionType" else "doc "
        print(f"  {kind} {d.get('ID')}  {d.get('VisibleName', '')}")


def cmd_find(args) -> None:
    require_tablet()
    want = args.name.lower()
    hits = [(d, p) for d, p in walk_tree() if want in d.get("VisibleName", "").lower()]
    if not hits:
        print(f"no match for '{args.name}'")
        return
    for d, p in hits:
        kind = "DIR " if d.get("Type") == "CollectionType" else "doc "
        print(f"  {kind} {d['ID']}  {p}")


def cmd_pull(args) -> None:
    require_tablet()
    doc_id = resolve_doc(args.doc)
    dest = Path(args.dest) if args.dest else PULL_DIR / f"{doc_id}.pdf"
    if dest.is_dir():
        dest = dest / f"{doc_id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = http_get(f"/download/{doc_id}/placeholder")
    dest.write_bytes(data)
    print(f"pulled {len(data):,} bytes -> {dest}")


def push_one(f: Path, folder_id: str | None) -> str:
    # set the last-browsed dir (root if no folder), then upload into it
    browse = f"{TABLET}/documents/{folder_id}" if folder_id else f"{TABLET}/documents/"
    subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "8", browse], check=False)
    ctype = UPLOADABLE[f.suffix.lower()]
    r = subprocess.run(
        ["curl", "-s", "-m", "60", "-o", "/dev/null", "-w", "%{http_code}",
         "-F", f"file=@{f};type={ctype}", f"{TABLET}/upload"],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def cmd_push(args) -> None:
    files = [Path(p) for p in args.files]
    for f in files:
        if f.suffix.lower() not in UPLOADABLE:
            sys.exit(f"{f.name}: only PDF/EPUB can be uploaded over the USB web interface.")
        if not f.is_file():
            sys.exit(f"{f} not found.")
    folder_id = resolve_folder(args.to)
    require_tablet()
    ok = 0
    for f in files:
        code = push_one(f, folder_id)
        print(f"  {'OK ' if code == '201' else f'FAIL({code})'} {f.name}"
              f" -> {args.to or 'root'}")
        ok += code == "201"
    print(f"pushed {ok}/{len(files)}")


# ---------------------------------------------------------------------------
# SSH transport — the verbs the USB web API can't do (folders, moves, trash).
# SSH_HOST (env SCRIS_SSH_HOST, default `scris`) is a key-authed root login on the
# tablet (see README); works over USB or WLAN.
#
# ⚠ The remote shell is BusyBox (v1.36), NOT GNU coreutils. Every command
# string passed to ssh_run() must be BusyBox-compatible: `head -n 1` not
# `head -1`, no `grep -P`, no `sed -i` suffix quirks, no `ls --time-style`,
# no `date -d`. (`find -mmin` and `grep -l -i` are confirmed OK.) A GNU-ism
# here fails as exit 1 inside a subshell and can silently disable a guard —
# see guard_no_recent_ink(), which was broken this way once.

SSH_HOST = os.environ.get("SCRIS_SSH_HOST", "scris")
XOCHITL = "/home/root/.local/share/remarkable/xochitl"


def ssh_run(cmd: str, *, input: bytes | None = None,
            timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", SSH_HOST, cmd],
        input=input, capture_output=True, timeout=timeout)


def ssh_reachable() -> bool:
    return ssh_run("true", timeout=15).returncode == 0


def require_ssh() -> None:
    if not ssh_reachable():
        sys.exit(f"`ssh {SSH_HOST}` unreachable — this verb needs SSH (USB or WLAN). "
                 "The USB web-API verbs (ls/find/pull/push) still work without it.")


def guard_no_recent_ink(window_s: int = 60) -> None:
    """Refuse to proceed toward a xochitl restart while ink is landing.

    Checked BEFORE any metadata edit so a refusal leaves the tablet untouched.
    """
    # Was `head -1`, which BusyBox head rejects —
    # the subshell always exited 1, so this guard aborted on every call and
    # `grade_batch.py --file` could never succeed. BusyBox needs `head -n 1`.
    r = ssh_run(f"find {XOCHITL} -name '*.rm' -mmin -1 2>/dev/null | head -n 1")
    if r.returncode != 0:
        sys.exit("could not check for recent ink — refusing to touch xochitl; retry.")
    if r.stdout.strip():
        sys.exit(f"a .rm stroke file was written in the last {window_s} s — someone may "
                 "be mid-stroke. Refusing to restart xochitl; retry in a minute.")


def restart_xochitl() -> None:
    r = ssh_run("systemctl restart xochitl", timeout=90)
    if r.returncode != 0:
        sys.exit(f"xochitl restart failed: {r.stderr.decode().strip()}")
    print("xochitl restarted (one restart for the whole batch)")


def ssh_read_meta(uuid: str) -> dict:
    r = ssh_run(f"cat {XOCHITL}/{uuid}.metadata")
    if r.returncode != 0:
        sys.exit(f"no .metadata for {uuid} on the tablet.")
    return json.loads(r.stdout.decode())


def ssh_write_file(remote_path: str, data: bytes) -> None:
    r = ssh_run(f"cat > {remote_path}", input=data)
    if r.returncode != 0:
        sys.exit(f"write failed for {remote_path}: {r.stderr.decode().strip()}")


def ssh_find_by_name(ref: str, want_type: str) -> tuple[str, str]:
    """Resolve a VisibleName (case-insensitive substring, exact wins) over SSH."""
    r = ssh_run(f"grep -l -i {json.dumps(ref)} {XOCHITL}/*.metadata || true")
    hits = []
    for m in r.stdout.decode().split():
        meta = json.loads(ssh_run(f"cat {m}").stdout.decode())
        if (meta.get("type") == want_type and not meta.get("deleted")
                and meta.get("parent") != "trash"
                and ref.lower() in meta.get("visibleName", "").lower()):
            hits.append((Path(m).stem, meta["visibleName"]))
    exact = [h for h in hits if h[1].lower() == ref.lower()]
    if exact:
        hits = exact
    kind = "folder" if want_type == "CollectionType" else "document"
    if not hits:
        sys.exit(f"no {kind} matching '{ref}' on the tablet.")
    if len(hits) > 1:
        listing = "\n".join(f"  {u}  {n}" for u, n in hits)
        sys.exit(f"'{ref}' is ambiguous:\n{listing}\nuse the uuid instead.")
    return hits[0]


def ssh_resolve_doc(ref: str) -> tuple[str, str]:
    if UUID_RE.match(ref):
        return ref, ssh_read_meta(ref).get("visibleName", ref)
    return ssh_find_by_name(ref, "DocumentType")


def ssh_resolve_parent(ref: str | None) -> str:
    """Target-folder ref → parent id: '' (root), 'trash', FOLDERS name, uuid,
    or an on-device folder name (SSH lookup)."""
    if ref is None:
        return ""
    if ref == "trash":
        return "trash"
    if ref in FOLDERS:
        return FOLDERS[ref]
    if UUID_RE.match(ref):
        return ref
    return ssh_find_by_name(ref, "CollectionType")[0]


def set_parent(uuid: str, name: str, parent: str) -> None:
    meta = ssh_read_meta(uuid)
    meta["parent"] = parent
    meta["metadatamodified"] = True
    meta["lastModified"] = str(int(time.time() * 1000))
    ssh_write_file(f"{XOCHITL}/{uuid}.metadata",
                   json.dumps(meta, indent=4).encode())
    print(f"  staged: {name} -> parent {parent or 'root'}")


def cmd_mkdir(args) -> None:
    require_ssh()
    parent = ssh_resolve_parent(args.in_folder)
    guard_no_recent_ink()
    new_id = str(__import__("uuid").uuid4())
    meta = {"deleted": False, "lastModified": str(int(time.time() * 1000)),
            "metadatamodified": False, "modified": False, "parent": parent,
            "pinned": False, "synced": False, "type": "CollectionType",
            "version": 0, "visibleName": args.name}
    ssh_write_file(f"{XOCHITL}/{new_id}.metadata", json.dumps(meta, indent=4).encode())
    ssh_write_file(f"{XOCHITL}/{new_id}.content", b"{}")
    restart_xochitl()
    print(f"created folder '{args.name}' ({new_id}) in {args.in_folder or 'root'}")
    if args.register:
        data = json.loads(FOLDERS_FILE.read_text()) if FOLDERS_FILE.is_file() \
            else {"folders": {}, "aliases": {}}
        data.setdefault("folders", {})[args.register] = new_id
        FOLDERS_FILE.write_text(json.dumps(data, indent=2) + "\n")
        print(f"registered as '{args.register}' in {FOLDERS_FILE}")
    else:
        print(f"(add it to {FOLDERS_FILE.name} to address it by name)")


def cmd_mv(args) -> None:
    require_ssh()
    docs = [ssh_resolve_doc(d) for d in args.docs]      # resolve everything first
    parent = ssh_resolve_parent(args.folder)
    guard_no_recent_ink()
    for uuid, name in docs:                             # batch all edits …
        set_parent(uuid, name, parent)
    restart_xochitl()                                   # … one restart
    print(f"moved {len(docs)} document(s) -> {args.folder}")


def cmd_trash(args) -> None:
    require_ssh()
    docs = [ssh_resolve_doc(d) for d in args.docs]
    guard_no_recent_ink()
    for uuid, name in docs:
        set_parent(uuid, name, "trash")
    restart_xochitl()
    print(f"trashed {len(docs)} document(s)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Minimal read/write to SCRIS over USB.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping", help="reachability check").set_defaults(func=cmd_ping)
    p_ls = sub.add_parser("ls", help="list root or a folder")
    p_ls.add_argument("folder", nargs="?", help="FOLDERS name or folder id (default: root)")
    p_ls.set_defaults(func=cmd_ls)
    p_find = sub.add_parser("find", help="search the whole tree by name")
    p_find.add_argument("name")
    p_find.set_defaults(func=cmd_find)
    p_pull = sub.add_parser("pull", help="download a document as PDF")
    p_pull.add_argument("doc", help="doc id or document name")
    p_pull.add_argument("dest", nargs="?", help="file or dir (default: pulled/<id>.pdf)")
    p_pull.set_defaults(func=cmd_pull)
    p_push = sub.add_parser("push", help="upload PDF/EPUB file(s)")
    p_push.add_argument("files", nargs="+")
    p_push.add_argument("--to", help="FOLDERS name or folder id (default: root)")
    p_push.set_defaults(func=cmd_push)
    p_mkdir = sub.add_parser("mkdir", help="create a folder on-device (SSH)")
    p_mkdir.add_argument("name", help="visible name of the new folder")
    p_mkdir.add_argument("--in", dest="in_folder", default=None,
                         help="parent: FOLDERS name, uuid, or on-device name (default: root)")
    p_mkdir.add_argument("--register", default=None,
                         help="also record the new id under this key in folders.json")
    p_mkdir.set_defaults(func=cmd_mkdir)
    p_mv = sub.add_parser("mv", help="move document(s) to a folder (SSH)")
    p_mv.add_argument("docs", nargs="+", help="doc name(s) or uuid(s)")
    p_mv.add_argument("folder", help="target: FOLDERS name, uuid, or on-device name")
    p_mv.set_defaults(func=cmd_mv)
    p_trash = sub.add_parser("trash", help="move document(s) to the tablet trash (SSH)")
    p_trash.add_argument("docs", nargs="+", help="doc name(s) or uuid(s)")
    p_trash.set_defaults(func=cmd_trash)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
