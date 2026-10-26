# scris

Move files on and off a **reMarkable Paper Pro Move** from the command line, and pull your
handwriting back as **editable SVG vectors**. Plain Python, stdlib transport, no cloud account.

*scris* is Latin for "written" (from *scrībere*, to write). Tested on the Paper Pro Move (OS 3.27+). The USB verbs should work on any reMarkable
that exposes the USB web interface; the SSH verbs assume the Paper Pro Move's `xochitl` layout.

## What you get

| tool | what it does | needs |
|---|---|---|
| `scris.py ping · ls · find · pull · push` | list, search, download (PDF), upload (PDF/EPUB) over the USB web interface | USB cable, nothing else |
| `scris.py mkdir · mv · trash` | the things the web API cannot do: folders, moves, trash | SSH (developer mode) |
| `tools/vector_pull.py` | handwriting → `page-NN.svg` with editable strokes | SSH + `rmc` |
| `tools/backup_tablet.py` | pull **every** document as flattened PDF into a dated folder | USB cable |
| `tools/make_guide.py` | generate a faint "guider" PDF to draw over (lanes or radial layout) | `reportlab` |
| `tools/test_scris_offline.py` | 13 guard tests, no tablet required | nothing |

## Quickstart (USB only, five minutes)

1. On the tablet: **Settings → Storage → USB web interface → on**. Plug it in, keep it awake.
2. Then:

```bash
git clone https://github.com/dasanache/scris && cd scris
python3 scris.py ping            # "reachable" or a clean refusal telling you what to enable
python3 scris.py ls              # root listing with folder UUIDs
python3 scris.py push notes.pdf  # upload to root
python3 scris.py pull "notes"    # download by name (strokes baked in), lands in pulled/
```

Give folders names once and stop copying UUIDs around:

```bash
cp folders.example.json folders.json   # gitignored; fill in UUIDs from `scris.py ls`
python3 scris.py push drill.pdf --to study
```

Anywhere a folder or document is expected you can pass a UUID, a name from `folders.json`, or
(for `pull`) the document's visible name.

**Web API limits, by design:** upload is PDF/EPUB only, into folders that already exist; downloads
are PDFs with pen strokes flattened in. Everything else needs SSH.

## SSH verbs and vectors

> **Warning: enabling developer mode factory-resets the tablet.** Run
> `python3 tools/backup_tablet.py` first. Cloud sync did not preserve my content; the local
> backup did.

1. Enable developer mode: **Settings → General → Paper Tablet → Software → Advanced → Developer
   Mode** ([official docs](https://developer.remarkable.com/documentation/developer-mode)). The
   tablet reboots wiped. The root password is then shown under **Help → About → Copyrights and
   Licenses → General Information**. Back up first.
2. Put your key on it and add a host alias:

```
# ~/.ssh/config
Host scris
  HostName 10.11.99.1        # USB; use the tablet's Wi-Fi IP for WLAN
  User root
  IdentityFile ~/.ssh/scris_ed25519
```

   A different alias works too: `export SCRIS_SSH_HOST=mytablet`.

3. Verbs:

```bash
python3 scris.py mkdir "Reading" --register reading   # also writes it into folders.json
python3 scris.py mv "notes" reading
python3 scris.py trash "old draft"
```

Each SSH verb batches its `.metadata` edits and restarts `xochitl` **once** per batch. It refuses
to restart while a stroke file was written in the last 60 s (someone may be mid-stroke), and it
refuses cleanly when SSH is down so the USB verbs keep working on their own.

4. Vectors:

```bash
python3 -m venv .venv && .venv/bin/pip install rmc
python3 tools/vector_pull.py "notes"      # → vectors/notes/page-01.svg …
```

[`rmc`](https://github.com/ricklupton/rmc) parses the v6 `.rm` stroke format. It warns on some newer
Paper Pro Move blocks and still converts. Known limit: pages with typed text boxes can come out with
misplaced strokes. Its PDF output needs Inkscape; SVG is the target here.

## Guider PDFs

```bash
pip install reportlab
python3 tools/make_guide.py --layout lanes --orientation portrait --ink 1.0
python3 tools/make_guide.py --layout radial --variant simple --ink 1.8 --out radial.pdf
```

Content is data at the top of the file; layout is computed. The bundled content is a
"get the most out of Claude" explainer. Replace it with your own.

## Guards

```bash
python3 tools/test_scris_offline.py     # 13 passed, 0 failed — no tablet needed
```

The tablet's shell is **BusyBox**, not GNU coreutils. Every remote command string must be
BusyBox-compatible (`head -n 1`, never `head -1`). A GNU-ism fails silently inside a subshell
and can disable a guard, which is exactly how one guard here was once broken.

## Status

v0.1.0, first public release of a tool I have used daily since mid-2026 for a handwritten
exam-drill loop: generate a worksheet, push, work by hand, pull, grade. Issues and PRs welcome.
Not affiliated with reMarkable.

## License

MIT.
