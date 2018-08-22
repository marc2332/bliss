import os
import weakref
import gevent
from gevent import sleep, select
from collections import defaultdict, deque
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QAbstractEventDispatcher, QEventLoop, QTimerEvent
from q_gevent_dispatcher import WindowSystemInterface


class QGeventDispatcher(QAbstractEventDispatcher):
    def __init__(self, *args):
        super(QGeventDispatcher, self).__init__(*args)
        self._rp, self._wp = os.pipe()
        self._timers = defaultdict(dict)
        self._timers_task = weakref.WeakValueDictionary()
        self._timer_event = deque()

    def wakeUp(self):
        os.write(self._wp, ".")

    def flush(self):
        QApplication.sendPostedEvents()
        self._timer_event.clear()

    def interrupt(self):
        os.write(self._wp, "|")

    def hasPendingEvents(self):
        return bool(self._timer_event) or WindowSystemInterface.hasPendingEvents()

    def processEvents(self, flags):
        self.awake.emit()
        QApplication.sendPostedEvents()
        include_notifiers = (flags & QEventLoop.ExcludeSocketNotifiers) == 0
        can_wait = flags & QEventLoop.WaitForMoreEvents

        if can_wait:
            self.aboutToBlock.emit()
            timeout = None
        else:
            timeout = 0.

        read_fds = [self._rp]
        write_fds = []
        error_fds = []
        if include_notifiers:  # add socket fds
            pass

        read_event, _, _ = select.select(read_fds, write_fds, error_fds, timeout)

        if self._rp in read_event:
            os.read(self._rp, 8192)  # flush pipe

        has_event = bool(read_event) or bool(self._timer_event)
        while self._timer_event:
            obj, evt = self._timer_event.popleft()
            QApplication.sendEvent(obj, evt)

        return WindowSystemInterface.sendWindowSystemEvents(flags) or has_event

    # Timers

    def registeredTimers(self, obj):
        return self._timers[obj]

    def registerTimer(self, tid, interval, ttype, obj):
        event = QTimerEvent(tid)
        self._timers[obj][tid] = self.TimerInfo(tid, interval, ttype)
        task = gevent.spawn(self._timer_run, interval / 1000., obj, event)
        self._timers_task[tid] = task

    def unregisterTimer(self, tid):
        try:
            return any(timer.pop(tid, None) for timer in self._timers.values())
        finally:
            task = self._timers_task.pop(tid, None)
            if task is not None:
                task.kill()

    def unregisterTimers(self, obj):
        return bool(self._timers.pop(obj))

    def _timer_run(self, interval, obj, event):
        while True:
            sleep(interval)
            self._timer_event.append((obj, event))
            os.write(self._wp, "T")

    # Sockets

    def registerSocketNotifier(self, *args):
        print(args)
        raise NotImplementedError

    def unregisterSocketNotifier(self, *args):
        raise NotImplementedError
