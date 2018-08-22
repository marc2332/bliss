cdef extern from "q_window_system.h" namespace "WindowSystemInterface":
    int sendWindowSystemEvents(int)
    int hasPendingEvents()

class WindowSystemInterface:
    @staticmethod
    def sendWindowSystemEvents(flags):
        return sendWindowSystemEvents(flags)
    @staticmethod
    def hasPendingEvents():
        return hasPendingEvents()
