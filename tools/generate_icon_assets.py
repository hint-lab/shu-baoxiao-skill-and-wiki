from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE_APP = ROOT / "ChatGPT Image 2026年6月30日 15_22_13.png"
SOURCE_LIGHT = ROOT / "ChatGPT Image 2026年6月30日 15_22_24.png"
WEB_ICON_DIR = ROOT / "web/static/icons"
TAURI_ICON_DIR = ROOT / "src-tauri/icons"
ROOT_ICON = ROOT / "icon.png"
ROOT_LOGO = ROOT / "logo.png"

WEB_SIZES = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "icon-48.png": 48,
    "icon-64.png": 64,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-256.png": 256,
    "icon-512.png": 512,
    "maskable-192.png": 192,
    "maskable-512.png": 512,
}

TAURI_SIZES = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
}

ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def open_square(source: Path) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    if image.width == image.height:
        return image
    side = min(image.width, image.height)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def crop_to_square(source: Path) -> Image.Image:
    image = open_square(source)
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        bbox = (0, 0, image.width, image.height)

    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    padding = max(width, height) * 0.08
    left = max(0, int(left - padding))
    top = max(0, int(top - padding))
    right = min(image.width, int(right + padding))
    bottom = min(image.height, int(bottom + padding))

    cropped = image.crop((left, top, right, bottom))
    side = max(cropped.width, cropped.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(cropped, ((side - cropped.width) // 2, (side - cropped.height) // 2))
    return canvas


def inset_on_canvas(base: Image.Image, padding_ratio: float = 0.0, fill=(0, 0, 0, 0)) -> Image.Image:
    if padding_ratio <= 0:
        return base
    side = max(base.width, base.height)
    canvas = Image.new("RGBA", (side, side), fill)
    target = max(1, int(side * (1 - padding_ratio * 2)))
    resized = base.resize((target, target), Image.Resampling.LANCZOS)
    canvas.alpha_composite(resized, ((side - target) // 2, (side - target) // 2))
    return canvas


def round_corners(base: Image.Image, radius_ratio: float = 0.22) -> Image.Image:
    image = base.convert("RGBA")
    side = max(image.width, image.height)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))

    scale = 4
    mask = Image.new("L", (side * scale, side * scale), 0)
    radius = int(side * radius_ratio * scale)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, side * scale, side * scale), radius=radius, fill=255)
    mask = mask.resize((side, side), Image.Resampling.LANCZOS)
    canvas.putalpha(Image.composite(canvas.getchannel("A"), Image.new("L", (side, side), 0), mask))
    return canvas


def save_png(base: Image.Image, target: Path, size: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    resized = base.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(target, "PNG", optimize=True)


def save_ico(base: Image.Image, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(target, "ICO", sizes=sizes)


def save_icns(base: Image.Image, target: Path) -> bool:
    iconutil = shutil.which("iconutil")
    if not iconutil:
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        for size in ICNS_SIZES:
            save_png(base, iconset / f"icon_{size}x{size}.png", size)
            if size <= 512:
                save_png(base, iconset / f"icon_{size}x{size}@2x.png", size * 2)
        subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(target)], check=True)
    return True


def main() -> None:
    missing = [path for path in [SOURCE_APP, SOURCE_LIGHT] if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing source image(s): " + ", ".join(str(path) for path in missing))

    app_base = round_corners(open_square(SOURCE_APP))
    light_base = round_corners(open_square(SOURCE_LIGHT))
    maskable_base = round_corners(inset_on_canvas(open_square(SOURCE_APP), padding_ratio=0.08, fill=(0, 102, 255, 255)))

    save_png(app_base, ROOT_ICON, 500)
    save_png(light_base, ROOT_LOGO, 500)
    save_png(app_base, WEB_ICON_DIR / "logo-blue.png", 512)
    save_png(light_base, WEB_ICON_DIR / "logo-light.png", 512)

    for filename, size in WEB_SIZES.items():
        source = maskable_base if filename.startswith("maskable-") else app_base
        save_png(source, WEB_ICON_DIR / filename, size)
    save_ico(app_base, WEB_ICON_DIR / "favicon.ico")

    for filename, size in TAURI_SIZES.items():
        save_png(app_base, TAURI_ICON_DIR / filename, size)
    save_ico(app_base, TAURI_ICON_DIR / "icon.ico")
    save_icns(app_base, TAURI_ICON_DIR / "icon.icns")

    print(f"updated root assets: {ROOT_ICON.relative_to(ROOT)}, {ROOT_LOGO.relative_to(ROOT)}")
    print(f"generated web icons in {WEB_ICON_DIR.relative_to(ROOT)}")
    print(f"generated tauri icons in {TAURI_ICON_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
