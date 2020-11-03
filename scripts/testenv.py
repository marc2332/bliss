#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Launch Beacon, Redis, TangoDb and LimaCCD for the test configuration
"""

import os
import sys
import tempfile
import traceback
import shutil
import gevent
from gevent import subprocess
from gevent import socket
from gevent import sleep
from contextlib import closing, contextmanager, ExitStack
import bliss
from tango import DeviceProxy, DevFailed, Database
from bliss.config import get_sessions_list
from nexus_writer_service.io.io_utils import temproot, tempname
from nexus_writer_service.utils.logging_utils import getLogger, add_cli_args
from nexus_writer_service.utils import log_levels

logger = getLogger(__name__, __file__, default="INFO")


def find_free_port():
    """Find an unused port

    :returns str:
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def local_bliss_test_db():
    """Path to Bliss test suite's YAML files

    :returns str:
    """
    db_path = os.path.normpath(
        os.path.join(bliss.__file__, "..", "..", "tests", "test_configuration")
    )
    if not os.path.isdir(db_path):
        db_path = os.path.normpath(os.path.join("tests", "test_configuration"))
    if not os.path.isdir(db_path):
        raise RuntimeError(repr(db_path), " is not the bliss test db")
    return db_path


def fresh_bliss_test_db(tmpdir):
    """Create a fresh copy of the Bliss test suite's YAML files

    :returns str:
    """
    old_db_path = local_bliss_test_db()
    new_db_path = os.path.join(tmpdir, "test_configuration")
    shutil.copytree(old_db_path, new_db_path)
    try:
        os.remove(os.path.join(new_db_path, "beacon.rdb"))
    except FileNotFoundError:
        pass
    return new_db_path


def tango_online(uri=None, timeout=10):
    """Check whether Tango device is online

    :param str uri: the tango database itself when missing
    :param num timeout:
    """
    if uri:
        uri = f"tango://{os.environ['TANGO_HOST']}/{uri}"
        device = repr(uri)
    else:
        device = f"Tango database {os.environ['TANGO_HOST']}"
    with gevent.Timeout(10, RuntimeError(device + " not online")):
        while True:
            try:
                if uri:
                    dev_proxy = DeviceProxy(uri)
                    dev_proxy.ping()
                    dev_proxy.state()
                else:
                    db = Database()
                    db.build_connection()
            except DevFailed as e:
                gevent.sleep(0.1)
            else:
                break


def beacon_online(timeout=10):
    """Check whether Beacon server is online

    :param num timeout:
    """
    with gevent.Timeout(timeout, RuntimeError("Beacon not online")):
        while True:
            try:
                get_sessions_list()
            except Exception:
                sleep(0.1)
            else:
                break


def wait_interrupt(prompt):
    """Wait for CTRL-C

    :param str prompt:
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    while True:
        try:
            input()
            # gevent.select.select([], [], [])
        except KeyboardInterrupt:
            return ""


def prefix_from_env(env=None):
    """Environment variables for the subprocesses

    :param dict env:
    """
    if not env:
        env = os.environ
    prefix = ""
    for k in ["BEACON_HOST", "TANGO_HOST"]:
        v = env.get(k)
        if v:
            prefix += f"{k}={v} "
    return prefix


def run(cliargs, logfile, env=None):
    """Run subprocess

    :param list cliargs:
    :param logfile:
    :param dict env:
    """
    p = subprocess.Popen(
        cliargs, stdout=logfile, stderr=logfile, env=env, universal_newlines=True
    )
    print(f"\nLaunched process {p.pid}:")
    prefix = prefix_from_env(env=env)
    print(f" {prefix}" + " ".join(cliargs))
    return p


def temp_filename(path, prefix, suffix):
    """Temporary file name

    :param str path:
    :param str prefix:
    :param str suffix:
    :returns str:
    """
    if not path:
        path = temproot()
    filename = tempname(prefix=prefix, suffix=suffix)
    while os.path.exists(os.path.join(path, filename)):
        filename = tempname(prefix=prefix, suffix=suffix)
    return os.path.join(path, filename)


@contextmanager
def log(tmpdir=None, prefix="tmp", suffix=".log"):
    """Open log file

    :param str tmpdir:
    :param str prefix:
    :param str suffix:
    :returns fd:
    """
    filename = os.path.join(tmpdir, prefix + suffix)
    with open(filename, mode="w+") as fd:
        yield fd


class RunContextExit(Exception):
    pass


@contextmanager
def runcontext(cliargs, tmpdir="", prefix="tmp", env=None):
    """Run sub process and log to file

    :param list cliargs:
    :param str tmpdir:
    :param str prefix:
    :param dict env:
    """
    with log(tmpdir=tmpdir, prefix=prefix) as fd:
        p = run(cliargs, fd, env=env)
        try:
            yield
        except RunContextExit:
            raise
        except Exception:
            traceback.print_exc()
            print("\nOutput logs:")
            print(" " + tmpdir)
            wait_interrupt("\nCTRL-C to exit")
            raise RunContextExit
        finally:
            p.terminate()
            try:
                p.wait(timeout=10)
            except Exception:
                print(f"{p.pid} STILL RUNNING")
            else:
                print(f"{p.pid} terminated")


@contextmanager
def testenv(root=None):
    """Create test environment

    :param str root: directory for logs and config files
    """
    if root:
        os.makedirs(root, exist_ok=True)
    else:
        root = None
    try:
        with tempfile.TemporaryDirectory(prefix="bliss_testenv_", dir=root) as tmpdir:
            try:
                yield tmpdir
            except RunContextExit as e:
                print(e)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
    except OSError as e:
        print(e)


@contextmanager
def beacon(tmpdir=None, freshdb=True):
    """Start beacon server (+ redis + tango db)

    :param str tmpdir:
    :param bool freshdb:
    """
    params = {}
    if freshdb:
        params["db_path"] = fresh_bliss_test_db(tmpdir)
    else:
        params["db_path"] = local_bliss_test_db()
    params["port"] = find_free_port()
    params["tango_port"] = find_free_port()
    params["redis_port"] = find_free_port()
    params["redis-data-port"] = find_free_port()
    params["webapp_port"] = find_free_port()
    params["redis_socket"] = temp_filename(tmpdir, "redis_", ".sock")
    params["redis-data-socket"] = temp_filename(tmpdir, "redis_data_", ".sock")
    level = logger.getEffectiveLevel()
    params["log_level"] = log_levels.beacon_log_level[level]
    params["tango_debug_level"] = log_levels.tango_cli_log_level[level]
    cliargs = ["beacon-server"]
    cliargs += [f"--{k}={v}" for k, v in params.items()]

    env = {}
    env["BEACON_HOST"] = f"{socket.gethostname()}:{params['port']}"
    env["TANGO_HOST"] = f"{socket.gethostname()}:{params['tango_port']}"
    os.environ.update(env)
    env["PATH"] = os.environ["PATH"]

    with runcontext(cliargs, tmpdir=tmpdir, prefix="beacon"):
        beacon_online(timeout=10)
        tango_online(timeout=10)
        yield env


@contextmanager
def lima(env=None, tmpdir=None, name="simulator1"):
    """Start lima Tango device

    :param dict env:
    :param str tmpdir:
    :param str name:
    """
    level = logger.getEffectiveLevel()
    level = log_levels.tango_cli_log_level[level]
    level = f"-v{level}"
    if name == "simulator1":
        cliargs = ["LimaCCDs", "simulator", level]
    else:
        cliargs = ["LimaCCDs", name, level]
    with runcontext(cliargs, tmpdir=tmpdir, prefix="lima_" + name, env=env):
        tango_online(uri="id00/limaccds/" + name, timeout=10)
        yield


@contextmanager
def metaexperiment(env=None, tmpdir=None, name="test"):
    """Start ICAT proposal/sample manager

    :param dict env:
    :param str tmpdir:
    :param str name:
    """
    level = logger.getEffectiveLevel()
    level = log_levels.tango_cli_log_level[level]
    level = f"-v{level}"
    cliargs = ["MetaExperiment", name, level]
    with runcontext(cliargs, tmpdir=tmpdir, prefix="metaexperiment_" + name, env=env):
        for session_name in ("test_session", "nexus_writer_session"):
            tango_online(uri="id00/metaexp/" + session_name, timeout=10)
        yield


@contextmanager
def metadatamanager(env=None, tmpdir=None, name="test"):
    """Start ICAT dataset manager.

    :param dict env:
    :param str tmpdir:
    :param str name:
    """
    level = logger.getEffectiveLevel()
    level = log_levels.tango_cli_log_level[level]
    level = f"-v{level}"
    cliargs = ["MetadataManager", name, level]
    with runcontext(cliargs, tmpdir=tmpdir, prefix="metadatamanager_" + name, env=env):
        for session_name in ("test_session", "nexus_writer_session"):
            tango_online(uri="id00/metadata/" + session_name, timeout=10)
        yield


@contextmanager
def nexuswriterservice(env=None, tmpdir=None, instance="testwriters"):
    """Start session writer tango device

    :param dict env:
    :param str tmpdir:
    :param str instance:
    """
    level = logger.getEffectiveLevel()
    level = log_levels.log_level_name[level]
    logfile = os.path.join(tmpdir, "NexusWriterService.log")
    cliargs = [
        "NexusWriterService",
        instance,
        "--log=" + level,
        "--nologstdout",
        f"--logfile={logfile}",
    ]
    sessions = ["nexus_writer_session", "test_session"]
    with runcontext(cliargs, tmpdir=tmpdir, prefix="nexuswriter_" + instance, env=env):
        for session_name in sessions:
            device_name = "id00/bliss_nxwriter/" + session_name
            tango_online(uri=device_name, timeout=20)
        yield


@contextmanager
def nexuswriterprocess(env=None, tmpdir=None):
    """Start session writer process

    :param dict env:
    :param str tmpdir:
    """
    level = logger.getEffectiveLevel()
    level = log_levels.log_level_name[level]
    sessions = ["nexus_writer_session", "test_session"]
    with ExitStack() as stack:
        for session in sessions:
            cliargs = ["NexusSessionWriter", session, "--log=" + level]
            ctx = runcontext(
                cliargs, tmpdir=tmpdir, prefix="nexuswriter_" + session, env=env
            )
            files = [stack.enter_context(ctx)]
        yield


def print_env_info(tmpdir, env=None, writer=True):
    """Print info for clients of the test environment

    :param str tmpdir:
    :param dict env:
    :param bool writer:
    """
    prefix = prefix_from_env(env=env)
    print("\nAll session in the bliss test configuration:")
    print(" " + "\n ".join(get_sessions_list()))
    if not writer:
        print("\nRun Nexus writer as a python process:")
        print(
            f" {prefix} NexusSessionWriter nexus_writer_session --log=info --logfile={tmpdir}/NexusSessionWriter.log"
        )
        print("\nRun Nexus writer as a TANGO server:")
        print(
            f" {prefix} NexusWriterService testwriters --log=info --logfile={tmpdir}/NexusWriterService.log"
        )
    print("\nRun Nexus writer stress tests:")
    print(f" {prefix} python scripts/testnexus.py --type many")
    print("\nStart CLI to BLISS session:")
    print(f" {prefix} bliss -s nexus_writer_session --no-tmux")
    print("\nOutput logs:")
    print(" " + tmpdir)
    wait_interrupt("\nCTRL-C to stop the servers")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Bliss test environment")
    parser.add_argument(
        "--writer",
        default="TANGO",
        type=str.upper,
        help="External writer ('TANGO' by default)",
        choices=["OFF", "TANGO", "PROCESS"],
    )
    parser.add_argument(
        "--nofreshdb",
        action="store_false",
        dest="freshdb",
        help="Copy the YAML files and delete beacon.rdb",
    )
    parser.add_argument("--root", default="", help="Log root directory")
    add_cli_args(parser, default="INFO")
    args, unknown = parser.parse_known_args()

    with testenv(root=args.root) as tmpdir:
        with beacon(tmpdir=tmpdir, freshdb=args.freshdb) as env:
            with metaexperiment(env=env, tmpdir=tmpdir, name="test"):
                with metadatamanager(env=env, tmpdir=tmpdir, name="test"):
                    with lima(env=env, tmpdir=tmpdir, name="simulator1"):
                        with lima(env=env, tmpdir=tmpdir, name="simulator2"):
                            if args.writer == "TANGO":
                                ctx = nexuswriterservice(
                                    env=env, tmpdir=tmpdir, instance="testwriters"
                                )
                            elif args.writer == "PROCESS":
                                ctx = nexuswriterprocess(env=env, tmpdir=tmpdir)
                            else:
                                ctx = None
                            if ctx is None:
                                print_env_info(tmpdir, env=env, writer=ctx is not None)
                            else:
                                with ctx:
                                    print_env_info(tmpdir, env=env)
