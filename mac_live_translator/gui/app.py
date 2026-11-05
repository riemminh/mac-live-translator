"""PySide6 application entrypoint."""

from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from mac_live_translator.gui.window import Window


def main() -> None:
    """Initialize and run the PySide6 bilingual desktop application."""
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

