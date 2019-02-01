"""A Qt event dispatcher based on the gevent event loop.

Example usage:

    import sys
    from PyQt5.QtWidgets import QApplication
    from qgevent import set_gevent_dispatcher

    if __name__ == '__main__':
        set_gevent_dispatcher()
        app = QApplication(sys.argv)
        sys.exit(app.exec_())

"""

import os
import time

import gevent
import gevent.select

from collections import defaultdict
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QAbstractEventDispatcher, QEventLoop, QTimerEvent, QEvent

import qwindowsystem

__all__ = ["QGeventDispatcher", "set_gevent_dispatcher"]


class QGeventDispatcher(QAbstractEventDispatcher):
    """A Qt event dispatcher based on the gevent event loop.

    It allows for gevent concurrency within a qt application.
    """

    def __init__(self):
        # Parent call
        super(QGeventDispatcher, self).__init__()

        # Pipe for thread-safe communication
        self._read_pipe, self._write_pipe = os.pipe()

        # {obj: {tid: timer_info}} dictionary
        self._timer_infos = defaultdict(dict)
        # {tid: (obj, timer_task)} dictionary
        self._timer_tasks = {}

        # Notifier dictionaries
        self._read_notifiers = {}
        self._write_notifiers = {}
        self._error_notifiers = {}

        # Internal flag
        self._interrupted = False

    # Thread-safe communication

    def wakeUp(self):
        """Wake the event loop up.

        Thread-safe.
        """
        os.write(self._write_pipe, b".")

    def interrupt(self):
        """Interrupt processEvents and wake up the event loop.

        Thread-safe.
        """
        self._interrupted = True
        self.wakeUp()

    # Event management

    def flush(self):
        """Send posted events."""
        QApplication.sendPostedEvents()

    def hasPendingEvents(self):
        """True if the QApplication or the WindowSystemInterface
        has events to process, False otherwise
        """
        return bool(
            qwindowsystem.globalPostedEventsCount()
            or qwindowsystem.windowSystemEventsQueued()
        )

    def processEvents(self, flags):
        """Process QApplication, WindowSystemInterface and socket events."""
        # Reset interrupted flag
        self._interrupted = False

        # Emit awake signal
        self.awake.emit()

        # Send all posted events
        QApplication.sendPostedEvents()

        # Check for interruption
        if self._interrupted:
            return False

        # Manage flags
        exclude_notifiers = flags & QEventLoop.ExcludeSocketNotifiers
        wait_for_more_events = flags & QEventLoop.WaitForMoreEvents

        # Emit about-to-block signal
        if wait_for_more_events:
            self.aboutToBlock.emit()
            timeout = None
        else:
            timeout = 0.

        # Poll the file descriptors
        rlist = [self._read_pipe]
        rlist += [] if exclude_notifiers else list(self._read_notifiers)
        wlist = [] if exclude_notifiers else list(self._write_notifiers)
        elist = [] if exclude_notifiers else list(self._error_notifiers)
        read_events, write_events, error_events = gevent.select.select(
            rlist, wlist, elist, timeout=timeout
        )

        # Flush the thread communication pipe
        if self._read_pipe in read_events:
            read_events.remove(self._read_pipe)
            os.read(self._read_pipe, 2 ** 10)

        # Get all activated notifiers
        all_events = read_events, write_events, error_events
        all_notifiers = (
            self._read_notifiers,
            self._write_notifiers,
            self._error_notifiers,
        )
        notifiers = [
            notifiers[event]
            for events, notifiers in zip(all_events, all_notifiers)
            for event in events
        ]

        # Send all notifier events
        for notifier in notifiers:
            QApplication.sendEvent(notifier, QEvent(QEvent.SockAct))

        # Process window system interface events
        wsi_events = qwindowsystem.sendWindowSystemEvents(flags)

        # Return True if some events have been processed, False otherwise
        return bool(wsi_events or notifiers)

    # Timers

    def registeredTimers(self, obj):
        """Get the timer info for all registered timers for a given object."""
        if obj not in self._timer_infos:
            return []
        return list(self._timer_infos[obj].values())

    def registerTimer(self, tid, interval, ttype, obj):
        """Register a new timer, given a unique tid."""
        self._timer_infos[obj][tid] = self.TimerInfo(tid, interval, ttype)
        self._timer_tasks[tid] = (
            obj,
            gevent.spawn(self._timer_run, interval / 1000., obj, tid),
        )

    def unregisterTimer(self, tid):
        """Unregister the timer corresponding to the given tid."""
        obj, timer_task = self._timer_tasks.pop(tid, (None, None))
        if obj is None:
            return True
        self._timer_infos[obj].pop(tid)
        if not self._timer_infos[obj]:
            self._timer_infos.pop(obj)
        timer_task.kill()
        return True

    def unregisterTimers(self, obj):
        """Unregister all the timers corresponding to the given object."""
        if obj not in self._timer_infos:
            return False
        tids = list(self._timer_infos[obj])
        for tid in tids:
            self.unregisterTimer(tid)
        return True

    def _timer_run(self, interval, obj, tid):
        """Target for the timer background tasks."""
        deadline = time.time()
        while True:
            deadline += interval
            sleep_time = max(0, deadline - time.time())
            # Sleep to the deadline
            if sleep_time < 1e-6:
                gevent.sleep(0)  # idle()
            else:
                gevent.sleep(sleep_time)
            try:
                # Use postEvent to avoid auto cancellation
                QApplication.postEvent(obj, QTimerEvent(tid))
            except RuntimeError:
                # obj is dead, cannot post event
                break

    # Sockets

    def registerSocketNotifier(self, notifier):
        fd = int(notifier.socket())
        types = notifier.Read, notifier.Write, notifier.Exception
        dicts = self._read_notifiers, self._write_notifiers, self._error_notifiers
        # Find the right notifier type
        for ntype, fds_dict in zip(types, dicts):
            if notifier.type() != ntype:
                continue
            # Prevent multiple registration
            if fd in fds_dict:
                raise ValueError(
                    "A notifier for socket {} and type {}"
                    "has already been registered".format(fd, notifier.type())
                )
            # Register the notifier
            fds_dict[fd] = notifier
            return

    def unregisterSocketNotifier(self, notifier):
        types = notifier.Read, notifier.Write, notifier.Exception
        dicts = self._read_notifiers, self._write_notifiers, self._error_notifiers
        # Find the right notifier type
        for ntype, fds_dict in zip(types, dicts):
            if notifier.type() != ntype:
                continue
            # Unregister the notifier
            fds_dict.pop(int(notifier.socket()))
            return


def set_gevent_dispatcher():
    """Set gevent qt event dispatcher."""
    QApplication.setEventDispatcher(QGeventDispatcher())
