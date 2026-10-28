"""单词/例句朗读：Piper 合成 + QMediaPlayer 播放。"""
from PyQt5.QtCore import QObject
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtCore import QUrl

from core import tts
from core.tasks import run_task


class Speaker(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.player.setVolume(95)
        self._seq = 0

    def speak(self, text, speed=1.0):
        text = (text or "").strip()
        if not text:
            return
        self._seq += 1
        seq = self._seq

        def done(path):
            if seq != self._seq:
                return
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self.player.play()

        run_task(tts.speak, done, on_error=lambda _m: None, on_progress=None, text=text, speed=speed)

    def stop(self):
        self._seq += 1
        self.player.stop()
