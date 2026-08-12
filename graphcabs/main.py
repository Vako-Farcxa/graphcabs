"""GraphCabs entry point."""

import logging
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from graphcabs.db import init_db
from graphcabs.game import GameEngine
from graphcabs.window import MainWindow

logging.basicConfig(level=logging.INFO)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("GraphCabs")
    init_db()
    engine = GameEngine()
    engine.start_game()
    window = MainWindow(engine)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
