"""Generate and validate OnePortfolio brand icon derivatives.

``portfolio_app/static/icons/favicon.svg`` is the single geometric source.
The master contains one quarter-pie path in a 64x64 viewBox. This script derives
transparent light/dark favicon variants, transparent ICO frames, and neutral
installed-app compositions from that same path. A small standard-library
scanline renderer keeps generation independent of a browser or third-party
image package.
"""

from __future__ import annotations

import argparse
import binascii
import json
import math
import re
import struct
import tempfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "portfolio_app" / "static" / "icons"
MASTER_SVG = ICONS_DIR / "favicon.svg"
LOGO_COMPONENT = ROOT / "portfolio_app" / "templates" / "components" / "logo_mark.html"
DEFAULT_SURFACE_ARTWORK = "#757575"
LIGHT_SURFACE_ARTWORK = "#0A0A0A"
DARK_SURFACE_ARTWORK = "#FAFAFA"
LIGHT_ICON_BACKGROUND = "#FAFAFA"
DARK_ICON_BACKGROUND = "#171717"
SVG_VARIANTS = {
    ICONS_DIR / "favicon-light.svg": LIGHT_SURFACE_ARTWORK,
    ICONS_DIR / "favicon-dark.svg": DARK_SURFACE_ARTWORK,
}
SVG_ARTWORK_COLORS = {
    MASTER_SVG: DEFAULT_SURFACE_ARTWORK,
    **SVG_VARIANTS,
}
TARGET_SURFACES = {
    MASTER_SVG: ("#FFFFFF", "#000000"),
    ICONS_DIR / "favicon-light.svg": (LIGHT_ICON_BACKGROUND,),
    ICONS_DIR / "favicon-dark.svg": (DARK_ICON_BACKGROUND,),
}
APP_PNGS = {
    "apple-touch-icon.png": 180,
    "android-chrome-192x192.png": 192,
    "android-chrome-512x512.png": 512,
}
ICO_SIZES = (16, 32, 48)
REFERENCE_SIZES = (16, 20, 24, 32, 48, 192, 512)
BRAND_MARK_ATTRIBUTE = "oneportfolio-quarter-pie"
BRAND_BACKGROUND_ATTRIBUTE = "oneportfolio-icon-background"
SUPERSAMPLE = 4


class IconValidationError(RuntimeError):
    pass


def inspect_svg(svg_path: Path) -> dict[str, object]:
    """Validate the deliberately small master/variant SVG contract."""
    source = svg_path.read_text(encoding="utf-8")
    return inspect_svg_text(source, svg_path.name)


def inspect_svg_text(source: str, source_name: str) -> dict[str, object]:
    """Validate an SVG source string against the brand geometry contract."""
    if "base64" in source.lower() or re.search(r"<\s*image\b", source, re.I):
        raise IconValidationError(f"{source_name} embeds raster content")
    root = ET.fromstring(source)
    view_box = root.attrib.get("viewBox", "")
    try:
        view_box_parts = [float(part) for part in view_box.replace(",", " ").split()]
    except ValueError as exc:
        raise IconValidationError(f"Unexpected viewBox: {view_box!r}") from exc
    if view_box_parts != [0.0, 0.0, 64.0, 64.0]:
        raise IconValidationError(
            f"{source_name} must use the canonical 0 0 64 64 viewBox"
        )

    children = list(root)
    marks = [
        element
        for element in root.iter()
        if element.attrib.get("data-brand-mark") == BRAND_MARK_ATTRIBUTE
    ]
    backgrounds = [
        element
        for element in root.iter()
        if element.attrib.get("data-brand-background") == BRAND_BACKGROUND_ATTRIBUTE
    ]
    if len(marks) != 1 or not marks[0].tag.endswith("path"):
        raise IconValidationError(
            f"{source_name} must contain exactly one quarter-pie path"
        )
    if len(backgrounds) > 1 or any(not item.tag.endswith("rect") for item in backgrounds):
        raise IconValidationError(f"{source_name} has an invalid icon background")
    expected_children = 2 if backgrounds else 1
    if len(children) != expected_children:
        raise IconValidationError(f"{source_name} contains decorative geometry")
    if any(
        attribute in element.attrib
        for element in root.iter()
        for attribute in ("transform", "mask", "clip-path", "filter", "style")
    ):
        raise IconValidationError(
            f"{source_name} must not use transforms, masks, clips, filters, or styles"
        )
    path_data = marks[0].attrib.get("d", "")
    if not path_data or len(path_data) > 500:
        raise IconValidationError(f"{source_name} has invalid brand path geometry")
    return {
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "viewBox": view_box,
        "viewBox_parts": view_box_parts,
        "preserveAspectRatio": root.attrib.get("preserveAspectRatio"),
        "artwork_fill": marks[0].attrib.get("fill"),
        "background_fill": backgrounds[0].attrib.get("fill") if backgrounds else None,
        "background_rect": backgrounds[0].attrib if backgrounds else None,
        "path_data": path_data,
        "element_count": sum(1 for _ in root.iter()),
    }


def svg_variant(
    svg_text: str,
    artwork_color: str,
) -> str:
    root = ET.fromstring(svg_text)
    marks = [
        element
        for element in root.iter()
        if element.attrib.get("data-brand-mark") == BRAND_MARK_ATTRIBUTE
    ]
    if len(marks) != 1:
        raise IconValidationError("Master SVG must contain one quarter-pie path")
    current_color = marks[0].attrib.get("fill")
    marker = f'fill="{current_color}"'
    if not current_color or svg_text.count(marker) != 1:
        raise IconValidationError("Could not isolate the master artwork color")
    return svg_text.replace(marker, f'fill="{artwork_color}"', 1)


def app_icon_composition(
    svg_text: str,
    artwork_color: str = LIGHT_SURFACE_ARTWORK,
    background_color: str = LIGHT_ICON_BACKGROUND,
) -> str:
    """Compose the neutral platform tile without changing favicon sources."""
    coloured = svg_variant(svg_text, artwork_color)
    path_start = coloured.index("  <path ")
    background = (
        '  <rect data-brand-background="oneportfolio-icon-background" '
        f'x="2" y="2" width="60" height="60" rx="12" fill="{background_color}"/>\n'
    )
    return coloured[:path_start] + background + coloured[path_start:]


def generate_svg_variants() -> None:
    master_text = MASTER_SVG.read_text(encoding="utf-8")
    for svg_path, artwork_color in SVG_VARIANTS.items():
        svg_path.write_text(
            svg_variant(master_text, artwork_color),
            encoding="utf-8",
        )


def logo_component_text(master_text: str) -> str:
    root = ET.fromstring(master_text)
    marks = [
        element
        for element in root.iter()
        if element.attrib.get("data-brand-mark") == BRAND_MARK_ATTRIBUTE
    ]
    if len(marks) != 1:
        raise IconValidationError("Master SVG must contain one quarter-pie path")
    path_data = marks[0].attrib["d"]
    template = """{#
  Generated by scripts/generate_app_icons.py from static/icons/favicon.svg.
  Edit the master SVG, not this path geometry.

  Params:
    logo_class       optional extra classes on the mark
    logo_decorative  hide from assistive technology (default true)
    logo_alt         accessible label when not decorative
#}
{% set brand_logo_class = logo_class|default('') %}
{% set brand_logo_decorative = logo_decorative|default(true) %}
<svg
    class="brand-logo{% if brand_logo_class %} {{ brand_logo_class }}{% endif %}"
    viewBox="8 8 48 48"
    fill="currentColor"
    focusable="false"
    {% if brand_logo_decorative %}aria-hidden="true"{% else %}role="img" aria-label="{{ logo_alt|default('OnePortfolio') }}"{% endif %}
>
    <path d="__MASTER_PATH__"></path>
</svg>
"""
    return template.replace("__MASTER_PATH__", path_data)


def generate_logo_component() -> None:
    LOGO_COMPONENT.write_text(
        logo_component_text(MASTER_SVG.read_text(encoding="utf-8")),
        encoding="utf-8",
    )


def _hex_rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    if len(value) != 6:
        raise IconValidationError(f"Expected a six-digit hex color: {color!r}")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _relative_luminance(color: str) -> float:
    channels = []
    for value in _hex_rgb(color):
        normalized = value / 255
        channels.append(
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def _path_contours(path_data: str) -> list[list[tuple[float, float]]]:
    """Flatten the master path's absolute SVG commands to scanline contours."""
    commands = {"M", "L", "H", "V", "Q", "C", "A", "Z"}
    tokens = re.findall(r"[MLHVQCAZ]|-?(?:\d+(?:\.\d*)?|\.\d+)", path_data)
    index = 0
    command = None
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    contour: list[tuple[float, float]] = []
    contours: list[list[tuple[float, float]]] = []

    def number() -> float:
        nonlocal index
        if index >= len(tokens) or tokens[index] in commands:
            raise IconValidationError("Malformed master SVG path")
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        if tokens[index] in commands:
            command = tokens[index]
            index += 1
        if command == "M":
            if contour:
                contours.append(contour)
            current = (number(), number())
            start = current
            contour = [current]
            command = "L"
        elif command == "L":
            current = (number(), number())
            contour.append(current)
        elif command == "H":
            current = (number(), current[1])
            contour.append(current)
        elif command == "V":
            current = (current[0], number())
            contour.append(current)
        elif command == "Q":
            p0 = current
            control = (number(), number())
            end = (number(), number())
            for step in range(1, 17):
                t = step / 16
                mt = 1 - t
                contour.append((
                    mt**2 * p0[0] + 2 * mt * t * control[0] + t**2 * end[0],
                    mt**2 * p0[1] + 2 * mt * t * control[1] + t**2 * end[1],
                ))
            current = end
        elif command == "C":
            p0 = current
            p1 = (number(), number())
            p2 = (number(), number())
            p3 = (number(), number())
            for step in range(1, 33):
                t = step / 32
                mt = 1 - t
                contour.append((
                    mt**3 * p0[0]
                    + 3 * mt**2 * t * p1[0]
                    + 3 * mt * t**2 * p2[0]
                    + t**3 * p3[0],
                    mt**3 * p0[1]
                    + 3 * mt**2 * t * p1[1]
                    + 3 * mt * t**2 * p2[1]
                    + t**3 * p3[1],
                ))
            current = p3
        elif command == "A":
            rx = abs(number())
            ry = abs(number())
            rotation = math.radians(number() % 360)
            large_arc = int(number())
            sweep = int(number())
            end = (number(), number())
            if not rx or not ry or large_arc not in (0, 1) or sweep not in (0, 1):
                raise IconValidationError("Master SVG path has an invalid arc")

            cosine = math.cos(rotation)
            sine = math.sin(rotation)
            dx = (current[0] - end[0]) / 2
            dy = (current[1] - end[1]) / 2
            x_prime = cosine * dx + sine * dy
            y_prime = -sine * dx + cosine * dy
            radius_scale = x_prime**2 / rx**2 + y_prime**2 / ry**2
            if radius_scale > 1:
                scale = math.sqrt(radius_scale)
                rx *= scale
                ry *= scale

            numerator = max(
                0,
                rx**2 * ry**2 - rx**2 * y_prime**2 - ry**2 * x_prime**2,
            )
            denominator = rx**2 * y_prime**2 + ry**2 * x_prime**2
            coefficient = 0 if denominator == 0 else math.sqrt(numerator / denominator)
            if large_arc == sweep:
                coefficient = -coefficient
            center_prime_x = coefficient * (rx * y_prime / ry)
            center_prime_y = coefficient * (-ry * x_prime / rx)
            center_x = (
                cosine * center_prime_x
                - sine * center_prime_y
                + (current[0] + end[0]) / 2
            )
            center_y = (
                sine * center_prime_x
                + cosine * center_prime_y
                + (current[1] + end[1]) / 2
            )

            def vector_angle(first: tuple[float, float], second: tuple[float, float]) -> float:
                dot = first[0] * second[0] + first[1] * second[1]
                determinant = first[0] * second[1] - first[1] * second[0]
                return math.atan2(determinant, dot)

            start_vector = (
                (x_prime - center_prime_x) / rx,
                (y_prime - center_prime_y) / ry,
            )
            end_vector = (
                (-x_prime - center_prime_x) / rx,
                (-y_prime - center_prime_y) / ry,
            )
            start_angle = vector_angle((1, 0), start_vector)
            sweep_angle = vector_angle(start_vector, end_vector)
            if not sweep and sweep_angle > 0:
                sweep_angle -= 2 * math.pi
            elif sweep and sweep_angle < 0:
                sweep_angle += 2 * math.pi
            steps = max(8, math.ceil(abs(sweep_angle) / (math.pi / 64)))
            for step in range(1, steps + 1):
                angle = start_angle + sweep_angle * step / steps
                x = rx * math.cos(angle)
                y = ry * math.sin(angle)
                contour.append((
                    cosine * x - sine * y + center_x,
                    sine * x + cosine * y + center_y,
                ))
            current = end
        elif command == "Z":
            if not contour:
                raise IconValidationError("Master SVG path closes an empty contour")
            if contour[-1] != start:
                contour.append(start)
            contours.append(contour)
            contour = []
            current = start
            command = None
        else:
            raise IconValidationError("Master SVG path uses an unsupported command")
    if contour:
        raise IconValidationError("Master SVG path must be closed")
    if not contours:
        raise IconValidationError("Master SVG path has no contours")
    return contours


def _render_alpha(path_data: str, size: int) -> list[int]:
    high_size = size * SUPERSAMPLE
    scale = high_size / 64
    contours = [
        [(x * scale, y * scale) for x, y in contour]
        for contour in _path_contours(path_data)
    ]
    mask = bytearray(high_size * high_size)
    for y in range(high_size):
        scan_y = y + 0.5
        crossings: list[float] = []
        for contour in contours:
            for first, second in zip(contour, contour[1:]):
                x1, y1 = first
                x2, y2 = second
                if (y1 > scan_y) == (y2 > scan_y):
                    continue
                crossings.append(x1 + (scan_y - y1) * (x2 - x1) / (y2 - y1))
        crossings.sort()
        if len(crossings) % 2:
            raise IconValidationError("Master SVG path has an invalid fill contour")
        for left, right in zip(crossings[::2], crossings[1::2]):
            start_x = max(0, math.ceil(left - 0.5))
            end_x = min(high_size - 1, math.floor(right - 0.5))
            if end_x >= start_x:
                offset = y * high_size + start_x
                mask[offset:offset + end_x - start_x + 1] = b"\xff" * (
                    end_x - start_x + 1
                )

    alpha: list[int] = []
    sample_count = SUPERSAMPLE * SUPERSAMPLE
    for out_y in range(size):
        for out_x in range(size):
            coverage = 0
            for sample_y in range(SUPERSAMPLE):
                row = (out_y * SUPERSAMPLE + sample_y) * high_size
                start = row + out_x * SUPERSAMPLE
                coverage += sum(mask[start:start + SUPERSAMPLE]) // 255
            alpha.append(round(coverage * 255 / sample_count))
    return alpha


def _render_rounded_rect_alpha(
    size: int,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float,
) -> list[int]:
    """Supersample the generated icon's one neutral rounded background."""
    scale = size / 64
    x *= scale
    y *= scale
    width *= scale
    height *= scale
    radius *= scale
    result = []
    for pixel_y in range(size):
        for pixel_x in range(size):
            inside = 0
            for sample_y in range(SUPERSAMPLE):
                point_y = pixel_y + (sample_y + 0.5) / SUPERSAMPLE
                for sample_x in range(SUPERSAMPLE):
                    point_x = pixel_x + (sample_x + 0.5) / SUPERSAMPLE
                    if not (x <= point_x <= x + width and y <= point_y <= y + height):
                        continue
                    clamped_x = min(max(point_x, x + radius), x + width - radius)
                    clamped_y = min(max(point_y, y + radius), y + height - radius)
                    if (point_x - clamped_x) ** 2 + (point_y - clamped_y) ** 2 <= radius**2:
                        inside += 1
            result.append(round(inside * 255 / (SUPERSAMPLE * SUPERSAMPLE)))
    return result


def _rgba_to_png(
    width: int,
    height: int,
    pixels: list[tuple[int, int, int, int]],
) -> bytes:
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


def render_svg_text_png_bytes(
    svg_text: str,
    size: int,
    source_name: str = "generated-icon.svg",
) -> bytes:
    info = inspect_svg_text(svg_text, source_name)
    artwork = _hex_rgb(str(info["artwork_fill"]))
    artwork_alpha = _render_alpha(str(info["path_data"]), size)
    background_fill = info["background_fill"]
    if background_fill:
        rectangle = info["background_rect"]
        background = _hex_rgb(str(background_fill))
        background_alpha = _render_rounded_rect_alpha(
            size,
            x=float(rectangle["x"]),
            y=float(rectangle["y"]),
            width=float(rectangle["width"]),
            height=float(rectangle["height"]),
            radius=float(rectangle["rx"]),
        )
        pixels = []
        for mark_alpha, surface_alpha in zip(artwork_alpha, background_alpha):
            mark_opacity = mark_alpha / 255
            surface_opacity = surface_alpha / 255
            output_opacity = mark_opacity + surface_opacity * (1 - mark_opacity)
            if output_opacity == 0:
                pixels.append((0, 0, 0, 0))
                continue
            pixels.append(tuple(
                round((
                    artwork[channel] * mark_opacity
                    + background[channel] * surface_opacity * (1 - mark_opacity)
                ) / output_opacity)
                for channel in range(3)
            ) + (round(output_opacity * 255),))
    else:
        pixels = [(*artwork, alpha) for alpha in artwork_alpha]
    return _rgba_to_png(size, size, pixels)


def render_png_bytes(svg_path: Path, size: int) -> bytes:
    return render_svg_text_png_bytes(
        svg_path.read_text(encoding="utf-8"),
        size,
        svg_path.name,
    )


def render_app_icon_png_bytes(size: int) -> bytes:
    """Render the installed-icon tile while favicons remain transparent."""
    source = app_icon_composition(MASTER_SVG.read_text(encoding="utf-8"))
    return render_svg_text_png_bytes(source, size, "installed-app-icon.svg")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
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
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + _paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise IconValidationError(f"{path.name} has bad PNG filter {filter_type}")
        rows.append(row)
        previous = row
    pixels: list[tuple[int, int, int, int]] = []
    mode = "RGBA" if channels == 4 else "RGB"
    for row in rows:
        for index in range(0, len(row), channels):
            if channels == 4:
                pixels.append(tuple(row[index:index + 4]))
            else:
                pixels.append((row[index], row[index + 1], row[index + 2], 255))
    return width, height, mode, pixels


def validate_png(
    path: Path,
    expected_size: int,
    *,
    expected_artwork: str = LIGHT_SURFACE_ARTWORK,
    expected_background: str | None = LIGHT_ICON_BACKGROUND,
) -> dict[str, object]:
    width, height, mode, pixels = decode_png(path)
    if (width, height) != (expected_size, expected_size):
        raise IconValidationError(
            f"{path.name} is {width}x{height}, expected {expected_size}x{expected_size}"
        )
    corners = (0, width - 1, (height - 1) * width, width * height - 1)
    if any(pixels[index][3] != 0 for index in corners):
        raise IconValidationError(f"{path.name} does not have transparent corners")
    if mode != "RGBA":
        raise IconValidationError(f"{path.name} does not have an alpha channel")
    expected_rgb = _hex_rgb(expected_artwork)
    expected_background_rgb = (
        _hex_rgb(expected_background) if expected_background is not None else None
    )
    opaque_colors = {pixel[:3] for pixel in pixels if pixel[3] == 255}
    if expected_rgb not in opaque_colors:
        raise IconValidationError(f"{path.name} is missing its opaque mark colour")
    if expected_background_rgb is not None and expected_background_rgb not in opaque_colors:
        raise IconValidationError(f"{path.name} is missing its background colour")
    if any(red != green or green != blue for red, green, blue in opaque_colors):
        raise IconValidationError(f"{path.name} is not monochrome")
    foreground = [
        (index % width, index // width)
        for index, pixel in enumerate(pixels)
        if pixel[3] != 0
    ]
    if not foreground:
        raise IconValidationError(f"{path.name} has no visible logo pixels")
    min_x = min(x for x, _ in foreground)
    max_x = max(x for x, _ in foreground)
    min_y = min(y for _, y in foreground)
    max_y = max(y for _, y in foreground)
    bbox_width = max_x - min_x + 1
    bbox_height = max_y - min_y + 1
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    canvas_center = (width - 1) / 2
    center_delta = math.hypot(center_x - canvas_center, center_y - canvas_center)
    minimum_extent = expected_size * (0.88 if expected_background_rgb else 0.68)
    if bbox_width < minimum_extent or bbox_height < minimum_extent:
        raise IconValidationError(
            f"{path.name} artwork bbox is too small: {(min_x, min_y, max_x, max_y)}"
        )
    if center_delta > expected_size * 0.08:
        raise IconValidationError(
            f"{path.name} artwork is off-center: ({center_x:.2f}, {center_y:.2f})"
        )
    mark_pixels = []
    for index, pixel in enumerate(pixels):
        if pixel[3] < 128:
            continue
        if expected_background_rgb is not None and max(
            abs(pixel[channel] - expected_background_rgb[channel])
            for channel in range(3)
        ) < 8:
            continue
        mark_pixels.append((index % width, index // width))
    if not mark_pixels:
        raise IconValidationError(f"{path.name} has no distinct quarter-pie mark")
    mark_min_x = min(x for x, _ in mark_pixels)
    mark_max_x = max(x for x, _ in mark_pixels)
    mark_min_y = min(y for _, y in mark_pixels)
    mark_max_y = max(y for _, y in mark_pixels)
    mark_width = mark_max_x - mark_min_x + 1
    mark_height = mark_max_y - mark_min_y + 1
    if mark_width < expected_size * 0.68 or mark_height < expected_size * 0.68:
        raise IconValidationError(
            f"{path.name} quarter-pie is too small: "
            f"{(mark_min_x, mark_min_y, mark_max_x, mark_max_y)}"
        )
    if (
        mark_min_x <= 0
        or mark_min_y <= 0
        or mark_max_x >= width - 1
        or mark_max_y >= height - 1
    ):
        raise IconValidationError(
            f"{path.name} quarter-pie lacks safe area: "
            f"{(mark_min_x, mark_min_y, mark_max_x, mark_max_y)}"
        )
    return {
        "file": path.name,
        "size": f"{width}x{height}",
        "mode": mode,
        "alpha_range": (min(pixel[3] for pixel in pixels), max(pixel[3] for pixel in pixels)),
        "transparent_pixels": sum(1 for pixel in pixels if pixel[3] == 0),
        "opaque_artwork_rgb": expected_rgb,
        "opaque_background_rgb": expected_background_rgb,
        "bbox": (min_x, min_y, max_x, max_y),
        "bbox_size": (bbox_width, bbox_height),
        "margins": (min_x, min_y, width - 1 - max_x, height - 1 - max_y),
        "center": (round(center_x, 2), round(center_y, 2)),
        "center_delta": round(center_delta, 3),
        "mark_bbox": (mark_min_x, mark_min_y, mark_max_x, mark_max_y),
        "mark_bbox_size": (mark_width, mark_height),
        "mark_margins": (
            mark_min_x,
            mark_min_y,
            width - 1 - mark_max_x,
            height - 1 - mark_max_y,
        ),
    }


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
        source_y = (y + 0.5) * scale_y - 0.5
        y0 = max(0, min(height - 1, int(math.floor(source_y))))
        y1 = max(0, min(height - 1, y0 + 1))
        fy = source_y - y0
        for x in range(out_size):
            source_x = (x + 0.5) * scale_x - 0.5
            x0 = max(0, min(width - 1, int(math.floor(source_x))))
            x1 = max(0, min(width - 1, x0 + 1))
            fx = source_x - x0
            samples = (
                (pixels[y0 * width + x0], (1 - fx) * (1 - fy)),
                (pixels[y0 * width + x1], fx * (1 - fy)),
                (pixels[y1 * width + x0], (1 - fx) * fy),
                (pixels[y1 * width + x1], fx * fy),
            )
            result.append(tuple(
                max(0, min(255, round(sum(pixel[channel] * weight for pixel, weight in samples))))
                for channel in range(4)
            ))
    return result


def validate_cross_size() -> float:
    width, height, _, pixels_512 = decode_png(ICONS_DIR / "android-chrome-512x512.png")
    _, _, _, pixels_192 = decode_png(ICONS_DIR / "android-chrome-192x192.png")
    resized = bilinear_resize(width, height, pixels_512, 192)
    difference = sum(
        sum(abs(first[channel] - second[channel]) for channel in range(4)) / 4
        for first, second in zip(resized, pixels_192)
    ) / len(pixels_192)
    if difference > 10:
        raise IconValidationError(
            f"192px icon differs from resized 512px icon: mean={difference:.3f}"
        )
    return round(difference, 3)


def write_ico(entries: dict[int, Path], ico_path: Path) -> None:
    images = [(size, entries[size].read_bytes()) for size in ICO_SIZES]
    offset = 6 + 16 * len(images)
    with ico_path.open("wb") as file:
        file.write(struct.pack("<HHH", 0, 1, len(images)))
        for size, data in images:
            file.write(struct.pack(
                "<BBBBHHII", size, size, 0, 0, 1, 32, len(data), offset,
            ))
            offset += len(data)
        for _, data in images:
            file.write(data)


def extract_ico_pngs(ico_path: Path, out_dir: Path) -> dict[int, Path]:
    data = ico_path.read_bytes()
    count = struct.unpack("<H", data[4:6])[0]
    result = {}
    for index in range(count):
        width, _, _, _, _, _, size, offset = struct.unpack(
            "<BBBBHHII", data[6 + index * 16:22 + index * 16],
        )
        entry_size = width or 256
        output = out_dir / f"favicon-ico-{entry_size}.png"
        output.write_bytes(data[offset:offset + size])
        result[entry_size] = output
    return result


def inspect_ico(ico_path: Path) -> list[dict[str, object]]:
    data = ico_path.read_bytes()
    reserved, icon_type, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or icon_type != 1:
        raise IconValidationError("favicon.ico is not an ICO image")
    entries = []
    for index in range(count):
        raw = data[6 + index * 16:22 + index * 16]
        width, height, _, _, planes, bpp, size, offset = struct.unpack(
            "<BBBBHHII", raw,
        )
        png_data = data[offset:offset + size]
        if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise IconValidationError("ICO entry is not PNG encoded")
        with tempfile.TemporaryDirectory(prefix="oneportfolio-ico-check-") as directory:
            entry_path = Path(directory) / f"favicon-{width}x{height}.png"
            entry_path.write_bytes(png_data)
            validation = validate_png(
                entry_path,
                width or 256,
                expected_background=None,
            )
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


def generate_rasters() -> None:
    for name, size in APP_PNGS.items():
        (ICONS_DIR / name).write_bytes(render_app_icon_png_bytes(size))
    with tempfile.TemporaryDirectory(prefix="oneportfolio-icons-") as directory:
        generated = {}
        for size in ICO_SIZES:
            output = Path(directory) / f"favicon-{size}.png"
            output.write_bytes(render_png_bytes(
                ICONS_DIR / "favicon-light.svg",
                size,
            ))
            generated[size] = output
        write_ico(generated, ICONS_DIR / "favicon.ico")


def generate() -> None:
    generate_svg_variants()
    generate_logo_component()
    generate_rasters()


def validate() -> None:
    master_text = MASTER_SVG.read_text(encoding="utf-8")
    if LOGO_COMPONENT.read_text(encoding="utf-8") != logo_component_text(master_text):
        raise IconValidationError(
            "logo_mark.html is not the deterministic currentColor master derivative"
        )
    if LIGHT_SURFACE_ARTWORK == DARK_SURFACE_ARTWORK:
        raise IconValidationError("Light and dark artwork colors must differ")
    for svg_path, expected_color in SVG_ARTWORK_COLORS.items():
        info = inspect_svg(svg_path)
        if info["artwork_fill"] != expected_color:
            raise IconValidationError(
                f"{svg_path.name} artwork is {info['artwork_fill']}, expected {expected_color}"
            )
        if info["background_fill"] is not None:
            raise IconValidationError(
                f"{svg_path.name} must remain a transparent bare mark"
            )
        if svg_path != MASTER_SVG:
            expected_artwork = SVG_VARIANTS[svg_path]
            expected_text = svg_variant(master_text, expected_artwork)
            if svg_path.read_text(encoding="utf-8") != expected_text:
                raise IconValidationError(
                    f"{svg_path.name} does not match the master SVG geometry"
                )
        contrasts = {
            surface: round(contrast_ratio(expected_color, surface), 2)
            for surface in TARGET_SURFACES[svg_path]
        }
        if min(contrasts.values()) < 4.5:
            raise IconValidationError(
                f"{svg_path.name} has insufficient target contrast: {contrasts}"
            )
        print(f"SVG ({svg_path.name}):", info, "contrast:", contrasts)

    for name, size in APP_PNGS.items():
        path = ICONS_DIR / name
        if path.read_bytes() != render_app_icon_png_bytes(size):
            raise IconValidationError(
                f"{name} is not the deterministic render of the master SVG"
            )
        print("PNG:", validate_png(path, size))
    print("Cross-size mean difference:", validate_cross_size())

    ico_entries = inspect_ico(ICONS_DIR / "favicon.ico")
    if [entry["width"] for entry in ico_entries] != list(ICO_SIZES):
        raise IconValidationError(f"Unexpected ICO sizes: {ico_entries}")
    with tempfile.TemporaryDirectory(prefix="oneportfolio-ico-source-") as directory:
        extracted = extract_ico_pngs(ICONS_DIR / "favicon.ico", Path(directory))
        for size, path in extracted.items():
            if path.read_bytes() != render_png_bytes(
                ICONS_DIR / "favicon-light.svg",
                size,
            ):
                raise IconValidationError(
                    f"favicon.ico {size}px frame does not match the master SVG"
                )
    print("ICO:", ico_entries)

    with tempfile.TemporaryDirectory(prefix="oneportfolio-size-check-") as directory:
        for size in REFERENCE_SIZES:
            rendered = Path(directory) / f"brand-{size}.png"
            rendered.write_bytes(render_png_bytes(
                ICONS_DIR / "favicon-light.svg",
                size,
            ))
            print(
                f"Reference size {size}px:",
                validate_png(
                    rendered,
                    size,
                    expected_background=None,
                ),
            )

    manifest_path = ICONS_DIR / "site.webmanifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "/static/icons/android-chrome-192x192.png": "192x192",
        "/static/icons/android-chrome-512x512.png": "512x512",
    }
    actual = {icon["src"]: icon["sizes"] for icon in manifest["icons"]}
    for source, sizes in expected.items():
        asset_path = ICONS_DIR / Path(source).name
        if actual.get(source) != sizes or not asset_path.exists():
            raise IconValidationError(
                f"Manifest entry mismatch for {source}: {actual.get(source)}"
            )
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
    args = parser.parse_args()
    if not args.validate_only:
        generate()
    validate()


if __name__ == "__main__":
    main()
