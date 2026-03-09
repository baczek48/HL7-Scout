# Copyright © 2026 Sebastian Bąk. All rights reserved.
"""Oracle DB panel — hospital list, connect, search by id_zlecenia, view HL7 packages."""

import sys
import os
from urllib.parse import unquote

def _fix_encoding(text: str) -> str:
    """Best-effort repair for cp1250 content misread as latin-1 by Oracle driver."""
    if '%' in text:
        return text   # URL-encoded — leave for unquote()
    try:
        candidate = text.encode('latin-1').decode('cp1250')
        polish = set('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ')
        if sum(c in polish for c in candidate) > sum(c in polish for c in text):
            return candidate
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return text


def _sanitize_oracle_error(e: Exception) -> str:
    """Return a safe error message — strip DSN, credentials and server details from Oracle exceptions."""
    msg = str(e)
    # oracledb errors have a code attribute, e.g. DPY-3015, ORA-01017
    code = getattr(e, 'code', None) or getattr(e, '_code', None)
    if code:
        return f"Błąd Oracle [{code}] — sprawdź dane połączenia lub skontaktuj się z DBA."
    # Fallback: keep only first line and strip anything after a colon that might hold DSN
    first_line = msg.splitlines()[0] if msg else "nieznany błąd"
    # Remove DSN-like patterns (host:port/service or @host)
    import re
    first_line = re.sub(r'[\w\-.]+:\d+/[\w\-.]+', '<dsn>', first_line)
    first_line = re.sub(r'@[\w\-.]+', '@<host>', first_line)
    return first_line[:200]  # hard cap


def _decode_raw(raw_bytes: bytes) -> str:
    """Decode raw Oracle bytes to string.

    Tries UTF-8 first (covers URL-encoded and proper UTF-8 content),
    then cp1250 (Polish Windows encoding — most common in legacy hospital systems),
    then iso-8859-2 as a final fallback.
    """
    for enc in ('utf-8', 'cp1250', 'iso-8859-2'):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode('utf-8', errors='replace')

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QFormLayout, QDialogButtonBox, QMessageBox,
    QAbstractItemView, QFrame, QCheckBox, QFileDialog, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QBrush

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db_config as cfg

# oracledb thick mode can only be initialised once per process
_thick_initialized = False


def _init_thick(lib_dir: str = ""):
    global _thick_initialized
    if _thick_initialized:
        return
    import oracledb
    kwargs = {}
    if lib_dir:
        kwargs["lib_dir"] = lib_dir
    oracledb.init_oracle_client(**kwargs)
    _thick_initialized = True


# ──────────────────────────────────────── Worker thread ──────────────────────

class _Worker(QThread):
    """Runs Oracle queries off the main thread."""
    connected = pyqtSignal(bool, str)          # success, message
    results_ready = pyqtSignal(list)           # list of (gidk_paczki, r_obiektu, status, dt_gener, dt_wyslania, tresc)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._conn = None
        self._task = None   # ('connect', hospital) | ('search', id_zlec)

    # ── public API called from main thread ───────────────────────────────────

    def connect(self, hospital: cfg.HospitalDB):
        self._task = ('connect', hospital)
        if not self.isRunning():
            self.start()

    def search(self, value: str, mode: str = 'zlecenie'):
        # mode: 'zlecenie' | 'paczka'
        self._task = ('search', value, mode)
        if not self.isRunning():
            self.start()

    def disconnect_db(self):
        # Wait for any running query to finish before closing the connection
        if self.isRunning():
            self.wait(3000)
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    # ── QThread.run ───────────────────────────────────────────────────────────

    def run(self):
        task = self._task
        if task is None:
            return

        if task[0] == 'connect':
            self._do_connect(task[1])
        elif task[0] == 'search':
            self._do_search(task[1], task[2])

    def _do_connect(self, h: cfg.HospitalDB):
        try:
            import oracledb
            if h.thick_mode:
                _init_thick(h.instant_client_dir)
            self._conn = oracledb.connect(
                user=h.user,
                password=h.password,
                dsn=f"{h.host}:{h.port}/{h.service}",
            )
            mode = "thick" if h.thick_mode else "thin"
            self.connected.emit(True, f"Połączono z {h.name} [{mode}] ({h.host}:{h.port}/{h.service})")
        except Exception as e:
            self._conn = None
            self.connected.emit(False, _sanitize_oracle_error(e))

    def _do_search(self, value: str, mode: str):
        if not self._conn:
            self.error.emit("Brak aktywnego połączenia z bazą danych.")
            return
        try:
            if mode == 'paczka':
                sql = """
                    SELECT p.gidk_paczki,
                           (SELECT o2.r_obiektu FROM wymd_paczka_obiekt o2
                            WHERE o2.gidk_paczki = p.gidk_paczki AND ROWNUM = 1) AS r_obiektu,
                           p.status, p.dt_gener, p.dt_wyslania, p.tresc
                    FROM wymd_paczka p
                    WHERE p.gidk_paczki = :val
                    ORDER BY p.dt_gener DESC
                """
            else:
                sql = """
                    SELECT p.gidk_paczki, o.r_obiektu, p.status, p.dt_gener, p.dt_wyslania, p.tresc
                    FROM wymd_paczka p
                    INNER JOIN wymd_paczka_obiekt o ON o.gidk_paczki = p.gidk_paczki
                    WHERE o.id_obiektu = :val
                    ORDER BY p.dt_gener DESC
                """
            cur = self._conn.cursor()
            try:
                cur.execute(sql, val=value.strip())
                raw_rows = cur.fetchall()
            finally:
                cur.close()
            rows = []
            for gidk, r_obj, status, dt_gen, dt_wys, tresc in raw_rows:
                if tresc is not None and hasattr(tresc, 'read'):
                    tresc = tresc.read()
                rows.append((gidk, r_obj, status, dt_gen, dt_wys, tresc))
            self.results_ready.emit(rows)
        except Exception as e:
            self._conn = None
            self.error.emit(f"Błąd zapytania: {_sanitize_oracle_error(e)}")


# ──────────────────────────────────────── Hospital dialog ─────────────────────

class HospitalDialog(QDialog):
    def __init__(self, parent=None, hospital: cfg.HospitalDB = None):
        super().__init__(parent)
        self.setWindowTitle("Szpital — ustawienia bazy" if hospital is None else "Edycja szpitala")
        self.setMinimumWidth(380)
        self._build_ui(hospital)

    def _build_ui(self, h: cfg.HospitalDB):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        def _le(text="", ph=""):
            w = QLineEdit(text)
            w.setPlaceholderText(ph)
            return w

        self._name = _le(h.name if h else "", "np. Szpital Miejski")
        self._host = _le(h.host if h else "", "np. 192.168.1.10")
        self._port = _le(str(h.port) if h else "1521", "1521")
        self._service = _le(h.service if h else "", "np. ORCL")
        self._user = _le(h.user if h else "", "login")
        self._pass = _le(h.password if h else "", "hasło")
        self._pass.setEchoMode(QLineEdit.EchoMode.Password)

        self._thick = QCheckBox("Thick mode (Oracle Instant Client)")
        self._thick.setChecked(h.thick_mode if h else False)
        self._thick.setToolTip(
            "Wymagany gdy serwer używa starszego systemu haseł (błąd DPY-3015).\n"
            "Wymaga zainstalowanego Oracle Instant Client."
        )
        self._thick.toggled.connect(self._on_thick_toggled)

        ic_row = QHBoxLayout()
        self._ic_dir = _le(h.instant_client_dir if h else "", "opcjonalnie — ścieżka do Instant Client")
        self._ic_dir.setEnabled(h.thick_mode if h else False)
        self._ic_btn = QPushButton("…")
        self._ic_btn.setFixedWidth(30)
        self._ic_btn.setEnabled(h.thick_mode if h else False)
        self._ic_btn.clicked.connect(self._browse_ic)
        ic_row.addWidget(self._ic_dir)
        ic_row.addWidget(self._ic_btn)

        form.addRow("Nazwa szpitala:", self._name)
        form.addRow("Host / IP:", self._host)
        form.addRow("Port:", self._port)
        form.addRow("Service name:", self._service)
        form.addRow("Użytkownik:", self._user)
        form.addRow("Hasło:", self._pass)
        form.addRow("", self._thick)
        form.addRow("Instant Client dir:", ic_row)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_thick_toggled(self, checked: bool):
        self._ic_dir.setEnabled(checked)
        self._ic_btn.setEnabled(checked)

    def _browse_ic(self):
        d = QFileDialog.getExistingDirectory(self, "Wybierz katalog Oracle Instant Client")
        if d:
            self._ic_dir.setText(d)

    def _validate(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Brak nazwy", "Podaj nazwę szpitala.")
            return
        if not self._host.text().strip():
            QMessageBox.warning(self, "Brak hosta", "Podaj host / IP bazy danych.")
            return
        try:
            int(self._port.text())
        except ValueError:
            QMessageBox.warning(self, "Zły port", "Port musi być liczbą całkowitą.")
            return
        self.accept()

    def get_hospital(self) -> cfg.HospitalDB:
        return cfg.HospitalDB(
            name=self._name.text().strip(),
            host=self._host.text().strip(),
            port=int(self._port.text()),
            service=self._service.text().strip(),
            user=self._user.text().strip(),
            password=self._pass.text(),
            thick_mode=self._thick.isChecked(),
            instant_client_dir=self._ic_dir.text().strip(),
        )


# ──────────────────────────────────────── DB Panel ───────────────────────────

class DbPanel(QWidget):
    """Full Oracle DB panel — hospital selector + search + results."""

    # Emitted when user wants to open an HL7 message in the parser tab
    open_in_parser = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hospitals: list[cfg.HospitalDB] = cfg.load_hospitals()
        self._worker = _Worker()
        self._rows: list = []          # current search result rows
        self._active_hospital: cfg.HospitalDB | None = None

        self._worker.connected.connect(self._on_connected)
        self._worker.results_ready.connect(self._on_results)
        self._worker.error.connect(self._on_error)

        self._build_ui()
        self._refresh_list()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ---- Left: hospital list ----
        left = QWidget()
        left.setMinimumWidth(190)
        left.setMaximumWidth(300)
        left.setStyleSheet("background: #161b22; border-right: 1px solid #21262d;")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 12, 10, 10)
        ll.setSpacing(8)

        lbl = QLabel("Szpitale")
        lbl.setFont(self._bold_font(11))
        lbl.setStyleSheet("color: #c9d1d9; letter-spacing: 0.5px;")
        ll.addWidget(lbl)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                background: #0d1117; border: 1px solid #30363d;
                border-radius: 6px; padding: 2px; color: #c9d1d9;
            }
            QListWidget::item { padding: 8px 10px; border-radius: 4px; }
            QListWidget::item:selected { background: #1f6feb; color: #fff; }
            QListWidget::item:hover:!selected { background: #21262d; }
        """)
        self._list.currentRowChanged.connect(self._on_hospital_changed)
        ll.addWidget(self._list)

        # hospital action buttons
        btn_add = self._mk_btn("＋  Dodaj", self._add_hospital)
        btn_add.setStyleSheet(
            "QPushButton { background: #1a2a3a; color: #58a6ff; border: 1px solid #1f4a70;"
            " border-radius: 5px; padding: 6px 10px; }"
            "QPushButton:hover { background: #1f6feb; color: #fff; }"
        )
        ll.addWidget(btn_add)

        row2 = QHBoxLayout()
        self._btn_edit = self._mk_btn("Edytuj", self._edit_hospital)
        self._btn_del = self._mk_btn("Usuń", self._delete_hospital)
        for b in (self._btn_edit, self._btn_del):
            b.setStyleSheet(
                "QPushButton { background: #21262d; color: #8b949e; border: 1px solid #30363d;"
                " border-radius: 5px; padding: 5px 8px; }"
                "QPushButton:hover { background: #30363d; color: #c9d1d9; }"
                "QPushButton:disabled { color: #444; border-color: #222; }"
            )
            b.setEnabled(False)
            row2.addWidget(b)
        ll.addLayout(row2)

        conn_row = QHBoxLayout()
        self._btn_connect = QPushButton("⚡  Połącz")
        self._btn_connect.setEnabled(False)
        self._btn_connect.setStyleSheet(
            "QPushButton { background: #1a3a2a; color: #3fb950; border: 1px solid #1f5a30;"
            " border-radius: 5px; padding: 6px 10px; font-weight: bold; }"
            "QPushButton:hover { background: #238636; color: #fff; }"
            "QPushButton:disabled { color: #444; border-color: #222; background: #161b22; }"
        )
        self._btn_connect.clicked.connect(self._connect_db)
        conn_row.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("✕")
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.setFixedWidth(32)
        self._btn_disconnect.setToolTip("Rozłącz od bazy")
        self._btn_disconnect.setStyleSheet(
            "QPushButton { background: #3a1a1a; color: #f85149; border: 1px solid #5a1f1f;"
            " border-radius: 5px; padding: 6px; font-weight: bold; }"
            "QPushButton:hover { background: #da3633; color: #fff; }"
            "QPushButton:disabled { color: #444; border-color: #222; background: #161b22; }"
        )
        self._btn_disconnect.clicked.connect(self._disconnect_db)
        conn_row.addWidget(self._btn_disconnect)
        ll.addLayout(conn_row)

        self._conn_status = QLabel("Nie połączono")
        self._conn_status.setStyleSheet("color: #8b949e; font-size: 10px;")
        self._conn_status.setWordWrap(True)
        ll.addWidget(self._conn_status)

        splitter.addWidget(left)

        # ---- Right: search + results ----
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(10)

        # Search row
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self._search_mode = QComboBox()
        self._search_mode.addItem("ID zlecenia", "zlecenie")
        self._search_mode.addItem("ID paczki", "paczka")
        self._search_mode.setFixedWidth(120)
        self._search_mode.setStyleSheet(
            "QComboBox { background: #21262d; border: 1px solid #30363d; border-radius: 5px;"
            " padding: 6px 10px; color: #c9d1d9; }"
            "QComboBox:focus { border-color: #1f6feb; }"
            "QComboBox::drop-down { border: none; width: 20px; }"
            "QComboBox QAbstractItemView { background: #21262d; color: #c9d1d9;"
            " selection-background-color: #1f6feb; border: 1px solid #30363d; }"
        )
        self._search_mode.currentIndexChanged.connect(self._on_mode_changed)

        self._id_edit = QLineEdit()
        self._id_edit.setMaxLength(200)
        self._id_edit.setPlaceholderText("wpisz ID zlecenia…")
        self._id_edit.setStyleSheet(
            "QLineEdit { background: #0d1117; border: 1px solid #30363d; border-radius: 5px;"
            " padding: 6px 10px; color: #c9d1d9; }"
            "QLineEdit:focus { border-color: #1f6feb; }"
        )
        self._id_edit.returnPressed.connect(self._search)

        self._btn_search = QPushButton("Szukaj ▶")
        self._btn_search.setEnabled(False)
        self._btn_search.setFixedWidth(100)
        self._btn_search.setStyleSheet(
            "QPushButton { background: #0078d7; color: #fff; border-radius: 5px;"
            " padding: 6px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #1a8fe0; }"
            "QPushButton:disabled { background: #21262d; color: #555; }"
        )
        self._btn_search.clicked.connect(self._search)

        search_row.addWidget(self._search_mode)
        search_row.addWidget(self._id_edit, 1)
        search_row.addWidget(self._btn_search)
        rl.addLayout(search_row)

        # Results label
        self._results_lbl = QLabel("Wyniki:")
        self._results_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        rl.addWidget(self._results_lbl)

        # Results table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["ID paczki", "R obiektu", "Status", "Data generowania", "Data wysłania"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setFont(QFont("Consolas", 10))
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.setStyleSheet("QTableWidget { border: 1px solid #30363d; border-radius: 5px; }")
        self._table.itemDoubleClicked.connect(self._open_selected)
        rl.addWidget(self._table, 1)

        # Bottom row: open in parser
        bottom_row = QHBoxLayout()
        self._btn_open = QPushButton("Otwórz w parserze  ▶")
        self._btn_open.setEnabled(False)
        self._btn_open.setStyleSheet(
            "QPushButton { background: #1a3a4a; color: #58a6ff; border: 1px solid #1f4a70;"
            " border-radius: 5px; padding: 7px 16px; font-weight: bold; }"
            "QPushButton:hover { background: #1f6feb; color: #fff; }"
            "QPushButton:disabled { background: #161b22; color: #444; border-color: #222; }"
        )
        self._btn_open.clicked.connect(self._open_selected)
        self._search_status = QLabel("")
        self._search_status.setStyleSheet("color: #8b949e; font-size: 11px;")
        bottom_row.addWidget(self._btn_open)
        bottom_row.addWidget(self._search_status)
        bottom_row.addStretch()
        rl.addLayout(bottom_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 700])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _mk_btn(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _bold_font(self, size: int = 10) -> QFont:
        f = QFont()
        f.setBold(True)
        f.setPointSize(size)
        return f

    def _refresh_list(self):
        row = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for h in self._hospitals:
            self._list.addItem(h.name)
        self._list.blockSignals(False)
        # restore selection
        if 0 <= row < self._list.count():
            self._list.setCurrentRow(row)
        elif self._list.count() > 0:
            self._list.setCurrentRow(0)
        self._update_buttons()

    def _update_buttons(self):
        has = self._list.currentRow() >= 0 and bool(self._hospitals)
        self._btn_edit.setEnabled(has)
        self._btn_del.setEnabled(has)
        self._btn_connect.setEnabled(has)

    def _current_hospital(self) -> cfg.HospitalDB | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._hospitals):
            return self._hospitals[row]
        return None

    # ── Hospital CRUD ─────────────────────────────────────────────────────────

    def _on_hospital_changed(self, _row: int):
        self._update_buttons()
        h = self._current_hospital()
        if h is not self._active_hospital:
            self._worker.disconnect_db()
            self._active_hospital = None
            self._conn_status.setText("Nie połączono")
            self._conn_status.setStyleSheet("color: #8b949e; font-size: 10px;")
            self._btn_search.setEnabled(False)
            self._btn_disconnect.setEnabled(False)

    def _add_hospital(self):
        dlg = HospitalDialog(self)
        if dlg.exec():
            self._hospitals.append(dlg.get_hospital())
            cfg.save_hospitals(self._hospitals)
            self._refresh_list()
            self._list.setCurrentRow(len(self._hospitals) - 1)

    def _edit_hospital(self):
        h = self._current_hospital()
        if not h:
            return
        dlg = HospitalDialog(self, h)
        if dlg.exec():
            row = self._list.currentRow()
            self._hospitals[row] = dlg.get_hospital()
            cfg.save_hospitals(self._hospitals)
            self._refresh_list()
            self._list.setCurrentRow(row)

    def _delete_hospital(self):
        h = self._current_hospital()
        if not h:
            return
        ans = QMessageBox.question(
            self, "Usuń szpital",
            f"Usunąć '{h.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            row = self._list.currentRow()
            self._hospitals.pop(row)
            cfg.save_hospitals(self._hospitals)
            self._worker.disconnect_db()
            self._active_hospital = None
            self._conn_status.setText("Nie połączono")
            self._btn_search.setEnabled(False)
            self._btn_disconnect.setEnabled(False)
            self._refresh_list()

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect_db(self):
        h = self._current_hospital()
        if not h:
            return
        self._conn_status.setText("Łączenie…")
        self._conn_status.setStyleSheet("color: #e3b341; font-size: 10px;")
        self._btn_connect.setEnabled(False)
        self._worker.disconnect_db()
        self._active_hospital = h
        self._worker.connect(h)

    def _disconnect_db(self):
        self._worker.disconnect_db()
        self._active_hospital = None
        self._conn_status.setText("Rozłączono")
        self._conn_status.setStyleSheet("color: #8b949e; font-size: 10px;")
        self._btn_search.setEnabled(False)
        self._btn_disconnect.setEnabled(False)
        # Results stay visible intentionally

    @pyqtSlot(bool, str)
    def _on_connected(self, ok: bool, msg: str):
        self._btn_connect.setEnabled(True)
        if ok:
            self._conn_status.setText(f"✓ {msg}")
            self._conn_status.setStyleSheet("color: #3fb950; font-size: 10px;")
            self._btn_search.setEnabled(True)
            self._btn_disconnect.setEnabled(True)
        else:
            self._conn_status.setText(f"✗ {msg}")
            self._conn_status.setStyleSheet("color: #f85149; font-size: 10px;")
            self._btn_search.setEnabled(False)
            self._btn_disconnect.setEnabled(False)
            self._active_hospital = None

    # ── Search ────────────────────────────────────────────────────────────────

    def _on_mode_changed(self, _idx: int):
        mode = self._search_mode.currentData()
        self._id_edit.setPlaceholderText(
            "wpisz ID paczki…" if mode == 'paczka' else "wpisz ID zlecenia…"
        )
        self._id_edit.clear()

    def _search(self):
        value = self._id_edit.text().strip()
        mode = self._search_mode.currentData()
        label = "ID paczki" if mode == 'paczka' else "ID zlecenia"
        if not value:
            self._set_search_status(f"Wpisz {label}.", error=True)
            return
        self._set_search_status("Szukam…")
        self._btn_search.setEnabled(False)
        self._table.setRowCount(0)
        self._btn_open.setEnabled(False)
        self._rows = []
        self._worker.search(value, mode)

    @pyqtSlot(list)
    def _on_results(self, rows: list):
        self._btn_search.setEnabled(True)
        self._rows = rows
        self._table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            gidk, r_obj, status, dt_gen, dt_wys, _tresc = row
            items = [
                QTableWidgetItem(str(gidk)),
                QTableWidgetItem(str(r_obj) if r_obj else "—"),
                QTableWidgetItem(str(status) if status else "—"),
                QTableWidgetItem(str(dt_gen) if dt_gen else "—"),
                QTableWidgetItem(str(dt_wys) if dt_wys else "—"),
            ]
            for col, it in enumerate(items):
                it.setForeground(QBrush(QColor("#c9d1d9")))
                self._table.setItem(i, col, it)

        if rows:
            self._set_search_status(
                f"Znaleziono {len(rows)} paczkę" if len(rows) == 1
                else f"Znaleziono {len(rows)} paczki/paczek."
            )
            self._table.selectRow(0)
            self._btn_open.setEnabled(True)
        else:
            self._set_search_status("Brak wyników dla podanego ID.", error=True)

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self._btn_search.setEnabled(self._worker.is_connected)
        self._set_search_status(msg, error=True)
        if not self._worker.is_connected:
            self._conn_status.setText("✗ Połączenie utracone")
            self._conn_status.setStyleSheet("color: #f85149; font-size: 10px;")

    def _set_search_status(self, text: str, error: bool = False):
        color = "#f85149" if error else "#3fb950"
        self._search_status.setText(f'<span style="color:{color};">{text}</span>')
        self._search_status.setTextFormat(Qt.TextFormat.RichText)

    # ── Open in parser ────────────────────────────────────────────────────────

    def _open_selected(self, _item=None):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        _gidk, _r_obj, _status, _dt_gen, _dt_wys, tresc = self._rows[row]
        if tresc:
            raw = tresc if isinstance(tresc, str) else tresc.read()
            # Try to fix cp1250 bytes misread as latin-1 by Oracle driver
            raw = _fix_encoding(raw)
            # Decode URL-encoding (%0D = \r, %C4%99 = ę, etc.)
            raw = unquote(raw)
            # Normalize all possible line endings to \r (HL7 standard)
            raw = raw.replace('\r\n', '\r').replace('\n', '\r')
            self.open_in_parser.emit(raw)
        else:
            QMessageBox.information(self, "Pusta treść", "Wybrana paczka nie zawiera treści HL7.")
