# Copyright © 2026 Sebastian Bąk. All rights reserved.
# Run once to generate icon.ico for PyInstaller build.

import sys, math, io
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QPen, QColor, QFont
from PyQt6.QtCore import Qt, QRectF
from PIL import Image

app = QApplication(sys.argv)


def render_icon(size: int) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    cx, cy, r = size / 2, size / 2, size * 0.44

    hex_path = QPainterPath()
    for i in range(6):
        angle = math.radians(60 * i - 30)
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        if i == 0:
            hex_path.moveTo(x, y)
        else:
            hex_path.lineTo(x, y)
    hex_path.closeSubpath()

    p.fillPath(hex_path, QColor(0, 60, 120))
    pen = QPen(QColor(0, 140, 220), size * 0.03)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(hex_path)

    # Clip text to hexagon so it can't overflow on any system font
    p.setClipPath(hex_path)

    font = QFont("Arial", max(6, int(size * 0.20)), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "HL7")

    p.end()
    return px


def pixmap_to_pil(px: QPixmap, size: int) -> Image.Image:
    path = f"_tmp_icon_{size}.png"
    px.save(path, "PNG")
    img = Image.open(path).convert("RGBA")
    img.load()
    return img


# Render once at 1024px, downscale with LANCZOS — covers all DPI scaling levels
source = pixmap_to_pil(render_icon(1024), 1024)

# Full set: standard + DPI-scaled intermediates (100/125/150/175/200%)
sizes = [16, 20, 24, 28, 32, 40, 48, 56, 64, 80, 96, 128, 256]

# Pillow ICO: pass `sizes` to the source image — it will downscale internally
source.save(
    "icon.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes],
)

import os
try:
    os.remove("_tmp_icon_1024.png")
except OSError:
    pass

# Verify
from PIL import Image as _I
check = _I.open("icon.ico")
frames = []
try:
    i = 0
    while True:
        check.seek(i)
        frames.append(check.size[0])
        i += 1
except EOFError:
    pass
print(f"Zapisano icon.ico — {len(frames)} rozmiarów: {frames}")
