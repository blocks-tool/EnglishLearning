"""口语学习助手入口。"""
import sys

from PyQt5.QtWidgets import QApplication

from core.paths import BASE_DIR
from core.ui import apply_theme
from .window import SpeakingWindow


def main():
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    app = QApplication(sys.argv)
    app.setApplicationName("口语学习助手")
    apply_theme(app)
    window = SpeakingWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
