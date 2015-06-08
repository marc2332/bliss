
from bliss.common import log as elog
from bliss.common import event
from gevent import _threading
import gevent.queue
import gevent.event
import gevent
import atexit

SETTINGS_WRITER_THREAD = None
SETTINGS_WRITER_QUEUE = None
SETTINGS_WRITER_WATCHER = None


def wait_settings_writing():
    if SETTINGS_WRITER_QUEUE:
        SETTINGS_WRITER_QUEUE.put((None, None, None, None))
        SETTINGS_WRITER_WATCHER.wait()


def write_settings():
    global SETTINGS_WRITER_WATCHER
    SETTINGS_WRITER_WATCHER.clear()

    try:
        while True:
            axis, setting_name, value, write_flag = SETTINGS_WRITER_QUEUE.get()
            if axis is None:
                break
            event.send(
                axis, "write_setting", axis.config, setting_name, value, write_flag)
    finally:
        SETTINGS_WRITER_WATCHER.set()


class ControllerAxisSettings:

    def __init__(self):
        self.setting_names = ["velocity", "position", "dial_position", "_set_position", "state",
                              "offset", "acceleration", "low_limit", "high_limit"]
        from bliss.common import axis
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "dial_position": float,
            "_set_position": float,
            "state": axis.AxisState,
            "offset": float,
            "low_limit": float,
            "high_limit": float,
            "acceleration": float}
        self.axis_settings_dict = dict()

        from bliss.config import motors as config
        global SETTINGS_WRITER_THREAD
        global SETTINGS_WRITER_QUEUE
        global SETTINGS_WRITER_WATCHER
        if SETTINGS_WRITER_THREAD is None:
            if config.BACKEND == 'xml':
                SETTINGS_WRITER_QUEUE = _threading.Queue()
                SETTINGS_WRITER_WATCHER = _threading.Event()
                SETTINGS_WRITER_WATCHER.set()
                atexit.register(wait_settings_writing)
                if SETTINGS_WRITER_THREAD is None:
                    SETTINGS_WRITER_THREAD = _threading.start_new_thread(
                        write_settings, ())
            else:
                SETTINGS_WRITER_QUEUE = gevent.queue.Queue()
                SETTINGS_WRITER_WATCHER = gevent.event.Event()
                SETTINGS_WRITER_WATCHER.set()
                if SETTINGS_WRITER_THREAD is None:
                    SETTINGS_WRITER_THREAD = gevent.spawn(write_settings)

    def add(self, setting_name, convert_func=str):
        self.setting_names.append(setting_name)
        self.convert_funcs[setting_name] = convert_func

    def load_from_config(self, axis):
        from bliss.config import motors as config
        for setting_name in self.setting_names:
            try:
                # Reads setting from XML file or redis DB.
                setting_value = config.get_axis_setting(axis, setting_name)
            except RuntimeError:
                elog.debug("settings.py : no '%s' in settings." % setting_name)
                return
            if setting_value is None:
                elog.debug("settings.py : '%s' is None (not found?)." % setting_name)
                continue
            elog.debug("settings.py : '%s' is %r" % (setting_name, setting_value))
            self._set_setting(axis, setting_name, setting_value)

    def _settings(self, axis):
        return self.axis_settings_dict.setdefault(
            axis,
            dict(zip(self.setting_names, (None,) * len(self.setting_names))))

    def _set_setting(self, axis, setting_name, value):
        '''
        set settting without event nor writing.
        '''
        settings = self._settings(axis)
        convert_func = self.convert_funcs.get(setting_name)
        if convert_func is not None:
            setting_value = convert_func(value)
        else:
            setting_value = value
        settings[setting_name] = setting_value
        return setting_value

    def set(self, axis, setting_name, value, write=True):
        '''
        *set setting (if updated)
        *send event
        *write
        '''
        old_value = self.get(axis, setting_name)
        if value == old_value:
            return

        setting_value = self._set_setting(axis, setting_name, value)
 
        SETTINGS_WRITER_QUEUE.put((axis, setting_name, setting_value, write))

        event.send(axis, setting_name, setting_value)

    def get(self, axis, setting_name):
        settings = self._settings(axis)
        return settings.get(setting_name)


class AxisSettings:

    def __init__(self, axis):
        self.__axis = axis
        self.__from_channel = dict()

    def set(self, setting_name, value, write=True, from_channel=False):
        self.__from_channel[setting_name]=from_channel
        return self.__axis.controller.axis_settings.set(
            self.__axis, setting_name, value, write)

    def get(self, setting_name):
        return self.__axis.controller.axis_settings.get(
            self.__axis, setting_name)

    def get_from_channel(self, setting_name):
        return self.get(setting_name) if self.__from_channel.get(setting_name) else None

    def load_from_config(self):
        return self.__axis.controller.axis_settings.load_from_config(
            self.__axis)

    def __iter__(self):
        for name in self.__axis.controller.axis_settings.setting_names:
            yield name
