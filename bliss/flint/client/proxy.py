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


class FlintClient:
    """
    Create a Flint proxy based on an already existing process,
    else create a new Flint application using subprocess and attach it.

    Arguments:
        process: A process object from (psutil) or an int
    """

    def __init__(self, process=None):
        self._pid: typing.Optional[int] = None
        self._proxy = None
        self._process = None
        self._greenlets = None
        self._callbacks = None
        if process is None:
            self.__start_flint()
        else:
            self.__attach_flint(process)

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
                "Attribute '%s' unknown. Flint proxy not yet created" % name
            )
        attr = self._proxy.__getattribute__(name)
        # Shortcut the lookup attribute
        setattr(self, name, attr)
        return attr

    def close_proxy(self):
        if self._proxy is not None:
            self._proxy.close()
        self._proxy = None
        self._pid = None
        self._process = None
        if self._greenlets is not None:
            gevent.killall(self._greenlets)
        self._greenlets = None
        self._callbacks = None

    def close(self):
        """Close Flint and clean up this proxy."""
        if self._proxy is None:
            raise RuntimeError("No proxy connected")
        self._proxy.close_application()
        self.close_proxy()

    def kill(self):
        """Interrupt Flint with SIGTERM and clean up this proxy."""
        if self._pid is None:
            raise RuntimeError("No proxy connected")
        os.kill(self._pid, signal.SIGTERM)
        self.close_proxy()

    def kill9(self):
        """Interrupt Flint with SIGKILL and clean up this proxy."""
        if self._pid is None:
            raise RuntimeError("No proxy connected")
        os.kill(self._pid, signal.SIGKILL)
        self.close_proxy()

    def __start_flint(self):
        process = self.__create_flint()
        try:
            # Try 3 times
            for nb in range(4):
                try:
                    self.__attach_flint(process)
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

    def __create_flint(self):
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

        scan_display = ScanDisplay()
        args = [sys.executable, "-m", "bliss.flint"]
        args.extend(scan_display.extra_args)
        process = subprocess.Popen(
            args,
            env=env,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return process

    def __attach_flint(self, process):
        """Attach a flint process, make a RPC proxy and bind Flint to the current
        session and return the FLINT proxy.
        """
        if isinstance(process, int):
            if not psutil.pid_exists(process):
                raise psutil.NoSuchProcess(
                    process, "Flint PID %s does not exist" % process
                )
            process = psutil.Process(process)

        def raise_if_dead(process):
            if hasattr(process, "returncode"):
                if process.returncode is not None:
                    raise RuntimeError("Processus terminaded")

        pid = process.pid
        FLINT_LOGGER.debug("Attach flint PID: %d...", pid)
        beacon = get_default_connection()
        redis = beacon.get_redis_connection()
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
        self._proxy = proxy
        self._pid = process.pid

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

        try:
            manager = current_session.scan_saving.metadata_manager
            proxy.set_tango_metadata_name(manager.name())
        except Exception:
            FLINT_LOGGER.debug("Error while registering the logbook", exc_info=True)
            FLINT_LOGGER.error("Logbook for Flint is not available")

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

    #
    # Helper on top of the proxy
    #

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
        silx_class_name, plot_class = self.__get_plot_info(plot_class)
        plot_id = self._proxy.add_plot(
            silx_class_name, name=name, selected=selected, closeable=closeable
        )
        return plot_class(plot_id=plot_id, flint=self)

    def __get_plot_info(self, plot_class):
        if isinstance(plot_class, str):
            classes = [
                plots.CurvePlot,
                plots.CurveListPlot,
                plots.HistogramImagePlot,
                plots.ImagePlot,
                plots.ImageStackPlot,
                plots.ScatterPlot,
            ]
            plot_class = [p for p in classes if p.WIDGET == plot_class][0]
        return plot_class.WIDGET, plot_class


def _get_beacon_config():
    beacon = get_default_connection()
    return "{}:{}".format(beacon._host, beacon._port)


def _get_flint_pid_from_redis(session_name):
    """Check if an existing Flint process is running and attached to session_name.

    Returns:
        The process object from psutil.
    """
    beacon = get_default_connection()
    redis = beacon.get_redis_connection()

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


def _get_cached_flint() -> typing.Optional[FlintClient]:
    """Returns the cached flint proxy"""
    global FLINT
    if FLINT is not None and FLINT.pid is None:
        FLINT = None
    return FLINT


def get_flint(start_new=False, creation_allowed=True, mandatory=True):
    """Get the running flint proxy or create one.

    Arguments:
        start_new: If true, force starting a new flint subprocess (which will be
            the new current one)
        creation_allowed: If false, a new application will not be created.
        mandatory: If True (default), a Flint proxy must be returned else
            an exception is raised.
            If False, try to return a Flint proxy, else None is returned.
    """
    if not mandatory:
        # Protect call to flint
        try:
            return get_flint(start_new=start_new, creation_allowed=creation_allowed)
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
        FLINT_LOGGER.debug("Check cache")

        flint = _get_cached_flint()
        if flint is not None:
            if psutil.pid_exists(flint._pid):
                try:
                    remote_session_name = flint.get_session_name()
                except Exception:
                    FLINT_LOGGER.error("Error while reaching Flint API. Restart Flint.")
                    FLINT_LOGGER.debug("Backtrace", exc_info=True)
                else:
                    if session_name == remote_session_name:
                        return flint

                # Do not use this Redis PID if is is already this one
                pid_from_redis = _get_flint_pid_from_redis(session_name)
                check_redis = pid_from_redis != flint._pid

        if check_redis:
            pid = _get_flint_pid_from_redis(session_name)
            if pid is not None:
                try:
                    return attach_flint(pid)
                except:
                    FLINT_LOGGER.error(
                        "Impossible to attach Flint to the already existing PID %s", pid
                    )
                    raise

    if not creation_allowed:
        return None

    reset_flint()
    global FLINT
    FLINT = FlintClient()
    return FLINT


def check_flint() -> bool:
    """
    Returns true if a Flint application from the current session is alive.
    """
    flint = _get_cached_flint()
    return flint is not None


def attach_flint(pid: int):
    """Attach to an external flint process, make a RPC proxy and bind Flint to
    the current session and return the FLINT proxy

    Argument:
        pid: Process identifier of Flint
    """
    global FLINT
    # Release the previous proxy before attaching the next one
    flint = _get_cached_flint()
    if flint is not None:
        flint.close_proxy()
        flint = None
        FLINT = None
    flint = FlintClient(process=pid)
    FLINT = flint
    return flint


def reset_flint():
    """Close the current flint proxy.
    """
    global FLINT
    try:
        flint = _get_cached_flint()
        if flint is not None:
            flint.close_proxy()
    finally:
        # Anyway, invalidate the proxy
        FLINT = None
