#!/usr/bin/env python

import os
import sys
import subprocess
import redis
import socket
import contextlib
import time
import tempfile
import shutil
import threading
import gevent
import typing

from docopt import docopt

from bliss.tango.clients import utils as tango_utils


BLISS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BEACON = [sys.executable, "-m", "bliss.config.conductor.server"]
BEACON_DB_PATH = os.path.join(BLISS, "demo", "demo_configuration")
CMDLINE_ARGS = docopt(
    """
Usage: start_demo_servers [--beacon-port=<arg>]
                          [--tango-port=<arg>]
                          [--redis-port=<arg>]
                          [--redis-data-port=<arg>]

Options:
    --tango-port=<arg>       Tango database server port [default: 10000]
    --beacon-port=<arg>      Beacon server port [default: 10001]
    --redis-port=<arg>       Redis server for stats [default: 10002]
    --redis-data-port=<arg>  Redis server for data [default: 10003]
"""
)


def wait_for(stream, target):
    def do_wait_for(stream, target, data=b""):
        target = target.encode()
        while target not in data:
            char = stream.read(1)
            if not char:
                raise RuntimeError(
                    "Target {!r} not found in the following stream:\n{}".format(
                        target, data.decode()
                    )
                )
            data += char

    return do_wait_for(stream, target)


@contextlib.contextmanager
def setup_resource_files():
    """Setup the configuration files"""
    tmp_dir = tempfile.mkdtemp(prefix="demo_resources")
    directory = os.path.join(tmp_dir, "configuration")
    shutil.copytree(BEACON_DB_PATH, directory)
    try:
        yield directory
    finally:
        shutil.rmtree(tmp_dir)


def cleanup_processes(processes):
    for p in processes:
        try:
            print("terminating", p.pid)
            p.terminate()
            p.wait(timeout=10)
            print("  - ok")
        except Exception:
            print("  - still running")


def start_beacon(db_path):

    redis_uds = os.path.join(db_path, "redis_demo.sock")
    redis_data_uds = os.path.join(db_path, "redis_data_demo.sock")

    class Ports(typing.NamedTuple):
        beacon_port: int
        tango_port: int
        redis_port: int
        redis_data_port: int

    port_names = ["--beacon-port", "--tango-port", "--redis-port", "--redis-data-port"]
    port_list = (int(CMDLINE_ARGS[p]) for p in port_names)
    ports = Ports(*port_list)

    args = [
        "--port=%d" % ports.beacon_port,
        "--redis_port=%d" % ports.redis_port,
        "--redis_socket=" + redis_uds,
        "--redis-data-port=%d" % ports.redis_data_port,
        "--redis-data-socket=" + redis_data_uds,
        "--db_path=" + db_path,
        "--tango_port=%d" % ports.tango_port,
        # "--log-level=INFO",
        # "--tango_debug_level=1",
    ]

    proc = subprocess.Popen(BEACON + args)
    try:
        tango_utils.wait_tango_db(host="localhost", port=ports.tango_port, db=2)

        time.sleep(1)  # Waiting for Redis?

        os.environ["TANGO_HOST"] = "%s:%d" % (socket.gethostname(), ports.tango_port)
        os.environ["BEACON_HOST"] = "%s:%d" % (socket.gethostname(), ports.beacon_port)
        os.environ["BEACON_REDIS_PORT"] = "%d" % ports.redis_port

        # disable .rdb files saving (redis persistence)
        r = redis.Redis(host="localhost", port=ports.redis_port)
        r.config_set("SAVE", "")
        del r
    except BaseException:
        cleanup_processes([proc])
        raise

    return proc


class TangoDeviceDescription(typing.NamedTuple):
    name: str
    cmdline: typing.List[str]
    server_name: str


TANGO_DEVICES = [
    TangoDeviceDescription(
        name="id00/limaccds/simulator1",
        cmdline=("LimaCCDs", "simulator"),
        server_name="LimaCCDs",
    ),
    TangoDeviceDescription(
        name="id00/limaccds/slits_simulator",
        cmdline=("SlitsSimulationLimaCCDs", "slits_simulator"),
        server_name="LimaCCDs",
    ),
    TangoDeviceDescription(
        name="id00/limaccds/tomo_simulator",
        cmdline=("TomoSimulationLimaCCDs", "tomo_simulator"),
        server_name="LimaCCDs",
    ),
    TangoDeviceDescription(
        name="id00/limaccds/diff_simulator",
        cmdline=("DiffSimulationLimaCCDs", "diff_simulator"),
        server_name="LimaCCDs",
    ),
    TangoDeviceDescription(
        name="id00/metadata/demo_session",
        cmdline=("MetadataManager", "demo"),
        server_name="MetadataManager",
    ),
    TangoDeviceDescription(
        name="id00/metaexp/demo_session",
        cmdline=("MetaExperiment", "demo"),
        server_name="MetaExperiment",
    ),
    TangoDeviceDescription(
        name="id00/bliss_nxwriter/demo_session",
        cmdline=("NexusWriterService", "demo"),
        server_name="NexusWriter",
    ),
]


def start_tango_servers():
    wait_tasks = []
    processes = []

    try:
        for description in TANGO_DEVICES:
            fqdn_prefix = f"tango://{os.environ['TANGO_HOST']}"
            # device_fqdn = f"{fqdn_prefix}/{device_name}"
            personal_name = description.cmdline[-1]
            admin_device_fqdn = (
                f"{fqdn_prefix}/dserver/{description.server_name}/{personal_name}"
            )
            processes.append(subprocess.Popen(description.cmdline))
            green_wait = gevent.spawn(tango_utils.wait_tango_device, admin_device_fqdn)
            wait_tasks.append(green_wait)

        gevent.joinall(wait_tasks)
    except BaseException:
        cleanup_processes(processes)
        gevent.killall(wait_tasks)
        raise

    return processes


def bordered_text(text):
    lines = text.splitlines()
    width = max([len(l) for l in lines])
    for i, l in enumerate(lines):
        before = (width - len(l)) // 2
        after = (width - len(l) + 1) // 2
        l = "# " + " " * before + l + " " * after + " #"
        lines[i] = l
    lines.insert(0, "#" * (width + 4))
    lines.append("#" * (width + 4))
    return "\n".join(lines)


def run(db_path):
    beacon_process = start_beacon(db_path)
    tango_processes = start_tango_servers()

    text = f"""Start BLISS in another Terminal using

> TANGO_HOST={os.environ["TANGO_HOST"]} BEACON_HOST={os.environ["BEACON_HOST"]} bliss -s demo_session

Press CTRL+C to quit this process
"""
    print(bordered_text(text))

    try:
        threading.Event().wait()
    except BaseException:
        cleanup_processes(tango_processes + [beacon_process])


with setup_resource_files() as db_path:
    run(db_path)
    print("done")
