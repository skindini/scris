#!/usr/bin/env python3
"""
Offline guard tests for scris.py — no tablet required.

Exercises every path that must fail fast BEFORE touching the network:
arg validation, name resolution, suffix guards, missing files. Run any time
scris.py changes:  python3 tools/test_scris_offline.py
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIS = Path(__file__).resolve().parent.parent / "scris.py"
PASS = FAIL = 0


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIS), *args],
                          capture_output=True, text=True, timeout=30)


def check(desc: str, ok: bool, r: subprocess.CompletedProcess) -> None:
    global PASS, FAIL
    PASS += ok
    FAIL += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {desc}")
    if not ok:
        print(f"       rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")


# 1. bad subcommand → argparse error, exit 2
r = run("teleport")
check("unknown subcommand rejected", r.returncode == 2, r)

# 2. push a non-PDF/EPUB → suffix guard fires before any network use
bad = Path(tempfile.mkstemp(suffix=".txt")[1])
bad.write_text("nope")
r = run("push", str(bad))
check("non-PDF/EPUB push rejected", r.returncode != 0 and "PDF/EPUB" in r.stderr, r)
bad.unlink()

# 3. push a missing file → not-found guard
r = run("push", "/no/such/file.pdf")
check("missing file push rejected", r.returncode != 0 and "not found" in r.stderr, r)

# 4. push --to with junk target → resolve_folder guard (before reachability)
ok_pdf = Path(tempfile.mkstemp(suffix=".pdf")[1])
ok_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
r = run("push", str(ok_pdf), "--to", "not-a-folder-or-uuid")
check("bad --to target rejected offline",
      r.returncode != 0 and "not a FOLDERS name" in r.stderr, r)
ok_pdf.unlink()

# 5. ls with junk folder ref → resolve_folder guard (before reachability)
r = run("ls", "definitely-not-real")
check("bad ls folder rejected offline",
      r.returncode != 0 and "not a FOLDERS name" in r.stderr, r)

# 6. known FOLDERS names resolve (guard passes, fails later only on reachability
#    if unplugged — either 'not reachable' or a live listing is acceptable).
#    Uses the shipped example registry so a fresh clone passes without a folders.json.
_env = dict(os.environ, SCRIS_FOLDERS_FILE=str(SCRIS.parent / "folders.example.json"))
r = subprocess.run([sys.executable, str(SCRIS), "ls", "study"],
                   capture_output=True, text=True, timeout=60, env=_env)
check("FOLDERS name accepted by ls",
      "not a FOLDERS name" not in r.stderr, r)

# 7. pull with no args → argparse usage error
r = run("pull")
check("pull without args rejected", r.returncode == 2, r)

# 8. SSH verbs with missing args → argparse usage error, no network touched
r = run("mkdir")
check("mkdir without args rejected", r.returncode == 2, r)
r = run("mv", "some-doc")
check("mv without target folder rejected", r.returncode == 2, r)
r = run("trash")
check("trash without args rejected", r.returncode == 2, r)

# 9. SSH verbs refuse cleanly when `ssh scris` is down (never fall back to the
#    web API, never edit anything). Skipped if SSH is live — a real mkdir would
#    create junk on the tablet.
ssh_up = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
                         "scris", "true"], capture_output=True).returncode == 0
if ssh_up:
    print("  skip mkdir/mv/trash refusal checks — `ssh scris` is live")
else:
    for verb_args in (("mkdir", "x"), ("mv", "x", "random"), ("trash", "x")):
        r = run(*verb_args)
        check(f"{verb_args[0]} refuses cleanly without SSH",
              r.returncode != 0 and "ssh scris" in r.stderr, r)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
