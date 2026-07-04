"""Generate and validate OnePortfolio raster app icons.

The master SVG intentionally uses a non-zero viewBox origin:

    viewBox="130 0 1014 1014"

Some screenshot-based render paths capture the top-left of the intrinsic SVG
document instead of fitting that viewBox into the target square canvas. This
script renders a temporary, visually equivalent SVG with the viewBox normalized
to 0,0 so every PNG/ICO entry is produced from the full centered artwork.
"""

from __future__ import annotations

import argparse
import binascii
import math
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "portfolio_app" / "static" / "icons"
MASTER_SVG = ICONS_DIR / "favicon.svg"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
APP_PNGS = {
    "apple-touch-icon.png": 180,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = (16, 32, 48)


class IconValidationError(RuntimeError):
    pass


def _file_uri(path: Path) -> str:
    return "file:///" + quote(str(path.resolve()).replace("\\", "/"))


def inspect_svg(svg_path: Path) -> dict[str, object]:
    root = ET.parse(svg_path).getroot()
    view_box = root.attrib["viewBox"]
    parts = [float(part) for part in view_box.replace(",", " ").split()]
    if len(parts) != 4:
        raise IconValidationError(f"Unexpected viewBox: {view_box!r}")
    rects = []
    for elem in root.iter():
        if elem.tag.endswith("rect"):
            rects.append({
                "x": elem.attrib.get("x", "0"),
                "y": elem.attrib.get("y", "0"),
                "width": elem.attrib.get("width"),
                "height": elem.attrib.get("height"),
                "fill": elem.attrib.get("fill"),
            })
    transforms = [
        elem.attrib["transform"]
        for elem in root.iter()
        if "transform" in elem.attrib
    ]
    return {
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "viewBox": view_box,
        "viewBox_parts": parts,
        "preserveAspectRatio": root.attrib.get("preserveAspectRatio"),
        "rects": rects,
        "transforms": transforms,
    }


def _svg_inner(svg_text: str) -> str:
    root_start = svg_text.find("<svg")
    if root_start < 0:
        raise IconValidationError("Could not locate SVG root")
    start = svg_text.find(">", root_start)
    end = svg_text.rfind("</svg>")
    if start < 0 or end < 0:
        raise IconValidationError("Could not locate SVG root contents")
    return svg_text[start + 1:end]


def normalized_svg(svg_path: Path, size: int) -> str:
    info = inspect_svg(svg_path)
    min_x, min_y, width, height = info["viewBox_parts"]
    inner = _svg_inner(svg_path.read_text(encoding="utf-8"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{size}" height="{size}" viewBox="0 0 {width:g} {height:g}"
     preserveAspectRatio="{info['preserveAspectRatio']}" shape-rendering="geometricPrecision">
  <g transform="translate({-min_x:g} {-min_y:g})">
{inner}
  </g>
</svg>
"""


def render_png(svg_path: Path, out_path: Path, size: int, tmp_dir: Path) -> None:
    render_svg_path = tmp_dir / f"render-{size}.svg"
    render_svg_path.write_text(normalized_svg(svg_path, size), encoding="utf-8")
    profile = tmp_dir / f"edge-profile-{size}-{time.time_ns()}"
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(EDGE),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        f"--user-data-dir={profile}",
        "--force-device-scale-factor=1",
        f"--window-size={size},{size}",
        f"--screenshot={out_path}",
        _file_uri(render_svg_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(path: Path) -> tuple[int, int, str, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise IconValidationError(f"{path.name} is not a PNG")
    pos = 8
    width = height = color_type = None
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(
                ">IIBBBBB", chunk_data,
            )
            if bit_depth != 8 or color_type not in (2, 6):
                raise IconValidationError(
                    f"{path.name} uses unsupported PNG format: "
                    f"bit_depth={bit_depth}, color_type={color_type}"
                )
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or color_type is None:
        raise IconValidationError(f"{path.name} is missing PNG metadata")
    channels = 4 if color_type == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows: list[bytearray] = []
    offset = 0
    prev = bytearray(stride)
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[i] = (row[i] + _paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise IconValidationError(f"{path.name} has bad PNG filter {filter_type}")
        rows.append(row)
        prev = row
    pixels: list[tuple[int, int, int, int]] = []
    mode = "RGBA" if channels == 4 else "RGB"
    for row in rows:
        for i in range(0, len(row), channels):
            if channels == 4:
                pixels.append((row[i], row[i + 1], row[i + 2], row[i + 3]))
            else:
                pixels.append((row[i], row[i + 1], row[i + 2], 255))
    return width, height, mode, pixels


def _is_background(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    return a >= 250 and r <= 18 and g <= 18 and b <= 18


def _is_white(pixel: tuple[int, int, int, int]) -> bool:
    r, g, b, a = pixel
    return a >= 250 and r >= 245 and g >= 245 and b >= 245


def validate_png(path: Path, expected_size: int, *, app_icon: bool) -> dict[str, object]:
    width, height, mode, pixels = decode_png(path)
    if (width, height) != (expected_size, expected_size):
        raise IconValidationError(
            f"{path.name} is {width}x{height}, expected {expected_size}x{expected_size}"
        )
    for name, idx in {
        "top_left": 0,
        "top_right": width - 1,
        "bottom_left": (height - 1) * width,
        "bottom_right": (height * width) - 1,
    }.items():
        if not _is_background(pixels[idx]):
            raise IconValidationError(f"{path.name} {name} corner is not black: {pixels[idx]}")
    if app_icon and any(px[3] != 255 for px in pixels):
        raise IconValidationError(f"{path.name} is not fully opaque")
    fg = [
        (i % width, i // width)
        for i, px in enumerate(pixels)
        if not _is_background(px)
    ]
    if not fg:
        raise IconValidationError(f"{path.name} has no visible logo pixels")
    min_x = min(x for x, _ in fg)
    max_x = max(x for x, _ in fg)
    min_y = min(y for _, y in fg)
    max_y = max(y for _, y in fg)
    bbox_w = max_x - min_x + 1
    bbox_h = max_y - min_y + 1
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_delta = math.hypot(center_x - (width - 1) / 2, center_y - (height - 1) / 2)
    min_extent = expected_size * (0.44 if expected_size <= 16 else 0.55)
    if bbox_w < min_extent or bbox_h < min_extent:
        raise IconValidationError(
            f"{path.name} logo bbox too small/narrow: {(min_x, min_y, max_x, max_y)}"
        )
    if center_delta > expected_size * 0.08:
        raise IconValidationError(
            f"{path.name} logo is off-center: center=({center_x:.2f},{center_y:.2f})"
        )
    if min_x <= 0 or min_y <= 0 or max_x >= width - 1 or max_y >= height - 1:
        raise IconValidationError(
            f"{path.name} logo touches canvas edge: {(min_x, min_y, max_x, max_y)}"
        )
    white_columns = 0
    for x in range(width):
        white_count = sum(1 for y in range(height) if _is_white(pixels[y * width + x]))
        if white_count > height * 0.92:
            white_columns += 1
    if white_columns > width * 0.12:
        raise IconValidationError(
            f"{path.name} has a large white rectangular region: {white_columns} columns"
        )
    return {
        "file": path.name,
        "size": f"{width}x{height}",
        "mode": mode,
        "bbox": (min_x, min_y, max_x, max_y),
        "bbox_size": (bbox_w, bbox_h),
        "center": (round(center_x, 2), round(center_y, 2)),
        "center_delta": round(center_delta, 3),
        "white_columns": white_columns,
    }


def _rgba_to_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(pixels[y * width + x])
    compressed = zlib.compress(bytes(rows), 9)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def bilinear_resize(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int, int]],
    out_size: int,
) -> list[tuple[int, int, int, int]]:
    result = []
    scale_x = width / out_size
    scale_y = height / out_size
    for y in range(out_size):
        src_y = (y + 0.5) * scale_y - 0.5
        y0 = max(0, min(height - 1, int(math.floor(src_y))))
        y1 = max(0, min(height - 1, y0 + 1))
        fy = src_y - y0
        for x in range(out_size):
            src_x = (x + 0.5) * scale_x - 0.5
            x0 = max(0, min(width - 1, int(math.floor(src_x))))
            x1 = max(0, min(width - 1, x0 + 1))
            fx = src_x - x0
            samples = [
                (pixels[y0 * width + x0], (1 - fx) * (1 - fy)),
                (pixels[y0 * width + x1], fx * (1 - fy)),
                (pixels[y1 * width + x0], (1 - fx) * fy),
                (pixels[y1 * width + x1], fx * fy),
            ]
            result.append(tuple(
                max(0, min(255, round(sum(px[c] * weight for px, weight in samples))))
                for c in range(4)
            ))
    return result


def validate_cross_size() -> float:
    w512, h512, _, px512 = decode_png(ICONS_DIR / "android-chrome-512x512.png")
    _, _, _, px192 = decode_png(ICONS_DIR / "android-chrome-192x192.png")
    resized = bilinear_resize(w512, h512, px512, 192)
    diff = 0
    for a, b in zip(resized, px192):
        diff += sum(abs(a[i] - b[i]) for i in range(4)) / 4
    mean = diff / len(px192)
    if mean > 10:
        raise IconValidationError(f"192px icon differs from resized 512px icon: mean={mean:.3f}")
    return round(mean, 3)


def write_ico(entries: dict[int, Path], ico_path: Path) -> None:
    images = [(size, entries[size].read_bytes()) for size in ICO_SIZES]
    offset = 6 + 16 * len(images)
    with ico_path.open("wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(images)))
        for size, data in images:
            fh.write(struct.pack(
                "<BBBBHHII",
                size if size < 256 else 0,
                size if size < 256 else 0,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            ))
            offset += len(data)
        for _, data in images:
            fh.write(data)


def inspect_ico(ico_path: Path) -> list[dict[str, object]]:
    data = ico_path.read_bytes()
    reserved, ico_type, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or ico_type != 1:
        raise IconValidationError("favicon.ico is not an ICO image")
    entries = []
    for i in range(count):
        raw = data[6 + i * 16:22 + i * 16]
        width, height, _, _, planes, bpp, size, offset = struct.unpack("<BBBBHHII", raw)
        png_data = data[offset:offset + size]
        if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise IconValidationError("ICO entry is not PNG encoded")
        entry_path = ico_path.parent / f".favicon-{width}x{height}.tmp.png"
        entry_path.write_bytes(png_data)
        try:
            validation = validate_png(entry_path, width or 256, app_icon=False)
        finally:
            entry_path.unlink(missing_ok=True)
        entries.append({
            "width": width or 256,
            "height": height or 256,
            "planes": planes,
            "bpp": bpp,
            "bytes": size,
            "offset": offset,
            "validation": validation,
        })
    return entries


def make_preview_sheet(out_path: Path) -> None:
    sources = [
        ("svg-render-512", ICONS_DIR / "android-chrome-512x512.png"),
        ("apple-180", ICONS_DIR / "apple-touch-icon.png"),
        ("android-192", ICONS_DIR / "android-chrome-192x192.png"),
        ("android-512", ICONS_DIR / "android-chrome-512x512.png"),
    ]
    ico_entries = extract_ico_pngs(ICONS_DIR / "favicon.ico", out_path.parent)
    sources.extend((f"ico-{size}", path) for size, path in ico_entries.items())
    tile = 160
    label_h = 20
    cols = 4
    rows = math.ceil(len(sources) / cols)
    width = cols * tile
    height = rows * (tile * 2 + label_h)
    canvas = [(238, 238, 238, 255)] * (width * height)

    def paste(img_w, img_h, img_px, ox, oy, bg):
        for y in range(tile):
            for x in range(tile):
                cx = ox + x
                cy = oy + y
                if bg == "checker":
                    v = 210 if ((x // 12 + y // 12) % 2 == 0) else 245
                    canvas[cy * width + cx] = (v, v, v, 255)
                else:
                    canvas[cy * width + cx] = (24, 24, 24, 255)
        scale = min((tile - 24) / img_w, (tile - 24) / img_h)
        draw_w = max(1, round(img_w * scale))
        draw_h = max(1, round(img_h * scale))
        resized = bilinear_resize(img_w, img_h, img_px, draw_w)
        start_x = ox + (tile - draw_w) // 2
        start_y = oy + (tile - draw_h) // 2
        for y in range(draw_h):
            for x in range(draw_w):
                canvas[(start_y + y) * width + start_x + x] = resized[y * draw_w + x]

    for idx, (_, path) in enumerate(sources):
        col = idx % cols
        row = idx // cols
        ox = col * tile
        oy = row * (tile * 2 + label_h) + label_h
        img_w, img_h, _, img_px = decode_png(path)
        paste(img_w, img_h, img_px, ox, oy, "checker")
        paste(img_w, img_h, img_px, ox, oy + tile, "dark")
    out_path.write_bytes(_rgba_to_png(width, height, canvas))
    for path in ico_entries.values():
        path.unlink(missing_ok=True)


def extract_ico_pngs(ico_path: Path, out_dir: Path) -> dict[int, Path]:
    data = ico_path.read_bytes()
    count = struct.unpack("<H", data[4:6])[0]
    result = {}
    for i in range(count):
        width, height, _, _, _, _, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + i * 16:22 + i * 16],
        )
        entry_size = width or 256
        out = out_dir / f"favicon-ico-{entry_size}.png"
        out.write_bytes(data[offset:offset + size])
        result[entry_size] = out
    return result


def generate() -> None:
    if not EDGE.exists():
        raise IconValidationError(f"Microsoft Edge not found at {EDGE}")
    with tempfile.TemporaryDirectory(prefix="oneportfolio-icons-") as td:
        tmp_dir = Path(td)
        generated_ico_pngs = {}
        for name, size in APP_PNGS.items():
            render_png(MASTER_SVG, ICONS_DIR / name, size, tmp_dir)
        for size in ICO_SIZES:
            out = tmp_dir / f"favicon-{size}.png"
            render_png(MASTER_SVG, out, size, tmp_dir)
            generated_ico_pngs[size] = out
        write_ico(generated_ico_pngs, ICONS_DIR / "favicon.ico")


def validate() -> None:
    print("SVG:", inspect_svg(MASTER_SVG))
    for name, size in APP_PNGS.items():
        print("PNG:", validate_png(ICONS_DIR / name, size, app_icon=True))
    print("Cross-size mean difference:", validate_cross_size())
    print("ICO:", inspect_ico(ICONS_DIR / "favicon.ico"))
    manifest = ROOT / "portfolio_app" / "static" / "icons" / "site.webmanifest"
    import json
    data = json.loads(manifest.read_text(encoding="utf-8"))
    expected = {
        "/static/icons/android-chrome-192x192.png": "192x192",
        "/static/icons/android-chrome-512x512.png": "512x512",
    }
    actual = {icon["src"]: icon["sizes"] for icon in data["icons"]}
    for src, sizes in expected.items():
        if actual.get(src) != sizes:
            raise IconValidationError(f"Manifest entry mismatch for {src}: {actual.get(src)}")
    print("Manifest: valid")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate OnePortfolio app icons from "
            "portfolio_app/static/icons/favicon.svg and validate the outputs."
        ),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate existing PNG/ICO/manifest outputs without regenerating files",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        help="optional output path for a temporary visual preview sheet",
    )
    args = parser.parse_args()
    if not args.validate_only:
        generate()
    validate()
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        make_preview_sheet(args.preview)
        print(f"Preview: {args.preview}")


if __name__ == "__main__":
    main()
