"""Неинтерактивная проверка native imports в той же политике сборки."""

import sys

from bs4 import BeautifulSoup
from lxml import etree
from PySide6.QtWidgets import QApplication, QWidget

from app.version import __version__
from app.ui.theme import apply_theme


def main() -> int:
    app = QApplication([])
    apply_theme(app)
    widget = QWidget()
    parsed = BeautifulSoup("<p>ok</p>", "lxml")
    if parsed.p.get_text() != "ok" or etree.LXML_VERSION is None:
        return 1
    print(f"frozen-smoke-ok {__version__}")
    widget.deleteLater()
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
