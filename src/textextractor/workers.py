"""Run blocking work (decoding, OCR) off the UI thread and deliver results on it."""
from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

log = logging.getLogger(__name__)


class _Signals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, object)


class _Task(QRunnable):
    def __init__(self, task_id: int, fn: Callable[[], Any]):
        super().__init__()
        self.setAutoDelete(False)
        self.task_id = task_id
        self._fn = fn
        self.signals = _Signals()

    def run(self) -> None:  # runs on a pool thread
        try:
            result = self._fn()
        except BaseException as e:  # noqa: BLE001 - forwarded to the UI thread
            self.signals.failed.emit(self.task_id, e)
        else:
            self.signals.finished.emit(self.task_id, result)


class TaskManager(QObject):
    """Callbacks always run on the thread that owns this object (the UI thread).
    A cancelled task still finishes in the background, but its result is discarded."""

    def __init__(self, parent: QObject | None = None, max_threads: int = 2):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._next_id = 0
        self._tasks: dict[int, _Task] = {}
        self._callbacks: dict[int, tuple[Callable[[Any], None], Callable[[BaseException], None] | None]] = {}

    def submit(self, fn: Callable[[], Any], on_done: Callable[[Any], None],
               on_error: Callable[[BaseException], None] | None = None) -> int:
        self._next_id += 1
        tid = self._next_id
        task = _Task(tid, fn)
        task.signals.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        task.signals.failed.connect(self._on_failed, Qt.ConnectionType.QueuedConnection)
        self._tasks[tid] = task
        self._callbacks[tid] = (on_done, on_error)
        self._pool.start(task)
        return tid

    def cancel(self, task_id: int | None) -> None:
        if task_id is not None:
            self._callbacks.pop(task_id, None)

    def wait_for_done(self, msecs: int = 5000) -> bool:
        return self._pool.waitForDone(msecs)

    @Slot(int, object)
    def _on_finished(self, tid: int, result: object) -> None:
        self._tasks.pop(tid, None)
        cb = self._callbacks.pop(tid, None)
        if cb:
            try:
                cb[0](result)
            except Exception:  # noqa: BLE001
                log.exception("task callback failed")

    @Slot(int, object)
    def _on_failed(self, tid: int, error: object) -> None:
        self._tasks.pop(tid, None)
        cb = self._callbacks.pop(tid, None)
        if cb and cb[1]:
            try:
                cb[1](error)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                log.exception("task error callback failed")
