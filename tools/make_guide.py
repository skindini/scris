#!/usr/bin/env python3
"""
make_guide.py — faint "guider" PDFs for hand-drawn explainers on a reMarkable.

You draw OVER the output on the tablet: the light-gray print is scaffolding,
not a finished template. Content lives in data at the top; layout is computed,
so one generator covers every variant:

    --layout      lanes | radial          (default: lanes — the chosen design)
    --orientation portrait | landscape    (default: portrait, 3:4 tablet screen)
    --variant     full | simple           (simple drops the API/dev branch)
    --ink         float                   (darkness multiplier: 1.0 = faint
                                           guider, ~1.8 = medium, ~2.5 = print-dark)
    --out         output path             (default: out/claude-explainer-guide.pdf)

Examples:
    python3 make_guide.py                                   # the canonical guider
    python3 make_guide.py --variant simple --ink 1.8 --out simple.pdf
    python3 make_guide.py --layout radial --orientation landscape --out radial.pdf

Preview:  pdftoppm -png -r 100 <out>.pdf preview
"""
from __future__ import annotations
import argparse
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

F, FB = "Helvetica", "Helvetica-Bold"
HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "out" / "claude-explainer-guide.pdf"

# ---- content (edit here, not in the renderers) ----------------------------
TITLE = "CLAUDE  ·  get the most out of it"
SUBTITLE = "faint lines are a guide — trace, connect, doodle, make it yours"

# node kinds: ("node", label, {opts})  |  ("hub", title, [items])
LANES = [
    dict(key="chat", header="CHAT  ·  everyday", header_size=10,
         rows=[
             [("node", "Projects", {}), ("node", "Artifacts", {}),
              ("node", "Memory + Chat Search", {})],
             [("hub", "Customize  (set once)",
               ["Styles  (your voice)", "Connectors (MCP)", "Skills", "Plugins"]),
              ("hub", "Per-chat toggles",
               ["Extended Thinking", "Web Search", "Deep Research",
                "Code + File creation"])],
         ]),
    dict(key="code", header="CLAUDE CODE", header_size=9.5,
         rows=[
             [("node", "Terminal / agentic coding — reads & edits your whole "
                       "project, runs commands.  Same Skills · Plugins · Connectors.",
               dict(size=7.7, wide=True))],
         ]),
    dict(key="cowork", header="COWORK / DESKTOP", header_size=9,
         rows=[
             [("node", "Computer Use", {}),
              ("node", "Claude in Chrome (beta)", dict(size=7.5)),
              ("node", "Claude in Excel / Office (beta)", dict(size=7.3))],
             [("node", "Scheduled Tasks / Routines", dict(size=7.7)),
              ("node", "Dispatch  (phone trigger)", dict(size=7.7))],
         ]),
    dict(key="api", header="API  ·  developers", header_size=9, dev=True,
         rows=[
             [("node", "Models — Opus 4.8 · Sonnet 5 · Haiku 4.5",
               dict(size=7.6, span=2)), ("node", "Tool Use", {})],
             [("node", "MCP", {}), ("node", "Batch + Streaming", dict(size=7.7))],
         ]),
]

HABITS_TITLE = "5 HABITS  —  how to actually get the most out of it"
HABITS = [("Give it", "context"), ("Ask for the", "format you want"),
          ("Let it think /", "search when hard"), ("Iterate —", "don't restart"),
          ("Save what works", "(Style/Project/Skill)")]

IDEAS_TITLE = "IDEAS  —  make it yours"
IDEAS = [
    "Give each feature a little icon — a folder for Projects, a magnifying glass "
    "for Web Search, a robot for Computer Use, a quill for Styles.",
    "Jot a one-line example by the ones you love  (Artifacts → “built me a budget "
    "app”;  Projects → “all my class notes in one place”).",
    "Shade the 3 everyday heroes — Projects, Artifacts, Memory — so friends know "
    "where to start.",
    "Circle what you actually use, cross out what you don't. It's a map of YOUR "
    "Claude, not a feature list.",
]


# ---- drawing primitives ----------------------------------------------------
class Guide:
    def __init__(self, out: Path, w: float, h: float, ink: float):
        self.c = canvas.Canvas(str(out), pagesize=(w, h))
        self.W, self.H = w, h
        self.ink = ink

    def g(self, gray: float) -> float:
        """Scale a design gray by the ink factor (1.0 = as-designed faintness)."""
        return max(0.0, 1.0 - (1.0 - gray) * self.ink)

    def wrap(self, text, font, size, maxw):
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if stringWidth(t, font, size) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def node(self, x, y, w, h, label, size=8, bold=False, tg=0.45, bg=0.66,
             lw=0.8, r=6):
        c = self.c
        c.setFillGray(1); c.setStrokeGray(self.g(bg)); c.setLineWidth(lw)
        c.roundRect(x, y, w, h, r, stroke=1, fill=1)
        font = FB if bold else F
        lines = self.wrap(label, font, size, w - 8)
        lh = size + 1.5
        ty = y + h / 2 + (len(lines) * lh) / 2 - size * 0.85
        c.setFillGray(self.g(tg)); c.setFont(font, size)
        for ln in lines:
            c.drawCentredString(x + w / 2, ty, ln)
            ty -= lh

    def hub(self, x, y, w, h, title, items):
        c = self.c
        c.setFillGray(1); c.setStrokeGray(self.g(0.6)); c.setLineWidth(0.9)
        c.roundRect(x, y, w, h, 6, stroke=1, fill=1)
        c.setFillGray(self.g(0.32)); c.setFont(FB, 8)
        c.drawString(x + 8, y + h - 13, title)
        c.setFillGray(self.g(0.5)); c.setFont(F, 7.5)
        yy = y + h - 25
        for it in items:
            c.drawString(x + 11, yy, "– " + it)
            yy -= 10.5

    def line(self, x1, y1, x2, y2, g=0.84, lw=0.7):
        self.c.setStrokeGray(self.g(g)); self.c.setLineWidth(lw)
        self.c.line(x1, y1, x2, y2)

    def divider(self, y, x0, x1):
        self.line(x0, y, x1, y, g=0.88, lw=0.6)

    # ---- shared bands (title / habits / ideas) -----------------------------
    def title_band(self):
        c = self.c
        c.setFillGray(self.g(0.42)); c.setFont(FB, 15.5)
        c.drawCentredString(self.W / 2, self.H - 24, TITLE)
        c.setFillGray(self.g(0.55)); c.setFont(F, 8)
        c.drawCentredString(self.W / 2, self.H - 36, SUBTITLE)

    def habits_band(self, top):
        """Draw the habits ribbon with its top edge at `top`; return its bottom y."""
        c = self.c
        c.setFillGray(self.g(0.34)); c.setFont(FB, 9.5)
        c.drawCentredString(self.W / 2, top - 10, HABITS_TITLE)
        n = len(HABITS)
        pw, gap, ph = 100, 12, 40
        x0 = (self.W - (n * pw + (n - 1) * gap)) / 2
        y = top - 20 - ph
        for i, (a, b) in enumerate(HABITS):
            x = x0 + i * (pw + gap)
            c.setFillGray(1); c.setStrokeGray(self.g(0.62)); c.setLineWidth(0.9)
            c.roundRect(x, y, pw, ph, 8, stroke=1, fill=1)
            c.setFillGray(self.g(0.4))
            c.setFont(FB, 8); c.drawCentredString(x + pw / 2, y + 24, a)
            c.setFont(F, 7.3); c.drawCentredString(x + pw / 2, y + 14, b)
            c.setFillGray(self.g(0.72)); c.setFont(FB, 11)
            c.drawCentredString(x + pw / 2, y + 3, str(i + 1))
        return y

    def ideas_band(self, top, margin):
        c = self.c
        c.setFillGray(self.g(0.34)); c.setFont(FB, 8.5)
        c.drawString(margin, top, IDEAS_TITLE)
        c.setFillGray(self.g(0.5)); c.setFont(F, 7.6)
        yy = top - 13
        maxw = self.W - 2 * margin - 56
        for it in IDEAS:
            for j, ln in enumerate(self.wrap(it, F, 7.6, maxw)):
                c.drawString(margin, yy, ("•  " if j == 0 else "    ") + ln)
                yy -= 10.5

    def save(self):
        self.c.showPage()
        self.c.save()


# ---- lanes layout (the chosen design) --------------------------------------
def render_lanes(gd: Guide, lanes):
    W = gd.W
    margin = 30
    hx, hw = margin, 122          # left header column
    spinex = hx + hw / 2
    cx0 = hx + hw + 13            # content area
    cx1 = W - margin - 13
    cw = cx1 - cx0
    hubx = W / 2

    gd.title_band()

    # measure lanes: node rows are 28pt + 10 gap; hub rows are 76pt + 10
    def row_h(row):
        return 76 if any(k == "hub" for k, *_ in row) else 28

    y = gd.H - 66                 # top of first lane content
    lane_tops, lane_bots = [], []
    root_y = gd.H - 74

    # CLAUDE root -> spine (drawn before nodes so fills hide it in the gaps)
    first_center = y - row_h(lanes[0]["rows"][0]) / 2
    gd.line(hubx, root_y, spinex, first_center, g=0.86)

    # pre-compute lane extents to draw the spine through all headers
    yy = y
    for lane in lanes:
        top = yy
        for row in lane["rows"]:
            yy -= row_h(row) + 10
        lane_tops.append(top)
        lane_bots.append(yy + 10)
        yy -= 17                  # divider gap
    gd.line(spinex, first_center, spinex,
            (lane_tops[-1] + lane_bots[-1]) / 2, g=0.86)

    gd.node(hubx - 62, root_y, 124, 30, "CLAUDE", size=13, bold=True,
            tg=0.28, bg=0.42, lw=1.4)

    yy = y
    for li, lane in enumerate(lanes):
        top, bot = lane_tops[li], lane_bots[li]
        gd.node(hx, bot, hw, top - bot, lane["header"],
                size=lane["header_size"], bold=True, tg=0.3, bg=0.5)
        ry = top
        for row in lane["rows"]:
            rh = row_h(row)
            ry -= rh
            # split content width among cells honoring span/wide
            spans = [o.get("span", 1) if k == "node" else o_hub_span(row)
                     for k, _, o in _norm(row)]
            total = sum(spans)
            gap = 10
            unit = (cw - gap * (len(row) - 1)) / total
            x = cx0
            for (kind, label, opts), sp in zip(_norm(row), spans):
                w = unit * sp + gap * (sp - 1)
                if kind == "hub":
                    gd.hub(x, ry, w, rh, label, opts)
                else:
                    gd.node(x, ry, w, rh, label,
                            size=opts.get("size", 8), tg=0.4)
                x += w + gap
            ry -= 10
        yy = bot - 17
        if li < len(lanes) - 1:
            gd.divider(bot - 7, margin - 2, W - margin + 2)

    # bands below the lanes
    hb_bottom = gd.habits_band(lane_bots[-1] - 17)
    gd.divider(hb_bottom - 13, margin - 2, W - margin + 2)
    gd.ideas_band(hb_bottom - 28, margin)


def _norm(row):
    for cell in row:
        kind, label, third = cell
        yield kind, label, third


def o_hub_span(row):
    return 1


# ---- radial layout (the offered-but-not-chosen variant, kept alive) --------
def render_radial(gd: Guide, lanes):
    """Organic-radial: CLAUDE at center, each branch owns a quadrant and its
    children stack in columns from the page corner inward — collision-free by
    construction (a true arc fan overlaps at this node count / page size)."""
    W, H = gd.W, gd.H
    margin = 30
    gd.title_band()

    bands_h = 175                          # habits + ideas at the bottom
    y0, y1 = bands_h + 45, H - 55          # diagram region
    cx, cy = W / 2, (y0 + y1) / 2

    # quadrant signs (sx, sy): CHAT TL, CODE TR, COWORK BL, API BR
    anchors = [(-1, 1), (1, 1), (-1, -1), (1, -1)]
    col_w, gap = 132, 8    # two columns per quadrant stay clear of the midline

    for lane, (sx, sy) in zip(lanes, anchors):
        hx = cx + sx * W * 0.26
        hy = cy + sy * (y1 - y0) * 0.17
        gd.line(cx, cy, hx, hy, g=0.86)

        children = list(_norm(cell for row in lane["rows"] for cell in row))

        # column-stack from the outer corner inward; a column stops at the page
        # midline — or earlier, above/below the header box if it shares its x-range
        def limit_for(col_x):
            if abs(col_x - hx) < col_w / 2 + 62:
                return hy + sy * 26
            return cy + sy * 14

        x = margin + col_w / 2 if sx < 0 else W - margin - col_w / 2
        y = y1 if sy > 0 else y0
        inner_limit = limit_for(x)
        for kind, label, opts in children:
            if kind == "hub":
                w, h = col_w, 64
            elif opts.get("wide"):
                w, h = col_w, 58
            else:
                w, h = col_w, 32
            ny = y - h / 2 if sy > 0 else y + h / 2
            crossed = (ny - h / 2 < inner_limit) if sy > 0 else (ny + h / 2 > inner_limit)
            if crossed:                    # next column, one step inward
                x -= sx * (col_w + gap)
                y = y1 if sy > 0 else y0
                inner_limit = limit_for(x)
                ny = y - h / 2 if sy > 0 else y + h / 2
            gd.line(hx, hy, x, ny, g=0.88)
            if kind == "hub":
                gd.hub(x - w / 2, ny - h / 2, w, h, label, opts)
            else:
                gd.node(x - w / 2, ny - h / 2, w, h, label,
                        size=opts.get("size", 7.4), tg=0.4)
            y = (ny - h / 2 - gap) if sy > 0 else (ny + h / 2 + gap)

        gd.node(hx - 62, hy - 16, 124, 32, lane["header"],
                size=lane["header_size"], bold=True, tg=0.3, bg=0.5)

    gd.node(cx - 62, cy - 16, 124, 32, "CLAUDE", size=13, bold=True,
            tg=0.28, bg=0.42, lw=1.4)

    hb_bottom = gd.habits_band(bands_h + 25)
    gd.divider(hb_bottom - 13, margin - 2, W - margin + 2)
    gd.ideas_band(hb_bottom - 28, margin)


# ---- cli --------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a faint hand-drawing guider PDF.")
    ap.add_argument("--layout", choices=["lanes", "radial"], default="lanes")
    ap.add_argument("--orientation", choices=["portrait", "landscape"],
                    default="portrait")
    ap.add_argument("--variant", choices=["full", "simple"], default="full",
                    help="simple = drop the API/developer branch")
    ap.add_argument("--ink", type=float, default=1.0,
                    help="darkness multiplier (1.0 faint guider, 1.8 medium, 2.5 dark)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    w, h = (612, 816) if args.orientation == "portrait" else (816, 612)
    lanes = [l for l in LANES if args.variant == "full" or not l.get("dev")]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    gd = Guide(args.out, w, h, args.ink)
    (render_lanes if args.layout == "lanes" else render_radial)(gd, lanes)
    gd.save()
    print(f"wrote {args.out}  [{args.layout}/{args.orientation}/{args.variant}, ink={args.ink}]")


if __name__ == "__main__":
    main()
