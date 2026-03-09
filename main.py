# Copyright © 2026 Sebastian Bąk. All rights reserved.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QSizePolicy
from PyQt6.QtGui import QPalette, QColor, QIcon, QPixmap, QPainter, QPainterPath, QPen
from PyQt6.QtCore import Qt, QRectF

from ui.main_window import MainWindow
from ui.db_panel import DbPanel


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

    # Clip text to hexagon so it can't overflow on any system font
    p.setClipPath(hex_path)

    # "HL7" text
    from PyQt6.QtGui import QFont
    font = QFont("Arial", int(size * 0.20), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "HL7")

    p.end()
    return QIcon(px)


class AppWindow(QMainWindow):
    """Top-level window with Parser and DB tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HL7 Scout")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 800)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().setExpanding(False)
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #0d1117;
            }
            QTabWidget::tab-bar {
                left: 0px;
            }
            QTabBar {
                background: #161b22;
                border-bottom: 1px solid #21262d;
            }
            QTabBar::tab {
                background: transparent;
                color: #8b949e;
                padding: 9px 16px 7px 16px;
                font-size: 12px;
                font-weight: 500;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                color: #e6edf3;
                border-bottom: 2px solid #1f6feb;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                color: #c9d1d9;
                background: rgba(255,255,255,0.04);
            }
            QTabBar::tab:first {
                margin-left: 8px;
            }
        """)

        # Parser tab
        self._parser = MainWindow()
        tabs.addTab(self._parser, "Parser HL7")

        # DB tab
        self._db_panel = DbPanel()
        self._db_panel.open_in_parser.connect(self._open_in_parser)
        tabs.addTab(self._db_panel, "Baza danych")

        self.setCentralWidget(tabs)
        self._tabs = tabs

    def _open_in_parser(self, raw: str):
        self._tabs.setCurrentIndex(0)
        self._parser.load_hl7(raw)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HL7 Scout")
    app.setApplicationDisplayName("HL7 Scout")
    apply_dark_theme(app)
    app.setWindowIcon(make_icon())

    window = AppWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
