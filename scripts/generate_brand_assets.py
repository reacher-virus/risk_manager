"""Regenerates the favicon set, Apple touch icon, PWA icons, web manifest and the 1200x630 social-share image.

    pip install pillow && python scripts/generate_brand_assets.py

Edit BRAND below (colours / names) and re-run; outputs go to frontend/public/. Nothing is downloaded or hot-linked.
"""
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND = {"name": "Risk Manager", "tagline_1": "AI fraud detection that explains", "tagline_2": "every decision.",
         "badges": "Defense-only  ·  Explainable  ·  Cost-aware", "bg": (9, 9, 11), "accent": (249, 115, 22)}
OUT = Path(__file__).resolve().parents[1] / "frontend" / "public"
PULSE = [(4, 16), (9, 16), (12, 7), (17, 25), (20, 16), (28, 16)]       # the same polyline as the SVG logo, on a 32x32 grid
BG, ORANGE = BRAND["bg"], BRAND["accent"]


def logo(size, radius_ratio=0.22, pad=0.0):
    s = size * 4                                                         # draw 4x, then downsample for smooth edges
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * radius_ratio), fill=BG + (255,))
    k, off = s / 32 * (1 - pad * 2), s * pad
    pts = [(off + x * k, off + y * k) for x, y in PULSE]
    w = int(2.7 * k)
    d.line(pts, fill=ORANGE, width=w, joint="curve")
    for x, y in pts:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=ORANGE)
    return im.resize((size, size), Image.LANCZOS)


def share_image():
    w, h = 1200, 630
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    rnd = random.Random(5)
    for gx in range(0, w, 24):                                           # faint dot matrix, echoing the sign-in background
        for gy in range(0, h, 24):
            a = rnd.choice([18, 26, 34, 48])
            d.ellipse([gx, gy, gx + 3, gy + 3], fill=(a, a, a + 4))
    glow = Image.new("RGB", (w, h), BG)
    g = ImageDraw.Draw(glow)
    for r in range(420, 0, -6):
        t = 1 - r / 420
        g.ellipse([930 - r, 120 - r, 930 + r, 120 + r], fill=tuple(int(BG[i] + (ORANGE[i] - BG[i]) * t * 0.16) for i in range(3)))
    im = Image.blend(im, glow, 0.55)
    d = ImageDraw.Draw(im)
    im.paste(logo(120, 0.22, 0.08).convert("RGB"), (80, 80))
    d.text((80, 250), BRAND["name"], font=ImageFont.load_default(size=84), fill=(250, 250, 250))
    d.text((80, 360), BRAND["tagline_1"], font=ImageFont.load_default(size=36), fill=(161, 161, 170))
    d.text((80, 408), BRAND["tagline_2"], font=ImageFont.load_default(size=36), fill=(161, 161, 170))
    d.text((80, 520), BRAND["badges"], font=ImageFont.load_default(size=26), fill=ORANGE)
    cx, cy = 930, 330                                                    # a small fraud ring: accounts linked to one shared device
    pts = [(cx + int(150 * math.cos(a * math.pi / 4)), cy + int(150 * math.sin(a * math.pi / 4))) for a in range(8)]
    for p in pts:
        d.line([(cx, cy), p], fill=ORANGE, width=2)
    for p in pts:
        d.ellipse([p[0] - 11, p[1] - 11, p[0] + 11, p[1] + 11], fill=(212, 212, 216))
    d.rounded_rectangle([cx - 20, cy - 20, cx + 20, cy + 20], radius=6, fill=ORANGE)
    return im


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, ratio, pad in [("favicon-32.png", 32, .22, .06), ("favicon-16.png", 16, .22, .06), ("apple-touch-icon.png", 180, 0, .12),
                                   ("icon-192.png", 192, .22, .1), ("icon-512.png", 512, .22, .1)]:
        logo(size, ratio, pad).save(OUT / name)
    logo(48, .22, .06).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    share_image().save(OUT / "og-image.png", optimize=True)
    (OUT / "site.webmanifest").write_text(json.dumps({
        "name": BRAND["name"], "short_name": BRAND["name"], "description": f"{BRAND['tagline_1']} {BRAND['tagline_2']}", "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#09090b", "theme_color": "#09090b",
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}, indent=2))
    print(f"Wrote brand assets to {OUT}")
