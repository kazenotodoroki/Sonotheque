from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

BG = "#09090a"
SURFACE = "#101012"
SURFACE2 = "#16161a"
HOVER = "#1b1b20"
BORDER = "#1f1f24"
TEXT = "#ececef"
MUTED = "#8b8b94"
DIM = "#55555d"
ACCENT = "#ff5c39"
WAVE = "#4a4a52"

FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'

QSS = f"""
* {{ font-family: {FONT}; font-size: 13px; color: {TEXT}; outline: 0; }}
QMainWindow, #root {{ background: {BG}; }}
QToolTip {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px 8px; }}

#sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#brand {{ font-size: 15px; font-weight: 600; letter-spacing: 0.3px; }}
#section {{ color: {DIM}; font-size: 11px; font-weight: 600; letter-spacing: 1.2px; }}
#muted {{ color: {MUTED}; }}
#dim {{ color: {DIM}; font-size: 12px; }}
#count {{ color: {MUTED}; font-size: 12px; }}

QListWidget, QTreeWidget {{ background: transparent; border: none; }}
QListWidget::item, QTreeWidget::item {{ padding: 5px 8px; border-radius: 6px; color: {MUTED}; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {HOVER}; color: {TEXT}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {SURFACE2}; color: {TEXT}; }}
QTreeWidget::branch {{ background: transparent; }}

#searchBox {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 10px; }}
#searchBox[focus="true"] {{ border: 1px solid #3a3a42; }}
#searchBox QLineEdit {{ background: transparent; border: none; font-size: 14px; padding: 0; selection-background-color: {ACCENT}; }}
#chip {{ background: #24242a; border-radius: 6px; }}
#chip QLabel {{ font-size: 12.5px; }}
#chip[neg="true"] QLabel {{ color: {MUTED}; text-decoration: line-through; }}
#chipX {{ background: transparent; border: none; color: {MUTED}; font-size: 14px; padding: 0 2px; }}
#chipX:hover {{ color: {TEXT}; }}

#seg {{ background: transparent; border: 1px solid {BORDER}; border-radius: 8px; }}
#seg QPushButton {{ background: transparent; border: none; border-radius: 6px; padding: 5px 11px; color: {MUTED}; font-size: 12.5px; }}
#seg QPushButton:hover {{ color: {TEXT}; }}
#seg QPushButton:checked {{ background: {SURFACE2}; color: {TEXT}; }}

QPushButton {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 12px; }}
QPushButton:hover {{ background: {HOVER}; border-color: #2c2c33; }}
QPushButton:pressed {{ background: #222228; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 4px; }}
QPushButton#ghost:hover {{ color: {TEXT}; background: {HOVER}; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: #0b0b0b; font-weight: 600; }}
QPushButton#primary:hover {{ background: #ff7352; }}
QPushButton#play {{ background: {TEXT}; border: none; border-radius: 20px; }}
QPushButton#play:hover {{ background: #ffffff; }}
QPushButton#toggle {{ background: transparent; color: {MUTED}; border: 1px solid {BORDER}; font-size: 12px; padding: 4px 10px; }}
QPushButton#toggle:checked {{ color: {TEXT}; border-color: #3a3a42; }}

QTableView {{ background: {BG}; border: none; gridline-color: transparent;
    selection-background-color: transparent; alternate-background-color: {BG}; }}
QTableView::item {{ padding: 0 10px; border-bottom: 1px solid #141417; }}
QTableView::item:hover {{ background: #121215; }}
QTableView::item:selected {{ background: #1c1614; }}
QHeaderView {{ background: {BG}; border: none; }}
QHeaderView::section {{ background: {BG}; color: {DIM}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 10px; font-size: 11px; font-weight: 600; letter-spacing: 0.8px; }}
QHeaderView::section:hover {{ color: {MUTED}; }}
QHeaderView::down-arrow, QHeaderView::up-arrow {{ width: 0; height: 0; }}

#player {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
#trackName {{ font-size: 15px; font-weight: 600; }}
#time {{ color: {MUTED}; font-size: 12px; font-family: "Cascadia Mono", "Consolas", monospace; }}

QSlider::groove:horizontal {{ height: 3px; background: #2a2a30; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: {TEXT}; border-radius: 1px; }}
QSlider::handle:horizontal {{ width: 11px; height: 11px; margin: -4px 0; border-radius: 5px; background: {TEXT}; }}

QProgressBar {{ background: #1d1d22; border: none; border-radius: 1px; max-height: 2px; }}
QProgressBar::chunk {{ background: {ACCENT}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2a2a30; border-radius: 3px; min-height: 30px; margin: 2px 3px; }}
QScrollBar::handle:vertical:hover {{ background: #3a3a42; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: #2a2a30; border-radius: 3px; min-width: 30px; margin: 3px 2px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}

QMenu {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 7px 26px 7px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

QDialog, QMessageBox, QInputDialog {{ background: {SURFACE}; }}
QLineEdit {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 8px; }}
QSplitter#mainSplit::handle {{ background: {BG}; }}
QSplitter#mainSplit::handle:hover {{ background: #2a2a30; }}

#detail {{ background: {SURFACE}; border-left: 1px solid {BORDER}; }}
#detail QScrollArea, #detailBody {{ background: {SURFACE}; }}
#detailTitle {{ font-size: 17px; font-weight: 600; }}
#detailDesc {{ font-size: 13.5px; color: #d6d6db; }}
#detailDesc[empty="true"] {{ color: {DIM}; }}
#fieldLabel {{ color: {DIM}; font-size: 12px; }}
#fieldValue {{ color: {TEXT}; font-size: 12.5px; }}
#pathValue {{ color: {MUTED}; font-size: 12px; }}
QPushButton#kw {{ background: #1f1f25; border: 1px solid #26262d; border-radius: 6px; padding: 3px 9px;
    color: #c9c9cf; font-size: 12px; }}
QPushButton#kw:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
QPushButton#link {{ background: transparent; border: none; color: {MUTED}; font-size: 12px; padding: 0; }}
QPushButton#link:hover {{ color: {ACCENT}; }}
QPushButton#ghost:checked {{ color: {TEXT}; background: {HOVER}; }}
#toast {{ color: {ACCENT}; font-size: 12px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #3a3a42; border-radius: 3px; background: {SURFACE2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
"""


def icon(name, color=TEXT, size=18):
    """Small vector icons drawn with QPainter (no external assets needed)."""
    s = size
    pm = QPixmap(s * 3, s * 3)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(3)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    k = s / 18.0
    p.scale(k, k)
    if name == "play":
        path = QPainterPath(QPointF(6, 3.5)); path.lineTo(15, 9); path.lineTo(6, 14.5); path.closeSubpath()
        p.setBrush(c); p.drawPath(path)
    elif name == "pause":
        p.setPen(Qt.NoPen); p.setBrush(c)
        p.drawRoundedRect(QRectF(4.5, 3.5, 3.2, 11), 1, 1); p.drawRoundedRect(QRectF(10.3, 3.5, 3.2, 11), 1, 1)
    elif name == "stop":
        p.setPen(Qt.NoPen); p.setBrush(c); p.drawRoundedRect(QRectF(4.5, 4.5, 9, 9), 1.5, 1.5)
    elif name == "search":
        p.drawEllipse(QRectF(3, 3, 9.5, 9.5)); p.drawLine(QPointF(11.2, 11.2), QPointF(15, 15))
    elif name == "folder":
        path = QPainterPath(QPointF(2.5, 5)); path.lineTo(7, 5); path.lineTo(8.5, 6.5); path.lineTo(15.5, 6.5)
        path.lineTo(15.5, 14); path.lineTo(2.5, 14); path.closeSubpath(); p.drawPath(path)
    elif name == "reaper":
        p.drawEllipse(QRectF(3, 3, 12, 12))
        p.setBrush(c); p.setPen(Qt.NoPen); p.drawEllipse(QRectF(7, 7, 4, 4))
    elif name == "plus":
        p.drawLine(QPointF(9, 4), QPointF(9, 14)); p.drawLine(QPointF(4, 9), QPointF(14, 9))
    elif name == "refresh":
        p.drawArc(QRectF(3.5, 3.5, 11, 11), 60 * 16, 290 * 16)
        p.drawLine(QPointF(12.2, 2.8), QPointF(12.8, 5.6)); p.drawLine(QPointF(12.8, 5.6), QPointF(10, 6.1))
    elif name == "volume":
        path = QPainterPath(QPointF(3, 7)); path.lineTo(6, 7); path.lineTo(9.5, 4); path.lineTo(9.5, 14)
        path.lineTo(6, 11); path.lineTo(3, 11); path.closeSubpath(); p.drawPath(path)
        p.drawArc(QRectF(8, 5.5, 6, 7), -50 * 16, 100 * 16)
    elif name == "settings":
        for y, x in ((5, 11), (9, 6), (13, 12)):
            p.drawLine(QPointF(3, y), QPointF(15, y))
            p.setBrush(QColor(SURFACE)); p.drawEllipse(QPointF(x, y), 1.8, 1.8)
    elif name == "panel":
        p.drawRoundedRect(QRectF(2.5, 3.5, 13, 11), 2, 2); p.drawLine(QPointF(11, 3.5), QPointF(11, 14.5))
    elif name == "close":
        p.drawLine(QPointF(5, 5), QPointF(13, 13)); p.drawLine(QPointF(13, 5), QPointF(5, 13))
    elif name == "logo":
        p.setPen(Qt.NoPen); p.setBrush(QColor(ACCENT))
        for i, h in enumerate((5, 10, 14, 8, 11, 4)):
            p.drawRoundedRect(QRectF(2 + i * 2.5, 9 - h / 2, 1.6, h), 0.8, 0.8)
    p.end()
    return QIcon(pm)


def app_icon():
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0d0d0f"))
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 54, 54)
    p.setBrush(QColor(ACCENT))
    for i, h in enumerate((60, 120, 170, 96, 136, 50)):
        p.drawRoundedRect(QRectF(50 + i * 28, 128 - h / 2, 16, h), 8, 8)
    p.end()
    return QIcon(pm)
