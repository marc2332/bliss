# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import gevent
import functools
import logging
from gevent.time import time
from bliss.scanning.writer.file import FileWriter
from bliss import current_session
from bliss.common.tango import DeviceProxy, DevState, DevFailed
from tango import CommunicationFailed
from nexus_writer_service.io import nexus
from nexus_writer_service import metadata
from nexus_writer_service.utils.config_utils import beamline
from nexus_writer_service.nexus_register_writer import find_session_writer, get_uri


logger = logging.getLogger(__name__)


def attempts(timeout=10, msg="timeout"):
    """
    Generator which yields `None` until timeout (raises RuntimeError)

    :param num timeout: in seconds
    :param str or callable msg:
    :raises RuntimeError: timeout
    """
    t0 = time()
    while (time() - t0) < timeout:
        yield
    else:
        # timeout
        if not isinstance(msg, str):
            msg = msg()
        raise RuntimeError(msg)


def retry_method(timeout=10, err_msg="", session=True):
    """
    Decorates a writer method which should to repeated until:

    * method returns True
    * method raises exception
    * timeout

    Tango proxy timeouts are captured and ignored.

    :param num timeout: in seconds
    :param str err_msg: message on timeout
    :param bool session: session or scan state
    :returns callable: decorator
    """

    def decorator_timeout(method):
        @functools.wraps(method)
        def _retry_method(self, *args, **kwargs):
            def msg_gen():
                if session:
                    state_func = self._str_session_state
                else:
                    state_func = self._str_scan_state
                try:
                    return err_msg + " ({})".format(state_func())
                except Exception:
                    return err_msg

            # Remark: gevent.Timeout does not work due to blocking proxy calls
            for _ in attempts(timeout=timeout, msg=msg_gen):
                try:
                    if method(self, *args, **kwargs):
                        break
                except CommunicationFailed as e:
                    if e.args[1].reason == "API_DeviceTimedOut":
                        logger.warning(
                            "{}: timeout {}".format(
                                repr(method.__qualname__), repr(self._full_writer_uri)
                            )
                        )
                        pass  # retry
                    else:
                        raise  # give up
                gevent.sleep(0.1)
                logger.debug("retry " + method.__qualname__)
            return True

        return _retry_method

    return decorator_timeout


def retry_session_method(**kwargs):
    return retry_method(session=True, **kwargs)


def retry_scan_method(**kwargs):
    return retry_method(session=False, **kwargs)


def skip_when_fault(method):
    @functools.wraps(method)
    def _skip_when_fault(self, *args, **kwargs):
        if self._fault:
            return None
        else:
            return method(self, *args, **kwargs)

    return _skip_when_fault


def mark_fault_on_exception(method):
    @functools.wraps(method)
    def _mark_fault_on_exception(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception:
            self._fault = True
            raise

    return _mark_fault_on_exception


class Writer(FileWriter):
    def __init__(self, root_path, images_root_path, data_filename, *args, **keys):
        FileWriter.__init__(
            self,
            root_path,
            images_root_path,
            data_filename,
            master_event_callback=self._on_event,
            device_event_callback=self._on_event,
            **keys
        )
        self._writer_proxy = None
        self._check_scan_time = time()
        self._check_scan_period = 3
        self._fault = False
        self._scan_name = ""
        metadata.register_all_metadata_generators()

    def create_path(self, full_path):
        """The root directory is owned by the Nexus writer.
        All other directories are owned by Bliss.
        """
        relpath = os.path.relpath(full_path, self.root_path)
        if relpath.replace(".", "").replace(os.path.sep, ""):
            super().create_path(full_path)
        else:
            self.writer_proxy.makedirs(full_path)
    @property
    def filename(self):
        return os.path.join(self.root_path, self.data_filename + ".h5")

    def prepare(self, scan):
        # Called at start of scan
        self._check_scan_time = time()
        self._fault = False
        self._scan_name = scan.node.name
        self.session_writer_on()
        self.create_path(self.root_path)
        self.scan_exists()
        self.scan_permitted()
        super().prepare(scan)

    def new_file(self, scan_name, scan_info):
        # Called for the first chain master
        pass

    def new_scan(self, scan_name, scan_info):
        # Called for all chain masters
        pass

    def _on_event(self, parent, event_dict, signal, sender):
        # Called during scan
        if signal == "new_data":
            _check_scan_time = time()
            # Make sure we do not check too frequent
            if _check_scan_time > self._check_scan_time + self._check_scan_period:
                self._check_scan_time = _check_scan_time
                self.valid_scan_writer()

    def finalize_scan_entry(self, scan):
        # Called at end of scan
        # self._set_writer_timeout(20)
        self.scan_writer_finished()

    def get_scan_entries(self):
        try:
            with nexus.File(self.filename, mode="r") as f:
                return list(f.keys())
        except IOError:  # file doesn't exist
            return []

    @property
    def _writer_uri(self):
        dev_name = find_session_writer(current_session.name)
        if dev_name:
            return dev_name
        domain = beamline()
        family = "bliss_nxwriter"
        device = current_session.name
        return "/".join([domain, family, device])

    @property
    def _full_writer_uri(self):
        uri = self._writer_uri
        p = self._writer_proxy
        if p is None:
            return uri
        else:
            return get_uri(p)

    @property
    def writer_proxy(self):
        self._store_writer_proxy()
        if self._writer_proxy is None:
            uri = self._writer_uri
            if uri:
                err_msg = "External writer {} not online".format(
                    repr(self._writer_proxy)
                )
            else:
                err_msg = "Missing tango URI of external writer in YAML configuration"
            raise RuntimeError(err_msg)
        return self._writer_proxy

    @skip_when_fault
    @mark_fault_on_exception
    def _store_writer_proxy(self):
        if self._writer_proxy is None:
            uri = self._writer_uri
            if not uri:
                raise RuntimeError(
                    "Missing tango URI of external writer in YAML configuration"
                )
            self._writer_proxy = DeviceProxy(uri)
            # self._set_writer_timeout(10)

    def _set_writer_timeout(self, timeout):
        """
        Set proxy timeout
        """
        proxy = self.writer_proxy
        proxy.set_timeout_millis(int(timeout * 1000))

    @property
    def session_state(self):
        proxy = self.writer_proxy
        return proxy.state()

    @property
    def session_state_reason(self):
        proxy = self.writer_proxy
        return proxy.state_reason

    @property
    def scan_state(self):
        proxy = self.writer_proxy
        return proxy.scan_state(self._scan_name)

    @property
    def scan_state_reason(self):
        proxy = self.writer_proxy
        return proxy.scan_state_reason(self._scan_name)

    @property
    def _scan_permitted(self):
        proxy = self.writer_proxy
        return proxy.scan_permitted(self._scan_name)

    @property
    def _scan_exists(self):
        proxy = self.writer_proxy
        return proxy.scan_exists(self._scan_name)

    # @skip_when_fault
    @mark_fault_on_exception
    @retry_session_method(err_msg="Nexus writer service is not ON or RUNNING")
    def session_writer_on(self):
        """
        :returns bool: state is valid and expected
        :raises RuntimeError: invalid state
        """
        state = self.session_state
        if state in [DevState.ON, DevState.RUNNING]:
            return True
        elif state in [DevState.FAULT, DevState.OFF, DevState.UNKNOWN]:
            reason = self.session_state_reason
            raise RuntimeError(
                "Nexus writer service is in {} state due to {} (hint: start {})".format(
                    state.name, repr(reason), self.writer_proxy
                )
            )
        else:
            return False

    @skip_when_fault
    @mark_fault_on_exception
    @retry_scan_method(err_msg="Data writer has not finished")
    def scan_writer_finished(self):
        """
        :returns bool: state is valid and expected
        :raises RuntimeError: invalid state
        """
        state = self.scan_state
        if state == DevState.OFF:
            return True
        elif state == DevState.FAULT:
            reason = self.scan_state_reason
            raise RuntimeError(
                "Data writer is in FAULT state due to {}".format(repr(reason))
            )
        else:
            return False

    # @skip_when_fault
    @mark_fault_on_exception
    @retry_scan_method(err_msg="Data writer is not in valid state")
    def valid_scan_writer(self):
        """
        :returns bool: state is valid and expected
        :raises RuntimeError: invalid state
        """
        state = self.scan_state
        if state == DevState.FAULT:
            reason = self.scan_state_reason
            raise RuntimeError(
                "Data writer is in FAULT state due to {}".format(repr(reason))
            )
        else:
            return True

    # @skip_when_fault
    @mark_fault_on_exception
    @retry_scan_method(err_msg="Data writer does not have write permissions")
    def scan_permitted(self):
        """
        :returns bool: writer can write
        :raises RuntimeError: invalid state
        """
        if not self._scan_permitted:
            raise RuntimeError("Data writer does not have write permissions")
        return True

    # @skip_when_fault
    @mark_fault_on_exception
    @retry_scan_method(err_msg="Data writer is created")
    def scan_exists(self):
        """
        :returns bool: writer exists
        :raises RuntimeError: invalid state
        """
        return self._scan_exists

    def _str_state(self, session):
        name = str(self.writer_proxy)
        if session:
            name += " session"
        else:
            name += " scan " + repr(self._scan_name)
        try:
            if session:
                state = self.session_state
                reason = self.session_state_reason
            else:
                state = self.scan_state
                reason = self.scan_state_reason
        except DevFailed as e:
            try:
                reason = e.args[-1].reason
                desc = e.args[-1].desc
            except (AttributeError, IndexError):
                reason = "DevFailed"
                desc = e.args[0].desc
            return "{}: cannot get state ({}: {})".format(name, reason, desc)
        else:
            return "{} in {} state due to {}".format(name, state.name, repr(reason))

    def _str_session_state(self):
        return self._str_state(True)

    def _str_scan_state(self):
        return self._str_state(False)
