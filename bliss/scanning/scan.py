# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import enum
import getpass
import gevent
import os
import string
import weakref
import sys
import time
import datetime
import tabulate
import collections
import uuid
from functools import wraps

from bliss import setup_globals, current_session, is_bliss_shell
from bliss.common.event import connect, disconnect
from bliss.common.cleanup import error_cleanup, axis as cleanup_axis, capture_exceptions
from bliss.common.greenlet_utils import KillMask
from bliss.common.plot import (
    get_flint,
    check_flint,
    CurvePlot,
    ImagePlot,
    ScatterPlot,
    McaPlot,
)
from bliss.common.utils import periodic_exec, deep_update
from .scan_meta import get_user_scan_meta
from bliss.common.axis import Axis
from bliss.common.utils import Statistics, Null
from bliss.config.settings import ParametersWardrobe
from bliss.config.settings import pipeline
from bliss.data.node import _get_or_create_node, _create_node, is_zerod
from bliss.data.scan import get_data
from .chain import AcquisitionSlave, AcquisitionMaster, StopChain
from .writer.null import Writer as NullWriter
from .scan_math import peak, cen, com
from . import writer

from louie import saferef


# Globals
current_module = sys.modules[__name__]

# STORE THE CALLBACK FUNCTIONS THAT ARE CALLED DURING A SCAN ON THE EVENTS SCAN_NEW, SCAN_DATA, SCAN_END
# THIS FUNCTIONS ARE EXPECTED TO PRINT INFO ABOUT THE SCAN AT THE CONSOLE LEVEL (see bliss/shell/cli/repl => ScanPrinter )
# USERS CAN OVERRIDE THE DEFAULT TO SPECIFY ITS OWN SCAN INFO DISPLAY
# BY DEFAULT THE CALLBACKS ARE SET TO NULL() TO AVOID UNNECESSARY PRINTS OUTSIDE A SHELL CONTEXT
_SCAN_WATCH_CALLBACKS = {"new": Null(), "data": Null(), "end": Null()}


def set_scan_watch_callbacks(scan_new=None, scan_data=None, scan_end=None):
    if scan_new is None:
        r_scan_new = Null()
    elif not hasattr(scan_new, "__call__"):
        raise TypeError(f"{scan_new} is not callable")
    else:
        r_scan_new = saferef.safe_ref(scan_new)

    if scan_data is None:
        r_scan_data = Null()
    elif not hasattr(scan_data, "__call__"):
        raise TypeError(f"{scan_data} is not callable")
    else:
        r_scan_data = saferef.safe_ref(scan_data)

    if scan_end is None:
        r_scan_end = Null()
    elif not hasattr(scan_end, "__call__"):
        raise TypeError(f"{scan_end} is not callable")
    else:
        r_scan_end = saferef.safe_ref(scan_end)

    _SCAN_WATCH_CALLBACKS.update(
        {"new": r_scan_new, "data": r_scan_data, "end": r_scan_end}
    )


class DataWatchCallback:
    def on_state(self, state):
        """Ask if callback **on_scan_data** will be called during
        **PREPARING** and **STOPPING** state. The return of this
        method will activate/deactivate the calling of the callback
        **on_scan_data** during this stage. By default
        **on_scan_data** will be only called when new data are
        emitted.

        state -- either ScanState.PREPARING or ScanState.STOPPING.

        i.e: return state == ScanState.PREPARING will inform that
        **on_scan_data** will be called during **PREPARING** scan
        state.

        """
        return False

    def on_scan_new(self, scan, scan_info):
        """
        This callback is called when the scan is about to starts
        
        scan -- is the scan object
        scan_info -- is the dict of information about this scan
        """
        pass

    def on_scan_data(self, data_events, nodes, scan_info):
        """
        This callback is called when new data is emitted.

        data_events --  a dict with Acq(Device/Master) as key and a set of signal as values
        nodes -- a dict with Acq(Device/Master) as key and the associated data node as value
        scan_info -- dictionnary which contains the current scan state
        """
        raise NotImplementedError

    def on_scan_end(self, scan_info):
        """
        Called at the end of the scan.
        """
        pass


class StepScanDataWatch(DataWatchCallback):
    """
    This class is an helper to follow data generation by a step scan like:
    an acquisition chain with motor(s) as the top-master.
    This produce event compatible with the ScanListener class (bliss.shell)
    """

    def __init__(self):
        self._last_point_display = 0
        self._channel_name_2_channel = dict()
        self._init_done = False

    def on_scan_new(self, scan, scan_info):

        cb = _SCAN_WATCH_CALLBACKS["new"]()
        if cb is not None:
            cb(scan, scan_info)

    def on_scan_data(self, data_events, nodes, scan_info):

        cb = _SCAN_WATCH_CALLBACKS["data"]()
        if cb is None:
            return

        if self._init_done is False:
            for acq_device_or_channel, data_node in nodes.items():
                if is_zerod(data_node):
                    channel = data_node
                    self._channel_name_2_channel[channel.name] = channel
            self._init_done = True

        min_nb_points = None
        for channels_name, channel in self._channel_name_2_channel.items():
            nb_points = len(channel)
            if min_nb_points is None:
                min_nb_points = nb_points
            elif min_nb_points > nb_points:
                min_nb_points = nb_points

        if min_nb_points is None or self._last_point_display >= min_nb_points:
            return

        for point_nb in range(self._last_point_display, min_nb_points):
            values = {
                ch_name: ch.get(point_nb)
                for ch_name, ch in iter(self._channel_name_2_channel.items())
            }

            cb(scan_info, values)

        self._last_point_display = min_nb_points

    def on_scan_end(self, scan_info):

        cb = _SCAN_WATCH_CALLBACKS["end"]()
        if cb is not None:
            cb(scan_info)


class WatchdogCallback:
    """
    This class is a watchdog for scan class.  It's role is to follow
    if detectors involved in the scan have the right behavior. If not
    the callback may raise an exception.
    All exception will bubble-up except StopIteration which will just stop
    the scan.
    """

    def __init__(self, watchdog_timeout=1.):
        """
        watchdog_timeout -- is the maximum calling frequency of **on_timeout**
        method.
        """
        self.__watchdog_timeout = watchdog_timeout

    @property
    def timeout(self):
        return self.__watchdog_timeout

    def on_timeout(self):
        """
        This method is called when **watchdog_timeout** elapsed it means
        that no data event is received for the time specified by
        **watchdog_timeout**
        """
        pass

    def on_scan_new(self, scan, scan_info):
        """
        Called when scan is starting
        """
        pass

    def on_scan_data(self, data_events, nodes, scan_info):
        """
        Called when new data are emitted by the scan.  This method should
        raise en exception to stop the scan.  All exception will
        bubble-up exception the **StopIteration**.  This one will just
        stop the scan.
        """
        pass

    def on_scan_end(self, scan_info):
        """
        Called at the end of the scan
        """
        pass


class _WatchDogTask(gevent.Greenlet):
    def __init__(self, scan, callback):
        super().__init__()
        self._scan = weakref.proxy(scan, self.stop)
        self._events = gevent.queue.Queue()
        self._data_events = dict()
        self._callback = callback
        self.__watchdog_timer = None
        self._lock = gevent.lock.Semaphore()

    def trigger_data_event(self, sender, signal):
        self._reset_watchdog()
        event_set = self._data_events.setdefault(sender, set())
        event_set.add(signal)
        if not len(self._events):
            self._events.put("Data Event")

    def on_scan_new(self, scan, scan_info):
        self._callback.on_scan_new(scan, scan_info)
        self._reset_watchdog()

    def on_scan_end(self, scan_info):
        self.stop()
        self._callback.on_scan_end(scan_info)

    def stop(self):
        self.clear_queue()
        self._events.put(StopIteration)

    def kill(self):
        super().kill()
        if self.__watchdog_timer is not None:
            self.__watchdog_timer.kill()

    def clear_queue(self):
        while True:
            try:
                self._events.get_nowait()
            except gevent.queue.Empty:
                break

    def _run(self):
        try:
            for ev in self._events:
                if isinstance(ev, BaseException):
                    raise ev
                try:
                    if self._data_events:
                        data_event = self._data_events
                        self._data_events = dict()
                        # disable the watchdog before calling the callback
                        if self.__watchdog_timer is not None:
                            self.__watchdog_timer.kill()
                        with KillMask():
                            with self._lock:
                                self._callback.on_scan_data(
                                    data_event, self._scan.nodes, self._scan.scan_info
                                )
                        # reset watchdog if it wasn't restarted in between
                        if self.__watchdog_timer:
                            self._reset_watchdog()
                        gevent.idle()

                except StopIteration:
                    break
        finally:
            if self.__watchdog_timer is not None:
                self.__watchdog_timer.kill()

    def _reset_watchdog(self):
        if self.__watchdog_timer:
            self.__watchdog_timer.kill()

        if self.ready():
            return

        def loop(timeout):
            while True:
                gevent.sleep(timeout)
                try:
                    with KillMask():
                        with self._lock:
                            self._callback.on_timeout()
                except StopIteration:
                    self.stop()
                    break
                except BaseException as e:
                    self.clear_queue()
                    self._events.put(e)
                    break

        self.__watchdog_timer = gevent.spawn(loop, self._callback.timeout)


class ScanSaving(ParametersWardrobe):
    SLOTS = []
    WRITER_MODULE_PATH = "bliss.scanning.writer"

    def __init__(self, name=None):
        """
        This class hold the saving structure for a session.

        This class generate the *root path* of scans and the *parent* node use
        to publish data.

        The *root path* is generate using *base path* argument as the first part
        and use the *template* argument as the final part.

        The *template* argument is basically a (python) string format use to
        generate the final part of the root_path.

        i.e: a template like "{session}/{date}" will use the session and the date attribute
        of this class.

        Attribute used in this template can also be a function with one argument
        (scan_data) which return a string.

        i.e: date argument can point to this method
             def get_date(scan_data): datetime.datetime.now().strftime("%Y/%m/%d")
             scan_data.add('date',get_date)

        The *parent* node should be use as parameters for the Scan.
        """
        # default and not removable values
        _default_values = {
            "base_path": "/tmp/scans",
            "data_filename": "data",
            "user_name": getpass.getuser(),
            "template": "{session}/",
            "images_path_relative": True,
            "images_path_template": "scan{scan_number}",
            "images_prefix": "{img_acq_device}_",
            "date_format": "%Y%m%d",
            "scan_number_format": "%04d",
            "_writer_module": "hdf5",
        }
        # read only attributes implemented with python properties
        _property_attributes = [
            "session",
            "date",
            "scan_name",
            "scan_number",
            "img_acq_device",
            "writer",
        ]

        super().__init__(
            "scan_saving:%s" % name if name else "scan_saving:%s" % uuid.uuid4().hex,
            default_values=_default_values,
            property_attributes=_property_attributes,
            not_removable=_default_values.keys(),
        )

    def __dir__(self):
        keys = super().__dir__()
        return keys + ["session", "get", "get_path", "get_parent_node", "writer"]

    def __info__(self):
        d = self._get_instance(self.current_instance)
        d["scan_name"] = "scan name"
        d["scan_number"] = "scan number"
        d["img_acq_device"] = "<images_* only> acquisition device name"

        info_str = super()._repr(d)
        info_str += self.get_data_info()

        return info_str

    def get_data_info(self):

        data_config = self.get()
        info_table = list()
        #        import pprint
        #       pprint.pprint(data_config['writer'].data_filename)
        #        pprint.pprint(data_config['writer'].file)
        #        pprint.pprint()
        if isinstance(data_config["writer"], NullWriter):
            info_table.append(("NO SAVING",))
        else:
            data_file = data_config["writer"].filename
            #        data_file = data_config["data_path"]
            if os.path.exists(data_file):
                exists = "exists"
            else:
                exists = "does not exist"
            info_table.append((exists, "filename", data_file))

            data_dir = data_config["root_path"]
            if os.path.exists(data_dir):
                exists = "exists"
            else:
                exists = "does not exist"
            info_table.append((exists, "root_path", data_dir))

        return tabulate.tabulate(tuple(info_table))

    @property
    def scan_name(self):
        return "{scan_name}"

    @property
    def scan_number(self):
        return "{scan_number}"

    @property
    def img_acq_device(self):
        return "{img_acq_device}"

    @property
    def session(self):
        """ This give the name of the current session or 'default' if no current session is defined """
        return current_session.name

    @property
    def date(self):
        return time.strftime(self.date_format)

    @property
    def writer(self):
        """
        Scan writer object.
        """
        return self._writer_module

    @writer.setter
    def writer(self, value):
        try:
            if value is not None:
                self._get_writer_class(value)
        except ImportError as exc:
            raise ImportError(
                "Writer module **%s** does not"
                " exist or cannot be loaded (%s)"
                " possible module are %s" % (value, exc, writer.__all__)
            )
        except AttributeError as exc:
            raise AttributeError(
                "Writer module **%s** does have"
                " class named Writer (%s)" % (value, exc)
            )
        else:
            self._writer_module = value

    def get(self):
        """
        This method will compute all configurations needed for a new acquisition.
        It will return a dictionary with:
            root_path -- compute root path with *base_path* and *template* attribute
            images_path -- compute images path with *base_path* and *images_path_template* attribute
                If images_path_relative is set to True (default), the path
                template is relative to the scan path, otherwise the
                image_path_template has to be an absolute path.
            parent -- DataNodeContainer to be used as a parent for new acquisition
        """
        try:
            template = self.template
            images_template = self.images_path_template
            images_prefix = self.images_prefix
            data_filename = self.data_filename
            formatter = string.Formatter()
            cache_dict = self.to_dict(export_properties=True)
            template_keys = [key[1] for key in formatter.parse(template)]

            for key in template_keys:
                value = cache_dict.get(key)
                if callable(value):
                    value = value(self)  # call the function
                    cache_dict[key] = value
            sub_path = template.format(**cache_dict)
            images_sub_path = images_template.format(**cache_dict)
            images_prefix = images_prefix.format(**cache_dict)
            data_filename = data_filename.format(**cache_dict)

            db_path_items = [(self.session, "container")]
            base_path_items = list(
                filter(
                    None,
                    os.path.normpath(cache_dict.get("base_path")).split(os.path.sep),
                )
            )
            sub_items = os.path.normpath(sub_path).split(os.path.sep)
            try:
                if db_path_items[0][0] == sub_items[0]:
                    del sub_items[0]
            except IndexError:
                pass
            sub_items = base_path_items + sub_items
            for path_item in sub_items:
                db_path_items.append((path_item, "container"))
        except KeyError as keyname:
            raise RuntimeError("Missing %s attribute in ScanSaving" % keyname)
        else:
            path = os.path.join(cache_dict.get("base_path"), sub_path)
            if self.images_path_relative:
                images_path = os.path.join(path, images_sub_path, images_prefix)
            else:
                images_path = os.path.join(images_sub_path, images_prefix)

            return {
                "root_path": path,
                "data_path": os.path.join(path, data_filename),
                "images_path": images_path,
                "db_path_items": db_path_items,
                "writer": self._get_writer_object(path, images_path, data_filename),
            }

    def get_path(self):
        """
        This method return the current saving path.
        The path is compute with *base_path* and follow the *template* attribute
        to generate it.
        """
        return self.get()["root_path"]

    def get_parent_node(self):
        """
        This method return the parent node which should be used to publish new data
        """
        db_path_items = self.get()["db_path_items"]
        parent_node = _get_or_create_node(*db_path_items[0])
        for item_name, node_type in db_path_items[1:]:
            parent_node = _get_or_create_node(item_name, node_type, parent=parent_node)
        return parent_node

    def _get_writer_class(self, writer_module):
        module_name = "%s.%s" % (self.WRITER_MODULE_PATH, writer_module)
        writer_module = __import__(module_name, fromlist=[""])
        return getattr(writer_module, "Writer")

    def _get_writer_object(self, path, images_path, data_filename):
        if self.writer is None:
            return
        klass = self._get_writer_class(self.writer)
        return klass(path, images_path, data_filename)


class ScanDisplay(ParametersWardrobe):
    SLOTS = []

    def __init__(self, session_name=None):
        """
        This class represents the display parameters for scans for a session.
        """
        if session_name is None:
            session_name = current_session.name

        super().__init__(
            "%s:scan_display_params" % session_name,
            default_values={
                "auto": False,
                "motor_position": True,
                "_counters": [],
                "_extra_args": [],
            },
            property_attributes=(
                "session",
                "counters",
                "extra_args",
                "flint_output_enabled",
            ),
            not_removable=("auto", "motor_position"),
        )

        self.add("_session_name", session_name)

    def __dir__(self):
        keys = super().__dir__()
        return keys

    def __repr__(self):
        return super().__repr__()

    @property
    def session(self):
        """ This give the name of the current session or default if no current session is defined """
        return self._session_name

    @property
    def extra_args(self):
        """Returns the list of extra arguments which will be provided to flint
        at it's next creation"""
        return self._extra_args

    @extra_args.setter
    def extra_args(self, extra_args):
        """Set the list of extra arguments to provide to flint at it's
        creation"""
        # FIXME: It could warn to restart flint in case it is already loaded
        if not isinstance(extra_args, (list, tuple)):
            raise TypeError(
                "SCAN_DISPLAY.extra_args expects a list or a tuple of strings"
            )

        # Do not load it while it is not needed
        from argparse import ArgumentParser
        from bliss.flint import config

        # Parse and check flint command line arguments
        parser = ArgumentParser(prog="Flint")
        config.configure_parser_arguments(parser)
        try:
            parser.parse_args(extra_args)
        except SystemExit:
            # Avoid to exit while parsing the arguments
            pass

        self._extra_args = list(extra_args)

    @property
    def counters(self):
        return self._counters

    @counters.setter
    def counters(self, counters_selection):
        """
        Select counter(s) which will be displayed in scan output. If no counters are given, it clears the filter list.
        """

        if counters_selection in [[], (), "All", "all", None, ""]:
            self._counters = []
        else:
            cnts = []
            for cnt in counters_selection:
                fullname = cnt.fullname
                cnts.append(fullname)

            self._counters = cnts

    @property
    def flint_output_enabled(self):
        """
        Returns true if the output (strout/stderr) is displayed using the
        logging system.

        This is an helper to display the `disabled` state of the logger
        `flint.output`.
        """
        from bliss.common import plot

        logger = plot.FLINT_OUTPUT_LOGGER
        return not logger.disabled

    @flint_output_enabled.setter
    def flint_output_enabled(self, enabled):
        """
        Enable or disable the display of flint output ((strout/stderr) )
        using the logging system.

        This is an helper to set the `disabled` state of the logger
        `flint.output`.
        """
        from bliss.common import plot

        logger = plot.FLINT_OUTPUT_LOGGER
        logger.disabled = not enabled


def _get_channels_dict(acq_object, channels_dict):
    scalars = channels_dict.setdefault("scalars", [])
    scalars_units = channels_dict.setdefault("scalars_units", {})
    spectra = channels_dict.setdefault("spectra", [])
    images = channels_dict.setdefault("images", [])
    display_names = channels_dict.setdefault("display_names", {})

    for acq_chan in acq_object.channels:
        fullname = acq_chan.fullname
        if fullname in display_names:
            continue
        try:
            _, controller_chan_name, chan_name = fullname.split(":")
        except ValueError:
            controller_chan_name, _, chan_name = fullname.rpartition(":")
        display_names[fullname] = (
            controller_chan_name,
            acq_chan.short_name,
        )  # use .name to get alias, if any
        scalars_units[fullname] = acq_chan.unit
        shape = acq_chan.shape
        if len(shape) == 0 and fullname not in scalars:
            scalars.append(fullname)
        elif len(shape) == 1 and fullname not in spectra:
            spectra.append(fullname)
        elif len(shape) == 2 and fullname not in images:
            images.append(fullname)

    return channels_dict


def _get_masters_and_channels(acq_chain):
    # go through acq chain, group acq channels by master and data shape
    tree = acq_chain._tree

    chain_dict = {}
    display_names_list = []
    for path in tree.paths_to_leaves():
        master = None
        # path[0] is root
        for acq_object in path[1:]:
            # it is mandatory to find an acq. master first
            if isinstance(acq_object, AcquisitionMaster):
                if master is None or acq_object.parent is None:
                    master = acq_object.name
                    channels = chain_dict.setdefault(master, {"master": {}})
                    _get_channels_dict(acq_object, channels["master"])
                    display_names_list.append(channels["master"]["display_names"])
                    continue
            _get_channels_dict(acq_object, channels)
            display_names_list.append(channels["display_names"])

    # find channel display labels
    names_count = collections.Counter()
    # eliminate duplicated display_names dict in list
    display_names_list = [
        d
        for i, d in enumerate(display_names_list)
        if d not in display_names_list[i + 1 :]
    ]
    for display_names in display_names_list:
        for controller_chan_name, chan_name in display_names.values():
            if controller_chan_name == chan_name:
                # weird case, but it can happen
                names_count.update([chan_name])
            else:
                names_count.update([controller_chan_name, chan_name])
    for display_names in display_names_list:
        for fullname, (controller_chan_name, chan_name) in display_names.items():
            if names_count[chan_name] == 1:
                # unique short name
                display_names[fullname] = chan_name
            else:
                if names_count[controller_chan_name] == 1:
                    display_names[fullname] = controller_chan_name
                else:
                    display_names[fullname] = fullname

    return chain_dict


def display_motor(func):
    @wraps(func)
    def f(self, *args, **kwargs):
        axis = func(self, *args, **kwargs)
        scan_display_params = ScanDisplay()
        if (
            is_bliss_shell()
            and scan_display_params.auto
            and scan_display_params.motor_position
        ):
            channel_name = self.get_channel_name(axis)
            if channel_name is None:
                print(
                    "The object %s have no obvious channel. Plot marker skiped."
                    % (axis,)
                )
            else:
                plot = self.get_plot(axis, plot_type="curve", as_axes=True)
                if plot is None:
                    print(
                        "There is no plot using %s as X-axes. Plot marker skiped."
                        % (channel_name,)
                    )
                else:
                    plot.update_motor_marker(
                        channel_name, axis.position, text=axis.name
                    )

    return f


class ScanPreset:
    def prepare(self, scan):
        """
        Called on the preparation phase of a scan.
        """
        pass

    def start(self, scan):
        """
        Called on the starting phase of a scan.
        """
        pass

    def stop(self, scan):
        """
        Called at the end of a scan.
        """
        pass


class ScanState(enum.IntEnum):
    IDLE = 0
    PREPARING = 1
    STARTING = 2
    STOPPING = 3
    DONE = 4


class Scan:
    def __init__(
        self,
        chain,
        name="scan",
        scan_info=None,
        save=True,
        save_images=None,  # None means follows "save"
        scan_saving=None,
        data_watch_callback=None,
        watchdog_callback=None,
    ):
        """
        This class publish data and trig the writer if any.

        chain -- acquisition chain you want to use for this scan.
        name -- scan name, if None set default name *scan*
        parent -- the parent is the root node of the data tree.
        usually the parent is a Container like to a session,sample,experiment...
        i.e: parent = Container('eh3')
        scan_info -- should be the scan parameters as a dict
        writer -- is the final file writer (hdf5,cvs,spec file...)
        data_watch_callback -- a callback inherited from DataWatchCallback
        """
        self.__name = name
        self.__scan_number = None
        self.root_node = None
        self._scan_info = dict(scan_info) if scan_info is not None else dict()

        if scan_saving is None:
            scan_saving = ScanSaving(current_session.name)
        session_name = scan_saving.session
        user_name = scan_saving.user_name
        self.__scan_saving = scan_saving
        scan_config = scan_saving.get()

        self._scan_info["save"] = save
        if save:
            self.__writer = scan_config["writer"]
        else:
            self.__writer = NullWriter(
                scan_config["root_path"],
                scan_config["images_path"],
                os.path.basename(scan_config["data_path"]),
            )
        self.__writer._save_images = save if save_images is None else save_images

        self.__nodes = dict()
        self._devices = []

        self.user_scan_meta = get_user_scan_meta().copy()
        # call all master and device to fill scan_meta
        for dev in chain.nodes_list:
            dev.fill_meta_at_scan_init(self.user_scan_meta)
        self._scan_info["session_name"] = session_name
        self._scan_info["user_name"] = user_name
        self._scan_info["filename"] = self.writer.filename
        self._scan_info.setdefault("title", name)

        deep_update(self._scan_info, self.user_scan_meta.to_dict(self))
        self._scan_info["scan_meta_categories"] = self.user_scan_meta.cat_list()
        self._data_watch_task = None
        self._data_watch_callback = data_watch_callback
        self._data_events = dict()
        self.set_watchdog_callback(watchdog_callback)
        self._acq_chain = chain
        self._scan_info["acquisition_chain"] = _get_masters_and_channels(
            self._acq_chain
        )

        scan_display_params = ScanDisplay()
        if is_bliss_shell() and scan_display_params.auto:
            get_flint()

        self.__state = ScanState.IDLE
        self.__state_change = gevent.event.Event()
        self._preset_list = list()
        self.__node = None

    def _create_data_node(self, node_name):
        self.__node = _create_node(
            node_name, "scan", parent=self.root_node, info=self._scan_info
        )

    def _prepare_node(self):
        if self.__node is None:
            self.root_node = self.__scan_saving.get_parent_node()

            ### order is important in the next lines...
            self.writer.template.update(
                {
                    "scan_name": self.name,
                    "session": self.__scan_saving.session,
                    "scan_number": "{scan_number}",
                }
            )

            self.__scan_number = self._next_scan_number()

            self.writer.template["scan_number"] = self.scan_number
            self._scan_info["scan_nb"] = self.__scan_number

            start_timestamp = time.time()
            start_time = datetime.datetime.fromtimestamp(start_timestamp)
            self._scan_info["start_time"] = start_time
            start_time_str = start_time.strftime("%a %b %d %H:%M:%S %Y")
            self._scan_info["start_time_str"] = start_time_str
            self._scan_info["start_timestamp"] = start_timestamp

            node_name = str(self.__scan_number) + "_" + self.name
            self._create_data_node(node_name)

    def __repr__(self):
        return "Scan(number={}, name={}, path={})".format(
            self.__scan_number, self.name, self.writer.filename
        )

    @property
    def name(self):
        return self.__name

    @property
    def state(self):
        return self.__state

    @property
    def writer(self):
        return self.__writer

    @property
    def node(self):
        return self.__node

    @property
    def nodes(self):
        return self.__nodes

    @property
    def acq_chain(self):
        return self._acq_chain

    @property
    def scan_info(self):
        return self._scan_info

    @property
    def scan_number(self):
        if self.__scan_number:
            return self.__scan_saving.scan_number_format % self.__scan_number
        else:
            return "{scan_number}"

    @property
    def statistics(self):
        return Statistics(self._acq_chain._stats_dict)

    @property
    def get_channels_dict(self):
        """
        returns a dict containing all channels used in this scan 
        identified by their fullname
        """
        flatten = lambda l: [item for sublist in l for item in sublist]

        return {
            c.name: c for c in flatten([n.channels for n in self.acq_chain.nodes_list])
        }

    def add_preset(self, preset):
        """
        Add a preset for this scan
        """
        if not isinstance(preset, ScanPreset):
            raise ValueError("Expected ScanPreset instance")
        self._preset_list.append(preset)

    def set_watchdog_callback(self, callback):
        """
        Set a watchdog callback for this scan
        """
        if callback:
            self._watchdog_task = _WatchDogTask(self, callback)
        else:
            self._watchdog_task = None

    def _get_data_axis_name(self, axis=None):
        axes_name = self._get_data_axes_name()
        if len(axes_name) > 1 and axis is None:
            raise ValueError(
                "Multiple axes detected, please provide axis for \
                                 calculation."
            )
        if axis is None:
            return axes_name[0]
        else:
            if axis.name not in axes_name:
                raise ValueError("No master for axis '%s`." % axis.name)
            return axis.name

    def _get_data_axes_name(self):
        """
        Return all axes in this scan
        """
        acq_chain = self._scan_info["acquisition_chain"]
        master_axes = []
        for top_level_master in acq_chain.keys():
            for scalar_master in acq_chain[top_level_master]["master"]["scalars"]:
                ma = scalar_master.split(":")[-1]
                if ma in self._scan_info["instrument"]["positioners"]:
                    master_axes.append(ma)

        if len(master_axes) == 0:
            if self._scan_info.get("type") == "timescan":
                return ["elapsed_time"]
            else:
                raise RuntimeError("No axis detected in scan.")
        return master_axes

    def _get_x_y_data(self, counter, axis=None):
        axis_name = self._get_data_axis_name(axis)
        counter_name = counter.name if not isinstance(counter, str) else counter
        data = self.get_data()
        x_data = data[axis_name]
        try:
            y_data = data[counter_name]
        except KeyError:
            # try with the counter short name
            y_data = data[counter_name.split(":")[-1]]
        return x_data, y_data, axis_name

    def fwhm(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        _, fwhm = cen(x, y)
        return fwhm

    def peak(self, counter_or_xy, axis=None):
        if isinstance(counter_or_xy, tuple):
            x, y = counter_or_xy
        else:
            counter = counter_or_xy
            x, y, _ = self._get_x_y_data(counter, axis)
        return peak(x, y)

    def com(self, counter_or_xy, axis=None):
        if isinstance(counter_or_xy, tuple):
            x, y = counter_or_xy
        else:
            counter = counter_or_xy
            x, y, _ = self._get_x_y_data(counter, axis)
        return com(x, y)

    def cen(self, counter_or_xy, axis=None):
        if isinstance(counter_or_xy, tuple):
            x, y = counter_or_xy
        else:
            counter = counter_or_xy
            x, y, _ = self._get_x_y_data(counter, axis)
        return cen(x, y)

    @display_motor
    def goto_peak(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        axis = getattr(setup_globals, axis_name)
        pk = self.peak((x, y))
        with error_cleanup(axis, restore_list=(cleanup_axis.POS,)):
            axis.move(pk)
        return axis

    @display_motor
    def goto_com(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        axis = getattr(setup_globals, axis_name)
        com_value = self.com((x, y))
        with error_cleanup(axis, restore_list=(cleanup_axis.POS,)):
            axis.move(com_value)
        return axis

    @display_motor
    def goto_cen(self, counter, axis=None):
        x, y, axis_name = self._get_x_y_data(counter, axis)
        axis = getattr(setup_globals, axis_name)
        cfwhm, _ = self.cen((x, y))
        with error_cleanup(axis, restore_list=(cleanup_axis.POS,)):
            axis.move(cfwhm)
        return axis

    @display_motor
    def where(self, axis=None):
        if axis is None:
            try:
                acq_chain = self._scan_info["acquisition_chain"]
                for top_level_master in acq_chain.keys():
                    for scalar_master in acq_chain[top_level_master]["master"][
                        "scalars"
                    ]:
                        axis_name = scalar_master.split(":")[-1]
                        if axis_name in self._scan_info["instrument"]["positioners"]:
                            raise StopIteration
            except StopIteration:
                axis = getattr(setup_globals, axis_name)
            else:
                RuntimeError("Can't find axis in this scan")
        return axis

    def wait_state(self, state):
        while self.__state < state:
            self.__state_change.clear()
            self.__state_change.wait()

    def __trigger_data_watch_callback(self, signal, sender, sync=False):
        if self._data_watch_callback is not None:
            event_set = self._data_events.setdefault(sender, set())
            event_set.add(signal)
            if sync:
                data_events = self._data_events
                self._data_events = dict()
                while self._data_watch_running and not self._data_watch_task.ready():
                    self._data_watch_callback_done.wait()
                    self._data_watch_callback_done.clear()
                self._scan_info["state"] = self.__state
                self._data_watch_callback.on_scan_data(
                    data_events, self.nodes, self._scan_info
                )
            else:
                self._data_watch_callback_event.set()
        if self._watchdog_task is not None:
            self._watchdog_task.trigger_data_event(sender, signal)

    def _channel_event(self, event_dict, signal=None, sender=None):
        with KillMask():
            self.nodes[sender].store(event_dict)

        self.__trigger_data_watch_callback(signal, sender)

    def set_ttl(self):
        for node in self.nodes.values():
            node.set_ttl()
        self.node.set_ttl()

    def _device_event(self, event_dict=None, signal=None, sender=None):
        if signal == "end":
            self.__trigger_data_watch_callback(signal, sender, sync=True)

    def _prepare_channels(self, channels, parent_node):
        for channel in channels:
            chan_name = channel.short_name
            self.nodes[channel] = _get_or_create_node(
                chan_name,
                channel.data_node_type,
                parent_node,
                shape=channel.shape,
                dtype=channel.dtype,
                unit=channel.unit,
                fullname=channel.fullname,
            )
            channel.data_node = self.nodes[channel]
            connect(channel, "new_data", self._channel_event)

    def prepare(self, scan_info, devices_tree):
        self.__nodes = dict()
        self._devices = list(devices_tree.expand_tree())[1:]

        for dev in self._devices:
            dev_node = devices_tree.get_node(dev)
            level = devices_tree.depth(dev_node)
            if level == 1:
                parent_node = self.node
            else:
                parent_node = self.nodes[dev_node.bpointer]
            if isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                data_container_node = _create_node(dev.name, parent=parent_node)
                self.nodes[dev] = data_container_node
                self._prepare_channels(dev.channels, data_container_node)

                for signal in ("start", "end"):
                    connect(dev, signal, self._device_event)

        self.writer.prepare(self)

    def disconnect_all(self):
        for dev in self._devices:
            if isinstance(dev, (AcquisitionSlave, AcquisitionMaster)):
                for channel in dev.channels:
                    disconnect(channel, "new_data", self._channel_event)
                for signal in ("start", "end"):
                    disconnect(dev, signal, self._device_event)
        self._devices = []

    def run(self):
        if self.state != ScanState.IDLE:
            raise RuntimeError(
                "Scan state is not idle. Scan objects can only be used once."
            )

        call_on_prepare, call_on_stop = False, False
        set_watch_event = None

        ### create scan node in redis
        self._prepare_node()

        if self._data_watch_callback is not None:
            data_watch_callback_event = gevent.event.Event()
            data_watch_callback_done = gevent.event.Event()

            def trig(*args):
                data_watch_callback_event.set()

            self._data_watch_running = False
            self._data_watch_task = gevent.spawn(
                Scan._data_watch,
                weakref.proxy(self, trig),
                data_watch_callback_event,
                data_watch_callback_done,
            )
            self._data_watch_callback_event = data_watch_callback_event
            self._data_watch_callback_done = data_watch_callback_done

            if hasattr(self._data_watch_callback, "on_state"):
                call_on_prepare = self._data_watch_callback.on_state(
                    ScanState.PREPARING
                )
                call_on_stop = self._data_watch_callback.on_state(ScanState.STOPPING)

            set_watch_event = self._data_watch_callback_event.set

        self.acq_chain.reset_stats()

        try:
            if self._data_watch_callback:
                self._data_watch_callback.on_scan_new(self, self.scan_info)
            if self._watchdog_task is not None:
                self._watchdog_task.start()
                self._watchdog_task.on_scan_new(self, self.scan_info)

            current_iters = [next(i) for i in self.acq_chain.get_iter_list()]

            # ---- apply parameters
            apply_parameters_tasks = [
                gevent.spawn(i.apply_parameters) for i in current_iters
            ]
            try:
                gevent.joinall(apply_parameters_tasks, raise_error=True)
            finally:
                gevent.killall(apply_parameters_tasks)
            # -----

            self.__state = ScanState.PREPARING
            self.__state_change.set()
            with periodic_exec(0.1 if call_on_prepare else 0, set_watch_event):
                self._execute_preset("prepare")
                self.prepare(self.scan_info, self.acq_chain._tree)
                prepare_tasks = [
                    gevent.spawn(i.prepare, self, self.scan_info) for i in current_iters
                ]
                try:
                    gevent.joinall(prepare_tasks, raise_error=True)
                finally:
                    gevent.killall(prepare_tasks)

            self.__state = ScanState.STARTING
            self.__state_change.set()
            self._execute_preset("start")
            run_next_tasks = [
                (gevent.spawn(self._run_next, i), i) for i in current_iters
            ]
            run_scan = True

            with capture_exceptions(raise_index=0) as capture:
                with capture():
                    kill_exception = StopChain
                    try:
                        while run_scan:
                            # The master defined as 'terminator' ends the loop
                            # (by default any top master will stop the loop),
                            # the loop is also stopped in case of exception.
                            wait_tasks = [t for t, _ in run_next_tasks]
                            if self._watchdog_task is not None:
                                wait_tasks += [self._watchdog_task]
                            gevent.joinall(wait_tasks, raise_error=True, count=1)
                            if self._watchdog_task is not None:
                                # stop the scan if watchdog_task end normally
                                # it received a StopIteration
                                run_scan = not self._watchdog_task.ready()

                            for i, (task, iterator) in enumerate(list(run_next_tasks)):
                                if task.ready():
                                    if iterator.top_master.terminator:
                                        # scan has to end
                                        run_scan = False
                                        break
                                    else:
                                        # remove finished task, as it does not
                                        # correspond to a "stopper" top master
                                        run_next_tasks.pop(i)
                                        run_scan = len(run_next_tasks) > 0
                    except:
                        kill_exception = gevent.GreenletExit
                        raise
                    finally:
                        gevent.killall(
                            [t for t, _ in run_next_tasks], exception=kill_exception
                        )

                self.__state = ScanState.STOPPING
                self.__state_change.set()

                with periodic_exec(0.1 if call_on_stop else 0, set_watch_event):
                    stop_task = [
                        gevent.spawn(i.stop) for i in current_iters if i is not None
                    ]
                    with capture():
                        try:
                            gevent.joinall(stop_task, raise_error=True)
                        except:
                            with KillMask(masked_kill_nb=1):
                                gevent.joinall(stop_task)
                            gevent.killall(stop_task)
                            raise
        finally:
            with capture_exceptions(raise_index=0) as capture:
                with capture():
                    # check if there is any master or device that would like
                    # to provide meta data at the end of the scan
                    for dev in self.acq_chain.nodes_list:
                        dev.fill_meta_at_scan_end(self.user_scan_meta)
                    self.user_scan_meta.instrument.remove("positioners")
                    deep_update(self._scan_info, self.user_scan_meta.to_dict(self))
                    self._scan_info[
                        "scan_meta_categories"
                    ] = self.user_scan_meta.cat_list()

                    # update scan_info in redis
                    self.node._info.update(self.scan_info)

                self.set_ttl()

                self.node.end()

                # Close nodes
                for node in self.nodes.values():
                    try:
                        node.close()
                    except AttributeError:
                        pass

                # Disconnect events
                self.disconnect_all()

                self.__state = ScanState.DONE
                self.__state_change.set()

                # Add scan to the globals
                current_session.scans.append(self)

                if self.writer:
                    # write scan_info to file
                    with capture():
                        self.writer.finalize_scan_entry(self)
                        self.writer.close()

                with capture():
                    if self._data_watch_callback:
                        self._data_watch_callback.on_scan_end(self.scan_info)
                with capture():
                    if self._watchdog_task is not None:
                        self._watchdog_task.kill()
                        self._watchdog_task.on_scan_end(self.scan_info)
                with capture():
                    # Kill data watch task
                    if self._data_watch_task is not None:
                        if (
                            self._data_watch_task.ready()
                            and not self._data_watch_task.successful()
                        ):
                            self._data_watch_task.get()
                        self._data_watch_task.kill()

                self._execute_preset("stop")

    def _run_next(self, next_iter):
        next_iter.start()
        for i in next_iter:
            i.prepare(self, self.scan_info)
            i.start()

    @staticmethod
    def _data_watch(scan, event, event_done):
        while True:
            event.wait()
            event.clear()
            try:
                data_events = scan._data_events
                scan._data_events = dict()
                scan._data_watch_running = True
                scan.scan_info["state"] = scan.state
                scan._data_watch_callback.on_scan_data(
                    data_events, scan.nodes, scan.scan_info
                )
                scan._data_watch_running = False
            except ReferenceError:
                break
            else:
                event_done.set()
                gevent.idle()

    def get_data(self):
        """Return a numpy array with the scan data.

        It is a 1D array corresponding to the scan points.
        Each point is a named structure corresponding to the counter names.
        """
        return get_data(self)

    def _find_plot_type_index(self, scan_item_name, channels):
        channel_name_match = (
            lambda scan_item_name, channel_name: ":" + scan_item_name in channel_name
            or scan_item_name + ":" in channel_name
        )

        scalars = channels.get("scalars", [])
        spectra = channels.get("spectra", [])
        images = channels.get("images", [])

        for i, channel_name in enumerate(scalars):
            if channel_name_match(scan_item_name, channel_name):
                return ("0d", 0)
        for i, channel_name in enumerate(spectra):
            if channel_name_match(scan_item_name, channel_name):
                return ("1d", i)
        for i, channel_name in enumerate(images):
            if channel_name_match(scan_item_name, channel_name):
                return ("2d", i)

        return None

    def get_channel_name(self, channel_item):
        """Return a channel name from a bliss object, else None

        If you are lucky the result is what you expect.

        Argument:
            channel_item: A bliss object which could have a channel during a scan.

        Return:
            A channel name identifying this object in scan data acquisition
        """
        if isinstance(channel_item, Axis):
            return "axis:%s" % channel_item.name
        return channel_item.fullname

    def get_plot(self, channel_item, plot_type, as_axes=False, wait=False):
        """Return the first plot object of type 'plot_type' showing the
        'channel_item' from Flint live scan view.

        Argument:
            channel_item: must be a channel
            plot_type: can be "image", "curve", "scatter", "mca"

        Keyword argument:
            as_axes (defaults to False): If true, reach a plot with this channel as
                X-axes (curves ans scatters), or Y-axes (scatter)
            wait (defaults to False): wait for plot to be shown

        Return:
            The expected plot, else None
        """
        # check that flint is running
        if not check_flint(current_session.name):
            return None

        flint = get_flint()
        if wait:
            flint.wait_end_of_scans()
        try:
            channel_name = self.get_channel_name(channel_item)
            if channel_name is None:
                return None
            plot_id = flint.get_live_scan_plot(channel_name, plot_type, as_axes=as_axes)
        except Exception:
            return None

        if plot_type == "curve":
            return CurvePlot(existing_id=plot_id)
        elif plot_type == "scatter":
            return ScatterPlot(existing_id=plot_id)
        elif plot_type == "mca":
            return McaPlot(existing_id=plot_id)
        elif plot_type == "image":
            return ImagePlot(existing_id=plot_id)
        else:
            assert False

    def _next_scan_number(self):
        LAST_SCAN_NUMBER = "last_scan_number"
        filename = self.writer.filename
        # last scan number is stored in the parent of the scan
        parent_node = self.__scan_saving.get_parent_node()
        last_scan_number = parent_node.connection.hget(
            parent_node.db_name, LAST_SCAN_NUMBER
        )
        if last_scan_number is None and "{scan_number}" not in filename:
            max_scan_number = 0
            for scan_entry in self.writer.get_scan_entries():
                try:
                    max_scan_number = max(
                        int(scan_entry.split("_")[0]), max_scan_number
                    )
                except Exception:
                    continue
            name = parent_node.db_name
            with pipeline(parent_node._struct) as p:
                p.hsetnx(name, LAST_SCAN_NUMBER, max_scan_number)
                p.hincrby(name, LAST_SCAN_NUMBER, 1)
                _, scan_number = p.execute()
        else:
            cnx = parent_node.connection
            scan_number = cnx.hincrby(parent_node.db_name, LAST_SCAN_NUMBER, 1)
        return scan_number

    def _execute_preset(self, method_name):
        preset_tasks = [
            gevent.spawn(getattr(preset, method_name), self)
            for preset in self._preset_list
        ]
        try:
            gevent.joinall(preset_tasks, raise_error=True)
        finally:
            gevent.killall(preset_tasks)
