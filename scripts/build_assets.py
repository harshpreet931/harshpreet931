#!/usr/bin/env python3
"""Draw the SVGs this README is made of.

The hero mirrors harshpreet.com: GitHub's dark mode gets the Midnight theme (a
drifting mesh gradient), light mode gets the Handwritten theme (ruled notebook
paper, ballpoint blue). In both, my name writes itself with the pen centrelines
of Harshpreet Hand, the font I made from 120 pages of my Computer Networks
notes, so the build needs that repo checked out next to this one.

Every other letter is outlined to a path here, because an SVG shown through
<img> can't load fonts.

Usage (from the repo root; needs numpy, fonttools, uharfbuzz, brotli, pillow):
  python3 scripts/build_assets.py [path/to/myHandwriting]
"""
import base64
import io
import json
import os
import sys
from functools import lru_cache

import numpy as np
import uharfbuzz as hb
from fontTools.agl import UV2AGL
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAND = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "myHandwriting"))
OUT = os.path.join(ROOT, "assets")

FONTS = {
    "inter": (os.path.join(ROOT, "scripts", "fonts", "Inter.woff2"), {"wght": 400}),
    "mono": (os.path.join(ROOT, "scripts", "fonts", "SpaceMono-Regular.woff2"), None),
    "hand": (os.path.join(HAND, "dist", "HarshpreetHand-Regular.ttf"), None),
}

# The two site themes the README follows (values from harshpreet.com).
THEMES = {
    "dark": {
        "bg": "#000814",
        "text": "#ffffff",
        "ink": "#ffffff",
        "note": "#7dd3fc",
        "accent": "#0ea5e9",
        "line": "rgba(255,255,255,0.14)",
        "edge": "rgba(255,255,255,0.14)",
    },
    "light": {
        "bg": "#f7f8fc",
        "text": "#1f2f8c",
        "ink": "#1f2f8c",
        "note": "#c2413f",
        "accent": "#1f2f8c",
        "rule": "rgba(84,116,196,0.2)",
        "margin": "rgba(208,86,84,0.5)",
        "edge": "rgba(31,47,140,0.10)",
    },
}

W = 1600  # every asset is 1600 units wide and shown at 100% of the README


# ── Pen strokes ──────────────────────────────────────────────────────────
# Ported from harshpreet-portfolio/scripts/handwriting-strokes.py so the
# README writes exactly the way the site does.

S = 440                      # font units per x-height
SB = 0.13 * S                # side bearing
TIGHT = set(".,:;'’‘\"“”!")
SPEED, MIN_STROKE = 9.0, 55  # font units per ms; shortest stroke in ms
PEN_UP, LETTER_GAP, WORD_GAP, DOT_GAP = 35, 50, 180, 90


def _glyph_name(ch):
    return UV2AGL.get(ord(ch)) or f"uni{ord(ch):04X}"


def _rdp(pts, eps):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.hypot(*ab)
    d = np.hypot(*(pts - a).T) if n == 0 else np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n
    i = int(np.argmax(d))
    if d[i] <= eps:
        return np.array([a, b])
    return np.vstack([_rdp(pts[: i + 1], eps)[:-1], _rdp(pts[i:], eps)])


def _orient(p):
    a, b = p[0], p[-1]
    if np.hypot(*(a - b)) < 0.05 * S:
        return p
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    if dx > 2.5 * dy:
        return p if a[0] <= b[0] else p[::-1]
    return p if a[1] >= b[1] else p[::-1]


@lru_cache(None)
def _hand_font():
    glyphs = json.load(open(os.path.join(HAND, "design", "glyphs.json")))
    ttf = FONTS["hand"][0]
    order = TTFont(ttf).getGlyphOrder()
    variants = {}
    for ch, vs in glyphs.items():
        base = _glyph_name(ch)
        for i, v in enumerate(vs):
            variants[base if i == 0 else f"{base}.alt{i}"] = (ch, v["paths"])
    return hb.Font(hb.Face(hb.Blob.from_file_path(ttf))), order, variants


def pen_text(text, start=0.0, pace=1.0):
    """Shape `text` and return its pen strokes, baseline at y=0, y down.

    Each stroke is (points, delay_ms, duration_ms). `pace` > 1 writes faster.
    """
    font, order, variants = _hand_font()
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"calt": True, "kern": True})

    words, cur, pending, x = [], [], [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        if name in ("space", "uni00A0"):
            if cur:
                words.append(cur + [pending] if pending else cur)
            cur, pending, x = [], [], 0.0
            continue
        ch, paths = variants[name]
        P = [np.asarray(p, float) * S for p in paths]
        x0 = min(p[:, 0].min() for p in P)
        dx = x + pos.x_offset - x0 + SB * (0.45 if ch in TIGHT else 1.0)
        strokes = [_orient(np.c_[p[:, 0] + dx, p[:, 1] + pos.y_offset]) for p in P]
        strokes.sort(key=lambda p: (round(p[0][0] / (0.15 * S)), -p[0][1]))
        dots = [p for p in strokes if ch in "ij" and p[:, 1].min() > 1.2 * S]
        cur.append([p for p in strokes if not any(p is d for d in dots)])
        pending.extend(dots)
        x += pos.x_advance
    if cur:
        words.append(cur + [pending] if pending else cur)

    pen = 0.13 * S
    gap = 0.72 * S + 2 * SB
    t, cursor, out = start, 0.0, []
    for wi, w in enumerate(words):
        if wi:
            t += WORD_GAP / pace
        left = min(p[:, 0].min() for g in w for p in g) - pen / 2
        right = max(p[:, 0].max() for g in w for p in g) + pen / 2
        for gi, g in enumerate(w):
            if gi:
                t += LETTER_GAP / pace
            if gi and all(p[:, 1].min() > 1.2 * S for p in g):
                t += DOT_GAP / pace
            for si, p in enumerate(g):
                if si:
                    t += PEN_UP / pace
                length = float(np.sum(np.hypot(*np.diff(p, axis=0).T)))
                dur = max(MIN_STROKE, length / SPEED) / pace
                q = _rdp(p, 1.2)
                q = np.c_[q[:, 0] - left + cursor, -q[:, 1]]
                out.append((q, t, dur))
                t += dur
        cursor += right - left + gap
    return {"strokes": out, "width": cursor - gap, "end": t}


def stroke_svg(pt, x, y, scale, width, color, animate=True):
    """Pen strokes as SVG paths, placed with their baseline at (x, y)."""
    paths = []
    for q, delay, dur in pt["strokes"]:
        q = np.round(q).astype(int)
        d = f"M{q[0][0]} {q[0][1]}" + "".join(f"l{b[0] - a[0]} {b[1] - a[1]}" for a, b in zip(q[:-1], q[1:]))
        if not animate:
            paths.append(f'<path d="{d}"/>')
            continue
        # Dash = the stroke, gap = stroke + nib, so the round cap can't peek out
        # before the pen arrives.
        L = float(np.sum(np.hypot(*np.diff(q, axis=0).T))) + 1
        off = L + width
        paths.append(
            f'<path class="s" d="{d}" stroke-dasharray="{L:.0f} {off:.0f}" stroke-dashoffset="{off:.0f}" '
            f'style="animation-delay:{delay:.0f}ms;animation-duration:{dur:.0f}ms"/>'
        )
    return (
        f'<g transform="translate({x:.1f} {y:.1f}) scale({scale:.5f})" fill="none" stroke="{color}" '
        f'stroke-width="{width:.0f}" stroke-linecap="round" stroke-linejoin="round">' + "".join(paths) + "</g>"
    )


# ── Outlined text ────────────────────────────────────────────────────────

@lru_cache(None)
def _outline_font(key):
    path, axes = FONTS[key]
    tt = TTFont(path)
    if axes:
        tt = instancer.instantiateVariableFont(tt, axes)
    data = io.BytesIO()
    tt.flavor = None
    tt.save(data)
    blob = data.getvalue()
    tt = TTFont(io.BytesIO(blob))
    return tt, hb.Font(hb.Face(hb.Blob(blob)))


def text_width(text, key, size, tracking=0.0):
    return outline(text, key, size, 0, 0, tracking)[1]


def outline(text, key, size, x, y, tracking=0.0):
    """Return (path d, advance) for `text` set at baseline (x, y)."""
    tt, font = _outline_font(key)
    upem = tt["head"].unitsPerEm
    s = size / upem
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "calt": True})
    order = tt.getGlyphOrder()
    gs = tt.getGlyphSet()
    parts, pen_x = [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = order[info.codepoint]
        svg = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        gx = x + (pen_x + pos.x_offset) * s
        gy = y - pos.y_offset * s
        gs[name].draw(TransformPen(svg, (s, 0, 0, -s, gx, gy)))
        parts.append(svg.getCommands())
        pen_x += pos.x_advance + tracking * upem
    return "".join(parts), pen_x * s


def text_svg(text, key, size, x, y, fill, tracking=0.0):
    d, _ = outline(text, key, size, x, y, tracking)
    return f'<path d="{d}" fill="{fill}"/>'


# ── Shared pieces ────────────────────────────────────────────────────────

@lru_cache(None)
def grain(size=180, seed=7):
    """A tile of film grain as a data URI. A 1-bit PNG is a few KB; an SVG
    turbulence filter would be recomputed on every frame of the mesh."""
    rng = np.random.default_rng(seed)
    img = Image.fromarray(rng.random((size, size)) > 0.5).convert("1")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def grain_layer(h, opacity, rx):
    return (
        f'<pattern id="grain" width="180" height="180" patternUnits="userSpaceOnUse">'
        f'<image width="180" height="180" xlink:href="{grain()}"/></pattern>'
    ), f'<rect width="{W}" height="{h}" rx="{rx}" fill="url(#grain)" opacity="{opacity}"/>'


def svg_doc(h, title, body, style=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-label="{title}">'
        f"<title>{title}</title>"
        + (f"<style>{style}</style>" if style else "")
        + body
        + "</svg>\n"
    )


MOTION = """
.s{animation-name:draw;animation-timing-function:linear;animation-fill-mode:forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.up{opacity:0;animation:up .45s cubic-bezier(.25,.1,.25,1) forwards}
@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important}
  .s{stroke-dashoffset:0!important}
  .up{opacity:1!important}
}
"""


# ── Hero ─────────────────────────────────────────────────────────────────

HERO_H = 760
NAME = "Harshpreet Singh"
NOTE = ["my handwriting, lifted from", "120 pages of my networks notes ↓"]
META = [
    ("BENGALURU", "12.97° N, 77.59° E"),
    ("Harshpreet Singh", "Software Development Engineer."),
    ("Building AI-Native Systems", "I build systems with", "depth and design."),
    ("CURRENTLY", "ASDE @ JUSPAY"),
]


def mesh(theme):
    """Blobs of the site's MeshGradient palette, each drifting on its own loop."""
    if theme == "dark":
        blobs = [
            # cx, cy, rx, ry, color, peak opacity, drift (dx, dy, scale), seconds
            (1380, 40, 900, 560, "#0ea5e9", 1.0, (-140, 70, 1.08), 23),
            (1500, 700, 760, 520, "#003566", 0.95, (-120, -60, 1.12), 29),
            (760, 420, 820, 520, "#001d3d", 0.9, (90, -40, 1.1), 31),
            (180, 520, 700, 520, "#000814", 0.95, (80, 40, 1.05), 27),
            (980, -60, 520, 300, "#38bdf8", 0.55, (-90, 40, 1.15), 19),
        ]
    else:
        blobs = [
            (1400, 60, 820, 460, "#e0e7ff", 0.85, (-120, 60, 1.08), 26),
            (260, 700, 760, 420, "#e0f2fe", 0.8, (100, -40, 1.1), 31),
            (980, 380, 600, 360, "#fdf2f8", 0.55, (-80, 30, 1.12), 23),
        ]
    defs, shapes, css = [], [], []
    for i, (cx, cy, rx, ry, c, o, (dx, dy, k), sec) in enumerate(blobs):
        stops = "".join(
            f'<stop offset="{r}" stop-color="{c}" stop-opacity="{o * np.exp(-4.5 * r * r):.3f}"/>'
            for r in (0, 0.2, 0.4, 0.6, 0.8)
        )
        defs.append(f'<radialGradient id="m{i}">{stops}<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient>')
        shapes.append(f'<ellipse class="m{i}" cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#m{i})"/>')
        css.append(
            f".m{i}{{transform-box:fill-box;transform-origin:center;animation:m{i} {sec}s ease-in-out infinite alternate}}"
            f"@keyframes m{i}{{to{{transform:translate({dx}px,{dy}px) scale({k})}}}}"
        )
    return "".join(defs), "".join(shapes), "".join(css)


def hero(theme):
    t = THEMES[theme]
    h, rx = HERO_H, 28
    dark = theme == "dark"
    left = 64 if dark else 104
    right = W - 64

    mdefs, mshapes, mcss = mesh(theme)
    gdefs, glayer = grain_layer(h, 0.07 if dark else 0.035, rx)

    paper = ""
    if not dark:
        # Ruled lines every 40 units and the red margin, as on the site.
        rules = "".join(f'<rect y="{y}" width="{W}" height="1.5" fill="{t["rule"]}"/>' for y in range(76, h - 20, 40))
        paper = rules + f'<rect x="72" width="1.5" height="{h}" fill="{t["margin"]}"/>'

    # The four-column strip from the top of harshpreet.com, fading up with the
    # site's stagger. The README is about half the site's width, so the columns
    # sit where the text fits instead of on the site's 1fr 1fr 2fr 1fr grid.
    span = right - left
    cols = [left + f * span for f in (0, 0.2, 0.5, 0.8)]
    meta = []
    for i, (x, lines) in enumerate(zip(cols, META)):
        if dark:
            rows = "".join(text_svg(s, "inter", 23, x, 112 + j * 31, t["text"]) for j, s in enumerate(lines))
        else:
            # Pen strokes, not font outlines: the same letters at a tenth of the size.
            rows = "".join(stroke_svg(pen_text(s), x, 116 + j * 40, 0.027, 62, t["text"], animate=False)
                           for j, s in enumerate(lines))
        meta.append(f'<g class="up" style="animation-delay:{100 + 70 * i}ms">{rows}</g>')

    # The name, written along the bottom like the site's handwritten theme.
    name = pen_text(NAME, start=650)
    scale = 1240 / name["width"]
    name_svg = stroke_svg(name, left - 6, 596, scale, 57.2, t["ink"])

    # A margin note, scribbled in after the name lands. pace 5 at this size
    # moves the pen exactly as fast across the page as it moved for the name.
    note_svg, ny = [], 0
    start = name["end"] + 250
    for line in NOTE:
        pt = pen_text(line, start=start, pace=5)
        note_svg.append(stroke_svg(pt, 0, ny, 0.034, 92, t["note"]))
        start = pt["end"] + 120
        ny += 40
    note = f'<g transform="translate(1036 404) rotate(-4)">' + "".join(note_svg) + "</g>"

    border = f'<rect x=".75" y=".75" width="{W - 1.5}" height="{h - 1.5}" rx="{rx}" fill="none" stroke="{t["edge"]}" stroke-width="1.5"/>'
    body = (
        f'<defs><clipPath id="c"><rect width="{W}" height="{h}" rx="{rx}"/></clipPath>{mdefs}{gdefs}</defs>'
        f'<g clip-path="url(#c)"><rect width="{W}" height="{h}" fill="{t["bg"]}"/>{mshapes}{paper}{glayer}'
        + "".join(meta) + name_svg + note + f"</g>{border}"
    )
    title = "Harshpreet Singh, written in my own handwriting. Software Development Engineer at Juspay, Bengaluru. I build systems with depth and design."
    return svg_doc(h, title, body, MOTION + mcss)


# ── Section labels ───────────────────────────────────────────────────────
# Labels go inside an <h2> in the README: GitHub draws the h2's hairline across
# the full width in both themes, and the label itself is shown at its natural
# size so it reads the same on a phone. GitHub turns an <img height> into
# height:auto, so a full-width strip would shrink to nothing on mobile.

DISPLAY = 0.525  # 1600 units across a ~840px profile README


def tight(inner, x0, y0, x1, y1, title):
    """An SVG cropped to (x0, y0)-(x1, y1), sized to show at DISPLAY scale."""
    w, h = x1 - x0, y1 - y0
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}" '
        f'width="{w * DISPLAY:.0f}" height="{h * DISPLAY:.0f}" role="img" aria-label="{title}">'
        f"<title>{title}</title>{inner}</svg>\n"
    )


def pen_bounds(pt, scale, width):
    ys = np.concatenate([q[:, 1] for q, _, _ in pt["strokes"]]) * scale
    pad = width * scale / 2 + 2
    return ys.min() - pad, ys.max() + pad, pt["width"] * scale + 2 * pad


def label(theme, text):
    t = THEMES[theme]
    if theme == "dark":
        # The site's small caps: Inter, tracked out a little.
        caps = text.upper()
        tw = text_width(caps, "inter", 22, 0.06)
        return tight(text_svg(caps, "inter", 22, 0, 0, t["text"], 0.06), -1, -20, tw + 1, 4, text)
    pt = pen_text(text)
    scale, width = 0.052, 72
    top, bottom, w = pen_bounds(pt, scale, width)
    pad = width * scale / 2 + 2
    return tight(stroke_svg(pt, pad, 0, scale, width, t["ink"], animate=False), 0, top, w, bottom, text)


# ── Footer ───────────────────────────────────────────────────────────────

WIRE_H = 24


def wire(theme):
    """A wire with packets running along it, closing the page. For the notes."""
    t = THEMES[theme]
    dark = theme == "dark"
    y = WIRE_H / 2
    packet = t["accent"]
    pkts = "".join(
        f'<rect class="p" x="-200" y="{y - 2}" width="200" height="4" rx="2" fill="url(#pk)" style="animation-delay:{d}s"/>'
        for d in (0, 2.6, 4.1)
    )
    css = (
        ".p{animation:run 7.8s cubic-bezier(.45,0,.2,1) infinite;opacity:0}"
        "@keyframes run{0%{transform:translateX(0);opacity:0}8%{opacity:1}92%{opacity:1}100%{transform:translateX(1800px);opacity:0}}"
        "@media (prefers-reduced-motion:reduce){.p{animation:none;opacity:0}}"
    )
    body = (
        f'<defs><linearGradient id="pk"><stop offset="0" stop-color="{packet}" stop-opacity="0"/>'
        f'<stop offset=".85" stop-color="{packet}" stop-opacity=".9"/>'
        f'<stop offset="1" stop-color="{"#ffffff" if dark else packet}"/></linearGradient></defs>'
        f'<rect y="{y - 0.75}" width="{W}" height="1.5" fill="{t["line"] if dark else t["rule"]}"/>{pkts}'
    )
    return svg_doc(WIRE_H, "", body, css)


def signoff(theme):
    pt = pen_text("thanks for stopping by :)")
    scale, width = 0.05, 80
    top, bottom, w = pen_bounds(pt, scale, width)
    pad = width * scale / 2 + 2
    return tight(stroke_svg(pt, pad, 0, scale, width, THEMES[theme]["ink"], animate=False),
                 0, top, w, bottom, "thanks for stopping by :)")


# ── Build ────────────────────────────────────────────────────────────────

LABELS = {"work": "selected work", "notes": "recent notes", "elsewhere": "elsewhere"}


def main():
    os.makedirs(OUT, exist_ok=True)
    files = {}
    for theme in THEMES:
        files[f"hero-{theme}.svg"] = hero(theme)
        files[f"wire-{theme}.svg"] = wire(theme)
        files[f"signoff-{theme}.svg"] = signoff(theme)
        for slug, text in LABELS.items():
            files[f"label-{slug}-{theme}.svg"] = label(theme, text)
    for name, svg in files.items():
        with open(os.path.join(OUT, name), "w") as f:
            f.write(svg)
        print(f"assets/{name}: {len(svg) / 1024:.1f} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
