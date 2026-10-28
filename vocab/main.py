"""单词本学习助手：Qt 界面入口。"""
import sys

from PyQt5.QtWidgets import QApplication

from core import db_vocab, dictionary
from core.paths import BASE_DIR
from core.ui import apply_theme
from .window import MainWindow


def main():
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    db_vocab.init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("单词本学习助手")
    apply_theme(app)
    if not dictionary.available():
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            None, "离线词典未就绪",
            "未在 data/ 目录找到 ecdict.db，导入单词时将无法自动生成音标和释义。\n"
            "可从 ECDICT 项目下载词典后放入 data/ 目录。")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
