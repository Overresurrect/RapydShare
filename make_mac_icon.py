"""Builds assets/RapydShare.icns, the macOS app icon, from the Windows icon.

macOS expects app icons to be a rounded square and puts anything else on a
system-drawn tile (dark in Dark Mode), so we draw our own blue tile and paint
the artwork white on top. For a sharper icon, pass a larger transparent PNG:

    python make_mac_icon.py path/to/artwork.png
"""
import os
import sys
import shutil
import tempfile
import subprocess
from PIL import Image, ImageDraw

SOURCE = sys.argv[1] if len(sys.argv) > 1 else os.path.join("assets", "Rapydshare.ico")
OUTPUT = os.path.join("assets", "RapydShare.icns")

TOP_COLOR = (96, 205, 255)      # App accent, #60CDFF
BOTTOM_COLOR = (58, 110, 255)
SUPERSAMPLE = 4                 # Draw the tile larger, then shrink it, for smooth corners

def make_tile():
    # Apple's icon grid: an 824px rounded square (corner radius 185) centred on a 1024px canvas
    size = 1024 * SUPERSAMPLE
    gradient = Image.composite(
        Image.new("RGBA", (size, size), BOTTOM_COLOR),
        Image.new("RGBA", (size, size), TOP_COLOR),
        Image.linear_gradient("L").resize((size, size)),
    )
    s = SUPERSAMPLE
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([100 * s, 100 * s, 924 * s, 924 * s], radius=185 * s, fill=255)

    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(gradient, (0, 0), mask)
    return tile.resize((1024, 1024), Image.LANCZOS)

def make_artwork():
    # Keep only the artwork's shape and paint it white so it stands out on the blue tile
    art = Image.open(SOURCE).convert("RGBA").resize((600, 600), Image.LANCZOS)
    white = Image.new("RGBA", art.size, (255, 255, 255, 255))
    white.putalpha(art.getchannel("A"))
    return white

def main():
    icon = make_tile()
    icon.alpha_composite(make_artwork(), (212, 200))

    # iconutil turns a folder of standard sizes into a .icns file
    work_dir = tempfile.mkdtemp()
    iconset = os.path.join(work_dir, "RapydShare.iconset")
    os.makedirs(iconset)
    for size in (16, 32, 128, 256, 512):
        icon.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, f"icon_{size}x{size}.png"))
        icon.resize((size * 2, size * 2), Image.LANCZOS).save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))

    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", OUTPUT], check=True)
    shutil.rmtree(work_dir)
    print(f"✅ Wrote {OUTPUT}")

if __name__ == "__main__":
    main()
