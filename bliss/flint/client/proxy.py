# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide helper to create a Flint proxy.
"""

import os
import sys
import subprocess
import logging
import psutil
import gevent
import typing
import signal
import enum

import bliss
from bliss.comm import rpc
from bliss.common import event

from bliss import current_session
from bliss.config.conductor.client import get_default_connection
from bliss.scanning.scan_display import ScanDisplay
from bliss.flint import config
from . import plots

try:
    from bliss.flint.patches import poll_patch
except ImportError:
    poll_patch = None


FLINT_LOGGER = logging.getLogger("flint")
FLINT_OUTPUT_LOGGER = logging.getLogger("flint.output")
# Disable the flint output
FLINT_OUTPUT_LOGGER.setLevel(logging.INFO)
FLINT_OUTPUT_LOGGER.disabled = True

FLINT = None


class _FlintState(enum.Enum):
    NO_PROXY = 0
    IS_AVAILABLE = 1
    IS_STUCKED = 2


class FlintClient:
    """
    Proxy on a optional Flint application.

    It provides API to create/connect/disconnect/ a Flint application.

    Arguments:
        process: A process object from (psutil) or an int
    """

    def __init__(self, process=None):
        self._pid: typing.Optional[int] = None
        self._proxy = None
        self._process = None
        self._greenlets = None
        self._callbacks = None
        self._shortcuts = set()
        self._on_new_pid = None

    @property
    def pid(self) -> typing.Optional[int]:
        """"Returns the PID of the Flint application connected by this proxy, else None"""
        return self._pid

    @property
    def __wrapped__(self):
        """See bliss.common.event"""
        return self._proxy

    def __getattr__(self, name):
        if self._proxy is None:
            raise AttributeError(
                "No Flint proxy created. Access to '%s' ignored." % name
            )
        attr = getattr(self._proxy, name)
        # Shortcut the lookup attribute
        self._shortcuts.add(name)
        setattr(self, name, attr)
        return attr

    def _proxy_get_flint_state(self, timeout=2) -> _FlintState:
        """Returns one of the state describing the life cycle of Flint"""
        pid = self._pid
        if pid is None:
            return _FlintState.NO_PROXY
        if not psutil.pid_exists(pid):
            return _FlintState.NO_PROXY
        proxy = self._proxy
        if proxy is None:
            return _FlintState.NO_PROXY
        try:
            with gevent.Timeout(seconds=timeout):
                proxy.get_bliss_version()
        except gevent.Timeout:
            return _FlintState.IS_STUCKED
        return _FlintState.IS_AVAILABLE

    def _proxy_create_flint(self) -> psutil.Process:
        """Start the flint application in a subprocess.

        Returns:
            The process object"""
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY", ""):
            FLINT_LOGGER.error(
                "DISPLAY environment variable have to be defined to launch Flint"
            )
            raise RuntimeError("DISPLAY environment variable is not defined")

        FLINT_LOGGER.warning("Flint starting...")
        env = dict(os.environ)
        env["BEACON_HOST"] = _get_beacon_config()
        # Do not use all the cores anyway used algorithms request it
        # NOTE:  Mitigate problem occurred with silx colormap computation
        env["OMP_NUM_THREADS"] = "4"
        if poll_patch is not None:
            poll_patch.set_ld_preload(env)

        session_name = current_session.name
        scan_display = ScanDisplay()

        args = [sys.executable, "-m", "bliss.flint"]
        args.extend(["-s", session_name])
        args.extend(scan_display.extra_args)
        process = subprocess.Popen(
            args,
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return process

    def _proxy_create_flint_proxy(self, process):
        """Attach a flint process, make a RPC proxy and bind Flint to the current
        session and return the FLINT proxy.
        """

        def raise_if_dead(process):
            if hasattr(process, "returncode"):
                if process.returncode is not None:
                    raise RuntimeError("Processus terminaded")

        pid = process.pid
        FLINT_LOGGER.debug("Attach flint PID: %d...", pid)
        beacon = get_default_connection()
        redis = beacon.get_redis_proxy()
        try:
            session_name = current_session.name
        except AttributeError:
            raise RuntimeError("No current session, cannot attach flint")

        # Current URL
        key = config.get_flint_key(pid)
        value = None
        for _ in range(3):
            raise_if_dead(process)
            value = redis.brpoplpush(key, key, timeout=5)

            if value is not None:
                break
        if value is None:
            raise ValueError(
                f"flint: cannot retrieve Flint RPC server address from pid '{pid}`"
            )
        url = value.decode().split()[-1]

        # Return flint proxy
        raise_if_dead(process)
        FLINT_LOGGER.debug("Creating flint proxy...")
        proxy = rpc.Client(url, timeout=3)

        # Check the Flint API version
        remote_flint_api_version = proxy.get_flint_api_version()
        if remote_flint_api_version != config.FLINT_API_VERSION:
            FLINT_LOGGER.debug("Flint used API: {config.FLINT_API_VERSION}")
            FLINT_LOGGER.debug("Flint provided API: {remote_flint_api_version}")
            # Display the BLISS version
            remote_bliss_version = proxy.get_bliss_version()
            FLINT_LOGGER.warning(
                "Bliss and Flint API does not match (bliss version %s, flint version: %s).",
                bliss.release.version,
                remote_bliss_version,
            )
            FLINT_LOGGER.warning("You should restart Flint.")

        proxy.set_session(session_name)
        self._set_new_proxy(proxy, process.pid)

        if hasattr(process, "stdout"):
            # process which comes from subprocess, and was pipelined
            g1 = gevent.spawn(
                self.__log_process_output_to_logger,
                process,
                "stdout",
                FLINT_OUTPUT_LOGGER,
                logging.INFO,
            )
            g2 = gevent.spawn(
                self.__log_process_output_to_logger,
                process,
                "stderr",
                FLINT_OUTPUT_LOGGER,
                logging.ERROR,
            )
            self._greenlets = (g1, g2)

        else:
            # Else we can use RPC events
            def stdout_callbacks(s):
                FLINT_OUTPUT_LOGGER.info("%s", s)

            def stderr_callbacks(s):
                FLINT_OUTPUT_LOGGER.error("%s", s)

            event.connect(proxy, "flint_stdout", stdout_callbacks)
            event.connect(proxy, "flint_stderr", stderr_callbacks)

            self._callbacks = (stdout_callbacks, stderr_callbacks)

            try:
                proxy.register_output_listener()
            except Exception:
                # FIXME: This have to be fixed or removed
                # See: https://gitlab.esrf.fr/bliss/bliss/issues/1249
                FLINT_LOGGER.error(
                    "Error while connecting to stdout logs from Flint (issue #1249)"
                )
                FLINT_LOGGER.debug("Backtrace", exc_info=True)

        scan_saving = current_session.scan_saving
        if scan_saving is not None:
            if scan_saving.data_policy == "ESRF":
                metadata_manager = scan_saving.icat_proxy.metadata_manager
                if metadata_manager is not None:
                    proxy.set_tango_metadata_name(metadata_manager.proxy.name())
                else:
                    FLINT_LOGGER.warning("Elogbook for Flint is not available")

    def _proxy_close_proxy(self, timeout=5):
        proxy = self._proxy
        if proxy is not None:
            for i in range(4):
                if i == 0:
                    pid = self._pid
                    FLINT_LOGGER.debug("Close Flint %s", pid)
                    try:
                        with gevent.Timeout(seconds=timeout):
                            proxy.close_application()
                    except gevent.Timeout:
                        pass
                    self._wait_for_closed(pid, timeout=2)
                    if not psutil.pid_exists(pid):
                        # Already dead
                        break
                elif i == 1:
                    pid = self._pid
                    FLINT_LOGGER.debug("Request trace info from %s", pid)
                    if not psutil.pid_exists(pid):
                        # Already dead
                        break
                    os.kill(pid, signal.SIGUSR1)
                    gevent.sleep(2)
                elif i == 2:
                    pid = self._pid
                    FLINT_LOGGER.debug("Kill flint %s", pid)
                    if not psutil.pid_exists(pid):
                        # Already dead
                        break
                    os.kill(pid, signal.SIGTERM)
                    self._wait_for_closed(pid, timeout=2)
                    if not psutil.pid_exists(pid):
                        break
                elif i == 3:
                    pid = self._pid
                    FLINT_LOGGER.debug("Force kill flint %s", pid)
                    if not psutil.pid_exists(pid):
                        # Already dead
                        break
                    os.kill(pid, signal.SIGABRT)

        self._proxy_cleanup()
        # FIXME: here we should clean up redis keys

    def _proxy_cleanup(self):
        """Disconnect Flint if there is such connection.

        Flint application stay untouched.
        """
        if self._callbacks is not None:
            stdout_callback, stderr_callback = self._callbacks
            try:
                event.disconnect(self._proxy, "flint_stdout", stdout_callback)
            except ConnectionRefusedError:
                pass
            try:
                event.disconnect(self._proxy, "flint_stderr", stderr_callback)
            except ConnectionRefusedError:
                pass
        self._callbacks = None
        for s in self._shortcuts:
            delattr(self, s)
        self._shortcuts = set()
        if self._proxy is not None:
            try:
                self._proxy.close()
            except Exception:
                pass
        self._proxy = None
        self._pid = None
        self._process = None
        if self._greenlets is not None:
            gevent.killall(self._greenlets, timeout=2.0)
        self._greenlets = None

    def _set_new_proxy(self, proxy, pid):
        # Make sure no cached functions are used
        for s in self._shortcuts:
            delattr(self, s)
        self._shortcuts = set()
        # Setup the new proxy
        self._proxy = proxy
        self._pid = pid
        if self._on_new_pid is not None:
            self._on_new_pid(pid)

    def _proxy_attach_pid(self, pid):
        """Attach the proxy to another Flint PID.

        If a Flint application is already connected, it will stay untouched,
        but will not be connected anymore, anyway the new PID exists or is
        responsive.
        """
        self._proxy_cleanup()
        process = psutil.Process(pid)
        self._proxy_create_flint_proxy(process)

    @staticmethod
    def _wait_for_closed(pid, timeout=None):
        """"Wait for the PID to be closed"""
        try:
            p = psutil.Process(pid)
        except psutil.NoSuchProcess:
            # process already closed
            return

        try:
            with gevent.Timeout(timeout):
                # gevent timeout have to be used here
                # See https://github.com/gevent/gevent/issues/622
                p.wait(timeout=None)
        except gevent.Timeout:
            pass

    def close(self, timeout=None):
        """Close Flint and clean up this proxy."""
        if self._proxy is None:
            raise RuntimeError("No proxy connected")
        with gevent.Timeout(timeout):
            self._proxy.close_application()
        self._wait_for_closed(self._pid, timeout=4.0)
        self._proxy_cleanup()

    def focus(self):
        """Set the focus to the Flint window."""
        if self._proxy is None:
            raise RuntimeError("No proxy connected")
        self._proxy.set_window_focus()

    def terminate(self):
        """Interrupt Flint with SIGTERM and clean up this proxy."""
        if self._pid is None:
            raise RuntimeError("No proxy connected")
        os.kill(self._pid, signal.SIGTERM)
        self._wait_for_closed(self._pid, timeout=4.0)
        self._proxy_cleanup()

    def kill(self):
        """Interrupt Flint with SIGKILL and clean up this proxy."""
        if self._pid is None:
            raise RuntimeError("No proxy connected")
        os.kill(self._pid, signal.SIGKILL)
        self._wait_for_closed(self._pid, timeout=4.0)
        self._proxy_cleanup()

    def kill9(self):
        """Deprecated. Provided for compatibility only"""
        self.kill()

    def _proxy_start_flint(self):
        """
        Start a new Flint application and connect a proxy to it.
        """
        process = self._proxy_create_flint()
        try:
            # Try 3 times
            for nb in range(4):
                try:
                    self._proxy_create_flint_proxy(process)
                    break
                except Exception:
                    # Is the process has terminated?
                    if process.returncode is not None:
                        if process.returncode != 0:
                            raise subprocess.CalledProcessError(
                                process.returncode, "flint"
                            )
                        # Else it is just a normal close
                        raise RuntimeError("Flint have been closed")
                    if nb == 3:
                        raise
        except subprocess.CalledProcessError as e:
            # The process have terminated with an error
            FLINT_LOGGER.error("Flint has terminated with an error.")
            scan_display = ScanDisplay()
            if not scan_display.flint_output_enabled:
                FLINT_LOGGER.error("You can enable the logs with the following line.")
                FLINT_LOGGER.error("    SCAN_DISPLAY.flint_output_enabled = True")
            out, err = process.communicate(timeout=1)

            def normalize(data):
                try:
                    return data.decode("utf-8")
                except UnicodeError:
                    return data.decode("latin1")

            out = normalize(out)
            err = normalize(err)
            FLINT_OUTPUT_LOGGER.error("---STDOUT---\n%s", out)
            FLINT_OUTPUT_LOGGER.error("---STDERR---\n%s", err)
            raise subprocess.CalledProcessError(e.returncode, e.cmd, out, err)
        except Exception:
            if hasattr(process, "stdout"):
                FLINT_LOGGER.error("Flint can't start.")
                scan_display = ScanDisplay()
                if not scan_display.flint_output_enabled:
                    FLINT_LOGGER.error(
                        "You can enable the logs with the following line."
                    )
                    FLINT_LOGGER.error("    SCAN_DISPLAY.flint_output_enabled = True")

                FLINT_OUTPUT_LOGGER.error("---STDOUT---")
                self.__log_process_output_to_logger(
                    process, "stdout", FLINT_OUTPUT_LOGGER, logging.ERROR
                )
                FLINT_OUTPUT_LOGGER.error("---STDERR---")
                self.__log_process_output_to_logger(
                    process, "stderr", FLINT_OUTPUT_LOGGER, logging.ERROR
                )
            raise
        FLINT_LOGGER.debug("Flint proxy initialized")
        self._proxy.wait_started()
        FLINT_LOGGER.debug("Flint proxy ready")

    def __log_process_output_to_logger(self, process, stream_name, logger, level):
        """Log the stream output of a process into a logger until the stream is
        closed.

        Args:
            process: A process object from subprocess or from psutil modules.
            stream_name: One of "stdout" or "stderr".
            logger: A logger from logging module
            level: A value of logging
        """
        was_openned = False
        if hasattr(process, stream_name):
            # process come from subprocess, and was pipelined
            stream = getattr(process, stream_name)
        else:
            # process output was not pipelined.
            # Try to open a linux stream
            stream_id = 1 if stream_name == "stdout" else 2
            try:
                path = f"/proc/{process.pid}/fd/{stream_id}"
                stream = open(path, "r")
                was_openned = True
            except Exception:
                FLINT_LOGGER.debug("Error while opening path %s", path, exc_info=True)
                FLINT_LOGGER.warning("Flint %s can't be attached.", stream_name)
                return
        if stream is None:
            # Subprocess returns None attributes if the streams are not catch
            return
        try:
            while self._proxy is not None and not stream.closed:
                line = stream.readline()
                try:
                    line = line.decode()
                except UnicodeError:
                    pass
                if not line:
                    break
                if line[-1] == "\n":
                    line = line[:-1]
                logger.log(level, "%s", line)
        except RuntimeError:
            # Process was terminated
            pass
        if stream is not None and was_openned and not stream.closed:
            stream.close()

    def is_available(self, timeout=2):
        """Returns true if Flint is available and not stucked.
        """
        state = self._proxy_get_flint_state(timeout=timeout)
        return state == _FlintState.IS_AVAILABLE

    #
    # Helper on top of the proxy
    #

    def get_live_plot(
        self,
        kind: typing.Optional[str] = None,
        image_detector: typing.Optional[str] = None,
        mca_detector: typing.Optional[str] = None,
    ):
        """Retrieve a live plot.

        This is an helper to simplify access to the plots used to display scans
        from BLISS.

        Arguments:
            kind: Can be one of "default-curve", "default-scatter"
            image_detector: Name of the detector displaying image.
            mca_detector: Name of the detector displaying MCA data.
        """
        if kind is not None:
            if kind == "default-curve":
                plot_class = plots.LiveCurvePlot
                plot_type = "curve"
            elif kind == "default-scatter":
                plot_class = plots.LiveScatterPlot
                plot_type = "scatter"
            else:
                raise ValueError(f"Unexpected plot kind '{kind}'.")

            plot_id = self.get_default_live_scan_plot(plot_type)
            if plot_id is None:
                raise ValueError(f"No {plot_type} plot available")

            return plot_class(plot_id=plot_id, flint=self)

        elif image_detector is not None:
            plot_class = plots.LiveImagePlot
            plot_id = self.get_live_plot_detector(image_detector, plot_type="image")
            return plot_class(plot_id=plot_id, flint=self)

        elif mca_detector is not None:
            plot_class = plots.LiveMcaPlot
            plot_id = self.get_live_plot_detector(mca_detector, plot_type="mca")
            return plot_class(plot_id=plot_id, flint=self)

        raise ValueError("No plot requested")

    def get_plot(
        self,
        plot_class: typing.Union[str, object],
        name: str = None,
        unique_name: str = None,
        selected: bool = False,
        closeable: bool = True,
    ):
        """Create or retrieve a plot from this flint instance.

        If the plot does not exists, it will be created in a new tab on Flint.

        Arguments:
            plot_class: A class defined in `bliss.flint.client.plot`, or a
                silx class name. Can be one of "Plot1D", "Plot2D", "ImageView",
                "StackView", "ScatterView".
            name: Name of the plot as displayed in the tab header. It is not a
                unique name.
            unique_name: If defined the plot can be retrieved from flint.
            selected: If true (not the default) the plot became the current
                displayed plot.
            closeable: If true (default), the tab can be closed manually
        """
        plot_class = self.__normalize_plot_class(plot_class)

        if unique_name is not None:
            if self.is_plot_exists(unique_name):
                return plot_class(flint=self, plot_id=unique_name)

        silx_class_name = plot_class.WIDGET
        plot_id = self._proxy.add_plot(
            silx_class_name,
            name=name,
            selected=selected,
            closeable=closeable,
            unique_name=unique_name,
        )
        return plot_class(plot_id=plot_id, flint=self, register=True)

    def add_plot(
        self,
        plot_class: typing.Union[str, object],
        name: str = None,
        selected: bool = False,
        closeable: bool = True,
    ):
        """Create a new custom plot based on the `silx` API.

        The plot will be created in a new tab on Flint.

        Arguments:
            plot_class: A class defined in `bliss.flint.client.plot`, or a
                silx class name. Can be one of "PlotWidget",
                "PlotWindow", "Plot1D", "Plot2D", "ImageView", "StackView",
                "ScatterView".
            name: Name of the plot as displayed in the tab header. It is not a
                unique name.
            selected: If true (not the default) the plot became the current
                displayed plot.
            closeable: If true (default), the tab can be closed manually
        """
        plot_class = self.__normalize_plot_class(plot_class)
        silx_class_name = plot_class.WIDGET
        plot_id = self._proxy.add_plot(
            silx_class_name, name=name, selected=selected, closeable=closeable
        )
        return plot_class(plot_id=plot_id, flint=self, register=True)

    def __normalize_plot_class(self, plot_class: typing.Union[str, object]):
        """Returns a BLISS side plot class.

        Arguments:
            plot_class: A BLISS side plot class, or one of its alias
        """
        if isinstance(plot_class, str):
            plot_class = plot_class.lower()
            for cls in plots.CUSTOM_CLASSES:
                if plot_class in cls.ALIASES:
                    plot_class = cls
                    break
            else:
                raise ValueError(f"Name '{plot_class}' does not refer to a plot class")
        return plot_class


def _get_beacon_config():
    beacon = get_default_connection()
    return "{}:{}".format(beacon._host, beacon._port)


def _get_flint_pid_from_redis(session_name) -> typing.Optional[int]:
    """Check if an existing Flint process is running and attached to session_name.

    Returns:
        The process object from psutil.
    """
    beacon = get_default_connection()
    redis = beacon.get_redis_proxy()

    # get existing flint, if any
    pattern = config.get_flint_key(pid="*")
    for key in redis.scan_iter(pattern):
        key = key.decode()
        pid = int(key.split(":")[-1])
        if psutil.pid_exists(pid):
            value = redis.lindex(key, 0).split()[0]
            if value.decode() == session_name:
                return pid
        else:
            redis.delete(key)
    return None


def _get_singleton() -> FlintClient:
    """Returns the Flint client singleton managed by this module.

    This singleton can be connected or not to a Flint application.
    """
    global FLINT
    if FLINT is None:
        FLINT = FlintClient()
    return FLINT


def _get_available_proxy() -> typing.Optional[FlintClient]:
    """Returns the Flint proxy only if there is a working connected Flint
    application."""
    proxy = _get_singleton()
    if proxy.is_available():
        return proxy
    return None


def get_flint(
    start_new=False, creation_allowed=True, mandatory=True, restart_if_stucked=False
) -> typing.Optional[FlintClient]:
    """Get the running flint proxy or create one.

    Arguments:
        start_new: If true, force starting a new flint subprocess (which will be
            the new current one)
        creation_allowed: If false, a new application will not be created.
        mandatory: If True (default), a Flint proxy must be returned else
            an exception is raised.
            If False, try to return a Flint proxy, else None is returned.
        restart_if_stucked: If True, if Flint is detected as stucked it is
            restarted.
    """
    if not mandatory:
        # Protect call to flint
        try:
            return get_flint(
                start_new=start_new,
                creation_allowed=creation_allowed,
                restart_if_stucked=restart_if_stucked,
            )
        except KeyboardInterrupt:
            # A warning should already be displayed in case of problem
            return None
        except Exception:
            # A warning should already be displayed in case of problem
            return None

    try:
        session_name = current_session.name
    except AttributeError:
        raise RuntimeError("No current session, cannot get flint")

    if not start_new:
        check_redis = True

        proxy = _get_singleton()
        state = proxy._proxy_get_flint_state(timeout=2)
        if state == _FlintState.NO_PROXY:
            pass
        elif state == _FlintState.IS_AVAILABLE:
            remote_session_name = proxy.get_session_name()
            if session_name == remote_session_name:
                return proxy
            # Do not use this Redis PID if is is already this one
            pid_from_redis = _get_flint_pid_from_redis(session_name)
            check_redis = pid_from_redis != proxy._pid
        elif state == _FlintState.IS_STUCKED:
            if restart_if_stucked:
                return restart_flint()
            raise RuntimeError("Flint is stucked")
        else:
            assert False, f"Unexpected state {state}"

        if check_redis:
            pid = _get_flint_pid_from_redis(session_name)
            if pid is not None:
                try:
                    return attach_flint(pid)
                except:  # noqa
                    FLINT_LOGGER.error(
                        "Impossible to attach Flint to the already existing PID %s", pid
                    )
                    raise

    if not creation_allowed:
        return None

    proxy = _get_singleton()
    proxy._proxy_start_flint()
    return proxy


def check_flint() -> bool:
    """
    Returns true if a Flint application from the current session is alive.
    """
    flint = _get_available_proxy()
    return flint is not None


def attach_flint(pid: int) -> FlintClient:
    """Attach to an external flint process, make a RPC proxy and bind Flint to
    the current session and return the FLINT proxy

    Argument:
        pid: Process identifier of Flint
    """
    flint = _get_singleton()
    flint._proxy_attach_pid(pid)
    return flint


def restart_flint(creation_allowed: bool = True):
    """Restart flint.

    Arguments:
        creation_allowed:  If true, if FLint was not started is will be created.
            Else, nothing will happen.
    """
    proxy = _get_singleton()
    state = proxy._proxy_get_flint_state(timeout=2)
    if state == _FlintState.NO_PROXY:
        if not creation_allowed:
            return
    elif state == _FlintState.IS_AVAILABLE:
        proxy._proxy_close_proxy()
    elif state == _FlintState.IS_STUCKED:
        proxy._proxy_close_proxy()
    else:
        assert False, f"Unexpected state {state}"
    flint = get_flint(start_new=True, mandatory=True)
    return flint


def close_flint():
    """Close the current flint proxy.
    """
    proxy = _get_singleton()
    state = proxy._proxy_get_flint_state(timeout=2)
    if state == _FlintState.NO_PROXY:
        pass
    elif state == _FlintState.IS_AVAILABLE:
        proxy._proxy_close_proxy()
    elif state == _FlintState.IS_STUCKED:
        proxy._proxy_close_proxy()
    else:
        assert False, f"Unexpected state {state}"


def reset_flint():
    """Close the current flint proxy.
    """
    close_flint()
