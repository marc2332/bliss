# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2010 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""This provides an API to the ICAT ingester. This service allows
"datasets" to be registered with the ICAT database and data
(a single directory) to be archived.

Currently the communication goes through two tango devices.
To start communication with the ICAT ingester, it is sufficient
to instantiate a proxy:

    icat_proxy = IcatIngesterProxy(beamline, session)

The tango devices are discovered automatically based on beamline
name and Bliss session name.
"""


import gevent
import functools
import json
import logging
import warnings
from bliss.common.tango import DeviceProxy, DevState
from bliss.tango.clients.utils import (
    is_devfailed,
    is_devfailed_timeout,
    is_devfailed_notallowed,
    is_devfailed_reconnect_delayed,
)
from bliss import current_session

DEFAULT_TIMEOUT = 10
logger = logging.getLogger(__name__)


class IcatError(RuntimeError):
    """Unified exception raised by IcatIngesterProxy, from Timeout or Devfailed
    (the cause is preserved).
    """

    def __init__(self, message=None):
        if message:
            super().__init__(message)
        else:
            super().__init__("")

    @property
    def message(self):
        return self.args[0]

    @message.setter
    def message(self, value):
        if value:
            self.args[0] = str(value)
        else:
            self.args[0] = ""


def icat_comm(method):
    """Decorator for methods that communicate with the ICAT tango devices.
    Takes care of timeout and exceptions.
    """

    @functools.wraps(method)
    def wrapper(self, *args, comm_state=None, **kwargs):
        if comm_state is None:
            comm_state = {}
        timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
        timeout = comm_state.get("timeout", timeout)
        comm_state.setdefault("global_timeout", timeout)

        # Comm state for the method
        comm_state["timeout"] = None
        caller_error_msg = comm_state.pop("error_msg", None)

        try:
            with gevent.Timeout(timeout):
                with self._lock:
                    return method(self, *args, comm_state=comm_state, **kwargs)
        except gevent.Timeout as e:
            error_msg = f"Timeout {comm_state.get('global_timeout')} seconds"
            error_msg = comm_state.pop("error_msg", error_msg)
            exception = comm_state.pop("exception", e)
            raise IcatError(error_msg) from exception
        except Exception as e:
            error_msg = comm_state.pop("error_msg", None)
            if error_msg:
                raise IcatError(error_msg) from e
            else:
                raise
        finally:
            # Reset the comm state of the caller
            comm_state.pop("exception", None)
            comm_state["error_msg"] = caller_error_msg

    return wrapper


class IcatDeviceProxy:
    """DeviceProxy wrapper specific for ICAT tango devices.
    Unifies exceptions (IcatError) and implements retry logic.
    """

    def __init__(self, url, period=0.1):
        """
        :param str url:
        :param num period: sleep period for retrying
        """
        self.proxy = DeviceProxy(url)
        self.period = period
        self._lock = gevent.lock.RLock()

    def __repr__(self):
        return repr(self.proxy)

    @icat_comm
    def ping(self, comm_state=None):
        """
        :param dict comm_state:
        :raises IcatError:
        """
        self.exec_command("ping", comm_state=comm_state)

    @icat_comm
    def read_attribute(
        self, attr, with_default=True, default=None, retry=None, comm_state=None
    ):
        """
        :param str attr:
        :param bool with_default: return `default` when API_AttrNotAllowed
        :param Any default:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Cannot read tango attribute {repr(attr)}"
        try:
            return self._tango_exec(
                getattr, args=(self.proxy, attr), retry=retry, comm_state=comm_state
            )
        except IcatError as e:
            if with_default and is_devfailed_notallowed(e):
                return default
            raise

    @icat_comm
    def write_attribute(self, attr, value, retry=None, comm_state=None):
        """
        :param str attr:
        :param Any value:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state[
            "error_msg"
        ] = f"Cannot write tango attribute {repr(attr)} = {repr(value)}"
        return self._tango_exec(
            setattr, args=(self.proxy, attr, value), retry=retry, comm_state=comm_state
        )

    @icat_comm
    def read_property(
        self, prop, with_default=True, default=None, retry=None, comm_state=None
    ):
        """Server does not need to be online.

        :param str prop:
        :param bool with_default: return `default` when API_AttrNotAllowed
        :param Any default:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Cannot read tango property {repr(prop)}"

        def func():
            return self.proxy.get_property(prop)[prop][0]

        try:
            return self._tango_exec(func, retry=retry, comm_state=comm_state)
        except IcatError as e:
            if with_default and is_devfailed_notallowed(e):
                return default
            raise

    @icat_comm
    def write_property(self, prop, value, retry=None, comm_state=None):
        """Server does not need to be online.

        :param str prop:
        :param Any value:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state[
            "error_msg"
        ] = f"Cannot write tango property {repr(prop)} = {repr(value)}"
        pdict = {prop: [value]}

        def func():
            self.proxy.put_property(pdict)

        return self._tango_exec(func, retry=retry, comm_state=comm_state)

    @icat_comm
    def exec_command(
        self, command, args=None, kwargs=None, retry=None, comm_state=None
    ):
        """
        :param str command:
        :param tuple args:
        :param dict kwargs:
        :param dict comm_state:
        :raises IcatError:
        """

        def func():
            f = getattr(self.proxy, command)
            # f is a partial, that's why:
            if args and kwargs:
                return f(*args, **kwargs)
            elif args:
                return f(*args)
            elif kwargs:
                return f(**kwargs)
            else:
                return f()

        comm_state["error_msg"] = f"Cannot execute tango method {repr(command)}"
        return self._tango_exec(func, retry=retry, comm_state=comm_state)

    @icat_comm
    def _tango_exec(self, method, args=None, kwargs=None, retry=None, comm_state=None):
        """All tango communication goes through this method. Retry on API_DeviceTimedOut,
        API_AttrNotAllowed and API_CommandNotAllowed.

        We assume that the most likely occurance of the not-allowed exceptions is a call
        too fast after another call. In that case the method will be allowed after a short
        time. If you really try the call a method that is not allowed (wrong call order)
        you will receive the not-allowed exception after timeout and hence loose time.

        :param callable method:
        :param tuple args: to be passed to `method`
        :param dict kwargs: to be passed to `method`
        :param callable retry: takes one argument or type `DevFailed`
        :param dict comm_state:
        :raises IcatError:
        """
        if not args:
            args = tuple()
        if not kwargs:
            kwargs = dict()
        if retry is None:

            def retry(e):
                return False

        while True:
            try:
                return method(*args, **kwargs)
            except Exception as e:
                comm_state["exception"] = e
                # Re-raise when not a DevFailed
                if not is_devfailed(e):
                    raise
                # "Connection delayed" exception needs a retry
                if is_devfailed_reconnect_delayed(e):
                    # The connection request was delayed.
                    # Last connection request was done less than 1000 ms ago
                    gevent.sleep(1.1)
                    continue
                # Timeout or not-allowed exceptions need a retry
                if is_devfailed_timeout(e) or is_devfailed_notallowed(e):
                    gevent.sleep(self.period)
                    continue
                # Retry when requested by the user
                if retry(e):
                    gevent.sleep(self.period)
                    continue
                # Re-raise DevFailed exception that doesn't need a retry
                raise


class IcatIngesterProxy(object):
    """This class provides one API to ICAT ingester (currently two tango devices) in a singleton pattern.
    It is a proxy and therefore does not contain state.
    """

    STATES = {
        "OFF": "No experiment ongoing",
        "STANDBY": "Experiment started, sample or dataset not specified",
        "ON": "No dataset running",
        "RUNNING": "Dataset is running",
        "FAULT": "Device is not functioning correctly",
    }

    _instances = {}

    def __new__(cls, *args, **kw):
        """Only one instance per beamline+session to ensure locking works.
        """
        instance = cls._instances.get(args)
        if instance is None:
            instance = cls._instances[args] = super().__new__(cls)
        return instance

    def __init__(self, beamline, session, period=0.1):
        """The arguments are the minimal information needed
        to compile the tango URL of the metadata devices.
        Changing them after instantiation will reset the
        tango proxies.

        :param str beamline: Beamline name
        :param str session: Bliss session name
        :param num period: retry sleep period
        """
        self.beamline = beamline
        self.session = session
        self.period = period
        self._lock = gevent.lock.RLock()

    def __repr__(self):
        return f"{self.__class__.__name__}({repr(self.beamline)}, {repr(self.session)})"

    @property
    def beamline(self):
        return self._beamline

    @beamline.setter
    def beamline(self, value):
        self._beamline = value
        self.delete_proxies()

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, value):
        self._session = value
        self.delete_proxies()

    @property
    def period(self):
        return self._period

    @period.setter
    def period(self, value):
        self._period = value
        self.delete_proxies()

    def delete_proxies(self):
        """The proxies will be recreated on the first call
        to the tango devices.
        """
        self._metaexp = None
        self._metamgr = None

    @property
    def metadata_experiment(self):
        """Manages the sample and proposal (for all techniques).
        """
        if self._metaexp is None:
            self._metaexp = IcatDeviceProxy(
                f"{self.beamline}/metaexp/{self.session}", period=self.period
            )
            if self.beamline != self._metaexp.read_property("beamlineID"):
                self._metaexp.write_property("beamlineID", self.beamline)
        return self._metaexp

    @property
    def metadata_manager(self):
        """Manages the dataset (data and metadata ingestion).
        Different techniques with different metadata will be served
        by different metadata managers.
        """
        if self._metamgr is None:
            self._metamgr = IcatDeviceProxy(
                f"{self.beamline}/metadata/{self.session}", period=self.period
            )
        return self._metamgr

    @icat_comm
    def ping(self, comm_state=None):
        self.metadata_experiment.ping(comm_state=comm_state)
        self.metadata_manager.ping(comm_state=comm_state)

    @property
    def state(self):
        return self.get_state()

    @property
    def status(self):
        return self.STATES[self.state]

    @property
    def full_status(self):
        s = self.state
        return f"{s}: {self.STATES[s]}"

    @icat_comm
    def get_state(self, comm_state=None):
        """
        :param dict comm_state:
        :raises IcatError:
        """
        return str(self.metadata_manager.exec_command("State", comm_state=comm_state))

    @icat_comm
    def is_in_states(self, states, comm_state=None):
        """
        :param list(str) states:
        :param dict comm_state:
        :raises IcatError:
        """
        return self.get_state(comm_state=comm_state) in states

    @icat_comm
    def is_not_in_states(self, states, comm_state=None):
        """
        :param list(str) states:
        :param dict comm_state:
        :raises IcatError:
        """
        return self.get_state(comm_state=comm_state) not in states

    @icat_comm
    def wait_until_state(self, states, comm_state=None):
        """
        :param list(str) states:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Device not in any of these states: {states}"
        while self.is_not_in_states(states, comm_state=comm_state):
            gevent.sleep(self.period)

    @icat_comm
    def wait_until_not_state(self, states, comm_state=None):
        """
        :param list(str) states:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Device still in one of these states: {states}"
        while self.is_in_states(states, comm_state=comm_state):
            gevent.sleep(self.period)

    @property
    def proposal(self):
        return self.get_proposal()

    @proposal.setter
    def proposal(self, value):
        self.set_proposal(value)

    @property
    def sample(self):
        return self.get_sample()

    @sample.setter
    def sample(self, value):
        self.set_sample(value)

    @property
    def dataset(self):
        return self.get_dataset()

    @dataset.setter
    def dataset(self, value):
        self.set_dataset(value)

    @property
    def path(self):
        """Full path of the dataset
        """
        return self.get_path()

    @path.setter
    def path(self, value):
        self.set_path(value)

    @icat_comm
    def get_proposal(self, comm_state=None):
        return self.metadata_experiment.read_attribute(
            "proposal", default="", comm_state=comm_state
        )

    @icat_comm
    def get_sample(self, comm_state=None):
        return self.metadata_experiment.read_attribute(
            "sample", default="", comm_state=comm_state
        )

    @icat_comm
    def get_dataset(self, comm_state=None):
        return self.metadata_manager.read_attribute(
            "datasetName", default="", comm_state=comm_state
        )

    @icat_comm
    def get_path(self, comm_state=None):
        return self.metadata_experiment.read_attribute(
            "dataRoot", default="", comm_state=comm_state
        )

    @icat_comm
    def set_proposal(self, proposal, comm_state=None):
        """Force the proposal name (i.e. modify/verify state)

        :param str proposal:
        :param dict comm_state:
        :raises IcatError:
        """
        if proposal:
            comm_state[
                "error_msg"
            ] = f"Failed to start the ICAT proposal {repr(proposal)}"
        else:
            comm_state[
                "error_msg"
            ] = f"Failed to reset the ICAT proposal {repr(proposal)}"
        self.ensure_notrunning(comm_state=comm_state)
        self._set_proposal(proposal=proposal, comm_state=comm_state)
        # TODO: times out sometimes
        # if proposal:
        #     self.wait_until_state(["STANDBY"], comm_state=comm_state)
        # else:
        #     self.wait_until_state(["OFF"], comm_state=comm_state)
        logger.debug(f"Proposal set: {repr(proposal)}")

    @icat_comm
    def set_sample(self, sample, comm_state=None):
        """Force the sample name (i.e. modify/verify state)

        :param str sample:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Failed to set the ICAT sample to {repr(sample)}"
        self.ensure_notrunning(comm_state=comm_state)
        self._set_sample(sample, comm_state=comm_state)
        self.wait_until_state(["STANDBY"], comm_state=comm_state)
        logger.debug(f"Sample set: {repr(sample)}")

    @icat_comm
    def set_dataset(self, dataset, comm_state=None):
        """Force the dataset name (i.e. modify/verify state)

        :param str dataset:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Failed to set the ICAT dataset to {repr(dataset)}"
        self.ensure_notrunning(comm_state=comm_state)
        self._set_dataset(dataset, comm_state=comm_state)
        # TODO: this times out sometimes
        # self.wait_until_state(["ON"], comm_state=comm_state)
        logger.debug(f"Dataset set: {repr(dataset)}")

    @icat_comm
    def set_path(self, path, comm_state=None):
        """Force the dataset full path.

        :param str path: dataset full path
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = f"Failed to set the ICAT dataset path to {repr(path)}"
        self._set_path(path, comm_state=comm_state)
        logger.debug(f"Dataset path set: {repr(path)}")

    @icat_comm
    def ensure_notrunning(self, comm_state=None):
        """Make sure the ICAT dataset is not running. When stopping a
        running dataset, data and metadata are ingested by the ICAT servers.

        :param dict comm_state:
        :raises IcatError:
        """
        if self.get_state(comm_state=comm_state) == "RUNNING":
            comm_state["error_msg"] = "Failed to stop the running ICAT dataset"
            self.metadata_manager.exec_command("endDataset", comm_state=comm_state)
            comm_state["error_msg"] = None
            # Dataset name is reset by the server
            # now in STANDBY(2)
        self.wait_until_not_state(["RUNNING"], comm_state=comm_state)

    @icat_comm
    def ensure_running(self, comm_state=None):
        """Make sure the ICAT dataset is running.

        :param dict comm_state:
        :raises IcatError:
        """
        if self.get_state(comm_state=comm_state) != "RUNNING":
            comm_state["error_msg"] = "Cannot start the ICAT dataset"
            # TODO: this times out sometimes
            # self.wait_until_state(["ON"], comm_state=comm_state)
            self.metadata_manager.exec_command("startDataset", comm_state=comm_state)
            comm_state["error_msg"] = None
        self.wait_until_state(["RUNNING"], comm_state=comm_state)

    @icat_comm
    def _set_proposal(self, proposal, comm_state=None):
        """Set the proposal name without state checking.
        Only for internal usage!

        :param str proposal:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = "Failed to set the ICAT proposal name"
        self.metadata_experiment.write_attribute(
            "proposal", proposal, comm_state=comm_state
        )
        # Side effects:
        #   sample -> 'please enter'
        #   dataRoot -> '/data/visitor'
        #   dataset -> ''
        # State is now STANDBY(1) (or will be shortly)

    @icat_comm
    def _set_sample(self, sample, comm_state=None):
        """Set the sample name without state checking.
        Only for internal usage!

        :param str sample:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = "Failed to set the ICAT sample name"
        self.metadata_experiment.write_attribute(
            "sample", sample, comm_state=comm_state
        )
        # Side effects:
        #   dataset -> ''
        # State is now STANDBY(2) (or will be shortly)

    @icat_comm
    def _set_dataset(self, dataset, comm_state=None):
        """Set the dataset name without state checking.
        Only for internal usage!

        :param str dataset:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = "Failed to set the ICAT dataset name"
        self.metadata_manager.write_attribute(
            "datasetName", dataset, comm_state=comm_state
        )
        # State is now ON (or will be shortly)

    @icat_comm
    def _set_path(self, path, comm_state=None):
        """Set the dataset path without state checking.
        Only for internal usage!

        :param str path:
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = "Failed to set the ICAT dataset path"
        template = "{dataRoot}"
        if template != self.metadata_manager.read_property("dataFolderPattern"):
            self.metadata_manager.write_property("dataFolderPattern", template)
        self.metadata_experiment.write_attribute(
            "dataRoot", path, comm_state=comm_state
        )

    @icat_comm
    def start_dataset(self, proposal, sample, dataset, path, comm_state=None):
        """Set the proposal, sample and dataset name. Then start the
        dataset. The final state (when not exception is raised)
        will be RUNNING.

        This method is NOT always idempotent as it modifies the state.

        :param str proposal:
        :param str sample:
        :param str dataset:
        :param str path: full path of the dataset
        :param dict comm_state:
        :raises IcatError:
        """
        comm_state["error_msg"] = "Failed to start the ICAT dataset"
        if proposal != self.get_proposal(comm_state=comm_state):
            self.set_proposal(proposal, comm_state=comm_state)
        if sample != self.get_sample(comm_state=comm_state):
            self.set_sample(sample, comm_state=comm_state)
        if dataset != self.get_dataset(comm_state=comm_state):
            self.set_dataset(dataset, comm_state=comm_state)
        if path != self.get_path(comm_state=comm_state):
            self.set_path(path, comm_state=comm_state)
        self.ensure_running(comm_state=comm_state)
        logger.debug(f"Dataset started: {repr(path)}")

    @icat_comm
    def stop_dataset(self, comm_state=None):
        """The final state (when not exception is raised)
        will be STANDBY.
        """
        comm_state["error_msg"] = "Failed to stop the ICAT dataset"
        self.ensure_notrunning(comm_state=comm_state)
        logger.debug("Dataset stopped")

    @icat_comm
    def send_to_elogbook(self, msg_type, msg, comm_state=None):
        warnings.warn(
            "Use 'send_message' instead of 'send_to_elogbook'. Note the difference in API.",
            FutureWarning,
        )
        if not msg_type:
            msg_type = "info"
        self.send_message(msg, msg_type=msg_type, comm_state=comm_state)

    @icat_comm
    def send_message(self, msg, msg_type=None, comm_state=None):
        """Send a message to the electronic logbook

        :param str msg:
        :param str msg_type: "comment" by default
        :param dict comm_state:
        """
        msg = msg.encode(
            "latin-1", errors="replace"
        )  # this is to circumvent pytango issue #72
        if self.get_state(comm_state=comm_state) == DevState.FAULT:
            return
        comm_state["error_msg"] = "Failed to send the e-logbook message"
        if msg_type == "command":
            cmd = "notifyCommand"
        elif msg_type == "comment":
            cmd = "userComment"
        elif msg_type in ("error", "warning", "critical", "fatal", "warn"):
            cmd = "notifyError"
        elif msg_type == "info":
            cmd = "notifyInfo"
        elif msg_type == "debug":
            cmd = "notifyDebug"
        else:
            cmd = "userComment"
        current_proposal = current_session.scan_saving.proposal_name
        if self.get_proposal(comm_state=comm_state) != current_proposal:
            self.set_proposal(current_proposal, comm_state=comm_state)
        try:
            self.metadata_manager.exec_command(cmd, args=(msg,), comm_state=comm_state)
        except IcatError as e:
            logger.error(self, f"elogbook: {e}")

    @icat_comm
    def store_dataset(
        self, proposal, sample, dataset, path, metadata=None, comm_state=None
    ):
        """Send a new dataset to the ICAT ingester.

        :param str proposal:
        :param str sample:
        :param str dataset:
        :param str path: full path of the dataset
        :param dict metadata: optional dataset metadata
        :param dict comm_state:
        :raises IcatError:
        """
        self.start_dataset(proposal, sample, dataset, path, comm_state=comm_state)
        comm_state["error_msg"] = "Failed to push ICAT metadata"
        if metadata:
            json_string = json.dumps(metadata)
            self.metadata_manager.exec_command(
                "SetParameters", args=(json_string,), comm_state=comm_state
            )
        comm_state["error_msg"] = None
        self.stop_dataset(comm_state=comm_state)
