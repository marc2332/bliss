# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import gevent
import functools
import logging
from gevent.time import time
from bliss.scanning.writer.file import FileWriter
from bliss import current_session
from bliss.common.tango import DeviceProxy, DevState, DevFailed
from tango import CommunicationFailed, ConnectionFailed
from nexus_writer_service.io import nexus
from nexus_writer_service import metadata
from nexus_writer_service.nexus_register_writer import find_session_writer, get_uri


logger = logging.getLogger(__name__)


def deverror_parse(deverror, msg=None):
    reason = deverror.reason
    desc = deverror.desc.strip()
    if not msg:
        msg = ""
    if "PythonError" in reason:
        msg += f" (Nexus writer {desc})"
    else:
        msg += f" (Nexus writer {reason}: {desc})"
    return msg


def skip_when_fault(method):
    @functools.wraps(method)
    def _skip_when_fault(self, *args, **kwargs):
        if self._fault:
            return True
        else:
            return method(self, *args, **kwargs)

    return _skip_when_fault


class Writer(FileWriter):
    FILE_EXTENSION = "h5"

    def __init__(self, root_path, images_root_path, data_filename, *args, **keys):
        FileWriter.__init__(
            self,
            root_path,
            images_root_path,
            data_filename,
            master_event_callback=self._on_event,
            **keys,
        )
        self._proxy = None
        self._check_scan_time = time()
        self._check_scan_period = 3
        self._fault = False
        self._state_checked = False
        self._scan_name = ""
        self._warn_msg_dict = {}
        metadata.register_all_metadata_generators()

    def create_path(self, full_path):
        """The root directory is owned by the Nexus writer.
        All other directories are owned by Bliss.
        """
        if os.path.isdir(full_path):
            return
        relpath = os.path.relpath(full_path, self.root_path)
        if relpath.replace(".", "").replace(os.path.sep, ""):
            super().create_path(full_path)
        else:
            self.proxy.makedirs(full_path)

    def _create_root_path(self):
        self.create_path(self.root_path)
        return True

    def prepare(self, scan):
        # Called at start of scan
        self._check_scan_time = time()
        self._fault = False
        self._state_checked = False
        self._scan_name = scan.node.name
        self._retry(
            self.is_writer_on,
            timeout_msg="Cannot check Nexus writer state",
            fail_msg="Nexus writer is not ON or RUNNING",
        )
        self._retry(
            self._create_root_path,
            timeout_msg="Cannot create directory",
            fail_msg="Nexus writer cannot create directory",
        )
        self._retry(
            self.scan_writer_started,
            timeout_msg="Cannot check Nexus writer scan state",
            fail_msg="Nexus scan writing not started",
        )
        self._retry(
            self.is_scan_permitted,
            timeout_msg="Cannot check Nexus writer permissions",
            fail_msg="Nexus writer does not have write permissions",
        )
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
            # Make sure we do not check too often
            if _check_scan_time > self._check_scan_time + self._check_scan_period:
                self._check_scan_time = _check_scan_time
                self._state_checked = True
                self._retry(
                    self.is_scan_notfault,
                    timeout_msg="Cannot check Nexus writer scan state",
                    fail_msg="Nexus writer error",
                    timeout=0,
                )

    def finalize_scan_entry(self, scan):
        if not self._state_checked:
            self._retry(
                self.is_scan_notfault,
                timeout_msg="Cannot check Nexus writer scan state",
                fail_msg="Nexus writer error",
                timeout=0,
            )
        # TODO: currently not checking for finish to not
        # alarm the user with the warning message
        # self._retry(
        #    self.is_scan_finished,
        #    timeout_msg="Cannot check Nexus writer finished",
        #    fail_msg="Nexus writer is not finished",
        # )
        pass

    def get_scan_entries(self):
        try:
            with nexus.File(self.filename, mode="r") as f:
                return list(f.keys())
        except IOError:  # file doesn't exist
            return []

    @property
    def _writer_uri(self):
        return find_session_writer(current_session.name)

    @property
    def _full_writer_uri(self):
        uri = self._writer_uri
        p = self._proxy
        if p is None:
            return uri
        else:
            return get_uri(p)

    @property
    def proxy(self):
        self._store_proxy()
        if self._proxy is None:
            raise RuntimeError("No Nexus writer registered for this session")
        return self._proxy

    def _set_proxy_timeout(self, sec):
        self.proxy.set_timeout_millis(int(sec * 1000.))

    @skip_when_fault
    def _store_proxy(self):
        if self._proxy is None:
            uri = self._writer_uri
            if not uri:
                self._fault = True
                raise RuntimeError("No Nexus writer registered for this session")
            self._proxy = DeviceProxy(uri)

    @property
    def session_state(self):
        return self.proxy.state()

    @property
    def session_state_reason(self):
        return self.proxy.status()

    @property
    def scan_state(self):
        return self.proxy.scan_state(self._scan_name)

    @property
    def scan_state_reason(self):
        return self.proxy.scan_state_reason(self._scan_name)

    @property
    def _scan_permitted(self):
        return self.proxy.scan_permitted(self._scan_name)

    @property
    def _scan_exists(self):
        return self.proxy.scan_exists(self._scan_name)

    def _retry(
        self,
        method,
        timeout_msg=None,
        fail_msg=None,
        timeout=10,
        proxy_timeout=3,
        raise_on_timeout=False,
    ):
        """Call `method` until

        * returns True
        * raises exception (some Tango communication exceptions are ignored)
        * timeout

        When retrying is pointless, the method should raise an
        exception instead of returning `False`.

        :param callable method: returns True or False
        :param num timeout_msg:
        :param str fail_msg:
        :param num timeout: in seconds (try only once when zero)
        :param bool raise_on_timeout:
        """
        t0 = time()
        if not timeout_msg:
            timeout_msg = "Nexus writer check failed"
        if not fail_msg:
            fail_msg = timeout_msg
        err_msg = fail_msg
        cause = None
        first = True
        self._set_proxy_timeout(proxy_timeout)
        while (time() - t0) < timeout or first:
            first = False
            try:
                if method():
                    return
            except ConnectionFailed as e:
                err_msg = deverror_parse(e.args[0], msg=timeout_msg)
                if e.args[0].reason in ["API_DeviceNotExported", "DB_DeviceNotDefined"]:
                    raise_on_timeout = self._fault = True
                    break
            except CommunicationFailed as e:
                cause = e
                err_msg = deverror_parse(e.args[1], msg=timeout_msg)
            except DevFailed as e:
                cause = e
                err_msg = deverror_parse(e.args[0], msg=timeout_msg)
                raise_on_timeout = self._fault = True
                break
            except Exception as e:
                raise_on_timeout = self._fault = True
                raise
            gevent.sleep(0.1)
        if raise_on_timeout:
            if cause is None:
                raise RuntimeError(err_msg)
            else:
                raise RuntimeError(err_msg) from cause
        else:
            # Do not repeat the same warning
            previous_msgs = self._warn_msg_dict.setdefault(method.__qualname__, set())
            if err_msg not in previous_msgs:
                previous_msgs.add(err_msg)
                logger.warning(err_msg)
            else:
                logger.debug(err_msg)

    def is_writer_on(self):
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
                "Nexus writer service is in {} state ({})".format(state.name, reason)
            )
        else:
            return False

    @skip_when_fault
    def is_scan_finished(self):
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
                "Nexus writer is in FAULT state due to {}".format(repr(reason))
            )
        else:
            return False

    def is_scan_notfault(self):
        """
        :returns bool: state is valid and expected
        :raises RuntimeError: invalid state
        """
        state = self.scan_state
        if state == DevState.FAULT:
            reason = self.scan_state_reason
            raise RuntimeError(f"Nexus writer is in FAULT state ({reason})")
        else:
            return True

    def is_scan_permitted(self):
        """
        :returns bool: writer can write
        :raises RuntimeError: invalid state
        """
        if not self._scan_permitted:
            raise RuntimeError("Nexus writer does not have write permissions")
        return True

    def scan_writer_started(self):
        """
        :returns bool: writer exists
        """
        return self._scan_exists

    def _str_state(self, session):
        if session:
            msg = "Nexus writer"
        else:
            msg = "Nexus writer scan " + repr(self._scan_name)
        try:
            if session:
                state = self.session_state
                reason = self.session_state_reason
            else:
                state = self.scan_state
                reason = self.scan_state_reason
        except CommunicationFailed as e:
            msg += ": cannot get state"
            return deverror_parse(e.args[1], msg)
        except DevFailed as e:
            msg += ": cannot get state"
            return deverror_parse(e.args[0], msg)
        else:
            return "{} in {} state ({})".format(msg, state.name, reason)

    @property
    def _str_session_state(self):
        return self._str_state(True)

    @property
    def _str_scan_state(self):
        return self._str_state(False)
