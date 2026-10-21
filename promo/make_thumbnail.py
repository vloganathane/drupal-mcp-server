#!/usr/bin/env python
"""Brand thumbnail for the promo video (1920x1080, Loom/GitHub card ready).

Brandkit-flavoured art direction: dark charcoal canvas, faint grid, one soft
Drupal-blue glow, sparse editorial headline on the left, and a single terminal
application mockup on the right showing the real installer's per-client
checkmarks. Everything is drawn from scratch with Pillow so the whole thing is
reproducible and re-themeable.

Usage:  venv/bin/python promo/make_thumbnail.py [output_path]
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080

# Palette -------------------------------------------------------------------
BG_TOP = (10, 12, 16)
BG_BOTTOM = (16, 20, 27)
GRID = (255, 255, 255, 7)
ACCENT = (89, 166, 255)  # lifted Drupal blue, tuned for dark backgrounds
ACCENT_DEEP = (30, 95, 184)
GREEN = (122, 223, 164)
TEXT = (242, 245, 250)
TEXT_SOFT = (198, 207, 220)
MUTED = (150, 162, 179)
DIM = (103, 116, 138)
FOOT = (85, 97, 122)
CARD_BG = (16, 19, 26)
CARD_BAR = (22, 26, 35)
CARD_EDGE = (38, 44, 56)
CHIP_BG = (19, 23, 32)
CHIP_EDGE = (41, 48, 62)
DIMS = {"cursor": (255, 95, 87), "min": (254, 188, 46), "close": (40, 200, 64)}


def _exists(cands: list[str]) -> str | None:
    for path in cands:
        if os.path.exists(path):
            return path
    return None


SANS = _exists(
    [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
)
SANS_BOLD = _exists(
    [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
)
MONO = _exists(["/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc"])


def font(path: str | None, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if path is None:
        raise SystemExit("no usable font found")
    if path.endswith(".ttc"):
        for idx in range(8):
            try:
                f = ImageFont.truetype(path, size, index=idx)
            except OSError:
                break
            family, style = f.getname()
            if "Italic" in style or "Condensed" in style or "Rounded" in style:
                continue
            if ("Bold" in style) == bold:
                return f
    f = ImageFont.truetype(path, size)
    return f


def tracking_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: tuple[int, ...],
    track: int,
) -> int:
    """Draw text with letter-spacing (PIL has no native tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += int(draw.textlength(ch, font=fnt)) + track
    return x


def v_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img.convert("RGBA")


def drop(draw: ImageDraw.ImageDraw, cx: int, top: int, height: int, fill: tuple[int, ...]) -> None:
    """A simple geometric teardrop (generic nod to Drupal's drop)."""
    r = height * 40 // 100
    cy = top + height - r
    draw.polygon([(cx, top), (cx - r * 7 // 10, cy), (cx + r * 7 // 10, cy)], fill=fill)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "promo/thumbnail.png"

    img = v_gradient((W, H), BG_TOP, BG_BOTTOM)

    # Faint blueprint grid ---------------------------------------------------
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 135):
        gd.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 135):
        gd.line([(0, y), (W, y)], fill=GRID, width=1)
    img.alpha_composite(grid)

    # Soft glow behind the terminal card ------------------------------------
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gld = ImageDraw.Draw(glow)
    gld.ellipse([1000, 150, 1860, 870], fill=ACCENT_DEEP + (90,))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img.alpha_composite(glow)

    draw = ImageDraw.Draw(img)

    # Left column ------------------------------------------------------------
    sans_b_big = font(SANS_BOLD, 132, bold=True)
    sans_b_sm = font(SANS_BOLD, 56, bold=True)
    sans = font(SANS, 34)
    mono = font(MONO, 30)
    mono_sm = font(MONO, 24)
    mono_kicker = font(MONO, 25, bold=True)
    mono_tag = font(MONO, 20)
    mono_term = font(MONO, 26)
    mono_term_sm = font(MONO, 25, bold=True)

    drop(draw, 126, 96, 44, ACCENT)
    tracking_text(draw, (160, 104), "MCP SERVER FOR DRUPAL", mono_kicker, MUTED, track=9)

    draw.text((108, 190), "414", font=sans_b_big, fill=ACCENT)
    x_414 = 108 + int(draw.textlength("414", font=sans_b_big))
    draw.text((x_414, 190), " tools", font=sans_b_big, fill=TEXT)
    draw.text((108, 316), "One MCP", font=sans_b_big, fill=TEXT)
    draw.text((108, 442), "server", font=sans_b_big, fill=TEXT)
    # blue full stop rhyming with the blue stat
    w_server = int(draw.textlength("server", font=sans_b_big))
    draw.text((108 + w_server + 2, 442), ".", font=sans_b_big, fill=ACCENT)

    draw.text((112, 600), "Content, config, users, migrations.", font=sans, fill=MUTED)
    draw.text((112, 646), "Callable from any MCP client.", font=sans, fill=MUTED)

    # Install chip -----------------------------------------------------------
    draw.rounded_rectangle([108, 716, 924, 796], radius=16, fill=CHIP_BG, outline=CHIP_EDGE, width=2)
    draw.text((140, 738), "$", font=mono, fill=GREEN)
    draw.text((140 + int(draw.textlength("$", font=mono)) + 14, 738),
              "pip install drupal-mcp-server", font=mono, fill=TEXT_SOFT)
    draw.text((140, 828), "or try it instantly:  uvx --from drupal-mcp-server", font=mono_sm, fill=DIM)

    tracking_text(draw, (112, 990), "GITHUB.COM/VLOGANATHANE/DRUPAL-MCP-SERVER", mono_tag, FOOT, track=3)
    tag = "PYPI  ·  DRUPAL-MCP-SERVER 0.3.8"
    tag_w = sum(int(draw.textlength(ch, font=mono_tag)) + 5 for ch in tag) - 5
    tracking_text(draw, (1812 - tag_w, 70), tag, mono_tag, (62, 73, 89), track=5)

    # Terminal card ----------------------------------------------------------
    cx0, cy0, cx1, cy1 = 1010, 210, 1812, 800
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([cx0 + 6, cy0 + 26, cx1 + 6, cy1 + 26], radius=20, fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(36))
    img.alpha_composite(shadow)

    draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=20, fill=CARD_BG, outline=CARD_EDGE, width=2)
    draw.rounded_rectangle([cx0, cy0, cx1, cy0 + 62], radius=20, fill=CARD_BAR)
    draw.rectangle([cx0, cy0 + 32, cx1, cy0 + 62], fill=CARD_BAR)
    draw.line([(cx0, cy0 + 62), (cx1, cy0 + 62)], fill=CARD_EDGE, width=2)
    for i, key in enumerate(("cursor", "min", "close")):
        x = cx0 + 34 + i * 34
        draw.ellipse([x, cy0 + 22, x + 18, cy0 + 40], fill=DIMS[key])
    draw.text((cx0 + 160, cy0 + 18), "drupal-mcp — install", font=mono_sm, fill=(121, 131, 154))

    pad = 44
    ty = cy0 + 104
    draw.text((cx0 + pad, ty), "$", font=mono_term, fill=GREEN)
    draw.text((cx0 + pad + 26, ty), "drupal-mcp install", font=mono_term, fill=TEXT)
    ty += 62

    agents = [
        ("claude-code", "cursor", "windsurf"),
        ("claude-desktop", "codex", "pi"),
        ("opencode", "hermes", "openclaw"),
    ]
    col_x = [cx0 + pad, cx0 + pad + 278, cx0 + pad + 546]
    for row in agents:
        for name, x in zip(row, col_x):
            draw.text((x, ty), "✓", font=mono_term_sm, fill=(74, 222, 128))
            draw.text((x + 34, ty), name, font=mono_term, fill=TEXT_SOFT)
        ty += 52

    ty += 22
    for line in ("9 agents configured", "414 tools registered"):
        draw.text((cx0 + pad, ty), "→", font=mono_term, fill=ACCENT)
        draw.text((cx0 + pad + 34, ty), line, font=mono_term, fill=MUTED)
        ty += 52

    # Filmic scanlines -------------------------------------------------------
    scan = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    scd = ImageDraw.Draw(scan)
    for y in range(0, H, 3):
        scd.line([(0, y), (W, y)], fill=(0, 0, 0, 9), width=1)
    img.alpha_composite(scan)

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.convert("RGB").save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


if __name__ == "__main__":
    main()
