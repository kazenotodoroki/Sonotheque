import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app import theme
from app.window import MainWindow


def main():
    if sys.platform.startswith("win"):
        try:  # icône propre dans la barre des tâches
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sonotheque.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setOrganizationName("Sonotheque")
    app.setApplicationName("Sonotheque")
    app.setStyle("Fusion")
    pal = QPalette()
    for role, c in ((QPalette.Window, theme.SURFACE), (QPalette.Base, theme.BG),
                    (QPalette.AlternateBase, theme.SURFACE), (QPalette.Text, theme.TEXT),
                    (QPalette.WindowText, theme.TEXT), (QPalette.Button, theme.SURFACE2),
                    (QPalette.ButtonText, theme.TEXT), (QPalette.Highlight, theme.ACCENT),
                    (QPalette.HighlightedText, "#0b0b0b"), (QPalette.ToolTipBase, theme.SURFACE2),
                    (QPalette.ToolTipText, theme.TEXT), (QPalette.PlaceholderText, theme.DIM)):
        pal.setColor(role, QColor(c))
    app.setPalette(pal)
    app.setStyleSheet(theme.QSS)
    app.setWindowIcon(theme.app_icon())
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
