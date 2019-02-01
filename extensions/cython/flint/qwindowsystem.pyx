cdef extern from "q_window_system.h" namespace "WindowSystemInterface":
    int _sendWindowSystemEvents(int)
    int _windowSystemEventsQueued()
    int _globalPostedEventsCount();


def sendWindowSystemEvents(flags):
    return _sendWindowSystemEvents(flags)

def windowSystemEventsQueued():
    return _windowSystemEventsQueued()

def globalPostedEventsCount():
    return _globalPostedEventsCount()
