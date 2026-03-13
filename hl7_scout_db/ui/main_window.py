# Copyright © 2026 Sebastian Bąk. All rights reserved.

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTextEdit, QLineEdit, QScrollArea, QPushButton,
    QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QGroupBox, QTabWidget, QFrame, QApplication, QMenu,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QFont, QBrush, QKeySequence, QShortcut,
    QIcon, QPixmap, QPainter, QPen, QPainterPath, QPolygonF,
)

import parser as hl7_parser
import hl7_fields as fields
import mllp_sender


# ──────────────────────────────────────── Button icons (QPainter) ─────────────

def _make_btn_icon(draw_fn, size: int = 32,
                   color: str = "#ffffff", bg: str | None = None) -> QIcon:
    """Create a crisp QIcon by painting with QPainter."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if bg:
        p.fillRect(0, 0, size, size, QColor(bg))
    draw_fn(p, size, QColor(color))
    p.end()
    return QIcon(px)


def _draw_play(p: QPainter, s: int, c: QColor):
    """Solid play triangle."""
    m = s * 0.22
    path = QPainterPath()
    path.moveTo(m + s * 0.08, m)
    path.lineTo(s - m, s / 2)
    path.lineTo(m + s * 0.08, s - m)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(path)


def _draw_copy(p: QPainter, s: int, c: QColor):
    """Two overlapping rounded rectangles — copy icon."""
    pen = QPen(c, s * 0.07)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    off = s * 0.12
    w = s * 0.52
    # Back sheet
    p.drawRoundedRect(QRectF(off, off, w, w * 1.15), s * 0.06, s * 0.06)
    # Front sheet
    p.drawRoundedRect(QRectF(s - off - w, s - off - w * 1.15, w, w * 1.15),
                      s * 0.06, s * 0.06)


def _draw_chevron_right(p: QPainter, s: int, c: QColor):
    """Right-pointing chevron >."""
    pen = QPen(c, s * 0.1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = s * 0.32
    p.drawPolyline(QPolygonF([
        QPointF(m, s * 0.2),
        QPointF(s - m, s * 0.5),
        QPointF(m, s * 0.8),
    ]))


def _draw_chevron_down(p: QPainter, s: int, c: QColor):
    """Down-pointing chevron v."""
    pen = QPen(c, s * 0.1)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = s * 0.25
    p.drawPolyline(QPolygonF([
        QPointF(s * 0.2, m),
        QPointF(s * 0.5, s - m),
        QPointF(s * 0.8, m),
    ]))


def _draw_send(p: QPainter, s: int, c: QColor):
    """Paper-plane / send arrow."""
    path = QPainterPath()
    m = s * 0.15
    path.moveTo(m, s * 0.5)
    path.lineTo(s - m, s * 0.5)
    p.setPen(QPen(c, s * 0.08, cap=Qt.PenCapStyle.RoundCap))
    p.drawPath(path)
    # Arrowhead
    arrow = QPainterPath()
    arrow.moveTo(s * 0.58, s * 0.25)
    arrow.lineTo(s - m, s * 0.5)
    arrow.lineTo(s * 0.58, s * 0.75)
    pen = QPen(c, s * 0.08)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPath(arrow)


def _draw_clear(p: QPainter, s: int, c: QColor):
    """X mark — clear."""
    pen = QPen(c, s * 0.09)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m = s * 0.26
    p.drawLine(QPointF(m, m), QPointF(s - m, s - m))
    p.drawLine(QPointF(s - m, m), QPointF(m, s - m))


# Pre-built icons (created lazily on first use)
_icon_cache: dict[str, QIcon] = {}


def _icon(name: str) -> QIcon:
    if name not in _icon_cache:
        builders = {
            "play":      lambda: _make_btn_icon(_draw_play, color="#ffffff"),
            "copy":      lambda: _make_btn_icon(_draw_copy, color="#aaccdd"),
            "copy_seg":  lambda: _make_btn_icon(_draw_copy, size=26, color="#aaaacc"),
            "mllp_r":    lambda: _make_btn_icon(_draw_chevron_right, color="#7799bb"),
            "mllp_d":    lambda: _make_btn_icon(_draw_chevron_down, color="#7799bb"),
            "send":      lambda: _make_btn_icon(_draw_send, color="#ffffff"),
            "clear":     lambda: _make_btn_icon(_draw_clear, color="#aaaaaa"),
        }
        _icon_cache[name] = builders[name]()
    return _icon_cache[name]


# ──────────────────────────────────────── MLLP worker thread ─────────────────

class _MLLPWorker(QThread):
    """Sends an HL7 message via MLLP in a background thread."""
    finished = pyqtSignal(object)  # MLLPResponse

    def __init__(self, host: str, port: int, message: str, timeout: float):
        super().__init__()
        self._host = host
        self._port = port
        self._message = message
        self._timeout = timeout

    def run(self):
        result = mllp_sender.send(self._host, self._port,
                                  self._message, self._timeout)
        self.finished.emit(result)


def _lighten(hex_color: str, amount: float = 0.18) -> str:
    """Mix hex_color with white by `amount` (0–1) to produce a lighter shade."""
    c = QColor(hex_color)
    r = min(255, int(c.red()   + (255 - c.red())   * amount))
    g = min(255, int(c.green() + (255 - c.green()) * amount))
    b = min(255, int(c.blue()  + (255 - c.blue())  * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_color_map(segments) -> list[str]:
    """Return a list of colors, one per segment.
    Repeated segment types alternate between base color and a lighter shade."""
    occurrence: dict[str, int] = {}
    colors = []
    for seg in segments:
        n = occurrence.get(seg.name, 0)
        base = fields.get_segment_color(seg.name)
        colors.append(base if n % 2 == 0 else _lighten(base))
        occurrence[seg.name] = n + 1
    return colors


# ──────────────────────────────────────── Segment tile ───────────────────────

class SegmentTile(QFrame):
    """One colored row representing a single HL7 segment."""

    def __init__(self, seg_name: str, seg_raw: str, color: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setObjectName("SegmentTile")
        self.setStyleSheet(
            f"#SegmentTile {{ background: {color}; border-radius: 3px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(8)

        # Segment name badge
        badge = QLabel(seg_name)
        badge.setFixedWidth(42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont("Consolas", 10)
        f.setBold(True)
        badge.setFont(f)
        badge.setStyleSheet("color: #e8eeff; background: transparent; border: none;")

        # Vertical divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFixedWidth(1)
        div.setStyleSheet("background: rgba(255,255,255,0.18); border: none;")

        # Editable segment content
        self.edit = QLineEdit(seg_raw)
        self.edit.setFont(QFont("Consolas", 9))
        self.edit.setCursorPosition(0)  # always show from left, even for long segments
        self.edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; "
            "color: #d0d8e8; selection-background-color: #4a6a9a; }"
        )

        # Copy button
        copy_btn = QPushButton()
        copy_btn.setIcon(_icon("copy_seg"))
        copy_btn.setFixedSize(26, 26)
        copy_btn.setToolTip("Kopiuj segment do schowka")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.10); border: none; "
            "border-radius: 3px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.30); }"
            "QPushButton:pressed { background: rgba(255,255,255,0.15); }"
        )
        copy_btn.clicked.connect(self._copy)

        layout.addWidget(badge)
        layout.addWidget(div)
        layout.addWidget(self.edit, 1)
        layout.addWidget(copy_btn)

    def _copy(self):
        QApplication.clipboard().setText(self.edit.text())

    def get_raw(self) -> str:
        return self.edit.text()


# ──────────────────────────────────────── Main window ────────────────────────

class MainWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_message = None
        self._segment_tiles: list[SegmentTile] = []
        self._mllp_worker: _MLLPWorker | None = None
        self._setup_ui()
        self._connect_signals()

    def load_hl7(self, raw: str):
        """Load an HL7 message programmatically (called from DB panel)."""
        raw = raw.strip()
        if not raw:
            return
        try:
            msg = hl7_parser.parse(raw)
        except Exception as e:
            self._set_status(f"Błąd parsowania: {e}", error=True)
            return
        if not msg.segments:
            self._set_status("Nie wykryto segmentów w treści HL7.", error=True)
            return
        self._current_message = msg
        self._show_tiles(msg)
        self._populate_tree(msg)
        self._populate_table(msg)
        count = len(msg.segments)
        self._set_status(
            f"Załadowano z bazy: {count} segment"
            f"{'y' if 2 <= count <= 4 else 'ów' if count != 1 else ''}."
        )

    # ──────────────────────────────────────── UI setup ───────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Input section ────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(6, 6, 6, 6)
        input_layout.setSpacing(4)

        paste_label = QLabel("Wklej wiadomość HL7 v2.x — segmenty pojawią się poniżej jako kafelki:")
        paste_label.setStyleSheet("color: #8888aa; font-size: 11px;")

        # Paste target — small, just for receiving paste
        self.paste_input = QTextEdit()
        self.paste_input.setPlaceholderText(
            "Wklej tutaj (Ctrl+V)…"
        )
        self.paste_input.setFixedHeight(44)
        self.paste_input.setFont(QFont("Consolas", 9))
        self.paste_input.setStyleSheet(
            "QTextEdit { background: #12121c; border: 1px solid #3a3a5a; border-radius: 4px; "
            "color: #888; padding: 4px 6px; }"
        )

        # ── Tile scroll area ─────────────────────────────────────────────────
        self.tiles_scroll = QScrollArea()
        self.tiles_scroll.setWidgetResizable(True)
        self.tiles_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tiles_scroll.setMinimumHeight(60)
        self.tiles_scroll.setMaximumHeight(220)
        self.tiles_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #3a3a4a; border-radius: 4px; background: #1a1a22; }"
            "QScrollBar:vertical { background: #1a1a22; width: 8px; border: none; }"
            "QScrollBar::handle:vertical { background: #3a3a5a; border-radius: 4px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._tiles_container = QWidget()
        self._tiles_container.setStyleSheet("background: #1a1a22;")
        self._tiles_layout = QVBoxLayout(self._tiles_container)
        self._tiles_layout.setContentsMargins(4, 4, 4, 4)
        self._tiles_layout.setSpacing(2)

        self._tile_placeholder = QLabel("Brak danych — wklej wiadomość HL7 powyżej")
        self._tile_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tile_placeholder.setStyleSheet(
            "color: #444466; font-size: 11px; font-style: italic; padding: 12px;"
        )
        self._tiles_layout.addWidget(self._tile_placeholder)
        self._tiles_layout.addStretch()

        self.tiles_scroll.setWidget(self._tiles_container)

        # ── Button row ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.parse_btn = QPushButton("  Parsuj")
        self.parse_btn.setIcon(_icon("play"))
        self.parse_btn.setFixedWidth(120)
        self.parse_btn.setStyleSheet(
            "QPushButton { background: #0078d7; color: white; border-radius: 4px; "
            "padding: 5px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #1a8fe0; }"
            "QPushButton:pressed { background: #005fa3; }"
        )

        self.copy_frame_btn = QPushButton("  Kopiuj ramke")
        self.copy_frame_btn.setIcon(_icon("copy"))
        self.copy_frame_btn.setFixedWidth(152)
        self.copy_frame_btn.setToolTip("Kopiuj całą wiadomość HL7 do schowka (z separatorem \\r)")
        self.copy_frame_btn.setStyleSheet(
            "QPushButton { background: #1a3a4a; color: #aaccdd; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background: #2a4a5a; }"
            "QPushButton:pressed { background: #0a2a3a; }"
        )

        self.clear_btn = QPushButton("  Wyczysc")
        self.clear_btn.setIcon(_icon("clear"))
        self.clear_btn.setFixedWidth(110)
        self.clear_btn.setStyleSheet(
            "QPushButton { background: #3a3a4a; color: #aaa; border-radius: 4px; padding: 5px 10px; }"
            "QPushButton:hover { background: #4a4a5a; }"
        )

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")

        self.mllp_toggle_btn = QPushButton("  MLLP")
        self.mllp_toggle_btn.setIcon(_icon("mllp_r"))
        self.mllp_toggle_btn.setFixedWidth(100)
        self.mllp_toggle_btn.setToolTip("Pokaż / ukryj panel wysyłki MLLP")
        self.mllp_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mllp_toggle_btn.setStyleSheet(
            "QPushButton { background: #2a2a3a; color: #7799bb; border-radius: 4px; "
            "padding: 5px 10px; font-weight: bold; }"
            "QPushButton:hover { background: #3a3a4a; color: #99bbdd; }"
            "QPushButton:pressed { background: #1a1a2a; }"
        )

        btn_row.addWidget(self.parse_btn)
        btn_row.addWidget(self.copy_frame_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.mllp_toggle_btn)
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()

        # ── MLLP send panel (hidden by default) ─────────────────────────────
        self.send_frame = QFrame()
        send_frame = self.send_frame
        send_frame.setObjectName("sendFrame")
        send_frame.setStyleSheet(
            "#sendFrame { background: #1a1a28; border: 1px solid #2a3a4a; border-radius: 4px; }"
        )
        send_layout = QVBoxLayout(send_frame)
        send_layout.setContentsMargins(8, 6, 8, 6)
        send_layout.setSpacing(4)

        send_header = QLabel("Wyślij MLLP — transmisja HL7 na bramkę wymiany:")
        send_header.setStyleSheet("color: #7799bb; font-size: 11px; border: none;")

        send_row = QHBoxLayout()
        send_row.setSpacing(6)

        host_label = QLabel("Host:")
        host_label.setStyleSheet("color: #8888aa; font-size: 11px; border: none;")
        self.host_input = QLineEdit("localhost")
        self.host_input.setFixedWidth(160)
        self.host_input.setFont(QFont("Consolas", 9))
        self.host_input.setStyleSheet(
            "QLineEdit { background: #12121c; border: 1px solid #3a3a5a; border-radius: 3px; "
            "color: #ccc; padding: 3px 6px; }"
        )

        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #8888aa; font-size: 11px; border: none;")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(2575)  # default MLLP port
        self.port_input.setFixedWidth(80)
        self.port_input.setFont(QFont("Consolas", 9))
        self.port_input.setStyleSheet(
            "QSpinBox { background: #12121c; border: 1px solid #3a3a5a; border-radius: 3px; "
            "color: #ccc; padding: 3px 6px; }"
        )

        timeout_label = QLabel("Timeout:")
        timeout_label.setStyleSheet("color: #8888aa; font-size: 11px; border: none;")
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 120)
        self.timeout_input.setValue(10)
        self.timeout_input.setSuffix("s")
        self.timeout_input.setFixedWidth(70)
        self.timeout_input.setFont(QFont("Consolas", 9))
        self.timeout_input.setStyleSheet(
            "QSpinBox { background: #12121c; border: 1px solid #3a3a5a; border-radius: 3px; "
            "color: #ccc; padding: 3px 6px; }"
        )

        self.send_btn = QPushButton("  Wyslij")
        self.send_btn.setIcon(_icon("send"))
        self.send_btn.setFixedWidth(120)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(
            "QPushButton { background: #1a6a3a; color: white; border-radius: 4px; "
            "padding: 5px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #22884a; }"
            "QPushButton:pressed { background: #0e5528; }"
            "QPushButton:disabled { background: #2a2a3a; color: #555; }"
        )

        self.send_status = QLabel("")
        self.send_status.setStyleSheet("color: #888; font-size: 11px; border: none;")

        send_row.addWidget(host_label)
        send_row.addWidget(self.host_input)
        send_row.addWidget(port_label)
        send_row.addWidget(self.port_input)
        send_row.addWidget(timeout_label)
        send_row.addWidget(self.timeout_input)
        send_row.addWidget(self.send_btn)
        send_row.addWidget(self.send_status)
        send_row.addStretch()

        # Response display
        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)
        self.response_display.setFixedHeight(60)
        self.response_display.setFont(QFont("Consolas", 9))
        self.response_display.setPlaceholderText("Odpowiedź ACK/NAK pojawi się tutaj…")
        self.response_display.setStyleSheet(
            "QTextEdit { background: #0e0e16; border: 1px solid #2a2a3a; border-radius: 3px; "
            "color: #99bbcc; padding: 4px 6px; }"
        )
        self.response_display.setVisible(False)

        send_layout.addWidget(send_header)
        send_layout.addLayout(send_row)
        send_layout.addWidget(self.response_display)
        send_frame.setVisible(False)

        input_layout.addWidget(paste_label)
        input_layout.addWidget(self.paste_input)
        input_layout.addWidget(self.tiles_scroll)
        input_layout.addLayout(btn_row)
        input_layout.addWidget(send_frame)
        layout.addWidget(input_frame)

        # ── Main splitter ────────────────────────────────────────────────────
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 18px; }"
            "QTabBar::tab:selected { background: #1e3a5c; color: white; }"
        )

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Segment / Pole", "Wartość"])
        self.tree.setColumnWidth(0, 420)
        self.tree.setAlternatingRowColors(True)
        self.tree.setFont(QFont("Consolas", 10))
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(1, 600)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.header().setStretchLastSection(True)
        self.tree.setStyleSheet(
            "QTreeWidget { border: none; } QTreeWidget::item { padding: 2px 0; }"
            "QScrollBar:horizontal { background: #1a1a22; height: 8px; border: none; }"
            "QScrollBar::handle:horizontal { background: #3a3a5a; border-radius: 4px; min-width: 20px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Segment", "Pole", "Nazwa pola", "Wartość"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 600)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Consolas", 10))
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setStyleSheet(
            "QTableWidget { border: none; }"
            "QScrollBar:horizontal { background: #1a1a22; height: 8px; border: none; }"
            "QScrollBar::handle:horizontal { background: #3a3a5a; border-radius: 4px; min-width: 20px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)

        self.tabs.addTab(self.tree, "  Drzewo  ")
        self.tabs.addTab(self.table, "  Tabela  ")

        # Legend
        legend_box = QGroupBox("Legenda")
        legend_layout = QVBoxLayout(legend_box)
        legend_layout.setContentsMargins(8, 6, 8, 6)
        self.legend_label = QLabel("Kliknij segment lub pole, aby zobaczyć opis.")
        self.legend_label.setWordWrap(True)
        self.legend_label.setTextFormat(Qt.TextFormat.RichText)
        self.legend_label.setStyleSheet("color: #ccc; font-size: 12px; padding: 2px;")
        self.legend_label.setMinimumHeight(52)
        legend_layout.addWidget(self.legend_label)

        main_splitter.addWidget(self.tabs)
        main_splitter.addWidget(legend_box)
        main_splitter.setSizes([540, 110])
        main_splitter.setCollapsible(1, False)

        layout.addWidget(main_splitter)

        QShortcut(QKeySequence("Ctrl+Return"), self, self._parse)

    # ──────────────────────────────────────── signals ────────────────────────

    def _connect_signals(self):
        self.parse_btn.clicked.connect(self._parse)
        self.copy_frame_btn.clicked.connect(self._copy_frame)
        self.clear_btn.clicked.connect(self._clear)
        self.mllp_toggle_btn.clicked.connect(self._toggle_mllp_panel)
        self.send_btn.clicked.connect(self._send_mllp)
        self.tree.itemClicked.connect(self._on_tree_click)
        self.table.itemSelectionChanged.connect(self._on_table_select)

        self._paste_timer = QTimer()
        self._paste_timer.setSingleShot(True)
        self._paste_timer.setInterval(120)
        self._paste_timer.timeout.connect(self._on_paste_timer)
        self._last_paste_len = 0
        self.paste_input.textChanged.connect(self._check_paste)

    def _check_paste(self):
        current_len = len(self.paste_input.toPlainText())
        if current_len - self._last_paste_len > 20:
            self._paste_timer.start()
        self._last_paste_len = current_len

    def _on_paste_timer(self):
        raw = self.paste_input.toPlainText().strip()
        if not raw:
            return
        try:
            msg = hl7_parser.parse(raw)
        except Exception:
            return
        if not msg.segments:
            return
        self._show_tiles(msg)
        self._current_message = msg
        self.paste_input.blockSignals(True)
        self.paste_input.clear()
        self.paste_input.blockSignals(False)
        self._last_paste_len = 0

    # ──────────────────────────────────────── tiles ──────────────────────────

    def _show_tiles(self, msg):
        """Replace current tiles with those from msg."""
        for tile in self._segment_tiles:
            self._tiles_layout.removeWidget(tile)
            tile.deleteLater()
        self._segment_tiles.clear()

        self._tile_placeholder.setVisible(False)
        colors = _build_color_map(msg.segments)

        for seg, color in zip(msg.segments, colors):
            tile = SegmentTile(seg.name, seg.raw, color, self._tiles_container)
            # Insert before the trailing stretch
            self._tiles_layout.insertWidget(self._tiles_layout.count() - 1, tile)
            self._segment_tiles.append(tile)

    def _get_assembled_raw(self) -> str:
        """Assemble HL7 message from tile line edits (HL7 CR separator)."""
        if self._segment_tiles:
            return '\r'.join(t.get_raw() for t in self._segment_tiles)
        return self.paste_input.toPlainText()

    def _copy_frame(self):
        raw = self._get_assembled_raw().strip()
        if raw:
            QApplication.clipboard().setText(raw)
            self._set_status("Ramka HL7 skopiowana do schowka.")
        else:
            self._set_status("Brak danych do skopiowania.", error=True)

    # ──────────────────────────────────────── parsing ────────────────────────

    def _parse(self):
        raw = self._get_assembled_raw().strip()
        if not raw:
            self._set_status("Brak danych do parsowania.", error=True)
            return
        try:
            msg = hl7_parser.parse(raw)
        except Exception as e:
            self._set_status(f"Błąd parsowania: {e}", error=True)
            return
        if not msg.segments:
            self._set_status("Nie wykryto żadnych segmentów.", error=True)
            return

        self._current_message = msg
        self._show_tiles(msg)
        self._populate_tree(msg)
        self._populate_table(msg)
        count = len(msg.segments)
        self._set_status(
            f"Sparsowano {count} segment"
            f"{'y' if 2 <= count <= 4 else 'ów' if count != 1 else ''}."
        )

    def _clear(self):
        for tile in self._segment_tiles:
            self._tiles_layout.removeWidget(tile)
            tile.deleteLater()
        self._segment_tiles.clear()
        self._tile_placeholder.setVisible(True)
        self.paste_input.blockSignals(True)
        self.paste_input.clear()
        self.paste_input.blockSignals(False)
        self._last_paste_len = 0
        self.tree.clear()
        self.tree.header().setStretchLastSection(True)
        self.table.setRowCount(0)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._set_status("")
        self.legend_label.setText("Kliknij segment lub pole, aby zobaczyć opis.")
        self._current_message = None

    # ──────────────────────────────────────── tree ───────────────────────────

    def _populate_tree(self, msg):
        self.tree.clear()
        colors = _build_color_map(msg.segments)
        for seg, color in zip(msg.segments, colors):
            seg_item = self._make_seg_tree_item(seg, color)
            self.tree.addTopLevelItem(seg_item)

            for f in seg.fields:
                field_item = self._make_field_tree_item(seg, f)
                seg_item.addChild(field_item)

                if f.repetitions:
                    first_rep = f.repetitions[0]
                    if len(first_rep) > 1 and any(c.raw for c in first_rep):
                        for ci, comp in enumerate(first_rep, start=1):
                            if comp.raw:
                                comp_item = QTreeWidgetItem()
                                comp_item.setText(0, f"    Komp. {ci}")
                                comp_item.setText(1, comp.raw)
                                comp_item.setForeground(0, QBrush(QColor("#778899")))
                                comp_item.setForeground(1, QBrush(QColor("#aabbcc")))
                                field_item.addChild(comp_item)

                    if len(f.repetitions) > 1:
                        for ri, rep in enumerate(f.repetitions, start=1):
                            rep_val = msg.component_sep.join(c.raw for c in rep)
                            rep_item = QTreeWidgetItem()
                            rep_item.setText(0, f"    Powtórzenie {ri}")
                            rep_item.setText(1, rep_val)
                            rep_item.setForeground(0, QBrush(QColor("#778899")))
                            rep_item.setForeground(1, QBrush(QColor("#aabbcc")))
                            field_item.addChild(rep_item)

            seg_item.setExpanded(True)

        # If content is wider than viewport, disable stretch so scroll works
        self.tree.header().setStretchLastSection(False)
        self.tree.resizeColumnToContents(1)
        remaining = self.tree.viewport().width() - self.tree.columnWidth(0)
        if self.tree.columnWidth(1) <= remaining:
            self.tree.header().setStretchLastSection(True)

    def _make_seg_tree_item(self, seg, color: str) -> QTreeWidgetItem:
        seg_name_full = fields.get_segment_name(seg.name)
        item = QTreeWidgetItem()
        item.setText(0, f"{seg.name}  —  {seg_name_full}")
        item.setText(1, "")
        qcolor = QColor(color)
        item.setBackground(0, QBrush(qcolor))
        item.setBackground(1, QBrush(qcolor))
        item.setForeground(0, QBrush(QColor("#e0e8ff")))
        bold = QFont("Consolas", 10)
        bold.setBold(True)
        item.setFont(0, bold)
        item.setData(0, Qt.ItemDataRole.UserRole, ("segment", seg.name))
        return item

    def _make_field_tree_item(self, seg, f) -> QTreeWidgetItem:
        field_name = self._field_name(seg.name, f.index)
        label = f"  {seg.name}-{f.index}"
        if field_name:
            label += f"  {field_name}"
        item = QTreeWidgetItem()
        item.setText(0, label)
        item.setText(1, f.raw if f.raw else "")
        item.setForeground(0, QBrush(QColor("#a0b4cc")))
        item.setForeground(1, QBrush(QColor("#dcdcdc")))
        item.setData(0, Qt.ItemDataRole.UserRole, ("field", seg.name, f.index))
        return item

    # ──────────────────────────────────────── table ──────────────────────────

    def _populate_table(self, msg):
        seg_colors = _build_color_map(msg.segments)
        rows = [
            (seg.name, f.index, f.raw, color)
            for seg, color in zip(msg.segments, seg_colors)
            for f in seg.fields
            if f.raw.strip()
        ]
        self.table.setRowCount(len(rows))

        for row_idx, (seg_name, field_num, value, color) in enumerate(rows):
            bg = QColor(color)
            field_name = self._field_name(seg_name, field_num)

            items = [
                QTableWidgetItem(seg_name),
                QTableWidgetItem(f"{seg_name}-{field_num}"),
                QTableWidgetItem(field_name),
                QTableWidgetItem(value),
            ]
            items[0].setFont(self._bold_font())
            for col, it in enumerate(items):
                it.setBackground(QBrush(bg))
                it.setForeground(QBrush(QColor("#dcdcdc")))
                it.setData(Qt.ItemDataRole.UserRole, (seg_name, field_num))
                self.table.setItem(row_idx, col, it)

        # If content is wider than viewport, disable stretch so scroll works
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.resizeColumnToContents(3)
        used = sum(self.table.columnWidth(c) for c in range(3))
        remaining = self.table.viewport().width() - used
        if self.table.columnWidth(3) <= remaining:
            self.table.horizontalHeader().setStretchLastSection(True)

    # ──────────────────────────────────────── legend ─────────────────────────

    def _on_tree_click(self, item: QTreeWidgetItem, _col):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        if data[0] == "segment":
            self._show_segment_legend(data[1])
        elif data[0] == "field":
            self._show_field_legend(data[1], data[2])

    def _table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item or not item.text():
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #2a2a38; border: 1px solid #4a4a5a; color: #dcdcdc; }"
            "QMenu::item:selected { background: #0078d7; color: white; }"
            "QMenu::item { padding: 5px 18px; }"
        )
        copy_action = menu.addAction("Kopiuj")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == copy_action:
            QApplication.clipboard().setText(item.text())

    def _on_table_select(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        data = selected[0].data(Qt.ItemDataRole.UserRole)
        if data:
            self._show_field_legend(*data)

    def _show_segment_legend(self, seg_name: str):
        name = fields.get_segment_name(seg_name)
        desc = fields.get_segment_description(seg_name)
        color = fields.get_segment_color(seg_name)
        self.legend_label.setText(
            f'<span style="background:{color}; color:#e0e8ff; padding:2px 8px; '
            f'border-radius:3px; font-weight:bold;">&nbsp;{seg_name}&nbsp;</span>&nbsp;&nbsp;'
            f'<b style="color:#e0e8ff;">{name}</b><br/>'
            f'<span style="color:#aaaacc;">{desc}</span>'
        )

    def _show_field_legend(self, seg_name: str, field_num: int):
        info = fields.get_field_info(seg_name, field_num)
        color = fields.get_segment_color(seg_name)
        tag = (f'<span style="background:{color}; color:#e0e8ff; padding:2px 8px; '
               f'border-radius:3px; font-weight:bold;">&nbsp;{seg_name}-{field_num}&nbsp;</span>')
        if info:
            fname, fdesc = info
            self.legend_label.setText(
                f'{tag}&nbsp;&nbsp;<b style="color:#e0e8ff;">{fname}</b><br/>'
                f'<span style="color:#aaaacc;">{fdesc}</span>'
            )
        else:
            self.legend_label.setText(
                f'{tag}&nbsp;&nbsp;<span style="color:#888;">Brak opisu dla tego pola.</span>'
            )

    # ──────────────────────────────────────── MLLP send ────────────────────

    def _toggle_mllp_panel(self):
        visible = not self.send_frame.isVisible()
        self.send_frame.setVisible(visible)
        self.mllp_toggle_btn.setIcon(_icon("mllp_d") if visible else _icon("mllp_r"))

    def _send_mllp(self):
        raw = self._get_assembled_raw().strip()
        if not raw:
            self._set_send_status("Brak ramki do wysłania.", error=True)
            return

        host = self.host_input.text().strip()
        if not host:
            self._set_send_status("Podaj adres hosta.", error=True)
            return

        port = self.port_input.value()
        timeout = self.timeout_input.value()

        self.send_btn.setEnabled(False)
        self._set_send_status("Wysyłanie…")
        self.response_display.clear()
        self.response_display.setVisible(False)

        self._mllp_worker = _MLLPWorker(host, port, raw, timeout)
        self._mllp_worker.finished.connect(self._on_mllp_result)
        self._mllp_worker.start()

    def _on_mllp_result(self, result: mllp_sender.MLLPResponse):
        self.send_btn.setEnabled(True)
        self._mllp_worker = None

        if result.success:
            ack_info = f" [ACK: {result.ack_code}]" if result.ack_code else ""
            self._set_send_status(f"Wysłano pomyślnie.{ack_info}")
        else:
            self._set_send_status(f"Błąd: {result.ack_code or 'wysyłka nieudana'}", error=True)

        # Show response content
        if result.raw_response:
            self.response_display.setVisible(True)
            formatted = result.raw_response.replace('\r', '\n')
            self.response_display.setPlainText(formatted)

    def _set_send_status(self, text: str, error: bool = False):
        color = "#e05555" if error else "#55cc77"
        self.send_status.setTextFormat(Qt.TextFormat.RichText)
        self.send_status.setText(f'<span style="color:{color};">{text}</span>')

    # ──────────────────────────────────────── helpers ────────────────────────

    def _field_name(self, seg_name: str, field_num: int) -> str:
        info = fields.get_field_info(seg_name, field_num)
        return info[0] if info else ""

    def _bold_font(self) -> QFont:
        f = QFont("Consolas", 10)
        f.setBold(True)
        return f

    def _set_status(self, text: str, error: bool = False):
        color = "#e05555" if error else "#55aa55"
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.status_label.setText(f'<span style="color:{color};">{text}</span>')
