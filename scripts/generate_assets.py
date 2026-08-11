"""Generate Plannix brand assets (logo, favicon set, web manifest).

Run from the project root with the project virtual environment:

    venv\\Scripts\\python.exe scripts\\generate_assets.py

Outputs:
    static/img/plannix-mark.svg      — standalone brand mark (vector)
    static/img/plannix-mark.png      — brand mark raster (for Jazzmin admin)
    static/img/logo.svg              — mark + wordmark lockup (vector)
    static/icon/favicon-16x16.png    — browser favicons
    static/icon/favicon-32x32.png
    static/icon/android-chrome-192x192.png
    static/icon/android-chrome-512x512.png
    static/icon/apple-touch-icon.png
    static/icon/favicon.ico
    static/icon/site.webmanifest

The design is a rounded gradient tile (indigo -> violet) containing a
calendar + check glyph — a simple, modern "plan it" mark.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
STATIC_ICON = ROOT / 'static' / 'icon'
STATIC_IMG = ROOT / 'static' / 'img'

# Brand palette
PRIMARY = (109, 94, 247)      # #6D5EF7 indigo
SECONDARY = (155, 108, 246)   # #9B6CF6 violet
WHITE = (255, 255, 255)

SVG_MARK = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img" aria-label="Plannix">
  <defs>
    <linearGradient id="plannix-g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6D5EF7"/>
      <stop offset="100%" stop-color="#9B6CF6"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="44" height="44" rx="12.5" fill="url(#plannix-g)"/>
  <g fill="none" stroke="#FFFFFF" stroke-linecap="round" stroke-linejoin="round">
    <rect x="10.5" y="13.5" width="27" height="4.5" rx="2.25" fill="#FFFFFF" stroke="none"/>
    <path d="M19.5 23.5 25.5 30 36 18" stroke-width="3.6"/>
  </g>
</svg>
'''

SVG_LOGO = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 232 48" role="img" aria-label="Plannix">
  <defs>
    <linearGradient id="plannix-g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6D5EF7"/>
      <stop offset="100%" stop-color="#9B6CF6"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="44" height="44" rx="12.5" fill="url(#plannix-g)"/>
  <g fill="none" stroke="#FFFFFF" stroke-linecap="round" stroke-linejoin="round">
    <rect x="10.5" y="13.5" width="27" height="4.5" rx="2.25" fill="#FFFFFF" stroke="none"/>
    <path d="M19.5 23.5 25.5 30 36 18" stroke-width="3.6"/>
  </g>
  <text x="58" y="32" font-family="Sora, 'Segoe UI', Arial, sans-serif" font-size="30"
        font-weight="800" fill="#0B1020" letter-spacing="0.5">Plannix</text>
</svg>
'''

MANIFEST = {
    "name": "Plannix",
    "short_name": "Plannix",
    "icons": [
        {"src": "/static/icon/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/icon/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
    ],
    "theme_color": "#6D5EF7",
    "background_color": "#ffffff",
    "display": "standalone",
    "start_url": "/",
}


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_mark(size: int) -> Image.Image:
    """Draw the Plannix mark (gradient tile + calendar/check glyph)."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(2, round(size * 0.04))
    tile = size - 2 * margin
    radius = round(tile * 0.27)

    # Diagonal gradient tile
    steps = tile
    for i in range(steps):
        t = i / steps
        color = _lerp(PRIMARY, SECONDARY, t) + (255,)
        top = margin + i
        height = 2 if i < steps - 1 else 1
        draw.rounded_rectangle(
            [margin, top, margin + tile, top + height],
            radius=radius,
            fill=color,
        )

    overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    small = size < 48
    s = size

    if small:
        # Simple bold checkmark — readable at tiny sizes
        lw = max(2, round(s * 0.13))
        odraw.line([(s * 0.28, s * 0.52), (s * 0.45, s * 0.68), (s * 0.74, s * 0.34)],
                   fill=WHITE, width=lw, joint='curve')
    else:
        # Calendar header bar
        bar_y = round(s * 0.24)
        bar_h = round(s * 0.10)
        odraw.rounded_rectangle(
            [round(s * 0.19), bar_y, round(s * 0.81), bar_y + bar_h],
            radius=round(bar_h / 2), fill=WHITE,
        )
        # Checkmark inside the tile
        lw = max(3, round(s * 0.075))
        odraw.line([(s * 0.38, s * 0.50), (s * 0.48, s * 0.61), (s * 0.66, s * 0.40)],
                   fill=WHITE, width=lw, joint='curve')

    img.alpha_composite(overlay)
    return img


def main():
    STATIC_ICON.mkdir(parents=True, exist_ok=True)
    STATIC_IMG.mkdir(parents=True, exist_ok=True)

    sizes = {
        'favicon-16x16.png': 16,
        'favicon-32x32.png': 32,
        'android-chrome-192x192.png': 192,
        'android-chrome-512x512.png': 512,
        'apple-touch-icon.png': 180,
    }
    for name, size in sizes.items():
        mark = draw_mark(size)
        # Apple touch icons are shown on a solid background — add padding
        if name == 'apple-touch-icon.png':
            canvas = Image.new('RGBA', (size, size), PRIMARY + (255,))
            inset = round(size * 0.18)
            mark_resized = mark.resize((size - 2 * inset, size - 2 * inset), Image.LANCZOS)
            canvas.alpha_composite(mark_resized, (inset, inset))
            canvas.convert('RGB').save(STATIC_ICON / name)
        else:
            mark.save(STATIC_ICON / name)

    # favicon.ico — multi-size ico
    mark.save(STATIC_ICON / 'favicon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])

    # Jazzmin admin logo (256px raster)
    draw_mark(256).save(STATIC_IMG / 'plannix-mark.png')

    # Vector assets
    (STATIC_IMG / 'plannix-mark.svg').write_text(SVG_MARK, encoding='utf-8')
    (STATIC_IMG / 'logo.svg').write_text(SVG_LOGO, encoding='utf-8')

    # Web manifest
    (STATIC_ICON / 'site.webmanifest').write_text(
        __import__('json').dumps(MANIFEST, indent=2), encoding='utf-8'
    )

    print('Plannix brand assets generated.')


if __name__ == '__main__':
    main()
