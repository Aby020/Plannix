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

The design is a rounded terracotta tile (the Plannix warm accent) holding a
cream calendar sheet with a terracotta header band, two binding pins, and a
dotted date grid with a highlighted "today" cell — a clean, modern
calendar-style "plan it" mark that matches the cream/paper, charcoal/ink,
restrained-terracotta editorial identity.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
STATIC_ICON = ROOT / 'static' / 'icon'
STATIC_IMG = ROOT / 'static' / 'img'

# Brand palette — warm editorial identity (see static/css/public.css tokens).
PRIMARY = (166, 83, 59)      # #A6533B terracotta
SECONDARY = (143, 69, 48)    # #8F4530 deep terracotta
CREAM = (253, 252, 250)      # #FDFCFA warm paper
TERRACOTTA = PRIMARY

# Rasters are rendered at this resolution, then downscaled with LANCZOS so the
# small favicon sizes stay anti-aliased and crisp.
RENDER_SIZE = 512

SVG_MARK = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" role="img" aria-label="Plannix">
  <defs>
    <linearGradient id="plannix-g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#A6533B"/>
      <stop offset="100%" stop-color="#8F4530"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="44" height="44" rx="12" fill="url(#plannix-g)"/>
  <rect x="10.5" y="10.5" width="27" height="27" rx="2.5" fill="#FDFCFA"/>
  <path d="M10.5 13 a2.5 2.5 0 0 1 2.5 -2.5 h24.5 a2.5 2.5 0 0 1 2.5 2.5 v4 h-29.5 z" fill="#A6533B"/>
  <circle cx="13.75" cy="13.75" r="1.4" fill="#FDFCFA" opacity="0.85"/>
  <circle cx="34.25" cy="13.75" r="1.4" fill="#FDFCFA" opacity="0.85"/>
  <circle cx="15.1" cy="23.2" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="22.1" cy="23.2" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="29.1" cy="23.2" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="15.1" cy="31.8" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="22.1" cy="31.8" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="29.1" cy="31.8" r="1.95" fill="#A6533B"/>
</svg>
'''

SVG_LOGO = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 232 48" role="img" aria-label="Plannix">
  <defs>
    <linearGradient id="plannix-g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#A6533B"/>
      <stop offset="100%" stop-color="#8F4530"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="44" height="44" rx="12" fill="url(#plannix-g)"/>
  <rect x="10.5" y="10.5" width="27" height="27" rx="2.5" fill="#FDFCFA"/>
  <path d="M10.5 13 a2.5 2.5 0 0 1 2.5 -2.5 h24.5 a2.5 2.5 0 0 1 2.5 2.5 v4 h-29.5 z" fill="#A6533B"/>
  <circle cx="13.75" cy="13.75" r="1.4" fill="#FDFCFA" opacity="0.85"/>
  <circle cx="34.25" cy="13.75" r="1.4" fill="#FDFCFA" opacity="0.85"/>
  <circle cx="15.1" cy="23.2" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="22.1" cy="23.2" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="29.1" cy="23.2" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="15.1" cy="31.8" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="22.1" cy="31.8" r="1.45" fill="#A6533B" opacity="0.25"/>
  <circle cx="29.1" cy="31.8" r="1.95" fill="#A6533B"/>
  <text x="58" y="32" font-family="Sora, 'Segoe UI', Arial, sans-serif" font-size="30"
        font-weight="800" fill="#24211E" letter-spacing="0.5">Plannix</text>
</svg>
'''

MANIFEST = {
    "name": "Plannix",
    "short_name": "Plannix",
    "icons": [
        {"src": "/static/icon/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/icon/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png"},
    ],
    "theme_color": "#A6533B",
    "background_color": "#FDFCFA",
    "display": "standalone",
    "start_url": "/",
}


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _calendar(size: int) -> Image.Image:
    """Cream calendar sheet + header band, pins and date grid (on the tile)."""
    s = size
    layer = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    x0, x1 = round(s * 0.219), round(s * 0.781)
    y0, y1 = round(s * 0.219), round(s * 0.781)
    sheet_rx = round(s * 0.052)

    # Cream calendar sheet
    d.rounded_rectangle([x0, y0, x1, y1], radius=sheet_rx, fill=CREAM)

    # Terracotta header band — rounded top corners, square bottom
    band_top = y0
    band_bottom = round(s * 0.354)
    d.rounded_rectangle([x0, band_top, x1, band_top + 2 * sheet_rx], radius=sheet_rx, fill=TERRACOTTA)
    d.rectangle([x0, band_top + sheet_rx, x1, band_bottom], fill=TERRACOTTA)

    # Two binding pins on the header band
    pin_r = round(s * 0.029)
    pin_cy = (band_top + band_bottom) // 2
    for cx in (round(s * 0.286), round(s * 0.714)):
        d.ellipse([cx - pin_r, pin_cy - pin_r, cx + pin_r, cx + pin_r], fill=CREAM)

    # Date grid — five translucent dots, one solid accent ("today")
    dot_r = round(s * 0.030)
    today_r = round(s * 0.040)
    cols = (round(s * 0.315), round(s * 0.460), round(s * 0.606))
    rows = (round(s * 0.483), round(s * 0.6625))
    for ci, cx in enumerate(cols):
        for rj, cy in enumerate(rows):
            if ci == 2 and rj == 1:
                r, fill = today_r, TERRACOTTA + (255,)
            else:
                r, fill = dot_r, TERRACOTTA + (60,)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)

    return layer


def render_mark(size: int) -> Image.Image:
    """Draw the Plannix mark (rounded terracotta tile + calendar sheet)."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))

    margin = round(size * 0.04)
    tile_size = size - 2 * margin
    tile_radius = round(tile_size * 0.27)

    # Smooth vertical terracotta gradient clipped to the rounded tile.
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=tile_radius,
        fill=255,
    )
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(size):
        d.line([(0, y), (size, y)], fill=_lerp(PRIMARY, SECONDARY, y / size) + (255,))
    tile = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    tile.paste(layer, (0, 0), mask)

    tile.alpha_composite(_calendar(size))
    return tile


def draw_mark(size: int) -> Image.Image:
    """Return the mark rasterized at ``size`` (anti-aliased)."""
    return render_mark(RENDER_SIZE).resize((size, size), Image.LANCZOS)


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
        # Apple touch icons sit on a solid (paper) background.
        if name == 'apple-touch-icon.png':
            inset = round(size * 0.18)
            canvas = Image.new('RGBA', (size, size), CREAM + (255,))
            mark_resized = mark.resize((size - 2 * inset, size - 2 * inset), Image.LANCZOS)
            canvas.alpha_composite(mark_resized, (inset, inset))
            canvas.convert('RGB').save(STATIC_ICON / name)
        else:
            mark.save(STATIC_ICON / name)

    # favicon.ico — multi-size ico
    draw_mark(64).save(STATIC_ICON / 'favicon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])

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