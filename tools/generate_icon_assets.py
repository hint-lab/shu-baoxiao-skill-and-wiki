from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "icon.png"
WEB_ICON_DIR = ROOT / "web/static/icons"
TAURI_ICON_DIR = ROOT / "src-tauri/icons"

WEB_SIZES = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "icon-48.png": 48,
    "icon-64.png": 64,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-256.png": 256,
    "icon-512.png": 512,
}

TAURI_SIZES = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
}

ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def crop_to_square(source: Path) -> Image.Image:
    image = Image.open(source).convert("RGBA")
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
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing source icon: {SOURCE}")

    base = crop_to_square(SOURCE)

    for filename, size in WEB_SIZES.items():
        save_png(base, WEB_ICON_DIR / filename, size)
    save_ico(base, WEB_ICON_DIR / "favicon.ico")

    for filename, size in TAURI_SIZES.items():
        save_png(base, TAURI_ICON_DIR / filename, size)
    save_ico(base, TAURI_ICON_DIR / "icon.ico")
    save_icns(base, TAURI_ICON_DIR / "icon.icns")

    print(f"generated web icons in {WEB_ICON_DIR.relative_to(ROOT)}")
    print(f"generated tauri icons in {TAURI_ICON_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
