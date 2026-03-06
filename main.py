# Copyright © 2026 Sebastian Bąk. All rights reserved.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor, QIcon, QPixmap, QPainter, QPainterPath, QPen
from PyQt6.QtCore import Qt, QRectF

from ui.main_window import MainWindow


def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()

    dark_bg   = QColor(28, 28, 34)
    mid_bg    = QColor(40, 40, 48)
    light_bg  = QColor(52, 52, 62)
    highlight = QColor(0, 120, 215)
    text      = QColor(220, 220, 220)
    dim_text  = QColor(130, 130, 130)

    palette.setColor(QPalette.ColorRole.Window,          dark_bg)
    palette.setColor(QPalette.ColorRole.WindowText,      text)
    palette.setColor(QPalette.ColorRole.Base,            mid_bg)
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(34, 34, 42))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     light_bg)
    palette.setColor(QPalette.ColorRole.ToolTipText,     text)
    palette.setColor(QPalette.ColorRole.Text,            text)
    palette.setColor(QPalette.ColorRole.Button,          light_bg)
    palette.setColor(QPalette.ColorRole.ButtonText,      text)
    palette.setColor(QPalette.ColorRole.BrightText,      QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Link,            highlight)
    palette.setColor(QPalette.ColorRole.Highlight,       highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       dim_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, dim_text)
    palette.setColor(QPalette.ColorRole.Mid,  light_bg)
    palette.setColor(QPalette.ColorRole.Dark, QColor(18, 18, 22))

    app.setPalette(palette)


def make_icon() -> QIcon:
    size = 256
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Hexagon background
    cx, cy, r = size / 2, size / 2, size * 0.44
    hex_path = QPainterPath()
    import math
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

    # "HL7" text
    from PyQt6.QtGui import QFont
    font = QFont("Arial", int(size * 0.22), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(0, size * 0.25, size, size * 0.5), Qt.AlignmentFlag.AlignCenter, "HL7")

    p.end()
    return QIcon(px)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HL7 Scout")
    app.setApplicationDisplayName("HL7 Scout")
    apply_dark_theme(app)
    app.setWindowIcon(make_icon())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
