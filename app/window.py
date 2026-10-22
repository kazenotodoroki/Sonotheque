import glob
import os
import subprocess
import sys

from PySide6.QtCore import (QAbstractTableModel, QMimeData, QModelIndex, QSettings, QSize,
                            QStandardPaths, Qt, QThread, QThreadPool, QTimer, QUrl)
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QSlider, QSplitter, QStyledItemDelegate, QStackedWidget, QTableView,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import db, reaper_bridge, theme
from .scanner import ExportJob, ImportJob, PeakJob, PeakSignals, ScanJob, WavesJob
from .widgets import DetailPanel, Segmented, TagSearch, Waveform, fmt_time

IS_WIN = sys.platform.startswith("win")
INDEX_NAME = "Sonotheque.sonolib"

# en-tête, clé de tri, index dans la ligne, largeur par défaut
COLS = [
    ("NOM", "name", 1, 300),
    ("DESCRIPTION", "description", 2, 260),
    ("CATÉGORIE", "category", 3, 104),
    ("SOUS-CATÉGORIE", "subcategory", 4, 134),
    ("BIBLIOTHÈQUE", "library", 5, 118),
    ("DURÉE", "duration", 6, 84),
    ("CANAUX", "channels", 7, 72),
    ("FRÉQ.", "samplerate", 8, 80),
    ("BITS", "bits", 9, 48),
    ("FORMAT", "format", 10, 70),
]
(R_ID, R_NAME, R_DESC, R_CAT, R_SUB, R_LIB, R_DUR, R_CH, R_SR, R_BITS, R_FMT, R_PATH, R_KW, R_FILE,
 R_SIZE, R_CATID, R_SRC, R_REL) = range(18)
C_NAME, C_DESC = 0, 1


def ch_label(n):
    return {None: "–", 1: "Mono", 2: "Stéréo"}.get(n, f"{n} canaux")


def pretty(s):
    """'ANIMALS' -> 'Animals' (les catégories UCS sont en majuscules)."""
    return s.title() if s and s.isupper() else (s or "")


def sr_label(sr):
    return f"{sr / 1000:g} kHz" if sr else "–"


def size_label(n):
    if not n:
        return ""
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or u == "Go":
            return f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024


def nfmt(n):
    return f"{n:,}".replace(",", " ")


class RowDelegate(QStyledItemDelegate):
    """Une ligne sélectionnée garde la couleur de son texte (sinon Windows applique la couleur
    « texte surligné » du thème, sombre, prévue pour le fond orange des champs de saisie)."""

    def initStyleOption(self, opt, idx):
        super().initStyleOption(opt, idx)
        fg = idx.data(Qt.ForegroundRole)
        c = fg if isinstance(fg, QColor) else QColor(theme.TEXT)
        for grp in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            opt.palette.setColor(grp, QPalette.HighlightedText, c)
            opt.palette.setColor(grp, QPalette.Text, c)


class SoundModel(QAbstractTableModel):
    """Ne garde que la liste des id ; les lignes sont lues par pages de 200 (tient 500 000+ sons)."""
    PAGE = 200

    def __init__(self, con):
        super().__init__()
        self.con, self.ids, self.cache = con, [], {}
        self.mono_color = QColor(theme.ACCENT)
        self.muted = QColor(theme.MUTED)
        self.text = QColor(theme.TEXT)
        self.bold = QFont()
        self.bold.setWeight(QFont.DemiBold)

    def set_ids(self, ids):
        self.beginResetModel()
        self.ids, self.cache = ids, {}
        self.endResetModel()

    def row(self, i):
        p = i // self.PAGE
        page = self.cache.get(p)
        if page is None:
            chunk = self.ids[p * self.PAGE:(p + 1) * self.PAGE]
            m = {r[R_ID]: r for r in db.fetch_rows(self.con, chunk)}
            page = [m.get(x) for x in chunk]
            if len(self.cache) > 400:
                self.cache.clear()
            self.cache[p] = page
        return page[i - p * self.PAGE]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ids)

    def columnCount(self, parent=QModelIndex()):
        return len(COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return COLS[s][0]
        if o == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)

    def data(self, idx, role=Qt.DisplayRole):
        if role not in (Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole):
            return None
        r = self.row(idx.row())
        if r is None:
            return None
        key = COLS[idx.column()][1]
        if role == Qt.DisplayRole:
            v = r[COLS[idx.column()][2]]
            if key == "duration":
                return fmt_time(v)
            if key == "channels":
                return ch_label(v).replace(" canaux", " ch")
            if key == "samplerate":
                return sr_label(v)
            if key in ("category", "subcategory"):
                return pretty(v)
            return v or ""
        if role == Qt.ForegroundRole:
            if key == "channels" and r[R_CH] == 1:
                return self.mono_color
            return self.text if key == "name" else self.muted
        if role == Qt.FontRole and key == "name":
            return self.bold
        return None

    def flags(self, idx):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def supportedDragActions(self):
        return Qt.CopyAction

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, idxs):
        rows = sorted({i.row() for i in idxs})
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(self.row(r)[R_PATH]) for r in rows if self.row(r)])
        return m


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sonothèque")
        self.setWindowIcon(theme.app_icon())
        self.settings = QSettings()
        data_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "library.db")
        self.con = db.connect(self.db_path)

        self.lib_filter = None
        self.cat_filter = (None, None)
        self.ch_filter = None
        self.sort_key, self.sort_desc = "name", False
        self.current = None
        self.job, self.job_thread, self.jobs = None, None, []
        self.pool = QThreadPool.globalInstance()
        self.peak_signals = PeakSignals()
        self.peak_signals.done.connect(self._peaks_ready)
        self._pending_reaper = None

        self._build()
        self._build_player()
        self._shortcuts()
        self._restore()

        self._refresh_timer = QTimer(self, singleShot=True, interval=800)
        self._refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_all()
        if self.settings.value("scan_on_start", True, bool):
            QTimer.singleShot(400, lambda: self.scan())  # vérification incrémentale au démarrage

    # ================================================================== UI
    def _build(self):
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---- barre latérale
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(256)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(6)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(theme.icon("logo", size=20).pixmap(20, 20))
        brand.addWidget(logo)
        brand.addWidget(QLabel("Sonothèque", objectName="brand"))
        brand.addStretch()
        self.menu_btn = self._ghost("settings", "Réglages")
        self.menu_btn.clicked.connect(self._settings_menu)
        brand.addWidget(self.menu_btn)
        sv.addLayout(brand)
        sv.addSpacing(18)

        row = QHBoxLayout()
        row.addWidget(QLabel("BIBLIOTHÈQUES", objectName="section"))
        row.addStretch()
        add = self._ghost("plus", "Ajouter une bibliothèque (dossier)")
        add.clicked.connect(self.add_library)
        row.addWidget(add)
        sv.addLayout(row)
        self.lib_list = QListWidget()
        self.lib_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lib_list.customContextMenuRequested.connect(self._lib_menu)
        self.lib_list.currentItemChanged.connect(self._lib_changed)
        self.lib_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sv.addWidget(self.lib_list)
        sv.addSpacing(10)

        sv.addWidget(QLabel("CATÉGORIES", objectName="section"))
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderHidden(True)
        self.cat_tree.setColumnCount(2)
        self.cat_tree.setIndentation(14)
        self.cat_tree.setRootIsDecorated(False)
        self.cat_tree.header().setStretchLastSection(False)
        self.cat_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cat_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.cat_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_tree.currentItemChanged.connect(self._cat_changed)
        self.cat_tree.itemClicked.connect(lambda it, _c: it.setExpanded(not it.isExpanded()) if it.childCount() else None)
        sv.addWidget(self.cat_tree, 1)

        jr = QHBoxLayout()
        self.scan_label = QLabel("", objectName="dim")
        jr.addWidget(self.scan_label, 1)
        self.cancel_btn = QPushButton("×", objectName="chipX")
        self.cancel_btn.setToolTip("Arrêter la tâche en cours")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_job)
        jr.addWidget(self.cancel_btn)
        sv.addLayout(jr)
        self.scan_bar = QProgressBar()
        self.scan_bar.setTextVisible(False)
        sv.addWidget(self.scan_bar)
        self._show_job(False)
        h.addWidget(side)

        # ---- zone principale
        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(22, 16, 22, 12)
        top.setSpacing(12)
        self.search = TagSearch()
        self.search.changed.connect(self.run_search)
        self.search.edit.installEventFilter(self)
        top.addWidget(self.search, 1)
        self.seg = Segmented([(None, "Tous"), ("mono", "Mono"), ("stereo", "Stéréo"), ("multi", "Multi")])
        self.seg.changed.connect(self._ch_changed)
        top.addWidget(self.seg)
        self.count = QLabel("", objectName="count")
        self.count.setMinimumWidth(96)
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.count)
        self.panel_btn = self._ghost("panel", "Afficher / masquer le panneau d'infos  (Ctrl+I)")
        self.panel_btn.setCheckable(True)
        self.panel_btn.setFixedSize(30, 30)
        self.panel_btn.toggled.connect(self._toggle_detail)
        top.addWidget(self.panel_btn)
        mv.addLayout(top)

        self.stack = QStackedWidget()
        # état vide
        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch()
        t = QLabel("Aucune bibliothèque")
        t.setStyleSheet("font-size: 20px; font-weight: 600;")
        t.setAlignment(Qt.AlignCenter)
        ev.addWidget(t)
        s = QLabel("Ajoutez le dossier d'une banque de sons (BOOM One, etc.).\n"
                   "Les métadonnées UCS / iXML / BWF sont lues automatiquement.\n"
                   "Si le dossier contient un index Sonothèque, rien n'est rescanné.", objectName="muted")
        s.setAlignment(Qt.AlignCenter)
        ev.addWidget(s)
        ev.addSpacing(14)
        b = QPushButton("  Ajouter un dossier", objectName="primary")
        b.setIcon(theme.icon("plus", "#0b0b0b", 16))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.add_library)
        bl = QHBoxLayout(); bl.addStretch(); bl.addWidget(b); bl.addStretch()
        ev.addLayout(bl)
        ev.addStretch(2)
        self.stack.addWidget(empty)

        # tableau
        self.model = SoundModel(self.con)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(RowDelegate(self.table))
        pal = self.table.palette()
        pal.setColor(QPalette.HighlightedText, QColor(theme.TEXT))
        self.table.setPalette(pal)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.setDefaultDropAction(Qt.CopyAction)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        self.table.doubleClicked.connect(lambda _: self.play(restart=True))
        self.table.installEventFilter(self)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionsMovable(True)
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(0, Qt.AscendingOrder)
        hh.sectionClicked.connect(self._sort_clicked)
        hh.setStretchLastSection(False)
        hh.setContextMenuPolicy(Qt.CustomContextMenu)
        hh.customContextMenuRequested.connect(self._header_menu)
        for i, c in enumerate(COLS):
            hh.resizeSection(i, c[3])
        for c in (C_DESC, 8, 9):  # dans le panneau de droite ; réactivables (clic droit sur l'en-tête)
            hh.setSectionHidden(c, True)
        self.table.selectionModel().currentRowChanged.connect(self._row_changed)
        tw = QWidget()
        tl = QVBoxLayout(tw)
        tl.setContentsMargins(12, 0, 6, 0)
        tl.addWidget(self.table)

        self.detail = DetailPanel()
        self.detail.tag_clicked.connect(self.search.add_tag)
        self.detail.closed.connect(lambda: self.panel_btn.setChecked(False))
        self.split = QSplitter(Qt.Horizontal, objectName="mainSplit")
        self.split.setHandleWidth(5)
        self.split.setChildrenCollapsible(False)
        self.split.addWidget(tw)
        self.split.addWidget(self.detail)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setSizes([900, 360])
        self.split.splitterMoved.connect(lambda *_: QTimer.singleShot(0, self._fit_columns))
        self.stack.addWidget(self.split)
        mv.addWidget(self.stack, 1)

        self.player_frame = QFrame(objectName="player")
        mv.addWidget(self.player_frame)
        h.addWidget(main, 1)

    def _ghost(self, ic, tip):
        b = QPushButton(objectName="ghost")
        b.setIcon(theme.icon(ic, theme.MUTED, 16))
        b.setIconSize(QSize(16, 16))
        b.setFixedSize(26, 26)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _build_player(self):
        v = QVBoxLayout(self.player_frame)
        v.setContentsMargins(22, 14, 22, 12)
        v.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.play_btn = QPushButton(objectName="play")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.setIconSize(QSize(18, 18))
        self.play_btn.setIcon(theme.icon("play", "#0b0b0b"))
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setToolTip("Lecture / pause  (Espace)")
        self.play_btn.clicked.connect(lambda: self.toggle_play())
        row.addWidget(self.play_btn)
        info = QVBoxLayout()
        info.setSpacing(1)
        self.track_name = QLabel("Aucun son sélectionné", objectName="trackName")
        self.track_meta = QLabel("", objectName="muted")
        info.addWidget(self.track_name)
        info.addWidget(self.track_meta)
        row.addLayout(info, 1)

        self.toast = QLabel("", objectName="toast")
        row.addWidget(self.toast)
        self._toast_timer = QTimer(self, singleShot=True, interval=3500)
        self._toast_timer.timeout.connect(lambda: self.toast.setText(""))
        self.auto_btn = QPushButton("Lecture auto", objectName="toggle")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setChecked(self.settings.value("autoplay", True, bool))
        self.auto_btn.setToolTip("Lire automatiquement le son sélectionné")
        self.auto_btn.toggled.connect(lambda b: self.settings.setValue("autoplay", b))
        self.auto_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.auto_btn)
        vol_ic = QLabel()
        vol_ic.setPixmap(theme.icon("volume", theme.MUTED, 16).pixmap(16, 16))
        row.addWidget(vol_ic)
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 1000)  # pas fins
        self.vol.setFixedWidth(90)
        self.vol.setValue(int(float(self.settings.value("volume", 80)) * 10))
        row.addWidget(self.vol)
        row.addSpacing(8)
        self.reaper_btn = QPushButton("  Reaper")
        self.reaper_btn.setIcon(theme.icon("reaper", theme.TEXT, 16))
        self.reaper_btn.setToolTip("Insérer dans Reaper, au curseur, sur la piste sélectionnée  (Ctrl+R)\n"
                                   "Astuce : vous pouvez aussi glisser-déposer les lignes dans Reaper.")
        self.reaper_btn.clicked.connect(self.send_to_reaper)
        self.reaper_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.reaper_btn)
        self.exp_btn = QPushButton("  Explorateur")
        self.exp_btn.setIcon(theme.icon("folder", theme.TEXT, 16))
        self.exp_btn.setToolTip("Afficher dans l'explorateur Windows  (Ctrl+E)")
        self.exp_btn.clicked.connect(self.show_in_explorer)
        self.exp_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.exp_btn)
        v.addLayout(row)

        self.wave = Waveform()
        self.wave.seek.connect(self._seek)
        v.addWidget(self.wave)
        tr = QHBoxLayout()
        self.t_pos = QLabel("0:00.000", objectName="time")
        self.t_dur = QLabel("", objectName="time")
        tr.addWidget(self.t_pos)
        tr.addStretch()
        tr.addWidget(self.t_dur)
        v.addLayout(tr)

        self.audio = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)
        # Volume lissé : la valeur réelle rejoint la cible par petits pas (évite les craquements)
        self._vol_target = self._vol_now = (self.vol.value() / 1000) ** 2
        self.audio.setVolume(self._vol_now)
        self._vol_timer = QTimer(self, interval=5)
        self._vol_timer.timeout.connect(self._vol_step)
        self.vol.valueChanged.connect(self._set_volume)
        self.vol.sliderReleased.connect(lambda: self.settings.setValue("volume", self.vol.value() / 10))
        self.player.playbackStateChanged.connect(self._play_state)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.tick = QTimer(self, interval=16)
        self.tick.timeout.connect(self._update_pos)
        self._enable_actions(False)

    def _shortcuts(self):
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.search.edit.setFocus(), self.search.edit.selectAll()))
        QShortcut(QKeySequence("Ctrl+R"), self, self.send_to_reaper)
        QShortcut(QKeySequence("Ctrl+E"), self, self.show_in_explorer)
        QShortcut(QKeySequence("Ctrl+O"), self, self.add_library)
        QShortcut(QKeySequence("Ctrl+I"), self, self.panel_btn.toggle)

    def notify(self, text):
        self.toast.setText(text)
        self._toast_timer.start()

    # ================================================================== colonnes / panneau
    def _fit_columns(self):
        """La colonne Description (si affichée), sinon Nom, occupe la place restante."""
        hh = self.table.horizontalHeader()
        fill = C_DESC if not hh.isSectionHidden(C_DESC) else C_NAME
        others = sum(hh.sectionSize(i) for i in range(len(COLS)) if i != fill and not hh.isSectionHidden(i))
        hh.resizeSection(fill, max(180, self.table.viewport().width() - others))

    def _header_menu(self, pos):
        hh = self.table.horizontalHeader()
        m = QMenu(self)
        for i, c in enumerate(COLS):
            if i == C_NAME:
                continue
            a = m.addAction(c[0].capitalize())
            a.setCheckable(True)
            a.setChecked(not hh.isSectionHidden(i))
            a.toggled.connect(lambda on, i=i: (hh.setSectionHidden(i, not on), self._fit_columns()))
        m.exec(hh.mapToGlobal(pos))

    def _toggle_detail(self, on):
        self.detail.setVisible(on)
        self.settings.setValue("detail", on)
        QTimer.singleShot(0, self._fit_columns)

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "table", None) and ev.type() == ev.Type.Resize:
            QTimer.singleShot(0, self._fit_columns)
        if ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if obj is self.table:
                if k == Qt.Key_Space:
                    self.toggle_play(); return True
                if k in (Qt.Key_Return, Qt.Key_Enter):
                    self.play(restart=True); return True
                if k == Qt.Key_Left and self.current:
                    self._nudge(-1); return True
                if k == Qt.Key_Right and self.current:
                    self._nudge(1); return True
            elif obj is self.search.edit:
                if k == Qt.Key_Down and self.model.ids:
                    self.table.setFocus()
                    if not self.table.currentIndex().isValid():
                        self.table.selectRow(0)
                    return True
                if k == Qt.Key_Escape:
                    self.search.clear(); return True
        return super().eventFilter(obj, ev)

    # ================================================================== données
    def refresh_all(self):
        self.refresh_libraries()
        self.refresh_categories()
        self.run_search()

    def refresh_libraries(self):
        libs = db.libraries(self.con)
        self.lib_list.blockSignals(True)
        self.lib_list.clear()
        total = sum(l[3] for l in libs)
        items = [(None, "Toutes", total, "")] + [(l[0], l[1], l[3], l[2]) for l in libs]
        sel = None
        for lid, name, n, path in items:
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, lid)
            tip = path or "Toutes les bibliothèques"
            if path and not os.path.isdir(path):
                tip += "\n(dossier introuvable — disque débranché ?)"
            it.setToolTip(tip)
            self.lib_list.addItem(it)
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(8, 0, 8, 0)
            hl.addStretch()
            c = QLabel(nfmt(n), objectName="dim")
            hl.addWidget(c)
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.lib_list.setItemWidget(it, w)
            if lid == self.lib_filter:
                sel = it
        if sel is None:
            self.lib_filter = None
            sel = self.lib_list.item(0)
        self.lib_list.setCurrentItem(sel)
        self.lib_list.setFixedHeight(min(len(items), 8) * 31 + 6)
        self.lib_list.blockSignals(False)
        self.stack.setCurrentIndex(0 if not libs else 1)

    def refresh_categories(self):
        rows = db.category_tree(self.con, self.lib_filter)
        self.cat_tree.blockSignals(True)
        self.cat_tree.clear()
        top = QTreeWidgetItem(["Toutes", ""])
        top.setData(0, Qt.UserRole, (None, None))
        self.cat_tree.addTopLevelItem(top)
        cats, total = {}, 0
        for cat, sub, n in rows:
            total += n
            if cat not in cats:
                it = QTreeWidgetItem([pretty(cat) or "(Sans catégorie)", ""])
                it.setData(0, Qt.UserRole, (cat, None))
                it.setData(1, Qt.UserRole, 0)
                it.setToolTip(0, cat or "Sans catégorie")
                self.cat_tree.addTopLevelItem(it)
                cats[cat] = it
            it = cats[cat]
            it.setData(1, Qt.UserRole, it.data(1, Qt.UserRole) + n)
            if sub:
                ch = QTreeWidgetItem([pretty(sub), nfmt(n)])
                ch.setData(0, Qt.UserRole, (cat, sub))
                ch.setForeground(1, QColor(theme.DIM))
                it.addChild(ch)
        top.setText(1, nfmt(total))
        top.setForeground(1, QColor(theme.DIM))
        sel = top
        for cat, it in cats.items():
            it.setText(1, nfmt(it.data(1, Qt.UserRole)))
            it.setForeground(1, QColor(theme.DIM))
            if self.cat_filter[0] == cat:
                sel = it
                if self.cat_filter[1] is not None:
                    it.setExpanded(True)
                    for i in range(it.childCount()):
                        if it.child(i).data(0, Qt.UserRole)[1] == self.cat_filter[1]:
                            sel = it.child(i)
        if sel is top:
            self.cat_filter = (None, None)
        self.cat_tree.setCurrentItem(sel)
        self.cat_tree.blockSignals(False)

    def run_search(self):
        cat, sub = self.cat_filter
        ids = db.search_ids(self.con, self.search.terms(), self.lib_filter,
                            cat if cat is not None else None,
                            (sub or "") if cat is not None and sub is not None else None,
                            self.ch_filter, self.sort_key, self.sort_desc)
        keep = self.current[R_ID] if self.current else None
        self._suppress = True
        self.model.set_ids(ids)
        n = len(ids)
        self.count.setText(f"{nfmt(n)} son{'s' if n > 1 else ''}")
        if keep is not None:
            try:
                i = ids.index(keep)
                self.table.selectRow(i)
                self.table.scrollTo(self.model.index(i, 0))
            except ValueError:
                pass
        self._suppress = False

    def _lib_changed(self, it, _prev):
        if it is None:
            return
        self.lib_filter = it.data(Qt.UserRole)
        self.refresh_categories()
        self.run_search()

    def _cat_changed(self, it, _prev):
        if it is None:
            return
        self.cat_filter = it.data(0, Qt.UserRole)
        self.run_search()

    def _ch_changed(self, key):
        self.ch_filter = key
        self.run_search()

    def _sort_clicked(self, col):
        key = COLS[col][1]
        if key == self.sort_key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, False
        self.table.horizontalHeader().setSortIndicator(col, Qt.DescendingOrder if self.sort_desc else Qt.AscendingOrder)
        self.run_search()

    # ================================================================== bibliothèques
    def _lib(self, lid):
        return self.con.execute("SELECT name, path FROM libraries WHERE id=?", (lid,)).fetchone()

    def _create_library(self, path, default_name):
        name, ok = QInputDialog.getText(self, "Nom de la bibliothèque", "Nom :", text=default_name)
        if not ok:
            return None
        try:
            cur = self.con.execute("INSERT INTO libraries(name,path) VALUES (?,?)", (name.strip() or path, path))
            self.con.commit()
        except Exception:
            QMessageBox.information(self, "Sonothèque", "Ce dossier est déjà dans vos bibliothèques.")
            return None
        self.lib_filter = cur.lastrowid
        self.refresh_all()
        return cur.lastrowid

    def add_library(self):
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier de la bibliothèque")
        if not path:
            return
        path = os.path.normpath(path)
        found = self._find_index(path)
        if found:
            idx, meta = found
            r = QMessageBox.question(
                self, "Index trouvé",
                f"Ce dossier contient un index Sonothèque :\n\n"
                f"   {meta.get('name', '')} — {nfmt(int(meta.get('count', 0)))} sons, "
                f"{nfmt(int(meta.get('waves', 0)))} formes d'onde\n   exporté le {meta.get('exported', '?')}\n\n"
                "L'utiliser ? Les sons apparaissent tout de suite, sans relire les fichiers.\n"
                "(Seuls les fichiers ajoutés ou modifiés depuis seront analysés.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                lid = self._create_library(path, meta.get("name") or os.path.basename(path))
                if lid:
                    self._import(lid, idx, path, meta.get("name", ""))
                return
        lid = self._create_library(path, os.path.basename(path) or path)
        if lid:
            self.scan([lid])

    def _find_index(self, folder):
        cands = [os.path.join(folder, INDEX_NAME)] + sorted(glob.glob(os.path.join(glob.escape(folder), "*.sonolib")))
        for c in cands:
            if os.path.isfile(c):
                meta = db.read_index_meta(c)
                if meta:
                    return c, meta
        return None

    def import_index_dialog(self):
        src, _ = QFileDialog.getOpenFileName(self, "Importer un index Sonothèque", "", "Index Sonothèque (*.sonolib)")
        if not src:
            return
        meta = db.read_index_meta(src)
        if not meta:
            QMessageBox.warning(self, "Sonothèque", "Ce fichier n'est pas un index Sonothèque valide.")
            return
        QMessageBox.information(self, "Dossier des sons",
                                f"Index « {meta.get('name')} » : {nfmt(int(meta.get('count', 0)))} sons.\n\n"
                                "Indiquez maintenant où se trouve ce dossier de sons sur CE PC.")
        root = QFileDialog.getExistingDirectory(self, f"Où est « {meta.get('name')} » sur ce PC ?", os.path.dirname(src))
        if not root:
            return
        root = os.path.normpath(root)
        row = self.con.execute("SELECT id, name FROM libraries WHERE path=?", (root,)).fetchone()
        if row:
            lid, name = row
        else:
            lid = self._create_library(root, meta.get("name") or os.path.basename(root))
            name = meta.get("name", "")
            if not lid:
                return
        self._import(lid, src, root, name)

    def _import(self, lid, src, root, name):
        job = ImportJob(self.db_path, lid, src, root, name)

        def done(res):
            if isinstance(res, tuple):
                self.notify(f"Index importé : {nfmt(res[0])} sons, {nfmt(res[1])} formes d'onde")
        self.start_job(job, done)
        self.scan([lid])  # vérifie ensuite les fichiers ajoutés / modifiés (lecture des dates seulement)

    def export_index_dialog(self, lid, ask_path=True):
        name, root = self._lib(lid)
        n, nw, size = db.wave_stats(self.con, lid)
        with_waves = self._ask_waves(n, nw, size, f"Exporter l'index de « {name} »")
        if with_waves is None:
            return
        dest = os.path.join(root, INDEX_NAME)
        if ask_path:
            dest, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'index", dest, "Index Sonothèque (*.sonolib)")
            if not dest:
                return
        self._export(lid, dest, with_waves, name)

    def export_all(self):
        libs = db.libraries(self.con)
        if not libs:
            return
        n = sum(l[3] for l in libs)
        nw = size = 0
        for l in libs:
            _, a, b = db.wave_stats(self.con, l[0])
            nw, size = nw + a, size + b
        with_waves = self._ask_waves(n, nw, size, "Exporter les index de toutes les bibliothèques",
                                     f"Un fichier {INDEX_NAME} sera créé à la racine de chaque bibliothèque.")
        if with_waves is None:
            return
        for lid, name, root, _ in libs:
            if os.path.isdir(root):
                self._export(lid, os.path.join(root, INDEX_NAME), with_waves, name)

    def _ask_waves(self, n, nw, size, title, extra=""):
        box = QMessageBox(self)
        box.setWindowTitle("Exporter")
        box.setText(title)
        info = (f"{nfmt(n)} sons. L'index contient catégories, descriptions, mots-clés et infos techniques ; "
                "sur un autre PC, ajoutez simplement le dossier : aucun rescan.")
        if nw < n:
            info += (f"\n\nFormes d'onde déjà calculées : {nfmt(nw)} / {nfmt(n)}. Pour toutes les inclure, "
                     "lancez d'abord « Calculer les formes d'onde » (clic droit sur la bibliothèque).")
        if extra:
            info += "\n\n" + extra
        box.setInformativeText(info)
        cb = QCheckBox(f"Inclure les formes d'onde ({nfmt(nw)}, ~{size_label(size) or '0 o'})")
        cb.setChecked(nw > 0)
        cb.setEnabled(nw > 0)
        box.setCheckBox(cb)
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.button(QMessageBox.Ok).setText("Exporter")
        box.button(QMessageBox.Cancel).setText("Annuler")
        if box.exec() != QMessageBox.Ok:
            return None
        return cb.isChecked()

    def _export(self, lid, dest, with_waves, name):
        def done(res):
            if isinstance(res, Exception):
                QMessageBox.warning(self, "Export", f"Impossible d'écrire l'index de « {name} » :\n{res}\n\n"
                                    "Le dossier est peut-être en lecture seule : exportez ailleurs "
                                    "(clic droit › Exporter l'index…) et copiez le fichier à côté des sons.")
            elif res:
                self.notify(f"Index de {name} exporté ({nfmt(res[0])} sons)")
        self.start_job(ExportJob(self.db_path, lid, dest, with_waves, name), done)

    def compute_waves(self, lib_ids):
        def done(res):
            if isinstance(res, int):
                self.notify(f"{nfmt(res)} formes d'onde calculées")
        self.start_job(WavesJob(self.db_path, lib_ids), done)

    def _lib_menu(self, pos):
        it = self.lib_list.itemAt(pos)
        if not it or it.data(Qt.UserRole) is None:
            return
        lid = it.data(Qt.UserRole)
        name, path = self._lib(lid)
        n, nw, _ = db.wave_stats(self.con, lid)
        m = QMenu(self)
        m.addAction("Renommer…", lambda: self._rename_lib(lid, name))
        m.addAction("Rescanner", lambda: self.scan([lid]))
        a = m.addAction(f"Calculer les formes d'onde ({nfmt(n - nw)} manquantes)", lambda: self.compute_waves([lid]))
        a.setEnabled(n > nw)
        m.addSeparator()
        m.addAction("Exporter l'index dans le dossier", lambda: self.export_index_dialog(lid, ask_path=False))
        m.addAction("Exporter l'index vers…", lambda: self.export_index_dialog(lid))
        m.addAction("Ouvrir le dossier", lambda: self._open_folder(path))
        m.addSeparator()
        m.addAction("Retirer de la Sonothèque", lambda: self._remove_lib(lid, name))
        m.exec(self.lib_list.mapToGlobal(pos))

    def _rename_lib(self, lid, name):
        new, ok = QInputDialog.getText(self, "Renommer", "Nom :", text=name)
        if ok and new.strip():
            self.con.execute("UPDATE libraries SET name=? WHERE id=?", (new.strip(), lid))
            self.con.commit()
            self.refresh_all()

    def _remove_lib(self, lid, name):
        if self.job:
            QMessageBox.information(self, "Sonothèque", "Attendez la fin de la tâche en cours (ou arrêtez-la).")
            return
        r = QMessageBox.question(self, "Retirer", f"Retirer « {name} » ?\nLes fichiers ne sont pas supprimés du disque.")
        if r == QMessageBox.Yes:
            db.remove_library(self.con, lid)
            self.refresh_all()

    def _settings_menu(self):
        m = QMenu(self)
        m.addAction("Ajouter une bibliothèque…", self.add_library)
        m.addAction("Importer un index (.sonolib)…", self.import_index_dialog)
        m.addAction("Exporter les index de toutes les bibliothèques", self.export_all)
        m.addSeparator()
        m.addAction("Rescanner toutes les bibliothèques", lambda: self.scan())
        ids = [l[0] for l in db.libraries(self.con)]
        if ids:
            m.addAction("Calculer toutes les formes d'onde", lambda: self.compute_waves(ids))
        a = m.addAction("Vérifier les bibliothèques au démarrage")
        a.setCheckable(True)
        a.setChecked(self.settings.value("scan_on_start", True, bool))
        a.toggled.connect(lambda on: self.settings.setValue("scan_on_start", on))
        m.addSeparator()
        rp = self.reaper_path()
        m.addAction("Chemin de Reaper…" + (f"   ({os.path.basename(rp)})" if rp else "   (non trouvé)"),
                    self.choose_reaper)
        res = self.reaper_resource()
        inst = reaper_bridge.is_installed(res)
        m.addAction(("Réinstaller" if inst else "Installer") + " le lien avec Reaper", self.install_bridge)
        m.addAction("Dossier de ressources Reaper…", self.choose_reaper_resource)
        m.addSeparator()
        m.addAction("Raccourcis clavier", self._help)
        m.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def _help(self):
        QMessageBox.information(self, "Raccourcis",
            "Espace\tLecture / pause\nEntrée\tRelire depuis le début\n←  →\tAvancer / reculer d'1 s\n"
            "↑  ↓\tSon précédent / suivant\nCtrl+F\tRechercher\nCtrl+R\tInsérer dans Reaper\n"
            "Ctrl+E\tAfficher dans l'explorateur\nCtrl+I\tPanneau d'infos\nÉchap\tEffacer la recherche\n\n"
            "Recherche : chaque mot doit correspondre (ET).\nEntrée transforme le texte en tag, -mot exclut.\n"
            "Cliquer un mot-clé dans le panneau l'ajoute à la recherche.\n"
            "Clic droit sur l'en-tête du tableau : choisir les colonnes.\n"
            "Glisser-déposer une ligne vers Reaper ou l'explorateur fonctionne aussi.")

    # ================================================================== tâches de fond
    def scan(self, lib_ids=None):
        if not self.con.execute("SELECT 1 FROM libraries LIMIT 1").fetchone():
            return
        self.start_job(ScanJob(self.db_path, lib_ids))

    def start_job(self, job, on_done=None):
        job._on_done = on_done
        self.jobs.append(job)
        if not self.job:
            self._next_job()

    def _next_job(self):
        if not self.jobs:
            self.job = self.job_thread = None
            self._show_job(False)
            return
        self.job = self.jobs.pop(0)
        self.job_thread = QThread(self)
        self.job.moveToThread(self.job_thread)
        self.job_thread.started.connect(self.job.run)
        self.job.progress.connect(self._job_progress)
        self.job.changed.connect(self._refresh_timer.start)  # slot de QTimer → exécuté dans le thread UI
        self.job.finished.connect(self._job_done)
        self.scan_label.setText("…")
        self.scan_bar.setRange(0, 0)
        self._show_job(True)
        self.job_thread.start()

    def _show_job(self, on):
        for w in (self.scan_label, self.scan_bar, self.cancel_btn):
            w.setVisible(on)

    def _job_progress(self, done, total, label):
        if total == 0:
            self.scan_bar.setRange(0, 0)
            self.scan_label.setText(label)
        else:
            self.scan_bar.setRange(0, total)
            self.scan_bar.setValue(done)
            self.scan_label.setText(f"{label} · {nfmt(done)} / {nfmt(total)}")

    def _job_done(self, res):
        job = self.job
        self.job_thread.quit()
        self.job_thread.wait()
        job.deleteLater()
        self.refresh_all()
        if job._on_done:
            job._on_done(res)
        self._next_job()

    def cancel_job(self):
        self.jobs.clear()
        if self.job:
            self.job.cancelled = True
            self.scan_label.setText("Arrêt…")

    # ================================================================== lecture
    def selected_rows(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        out = [self.model.row(r) for r in rows]
        out = [r for r in out if r]
        return out or ([self.current] if self.current else [])

    def _row_changed(self, cur, _prev):
        if not cur.isValid():
            return
        r = self.model.row(cur.row())
        if r is None or (self.current and self.current[R_ID] == r[R_ID]):
            return
        self.current = r
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(r[R_PATH]))
        self.track_name.setText(r[R_NAME])
        meta = [ch_label(r[R_CH]), sr_label(r[R_SR]), (r[R_BITS] + " bits") if r[R_BITS] else "", r[R_FMT],
                " / ".join(pretty(x) for x in (r[R_CAT], r[R_SUB]) if x), r[R_LIB]]
        self.track_meta.setText("   ·   ".join(m for m in meta if m))
        self.t_dur.setText(fmt_time(r[R_DUR]))
        self.t_pos.setText(fmt_time(0))
        self.wave.set_loading(r[R_DUR])
        self.pool.start(PeakJob(self.db_path, r[R_ID], r[R_PATH], r[R_DUR], self.peak_signals))
        self.detail.show_sound({
            "name": r[R_NAME], "desc": r[R_DESC], "keywords": r[R_KW],
            "cat": pretty(r[R_CAT]), "sub": pretty(r[R_SUB]), "catid": r[R_CATID], "lib": r[R_LIB],
            "src": r[R_SRC] if r[R_SRC] != r[R_LIB] else "", "dur": fmt_time(r[R_DUR]),
            "ch": ch_label(r[R_CH]) if r[R_CH] else "", "sr": sr_label(r[R_SR]) if r[R_SR] else "",
            "bits": (r[R_BITS].replace("f", " bits flottant") if "f" in (r[R_BITS] or "") else
                     (r[R_BITS] + " bits" if r[R_BITS] else "")),
            "fmt": r[R_FMT], "size": size_label(r[R_SIZE]), "file": r[R_FILE], "path": r[R_PATH]})
        self._enable_actions(True)
        if self.auto_btn.isChecked() and not getattr(self, "_suppress", False):
            self.player.play()

    def _peaks_ready(self, sid, peaks):
        if self.current and self.current[R_ID] == sid:
            self.wave.set_peaks(peaks, self.current[R_DUR])

    def play(self, restart=False):
        if not self.current:
            return
        if restart:
            self.player.setPosition(0)
        self.player.play()

    def toggle_play(self):
        if not self.current:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _nudge(self, sec):
        self.player.setPosition(max(0, self.player.position() + int(sec * 1000)))

    def _seek(self, frac):
        dur = self.player.duration() or int((self.current[R_DUR] or 0) * 1000)
        self.player.setPosition(int(frac * dur))
        self.player.play()
        self.wave.set_progress(frac)

    def _set_volume(self, v):
        self._vol_target = (v / 1000) ** 2
        if not self.vol.isSliderDown():
            self.settings.setValue("volume", v / 10)
        if not self._vol_timer.isActive():
            self._vol_timer.start()

    def _vol_step(self):
        d = self._vol_target - self._vol_now
        if abs(d) < 0.002:
            self._vol_now = self._vol_target
            self._vol_timer.stop()
        else:
            self._vol_now += max(-0.02, min(0.02, d * 0.25))
        self.audio.setVolume(self._vol_now)

    def _play_state(self, st):
        playing = st == QMediaPlayer.PlayingState
        self.play_btn.setIcon(theme.icon("pause" if playing else "play", "#0b0b0b"))
        if playing:
            self.tick.start()
        else:
            self.tick.stop()
            self._update_pos()

    def _media_status(self, st):
        if st == QMediaPlayer.EndOfMedia:
            self.player.setPosition(0)
            self.wave.set_progress(0)
            self.t_pos.setText(fmt_time(0))

    def _update_pos(self):
        dur = self.player.duration() or int((self.current[R_DUR] or 0) * 1000 if self.current else 0)
        pos = self.player.position()
        if dur:
            self.wave.set_progress(min(pos / dur, 1))
        self.t_pos.setText(fmt_time(pos / 1000))

    def _enable_actions(self, on):
        for b in (self.reaper_btn, self.exp_btn, self.play_btn):
            b.setEnabled(on)

    # ================================================================== Reaper
    def reaper_path(self):
        p = self.settings.value("reaper", "")
        if p and os.path.isfile(p):
            return p
        cands = [r"C:\Program Files\REAPER (x64)\reaper.exe", r"C:\Program Files\REAPER\reaper.exe",
                 r"C:\Program Files (x86)\REAPER\reaper.exe",
                 os.path.expandvars(r"%LOCALAPPDATA%\Programs\REAPER\reaper.exe")]
        for c in cands:
            if os.path.isfile(c):
                return c
        return ""

    def choose_reaper(self):
        p, _ = QFileDialog.getOpenFileName(self, "Où se trouve reaper.exe ?", r"C:\Program Files",
                                           "REAPER (reaper.exe);;Programmes (*.exe)")
        if p:
            self.settings.setValue("reaper", os.path.normpath(p))
        return p

    def reaper_resource(self):
        return self.settings.value("reaper_resource", "") or reaper_bridge.default_resource(self.reaper_path())

    def choose_reaper_resource(self):
        QMessageBox.information(self, "Reaper",
                                "Dans Reaper : Options › Show REAPER resource path in explorer.\n"
                                "Choisissez ensuite ce dossier (celui qui contient reaper.ini).")
        p = QFileDialog.getExistingDirectory(self, "Dossier de ressources de Reaper", self.reaper_resource())
        if p:
            self.settings.setValue("reaper_resource", os.path.normpath(p))

    def install_bridge(self, quiet=False):
        res = self.reaper_resource()
        if not os.path.isdir(res):
            QMessageBox.warning(self, "Reaper", f"Dossier de ressources Reaper introuvable :\n{res}\n\n"
                                "Réglages › Dossier de ressources Reaper…")
            return False
        try:
            reaper_bridge.install(res)
        except OSError as e:
            QMessageBox.warning(self, "Reaper", f"Installation impossible :\n{e}")
            return False
        if not quiet:
            msg = "Lien avec Reaper installé."
            if reaper_bridge.reaper_running() and not reaper_bridge.alive(res):
                msg += "\n\nReaper est ouvert : fermez-le et rouvrez-le une fois pour activer le lien."
            QMessageBox.information(self, "Reaper", msg)
        return True

    def send_to_reaper(self):
        rows = self.selected_rows()
        if not rows:
            return
        paths = [r[R_PATH] for r in rows]
        exe = self.reaper_path()
        res = self.reaper_resource()
        if not reaper_bridge.is_installed(res):
            r = QMessageBox.question(
                self, "Lien avec Reaper",
                "Pour insérer les sons au curseur, sur la piste sélectionnée du projet ouvert, la Sonothèque "
                "installe un petit script dans Reaper (démarré automatiquement avec Reaper).\n\nL'installer ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if r != QMessageBox.Yes or not self.install_bridge(quiet=True):
                return
        if reaper_bridge.alive(res):
            reaper_bridge.send(res, paths)
            self.notify(f"→ Reaper : {len(paths)} son{'s' if len(paths) > 1 else ''}")
            return
        if reaper_bridge.reaper_running():
            QMessageBox.information(self, "Reaper",
                                    "Reaper est ouvert mais le lien n'est pas encore actif.\n"
                                    "Fermez et rouvrez Reaper une fois (le lien démarre ensuite tout seul).")
            return
        exe = exe or self.choose_reaper()
        if not exe:
            return
        reaper_bridge.clear_inbox(res)
        try:
            subprocess.Popen([exe])
        except OSError as e:
            QMessageBox.warning(self, "Reaper", f"Impossible de lancer Reaper :\n{e}")
            return
        self.notify("Ouverture de Reaper…")
        self._pending_reaper = (paths, 0)
        QTimer.singleShot(1000, self._wait_reaper)

    def _wait_reaper(self):
        if not self._pending_reaper:
            return
        paths, tries = self._pending_reaper
        res = self.reaper_resource()
        if reaper_bridge.alive(res):
            QTimer.singleShot(1500, lambda: (reaper_bridge.send(res, paths),
                                             self.notify(f"→ Reaper : {len(paths)} son(s)")))
            self._pending_reaper = None
        elif tries < 60:
            self._pending_reaper = (paths, tries + 1)
            QTimer.singleShot(1000, self._wait_reaper)
        else:
            self._pending_reaper = None
            self.notify("Reaper ne répond pas")

    # ================================================================== explorateur
    def show_in_explorer(self):
        rows = self.selected_rows()
        if not rows:
            return
        p = os.path.normpath(rows[0][R_PATH])
        if IS_WIN:
            subprocess.Popen(f'explorer /select,"{p}"')
        else:
            self._open_folder(os.path.dirname(p))

    def _open_folder(self, path):
        if IS_WIN:
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", path])

    def _row_menu(self, pos):
        if not self.table.indexAt(pos).isValid():
            return
        rows = self.selected_rows()
        m = QMenu(self)
        m.addAction("Lire", lambda: self.play(restart=True))
        m.addAction("Insérer dans Reaper" + (f" ({len(rows)})" if len(rows) > 1 else ""), self.send_to_reaper)
        m.addAction("Afficher dans l'explorateur", self.show_in_explorer)
        m.addSeparator()
        m.addAction("Copier le chemin", lambda: QApplication.clipboard().setText("\n".join(r[R_PATH] for r in rows)))
        r = rows[0]
        if r[R_CAT]:
            m.addAction(f"Ajouter le tag « {pretty(r[R_CAT])} »", lambda: self.search.add_tag(r[R_CAT]))
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ================================================================== état de la fenêtre
    def _restore(self):
        g = self.settings.value("geometry")
        if g:
            self.restoreGeometry(g)
        else:
            self.resize(1480, 880)
        hs = self.settings.value("header2")
        if hs:
            self.table.horizontalHeader().restoreState(hs)
        sp = self.settings.value("split")
        if sp:
            self.split.restoreState(sp)
        on = self.settings.value("detail", True, bool)
        self.panel_btn.setChecked(on)
        self.detail.setVisible(on)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._fit_columns)
        if IS_WIN:  # barre de titre sombre (Windows 10 20H1+ / 11)
            try:
                import ctypes
                hwnd = int(self.winId())
                val = ctypes.c_int(1)
                for attr in (20, 19):
                    if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                        break
                col = ctypes.c_int(0x000A0909)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(col), 4)
            except Exception:
                pass

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("header2", self.table.horizontalHeader().saveState())
        self.settings.setValue("split", self.split.saveState())
        self.jobs.clear()
        if self.job:
            self.job.cancelled = True
            self.job_thread.quit()
            self.job_thread.wait(5000)
        self.player.stop()
        super().closeEvent(e)
