import re

import numpy as np
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLayout, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import db, theme


def fmt_time(sec, ms=True):
    if sec is None:
        return "–"
    m, s = divmod(max(sec, 0), 60)
    return f"{int(m)}:{s:06.3f}" if ms else f"{int(m)}:{int(s):02d}"


# ------------------------------------------------------------------ waveform
class Waveform(QWidget):
    seek = Signal(float)  # 0..1

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(84)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.peaks = None
        self.progress = 0.0
        self.hover = None
        self.loading = False
        self.duration = None
        self._cache = (None, None)

    def set_peaks(self, peaks, duration=None):
        if peaks is not None and len(peaks):
            peaks = peaks / max(float(peaks.max()), 0.3)  # affichage normalisé (×3 max)
        self.peaks, self.duration, self.loading = peaks, duration, False
        self._cache = (None, None)
        self.update()

    def set_loading(self, duration=None):
        self.peaks, self.duration, self.loading, self.progress = None, duration, True, 0.0
        self.update()

    def set_progress(self, f):
        if abs(f - self.progress) > 1e-4:
            self.progress = f
            self.update()

    def _columns(self, n):
        key = (id(self.peaks), n)
        if self._cache[0] == key:
            return self._cache[1]
        p = self.peaks
        L = len(p)
        if n >= L:
            cols = np.interp(np.linspace(0, L - 1, n), np.arange(L), p)
        else:
            idx = (np.arange(L) * n) // L
            cols = np.maximum.reduceat(p, np.flatnonzero(np.r_[True, idx[1:] != idx[:-1]]))
        self._cache = (key, cols)
        return cols

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        if self.peaks is None:
            p.setPen(QColor(theme.BORDER))
            p.drawLine(0, int(mid), w, int(mid))
            if self.loading:
                p.setPen(QColor(theme.DIM))
                p.drawText(self.rect(), Qt.AlignCenter, "Analyse…")
            return
        step = 3
        n = max(w // step, 1)
        cols = self._columns(n)
        played = self.progress * w
        p.setPen(Qt.NoPen)
        wave, acc = QColor(theme.WAVE), QColor(theme.ACCENT)
        if self.hover is not None:
            hov = QColor(theme.WAVE).lighter(150)
        for i, v in enumerate(cols):
            x = i * step
            bh = max(v * (h - 6), 1.0)
            if x < played:
                p.setBrush(acc)
            elif self.hover is not None and x < self.hover:
                p.setBrush(hov)
            else:
                p.setBrush(wave)
            p.drawRoundedRect(QRectF(x, mid - bh / 2, 2, bh), 1, 1)
        if self.progress > 0:
            p.setBrush(QColor(theme.TEXT))
            p.drawRect(QRectF(played - 0.5, 0, 1.2, h))
        if self.hover is not None and self.duration:
            t = fmt_time(self.hover / w * self.duration)
            p.setPen(QColor(theme.TEXT))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(t) + 10
            x = min(self.hover + 6, w - tw)
            p.fillRect(QRectF(x, 2, tw, 18), QColor(theme.SURFACE2))
            p.drawText(QRectF(x, 2, tw, 18), Qt.AlignCenter, t)

    def mouseMoveEvent(self, e):
        self.hover = e.position().x()
        self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.peaks is not None:
            self.seek.emit(min(max(e.position().x() / max(self.width(), 1), 0), 1))


# ------------------------------------------------------------------ tag search
class Chip(QFrame):
    removed = Signal(object)

    def __init__(self, term, neg):
        super().__init__()
        self.setObjectName("chip")
        self.setProperty("neg", neg)
        self.term, self.neg = term, neg
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 3, 4, 3)
        lay.setSpacing(2)
        lay.addWidget(QLabel(("− " if neg else "") + term))
        x = QPushButton("×")
        x.setObjectName("chipX")
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(x)


class TagSearch(QFrame):
    """Search box with tags. Every tag (and every word typed) must match: AND."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("searchBox")
        self.setFixedHeight(42)
        self.chips = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(6)
        ic = QLabel()
        ic.setPixmap(theme.icon("search", theme.MUTED, 16).pixmap(16, 16))
        lay.addWidget(ic)
        self.chip_lay = QHBoxLayout()
        self.chip_lay.setSpacing(5)
        lay.addLayout(self.chip_lay)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Rechercher…   Entrée = ajouter un tag  ·  -mot = exclure")
        self.edit.textChanged.connect(lambda: self._timer.start())
        self.edit.returnPressed.connect(self.commit_text)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit, 1)
        self.clear_btn = QPushButton("×")
        self.clear_btn.setObjectName("chipX")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear)
        self.clear_btn.hide()
        lay.addWidget(self.clear_btn)
        self._timer = QTimer(self, singleShot=True, interval=140)
        self._timer.timeout.connect(self._emit)

    def eventFilter(self, obj, ev):
        if obj is self.edit:
            if ev.type() == ev.Type.KeyPress:
                if ev.key() == Qt.Key_Backspace and not self.edit.text() and self.chips:
                    self.remove_chip(self.chips[-1]); return True
                if ev.text() in (",", ";"):
                    self.commit_text(); return True
            elif ev.type() in (ev.Type.FocusIn, ev.Type.FocusOut):
                self.setProperty("focus", ev.type() == ev.Type.FocusIn)
                self.style().unpolish(self); self.style().polish(self)
        return super().eventFilter(obj, ev)

    def commit_text(self):
        terms = db.parse_terms(self.edit.text())
        if not terms:
            return
        self.edit.blockSignals(True)
        self.edit.clear()
        self.edit.blockSignals(False)
        for t, n in terms:
            if any(c.term.lower() == t.lower() and c.neg == n for c in self.chips):
                continue
            c = Chip(t, n)
            c.removed.connect(self.remove_chip)
            self.chips.append(c)
            self.chip_lay.addWidget(c)
        self._emit()

    def add_tag(self, term):
        self.edit.setText(f'"{term}"' if " " in term else term)
        self.commit_text()

    def remove_chip(self, c):
        self.chips.remove(c)
        c.deleteLater()
        self._emit()

    def clear(self):
        for c in list(self.chips):
            c.deleteLater()
        self.chips.clear()
        self.edit.blockSignals(True)
        self.edit.clear()
        self.edit.blockSignals(False)
        self._emit()

    def terms(self):
        return [(c.term, c.neg) for c in self.chips] + db.parse_terms(self.edit.text())

    def _emit(self):
        self.clear_btn.setVisible(bool(self.chips or self.edit.text()))
        self.changed.emit()


# ------------------------------------------------------------------ segmented
class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, items):
        super().__init__()
        self.setObjectName("seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        for i, (key, label) in enumerate(items):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("key", key)
            b.setChecked(i == 0)
            self.group.addButton(b)
            lay.addWidget(b)
        self.group.buttonClicked.connect(lambda b: self.changed.emit(b.property("key")))


# ------------------------------------------------------------------ flow layout
class FlowLayout(QLayout):
    """Dispose les widgets en lignes qui passent à la ligne (pour les mots-clés)."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items, self._sp = [], spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, it):
        self._items.append(it)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._do(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, r, test):
        x, y, lh = r.x(), r.y(), 0
        for it in self._items:
            sh = it.sizeHint()
            if x > r.x() and x + sh.width() > r.right() + 1:
                x, y, lh = r.x(), y + lh + self._sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sh))
            x += sh.width() + self._sp
            lh = max(lh, sh.height())
        return y + lh - r.y()

    def clear(self):
        while self._items:
            w = self._items.pop().widget()
            if w:
                w.deleteLater()


# ------------------------------------------------------------------ detail panel
def _wrap_path(p):
    """Autorise le retour à la ligne après les séparateurs d'un long chemin."""
    return re.sub(r"([\\/_])", "\\1\u200b", p or "")


class DetailPanel(QFrame):
    tag_clicked = Signal(str)
    closed = Signal()

    FIELDS = (("cat", "Catégorie"), ("sub", "Sous-catégorie"), ("catid", "CatID"), ("lib", "Bibliothèque"),
              ("src", "Source"), ("dur", "Durée"), ("ch", "Canaux"), ("sr", "Fréquence"),
              ("bits", "Résolution"), ("fmt", "Format"), ("size", "Taille"))

    def __init__(self):
        super().__init__()
        self.setObjectName("detail")
        self.setMinimumWidth(240)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(sc)
        body = QWidget(objectName="detailBody")
        sc.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(22, 16, 22, 22)
        v.setSpacing(0)

        head = QHBoxLayout()
        head.addWidget(QLabel("INFOS", objectName="section"))
        head.addStretch()
        x = QPushButton("×", objectName="chipX")
        x.setToolTip("Masquer le panneau (Ctrl+I)")
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(self.closed.emit)
        head.addWidget(x)
        v.addLayout(head)
        v.addSpacing(10)

        self.title = self._label("detailTitle")
        v.addWidget(self.title)
        v.addSpacing(8)
        self.desc = self._label("detailDesc")
        v.addWidget(self.desc)

        v.addSpacing(20)
        self.kw_head = QLabel("MOTS-CLÉS", objectName="section")
        v.addWidget(self.kw_head)
        v.addSpacing(8)
        self.kw_box = QWidget()
        self.kw_flow = FlowLayout(self.kw_box, 5)
        v.addWidget(self.kw_box)

        v.addSpacing(20)
        v.addWidget(QLabel("DÉTAILS", objectName="section"))
        v.addSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        self.vals = {}
        for i, (k, lab) in enumerate(self.FIELDS):
            l = QLabel(lab, objectName="fieldLabel")
            l.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            val = self._label("fieldValue")
            grid.addWidget(l, i, 0)
            grid.addWidget(val, i, 1)
            self.vals[k] = (l, val)
        v.addLayout(grid)

        v.addSpacing(20)
        fh = QHBoxLayout()
        fh.addWidget(QLabel("FICHIER", objectName="section"))
        fh.addStretch()
        self.copy_btn = QPushButton("Copier le chemin", objectName="link")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        fh.addWidget(self.copy_btn)
        v.addLayout(fh)
        v.addSpacing(8)
        self.file = self._label("fieldValue", select=False)
        v.addWidget(self.file)
        v.addSpacing(4)
        self.path = self._label("pathValue", select=False)
        v.addWidget(self.path)
        v.addStretch()
        self._path = ""
        self.show_sound(None)

    def _label(self, name, select=True):
        l = QLabel(objectName=name)
        l.setWordWrap(True)
        l.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        if select:
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return l

    def _copy(self):
        if self._path:
            QApplication.clipboard().setText(self._path)
            self.copy_btn.setText("Copié ✓")
            QTimer.singleShot(1200, lambda: self.copy_btn.setText("Copier le chemin"))

    def show_sound(self, d):
        """d : dict (name, desc, keywords, cat, sub, catid, lib, src, dur, ch, sr, bits, fmt, size, file, path) ou None."""
        self.kw_flow.clear()
        if not d:
            self.title.setText("Aucun son sélectionné")
            self.desc.setText("Sélectionnez un son pour voir sa description et ses métadonnées.")
            self.kw_head.hide(); self.kw_box.hide()
            for l, val in self.vals.values():
                l.hide(); val.hide()
            self.file.setText(""); self.path.setText(""); self.copy_btn.hide()
            self._path = ""
            return
        self.title.setText(d["name"])
        self.desc.setText(d["desc"] or "Pas de description.")
        self.desc.setProperty("empty", not d["desc"])
        self.desc.style().unpolish(self.desc); self.desc.style().polish(self.desc)
        kws = [k.strip() for k in re.split(r"[,;]" if re.search(r"[,;]", d["keywords"] or "") else r"\s+",
                                           d["keywords"] or "") if k.strip()]
        seen = set()
        for k in kws:
            if k.lower() in seen:
                continue
            seen.add(k.lower())
            b = QPushButton(k, objectName="kw")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(f"Ajouter « {k} » à la recherche")
            b.clicked.connect(lambda _=False, k=k: self.tag_clicked.emit(k))
            self.kw_flow.addWidget(b)
        self.kw_head.setVisible(bool(seen)); self.kw_box.setVisible(bool(seen))
        for k, (l, val) in self.vals.items():
            txt = d.get(k) or ""
            val.setText(txt)
            l.setVisible(bool(txt)); val.setVisible(bool(txt))
        self.file.setText(_wrap_path(d["file"]))
        self.path.setText(_wrap_path(d["path"]))
        self._path = d["path"]
        self.copy_btn.show()
