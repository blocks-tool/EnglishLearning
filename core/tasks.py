"""轻量的后台任务封装：耗时操作（TTS 合成、语音评测、字幕识别）放到线程池，
通过 Qt 信号回主线程更新界面。"""
import inspect
import traceback

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class TaskSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, str)


class Task(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            kwargs = dict(self.kwargs)
            try:
                if "progress" in inspect.signature(self.fn).parameters:
                    kwargs["progress"] = self.signals.progress.emit
            except (TypeError, ValueError):
                pass
            result = self.fn(*self.args, **kwargs)
            self._emit(self.signals.finished, result)
        except Exception as exc:  # noqa: BLE001 - 后台任务统一兜底
            traceback.print_exc()
            self._emit(self.signals.failed, str(exc))

    @staticmethod
    def _emit(signal, value):
        """接收方窗口已销毁时静默忽略，避免线程内 RuntimeError 导致进程崩溃。"""
        try:
            signal.emit(value)
        except RuntimeError:
            pass


def run_task(fn, on_done=None, on_error=None, on_progress=None, *args, **kwargs):
    task = Task(fn, *args, **kwargs)
    if on_done:
        task.signals.finished.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    if on_progress:
        task.signals.progress.connect(on_progress)
    QThreadPool.globalInstance().start(task)
    return task
